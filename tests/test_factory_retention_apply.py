from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_retention_transaction  # noqa: E402
from scripts.factory_retention_apply import (  # noqa: E402
    RetentionApplyError,
    apply_retention_plan,
    recover_incomplete,
)
from scripts.factory_retention_inventory import (  # noqa: E402
    RetentionInventory,
    inventory_factory,
)
from scripts.factory_retention_journal import JournalOperation  # noqa: E402
from scripts.factory_retention_models import (  # noqa: E402
    RetentionClassPolicy,
    RetentionPlanReport,
    RetentionPolicy,
    RetentionStatePolicy,
)
from scripts.factory_retention_plan import plan_retention  # noqa: E402
from scripts.factory_retention_types import MANAGED_CLASSES, POLICY_SCHEMA_VERSION  # noqa: E402

AS_OF = datetime(2026, 7, 28, tzinfo=UTC)


def _fixture(repo: Path) -> tuple[Path, Path]:
    _ = subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=True,
        capture_output=True,
    )
    completed = repo / ".entroping" / "ai-jobs" / "completed"
    failed = repo / ".entroping" / "ai-jobs" / "failed"
    reviews = repo / ".entroping" / "ai-reviews"
    logs = repo / ".entroping" / "factory-logs"
    for path in (completed, failed, reviews, logs):
        path.mkdir(parents=True, exist_ok=True)
    review = reviews / "review-j1"
    review.mkdir()
    _ = (review / "metadata.json").write_text(
        json.dumps(
            {
                "status": "ready_for_codex",
                "codex_inbox_status": "rejected",
                "reviewed_at": "2026-06-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    _ = (review / "result.md").write_text("result", encoding="utf-8")
    job = completed / "j1.json"
    _ = job.write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job.v1",
                "job_id": "j1",
                "queue_status": "completed",
                "artifact_dir": str(review),
                "completed_at": "2026-06-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return job, review


def _policy() -> RetentionPolicy:
    return RetentionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        class_policies=tuple(
            RetentionClassPolicy(
                schema_version=POLICY_SCHEMA_VERSION,
                artifact_class=item,
                byte_ceiling=1_000_000,
                state_policies=tuple(
                    RetentionStatePolicy(state=state, max_age_days=7)
                    for state in {
                        "ai_job": ("completed", "failed"),
                        "ai_review": ("accepted", "rejected"),
                        "factory_log": ("rotated",),
                        "factory_metrics_archive": ("archived",),
                        "retention_journal": ("completed", "rolled_back"),
                    }[item]
                ),
            )
            for item in MANAGED_CLASSES
        ),
    )


def _plan(repo: Path) -> tuple[RetentionInventory, RetentionPlanReport]:
    inventory = inventory_factory(repo)
    plan = plan_retention(_policy(), inventory.candidates, AS_OF)
    return inventory, plan


def test_explicit_apply_stages_purges_and_keeps_completed_receipt(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    assert plan.total_delete_count == 2
    result = apply_retention_plan(tmp_path, plan, inventory)
    assert result.reclaimed_count == 2
    assert result.reclaimed_bytes > 0
    assert not job.exists()
    assert not review.exists()
    assert result.journal_path is not None
    journal = tmp_path / result.journal_path
    raw_payload = cast(object, json.loads(journal.read_text(encoding="utf-8")))
    assert isinstance(raw_payload, dict)
    payload = cast(dict[str, object], raw_payload)
    assert payload["status"] == "completed"
    operations = payload["operations"]
    assert isinstance(operations, list)
    for item in cast(list[object], operations):
        assert isinstance(item, dict)
        operation = cast(dict[object, object], item)
        assert operation.get("state") == "purged"
    assert list((tmp_path / ".entroping" / "retention-trash").iterdir()) == []


def test_inventory_and_plan_do_not_create_apply_state(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    assert plan.total_delete_count == 2
    assert inventory.errors == ()
    assert job.exists() and review.exists()
    assert not (tmp_path / ".entroping" / "retention-journal").exists()
    assert not (tmp_path / ".entroping" / "retention-trash").exists()


def test_apply_rejects_fingerprint_drift_before_any_move(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    _ = (review / "result.md").write_text("changed", encoding="utf-8")
    with pytest.raises(RetentionApplyError, match="changed before apply"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    assert job.exists() and review.exists()
    assert not (tmp_path / ".entroping" / "retention-journal").exists()


def test_apply_rejects_symlink_swap_before_any_move(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.rmtree(review)
    os.symlink(outside, review)
    with pytest.raises(RetentionApplyError, match="fail-closed errors"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    assert job.exists()
    assert review.is_symlink()


def test_interrupted_purge_resumes_from_durable_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    original_purge = cast(
        Callable[[int, str], None],
        factory_retention_transaction.__dict__["_purge_entry"],
    )
    interrupted = False

    def interrupt_after_nested_unlink(parent_fd: int, name: str) -> None:
        nonlocal interrupted
        if name == "metadata.json" and not interrupted:
            original_purge(parent_fd, name)
            interrupted = True
            raise OSError("simulated interruption")
        original_purge(parent_fd, name)

    monkeypatch.setattr(
        factory_retention_transaction,
        "_purge_entry",
        interrupt_after_nested_unlink,
    )
    with pytest.raises(RetentionApplyError, match="simulated interruption"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    assert not job.exists() and not review.exists()
    monkeypatch.setattr(factory_retention_transaction, "_purge_entry", original_purge)
    assert recover_incomplete(tmp_path) == 1
    journal = next((tmp_path / ".entroping" / "retention-journal").glob("*.json"))
    raw_payload = cast(object, json.loads(journal.read_text(encoding="utf-8")))
    assert isinstance(raw_payload, dict)
    payload = cast(dict[str, object], raw_payload)
    assert payload["status"] == "completed"
    assert recover_incomplete(tmp_path) == 0


def test_completed_journal_recovers_interrupted_trash_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    original_cleanup = factory_retention_transaction.cleanup_completed_transaction

    def interrupt_transaction_cleanup(trash_root_fd: int, transaction_id: str) -> None:
        _ = (trash_root_fd, transaction_id)
        raise OSError("simulated final cleanup interruption")

    monkeypatch.setattr(
        factory_retention_transaction,
        "cleanup_completed_transaction",
        interrupt_transaction_cleanup,
    )
    with pytest.raises(RetentionApplyError, match="final cleanup interruption"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    assert not job.exists() and not review.exists()
    journal = next((tmp_path / ".entroping" / "retention-journal").glob("*.json"))
    payload = cast(dict[str, object], json.loads(journal.read_text(encoding="utf-8")))
    assert payload["status"] == "completed"
    assert list((tmp_path / ".entroping" / "retention-trash").iterdir())

    monkeypatch.setattr(
        factory_retention_transaction,
        "cleanup_completed_transaction",
        original_cleanup,
    )
    assert recover_incomplete(tmp_path) == 0
    assert list((tmp_path / ".entroping" / "retention-trash").iterdir()) == []


def test_corrupt_journal_blocks_recovery_without_touching_sources(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    journal_root = tmp_path / ".entroping" / "retention-journal"
    journal_root.mkdir()
    _ = (journal_root / "bad.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(RetentionApplyError, match="journal is unreadable"):
        _ = recover_incomplete(tmp_path)
    assert job.exists() and review.exists()


def test_nested_symlink_blocks_inventory_and_apply(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, review / "escape")
    inventory = inventory_factory(tmp_path)
    plan = plan_retention(_policy(), inventory.candidates, AS_OF)
    assert inventory.errors
    with pytest.raises(RetentionApplyError, match="fail-closed errors"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    assert job.exists() and review.exists()


def test_recovery_rolls_back_source_moved_before_journal_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    original_stage = cast(
        Callable[[Path, int, JournalOperation, frozenset[str]], None],
        factory_retention_transaction.__dict__["_stage_operation"],
    )
    calls = 0

    def interrupt_after_first_stage(
        repo_root: Path,
        trash_fd: int,
        operation: JournalOperation,
        tracked: frozenset[str],
    ) -> None:
        nonlocal calls
        original_stage(repo_root, trash_fd, operation, tracked)
        calls += 1
        if calls == 1:
            raise OSError("simulated staging interruption")

    monkeypatch.setattr(
        factory_retention_transaction,
        "_stage_operation",
        interrupt_after_first_stage,
    )
    with pytest.raises(RetentionApplyError, match="staging interruption"):
        _ = apply_retention_plan(tmp_path, plan, inventory)
    monkeypatch.setattr(factory_retention_transaction, "_stage_operation", original_stage)

    assert recover_incomplete(tmp_path) == 1
    assert job.exists() and review.exists()
    journal = next((tmp_path / ".entroping" / "retention-journal").glob("*.json"))
    raw_payload = cast(object, json.loads(journal.read_text(encoding="utf-8")))
    assert isinstance(raw_payload, dict)
    payload = cast(dict[str, object], raw_payload)
    assert payload["status"] == "rolled_back"
    raw_operations = payload["operations"]
    assert isinstance(raw_operations, list)
    operations = cast(list[object], raw_operations)
    states: set[object] = set()
    for item in operations:
        assert isinstance(item, dict)
        states.add(cast(dict[str, object], item)["state"])
    assert states == {"restored"}


def test_apply_rejects_tracked_terminal_job_before_any_move(tmp_path: Path) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    _ = subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--force", str(job.relative_to(tmp_path))],
        check=True,
        capture_output=True,
    )

    with pytest.raises(RetentionApplyError, match="Git-tracked path"):
        _ = apply_retention_plan(tmp_path, plan, inventory)

    assert job.exists() and review.exists()
    assert not (tmp_path / ".entroping" / "retention-journal").exists()


def test_apply_rejects_review_with_tracked_descendant_before_any_move(
    tmp_path: Path,
) -> None:
    job, review = _fixture(tmp_path)
    inventory, plan = _plan(tmp_path)
    tracked = review / "result.md"
    _ = subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--force", str(tracked.relative_to(tmp_path))],
        check=True,
        capture_output=True,
    )

    with pytest.raises(RetentionApplyError, match="Git-tracked path"):
        _ = apply_retention_plan(tmp_path, plan, inventory)

    assert job.exists() and review.exists()
    assert not (tmp_path / ".entroping" / "retention-journal").exists()


def test_zero_operation_apply_does_not_create_a_journal_receipt(tmp_path: Path) -> None:
    _ = subprocess.run(
        ["git", "init", "--quiet", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    inventory = inventory_factory(tmp_path)
    plan = plan_retention(_policy(), inventory.candidates, AS_OF)

    result = apply_retention_plan(tmp_path, plan, inventory)

    assert result.reclaimed_count == 0
    assert result.journal_path is None
    assert not (tmp_path / ".entroping" / "retention-journal").exists()


def test_apply_bounds_terminal_metrics_and_prior_journal_receipts(tmp_path: Path) -> None:
    _ = _fixture(tmp_path)
    archive = (
        tmp_path
        / ".entroping"
        / "factory-metrics"
        / "finished-issues"
        / "issue-1562"
    )
    archive.mkdir(parents=True)
    _ = (archive / "events.jsonl").write_text("{}\n", encoding="utf-8")
    _ = (archive / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.factory-metrics-archive.v1",
                "issue": 1562,
                "pull_request": 1600,
                "status": "archived",
                "issue_state": "closed",
                "pr_state": "merged",
                "archived_at": "2026-06-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    prior_id = "a" * 32
    journal_root = tmp_path / ".entroping" / "retention-journal"
    journal_root.mkdir()
    prior_receipt = journal_root / f"{prior_id}.json"
    _ = prior_receipt.write_text(
        json.dumps(
            {
                "schema_version": "entroping.factory-retention-journal.v1",
                "transaction_id": prior_id,
                "status": "completed",
                "created_at": "2026-06-01T00:00:00Z",
                "completed_at": "2026-06-02T00:00:00Z",
                "operations": [],
            }
        ),
        encoding="utf-8",
    )

    inventory, plan = _plan(tmp_path)
    result = apply_retention_plan(tmp_path, plan, inventory)

    assert not archive.exists()
    assert not prior_receipt.exists()
    assert result.reclaimed_count == 4
    receipts = tuple(journal_root.glob("*.json"))
    assert len(receipts) == 1
    assert receipts[0].name == f"{result.transaction_id}.json"
