from __future__ import annotations

import importlib
import os
import sqlite3
import stat
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from factory_orchestration_test_support import repository, request_payload

if TYPE_CHECKING:
    from scripts.factory_orchestration_models import OrchestrationRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_orchestration_models import OrchestrationReceipt  # noqa: E402

journal_module = importlib.import_module("scripts.factory_orchestration_journal")
storage = importlib.import_module("scripts.factory_orchestration_journal_storage")
models = importlib.import_module("scripts.factory_orchestration_models")
receipts = importlib.import_module("scripts.factory_orchestration_receipts")
git_module = importlib.import_module("scripts.factory_orchestration_git")


def _request(tmp_path: Path) -> tuple[Path, OrchestrationRequest]:
    main, worktree, base = repository(tmp_path)
    request = models.OrchestrationRequest.model_validate(
        request_payload(main, worktree, base), strict=True
    )
    return main, request


def test_journal_persists_private_lifecycle_and_exact_replay(tmp_path: Path) -> None:
    # Given: a new immutable orchestration request.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)

    # When: prepare intent is persisted and replayed.
    first = subject.prepare(request)
    replay = subject.prepare(request)

    # Then: exact replay returns one durable identity under owner-only state.
    assert first == replay
    assert first.lifecycle == "prepared"
    state = main / ".entroping" / "factory-orchestration"
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert stat.S_IMODE((state / "orchestration.sqlite3").stat().st_mode) == 0o600


def test_journal_rejects_conflicting_request_and_active_overlap(tmp_path: Path) -> None:
    # Given: one prepared request owning its issue/worktree lifecycle.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)

    # When/Then: the same ID with a different digest is a replay conflict.
    conflicting = request.model_copy(update={"proposal_sha256": "c" * 64})
    assert conflicting.request_digest != request.request_digest
    with pytest.raises(journal_module.OrchestrationJournalError) as conflict:
        subject.prepare(conflicting)
    assert conflict.value.code == "request-conflict"

    # When/Then: another request cannot overlap the active issue/worktree.
    overlap = request.model_copy(update={"request_id": "orchestrate-1574-2"})
    with pytest.raises(journal_module.OrchestrationJournalError) as active:
        subject.prepare(overlap)
    assert active.value.code == "authority-mismatch"


def test_uncertain_lifecycle_blocks_reuse_for_recovery(tmp_path: Path) -> None:
    # Given: mutation intent whose owner was interrupted.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    applying = subject.transition(request, expected="prepared", lifecycle="applying")
    uncertain = subject.transition(
        request,
        expected=applying.lifecycle,
        lifecycle="uncertain",
        reason="interrupted",
    )

    # When/Then: uncertainty is durable and exact replay remains blocked.
    assert uncertain.lifecycle == "uncertain"
    with pytest.raises(journal_module.OrchestrationJournalError) as replay:
        subject.prepare(request)
    assert replay.value.code == "uncertain-recovery-required"


def test_active_replay_advances_timestamp_and_becomes_uncertain(tmp_path: Path) -> None:
    # Given: persisted mutation intent left in the applying state.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    applying = subject.transition(request, expected="prepared", lifecycle="applying")
    time.sleep(0.001)

    # When: the same process replays an in-flight request after interruption.
    with pytest.raises(journal_module.OrchestrationJournalError) as replay:
        subject.prepare(request)

    # Then: replay is fail-closed and records a new uncertainty observation time.
    assert replay.value.code == "uncertain-recovery-required"
    database = main / ".entroping" / "factory-orchestration" / "orchestration.sqlite3"
    with sqlite3.connect(database) as connection:
        lifecycle, updated_at = connection.execute(
            "SELECT lifecycle, updated_at_utc FROM orchestration_lifecycle WHERE request_id = ?",
            (request.request_id,),
        ).fetchone()
    assert lifecycle == "uncertain"
    assert updated_at > applying.updated_at.isoformat()


def test_journal_rejects_unexpected_sqlite_sidecar(tmp_path: Path) -> None:
    # Given: a valid journal whose pathname identity is shadowed by a sidecar.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    database = main / ".entroping" / "factory-orchestration" / "orchestration.sqlite3"
    sidecar = database.with_name(f"{database.name}-wal")
    sidecar.write_bytes(b"attacker-controlled")
    os.chmod(sidecar, 0o600)

    # When/Then: a new journal operation rejects the unexpected storage shape.
    with pytest.raises(journal_module.OrchestrationJournalError) as rejected:
        subject.prepare(request)
    assert rejected.value.code == "journal-invalid"


