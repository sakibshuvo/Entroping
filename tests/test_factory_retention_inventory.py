from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_retention_fs import (  # noqa: E402
    MAX_POLICY_TOTAL_BYTES,
    RetentionFsError,
    SnapshotBudget,
    entry_snapshot,
    open_relative_directory,
)
from scripts.factory_retention_inventory import inventory_factory  # noqa: E402
from scripts.factory_retention_models import RetentionPolicy  # noqa: E402


def _roots(repo: Path) -> None:
    for path in (
        repo / ".entroping" / "ai-jobs" / "queued",
        repo / ".entroping" / "ai-jobs" / "running",
        repo / ".entroping" / "ai-jobs" / "completed",
        repo / ".entroping" / "ai-jobs" / "failed",
        repo / ".entroping" / "ai-reviews",
        repo / ".entroping" / "factory-logs",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _job(repo: Path, job_id: str, review_name: str | None, *, state: str = "completed") -> Path:
    payload = {
        "schema_version": "entroping.ai-job.v1",
        "job_id": job_id,
        "queue_status": state,
        "artifact_dir": (
            str(repo / ".entroping" / "ai-reviews" / review_name)
            if review_name is not None
            else None
        ),
        "completed_at": "2026-06-01T00:00:00Z",
    }
    path = repo / ".entroping" / "ai-jobs" / state / f"{job_id}.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _review(repo: Path, name: str, *, decision: str = "rejected") -> Path:
    path = repo / ".entroping" / "ai-reviews" / name
    path.mkdir()
    _ = (path / "metadata.json").write_text(
        json.dumps(
            {
                "status": "ready_for_codex",
                "codex_inbox_status": decision,
                "issue": 1562,
                "reviewed_at": "2026-06-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    _ = (path / "result.md").write_text("bounded result", encoding="utf-8")
    return path


def test_snapshot_budget_exceeds_committed_policy_class_ceilings() -> None:
    policy = RetentionPolicy.model_validate_json(
        (REPO_ROOT / "docs/meta/factory-retention-policy.example.json").read_text(encoding="utf-8")
    )

    assert sum(item.byte_ceiling for item in policy.class_policies) < MAX_POLICY_TOTAL_BYTES


def test_relative_directory_opener_rejects_parent_components(tmp_path: Path) -> None:
    with (
        pytest.raises(RetentionFsError, match="invalid component"),
        open_relative_directory(tmp_path, ("..",)),
    ):
        pytest.fail("parent component unexpectedly opened")


def test_inventory_couples_terminal_job_and_review_without_rendering_contents(
    tmp_path: Path,
) -> None:
    _roots(tmp_path)
    _ = _job(tmp_path, "j1", "review-j1")
    _ = _review(tmp_path, "review-j1")
    inventory = inventory_factory(tmp_path)
    assert inventory.errors == ()
    assert len(inventory.entries) == 2
    job, review = inventory.entries
    assert job.candidate.bundle_id == review.candidate.bundle_id == "job:j1"
    assert job.snapshot is not None and len(job.snapshot.sha256) == 64
    assert review.snapshot is not None and "bounded result" not in review.snapshot.sha256
    assert review.candidate.references[0].state == "unknown"


def test_inventory_excludes_active_queues_and_unrelated_log_names(tmp_path: Path) -> None:
    _roots(tmp_path)
    active = tmp_path / ".entroping" / "ai-jobs" / "running" / "active.json"
    _ = active.write_text("{}", encoding="utf-8")
    logs = tmp_path / ".entroping" / "factory-logs"
    _ = (logs / "other.log").write_text("ignore", encoding="utf-8")
    _ = (logs / "factory-tick.out.log").write_text("active", encoding="utf-8")
    _ = (logs / "factory-tick.err.log.1").write_text("rotated", encoding="utf-8")
    inventory = inventory_factory(tmp_path)
    assert inventory.errors == ()
    assert tuple(item.candidate.state for item in inventory.entries) == ("rotated", "active")


def test_orphan_review_is_visible_but_fail_closed(tmp_path: Path) -> None:
    _roots(tmp_path)
    _ = _review(tmp_path, "orphan")
    inventory = inventory_factory(tmp_path)
    assert inventory.errors == ("unmanaged review artifact: .entroping/ai-reviews/orphan",)
    assert inventory.candidates[0].metadata_valid is False


def test_malformed_terminal_job_blocks_inventory_apply_surface(tmp_path: Path) -> None:
    _roots(tmp_path)
    path = tmp_path / ".entroping" / "ai-jobs" / "completed" / "bad.json"
    _ = path.write_text("{not-json", encoding="utf-8")
    inventory = inventory_factory(tmp_path)
    assert inventory.errors == (
        "invalid terminal job .entroping/ai-jobs/completed/bad.json: JSONDecodeError",
    )
    assert inventory.candidates[0].metadata_valid is False


def test_external_artifact_reference_is_rejected(tmp_path: Path) -> None:
    _roots(tmp_path)
    _ = _review(tmp_path, "review-j1")
    payload = {
        "schema_version": "entroping.ai-job.v1",
        "job_id": "j1",
        "queue_status": "completed",
        "artifact_dir": str(tmp_path / "outside" / "ai-reviews" / "review-j1"),
    }
    path = tmp_path / ".entroping" / "ai-jobs" / "completed" / "j1.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    inventory = inventory_factory(tmp_path)
    assert any("invalid terminal job" in error for error in inventory.errors)
    assert any("unmanaged review artifact" in error for error in inventory.errors)


def test_symlinked_review_bundle_is_not_followed(tmp_path: Path) -> None:
    _roots(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _ = (outside / "metadata.json").write_text("{}", encoding="utf-8")
    target = tmp_path / ".entroping" / "ai-reviews" / "linked"
    os.symlink(outside, target)
    _ = _job(tmp_path, "j1", "linked")
    inventory = inventory_factory(tmp_path)
    assert any("invalid review artifact" in error for error in inventory.errors)
    assert all(
        item.candidate.relative_path != ".entroping/ai-reviews/linked" for item in inventory.entries
    )


def test_directory_snapshot_changes_when_nested_content_changes(tmp_path: Path) -> None:
    _roots(tmp_path)
    _ = _job(tmp_path, "j1", "review-j1")
    review = _review(tmp_path, "review-j1")
    first = inventory_factory(tmp_path)
    first_digest = first.entry_by_path()[".entroping/ai-reviews/review-j1"].snapshot
    _ = (review / "result.md").write_text("changed content", encoding="utf-8")
    second = inventory_factory(tmp_path)
    second_digest = second.entry_by_path()[".entroping/ai-reviews/review-j1"].snapshot
    assert first_digest is not None and second_digest is not None
    assert first_digest.sha256 != second_digest.sha256


def test_inventory_timestamps_are_utc(tmp_path: Path) -> None:
    _roots(tmp_path)
    _ = _job(tmp_path, "j1", None)
    inventory = inventory_factory(tmp_path)
    created_at = inventory.candidates[0].created_at
    assert created_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_present_invalid_terminal_timestamp_blocks_apply_inventory(tmp_path: Path) -> None:
    _roots(tmp_path)
    path = _job(tmp_path, "j1", None)
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    payload["completed_at"] = "not-a-timestamp"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")

    inventory = inventory_factory(tmp_path)

    assert inventory.errors == (
        "invalid terminal job .entroping/ai-jobs/completed/j1.json: ValueError",
    )
    assert inventory.candidates[0].metadata_valid is False


def test_present_naive_terminal_timestamp_blocks_apply_inventory(tmp_path: Path) -> None:
    _roots(tmp_path)
    path = _job(tmp_path, "j1", None)
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    payload["completed_at"] = "2026-06-01T00:00:00"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")

    inventory = inventory_factory(tmp_path)

    assert inventory.errors == (
        "invalid terminal job .entroping/ai-jobs/completed/j1.json: ValueError",
    )
    assert inventory.candidates[0].metadata_valid is False


def test_absolute_review_reference_accepts_canonical_system_path_alias(
    tmp_path: Path,
) -> None:
    _roots(tmp_path)
    review = _review(tmp_path, "review-j1")
    path = _job(tmp_path, "j1", None)
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    alias_root = tmp_path.parent / f"{tmp_path.name}-alias"
    os.symlink(tmp_path, alias_root)
    payload["artifact_dir"] = str(alias_root / review.relative_to(tmp_path))
    _ = path.write_text(json.dumps(payload), encoding="utf-8")

    inventory = inventory_factory(tmp_path)

    assert inventory.errors == ()
    assert len(inventory.entries) == 2


def test_snapshot_budget_rejects_excessive_nested_entries(tmp_path: Path) -> None:
    review = tmp_path / "review"
    review.mkdir()
    _ = (review / "one").write_text("1", encoding="utf-8")
    _ = (review / "two").write_text("2", encoding="utf-8")

    with (
        open_relative_directory(tmp_path, ()) as root_fd,
        pytest.raises(RetentionFsError, match="snapshot entry limit"),
    ):
        _ = entry_snapshot(
            root_fd,
            "review",
            budget=SnapshotBudget(max_entries=2),
        )


def test_snapshot_budget_rejects_excessive_bytes_before_hashing(tmp_path: Path) -> None:
    _ = (tmp_path / "large").write_bytes(b"12345")

    with (
        open_relative_directory(tmp_path, ()) as root_fd,
        pytest.raises(RetentionFsError, match="snapshot byte limit"),
    ):
        _ = entry_snapshot(
            root_fd,
            "large",
            budget=SnapshotBudget(max_bytes=4),
        )


def test_control_character_name_fails_closed_without_echoing_name(tmp_path: Path) -> None:
    _roots(tmp_path)
    malicious_name = "bad\nname.json"
    _ = (tmp_path / ".entroping" / "ai-jobs" / "completed" / malicious_name).write_text(
        "{}", encoding="utf-8"
    )

    inventory = inventory_factory(tmp_path)

    assert inventory.errors == ("unsafe terminal job root completed: RetentionFsError",)
    assert malicious_name not in "\n".join(inventory.errors)


def test_finished_metrics_archive_requires_terminal_provenance_to_expire(
    tmp_path: Path,
) -> None:
    archive = tmp_path / ".entroping" / "factory-metrics" / "finished-issues" / "issue-1562"
    archive.mkdir(parents=True)
    _ = (archive / "events.jsonl").write_text("{}\n", encoding="utf-8")

    legacy = inventory_factory(tmp_path)

    assert legacy.errors == ()
    assert legacy.candidates[0].artifact_class == "factory_metrics_archive"
    assert legacy.candidates[0].metadata_valid is False

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

    terminal = inventory_factory(tmp_path)

    assert terminal.errors == ()
    assert terminal.candidates[0].state == "archived"
    assert terminal.candidates[0].metadata_valid is True
    assert terminal.candidates[0].created_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_inventory_includes_only_terminal_retention_journals(tmp_path: Path) -> None:
    journal_root = tmp_path / ".entroping" / "retention-journal"
    journal_root.mkdir(parents=True)
    completed_id = "a" * 32
    moving_id = "b" * 32
    for transaction_id, status in (
        (completed_id, "completed"),
        (moving_id, "moving"),
    ):
        payload: dict[str, object] = {
            "schema_version": "entroping.factory-retention-journal.v1",
            "transaction_id": transaction_id,
            "status": status,
            "created_at": "2026-06-01T00:00:00Z",
            "operations": [],
        }
        if status == "completed":
            payload["completed_at"] = "2026-06-02T00:00:00Z"
        _ = (journal_root / f"{transaction_id}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    inventory = inventory_factory(tmp_path)

    assert inventory.errors == ()
    assert tuple(item.artifact_id for item in inventory.candidates) == (f"journal:{completed_id}",)
    assert inventory.candidates[0].created_at == datetime(2026, 6, 2, tzinfo=UTC)