def test_journal_rejects_extra_schema_objects(tmp_path: Path) -> None:
    # Given: a valid journal with an attacker-defined trigger added out of band.
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    database = main / ".entroping" / "factory-orchestration" / "orchestration.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER attacker AFTER UPDATE ON orchestration_lifecycle BEGIN SELECT 1; END"
        )

    # When/Then: exact schema validation rejects the trigger before lifecycle SQL.
    with pytest.raises(journal_module.OrchestrationJournalError) as rejected:
        subject.prepare(request)
    assert rejected.value.code == "journal-invalid"


def test_journal_rejects_symlinked_state_root(tmp_path: Path) -> None:
    # Given: an attacker-controlled symlink at the private journal root.
    main, request = _request(tmp_path)
    entroping = main / ".entroping"
    entroping.mkdir(mode=0o700)
    target = tmp_path / "foreign"
    target.mkdir()
    os.symlink(target, entroping / "factory-orchestration")

    # When/Then: journal creation refuses to follow it.
    with pytest.raises(journal_module.OrchestrationJournalError):
        journal_module.OrchestrationJournal(main).prepare(request)


@pytest.mark.parametrize("column", ["issue_number", "worktree_id"])
def test_journal_rejects_corrupted_row_identity(tmp_path: Path, column: str) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    database = main / ".entroping/factory-orchestration/orchestration.sqlite3"
    replacement: object = 9999 if column == "issue_number" else f"wt_{'f' * 64}"
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"UPDATE orchestration_lifecycle SET {column} = ? WHERE request_id = ?",
            (replacement, request.request_id),
        )

    with pytest.raises(journal_module.OrchestrationJournalError) as exc_info:
        subject.prepare(request)

    assert exc_info.value.code == "journal-invalid"


def test_journal_rejects_cross_request_terminal_receipt(tmp_path: Path) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    foreign = request.model_copy(
        update={
            "request_id": "orchestrate-1574-foreign",
            "job_id": "implementation-1574-foreign",
        }
    )
    foreign_receipt = receipts.build_receipt(
        foreign,
        lifecycle="failed",
        reason="gate-failed",
        authoritative=True,
        paths=("docs/user/guide.md",),
        additions=1,
        deletions=1,
    )

    with pytest.raises(journal_module.OrchestrationJournalError) as exc_info:
        subject.transition(
            request,
            expected="prepared",
            lifecycle="failed",
            receipt=foreign_receipt,
        )

    assert exc_info.value.code == "journal-invalid"


def test_journal_rejects_corrupted_primary_request_identity(tmp_path: Path) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    database = main / ".entroping/factory-orchestration/orchestration.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE orchestration_lifecycle SET request_id = ? WHERE request_id = ?",
            ("orchestrate-corrupted", request.request_id),
        )

    with pytest.raises(journal_module.OrchestrationJournalError) as exc_info:
        subject.prepare(request)

    assert exc_info.value.code == "journal-invalid"


def test_journal_rechecks_late_sidecar_under_acquired_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    original = storage._require_stable_paths
    calls = 0

    def inject_sidecar(
        state: Path,
        state_identity: tuple[int, int, int, int, int],
        database: Path,
        database_identity: tuple[int, int, int, int, int],
    ) -> None:
        nonlocal calls
        original(state, state_identity, database, database_identity)
        calls += 1
        if calls == 2:
            sidecar = main / ".entroping/factory-orchestration/orchestration.sqlite3-journal"
            sidecar.write_bytes(b"late")
            sidecar.chmod(0o600)

    monkeypatch.setattr(storage, "_require_stable_paths", inject_sidecar)

    with pytest.raises(journal_module.OrchestrationJournalError) as exc_info:
        subject.prepare(request)

    assert exc_info.value.code == "journal-invalid"


def test_concurrent_conflicting_prepare_admits_exactly_one_request(tmp_path: Path) -> None:
    main, first = _request(tmp_path)
    second = first.model_copy(
        update={
            "request_id": "orchestrate-1574-concurrent",
            "job_id": "implementation-1574-concurrent",
        }
    )
    barrier = threading.Barrier(2)

    def prepare(request: OrchestrationRequest) -> str:
        barrier.wait()
        try:
            return str(journal_module.OrchestrationJournal(main).prepare(request).lifecycle)
        except journal_module.OrchestrationJournalError as exc:
            return str(exc.code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(prepare, (first, second)))

    assert sorted(outcomes) == ["authority-mismatch", "prepared"]
    database = main / ".entroping/factory-orchestration/orchestration.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM orchestration_lifecycle WHERE lifecycle = 'prepared'"
        ).fetchone() == (1,)


def _accepted_receipt(request: OrchestrationRequest) -> OrchestrationReceipt:
    gate = models.GateExitState.model_validate(
        {
            "name": "docs-gate",
            "command_id": "docs-gate-v1",
            "exit_code": 0,
            "signal_number": None,
            "state": "passed",
            "stdout_sha256": "1" * 64,
            "stderr_sha256": "2" * 64,
            "started_at": datetime.now(UTC),
            "finished_at": datetime.now(UTC),
        },
        strict=True,
    )
    truth = git_module.PatchTruth(
        head=request.base_commit,
        manifest_sha256="3" * 64,
        diff_sha256="4" * 64,
        paths=("docs/user/guide.md",),
        status_sha256="5" * 64,
    )
    receipt = receipts.build_receipt(
        request,
        lifecycle="accepted",
        reason="accepted",
        authoritative=True,
        paths=("docs/user/guide.md",),
        additions=1,
        deletions=1,
        truth=truth,
        gates=(gate,),
    )
    assert isinstance(receipt, OrchestrationReceipt)
    return receipt


@pytest.mark.parametrize(
    ("lifecycle", "reason", "receipt_kind"),
    (
        ("failed", "none", "accepted"),
        ("prepared", "none", "failed"),
        ("failed", "none", "missing"),
        ("uncertain", "none", "missing"),
        ("prepared", "interrupted", "missing"),
    ),
)
def test_journal_rejects_corrupted_row_lifecycle_invariants(
    tmp_path: Path,
    lifecycle: str,
    reason: str,
    receipt_kind: str,
) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    failed = receipts.build_receipt(
        request,
        lifecycle="failed",
        reason="gate-failed",
        authoritative=True,
        paths=("docs/user/guide.md",),
        additions=1,
        deletions=1,
    )
    receipt_json = {
        "accepted": _accepted_receipt(request).model_dump_json(),
        "failed": failed.model_dump_json(),
        "missing": None,
    }[receipt_kind]
    database = main / ".entroping/factory-orchestration/orchestration.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE orchestration_lifecycle SET lifecycle = ?, reason = ?, receipt_json = ? "
            "WHERE request_id = ?",
            (lifecycle, reason, receipt_json, request.request_id),
        )

    with pytest.raises(journal_module.OrchestrationJournalError) as exc_info:
        subject.prepare(request)

    assert exc_info.value.code == "journal-invalid"


def test_journal_valid_terminal_receipt_replays_unchanged(tmp_path: Path) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    receipt = receipts.build_receipt(
        request,
        lifecycle="failed",
        reason="gate-failed",
        authoritative=True,
        paths=("docs/user/guide.md",),
        additions=1,
        deletions=1,
    )
    _ = subject.transition(
        request,
        expected="prepared",
        lifecycle="failed",
        receipt=receipt,
    )

    assert subject.terminal_receipt(request) == receipt
    assert subject.prepare(request).receipt == receipt


def test_second_prepare_serializes_behind_active_sqlite_writer(tmp_path: Path) -> None:
    main, request = _request(tmp_path)
    subject = journal_module.OrchestrationJournal(main)
    _ = subject.prepare(request)
    entered = threading.Event()
    release = threading.Event()

    def active_writer() -> None:
        with storage.journal_connection(main) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE orchestration_lifecycle SET updated_at_utc = updated_at_utc "
                "WHERE request_id = ?",
                (request.request_id,),
            )
            entered.set()
            assert release.wait(timeout=5)
            connection.execute("COMMIT")

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(active_writer)
        assert entered.wait(timeout=5)
        waiter = executor.submit(subject.prepare, request)
        assert not waiter.done()
        release.set()
        writer.result(timeout=5)
        replay = waiter.result(timeout=5)

    assert replay.lifecycle == "prepared"
