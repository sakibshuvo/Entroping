from __future__ import annotations

import inspect
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_pr_delivery_test_support import (  # noqa: E402
    accepted_artifacts,
    write_delivery_request,
)

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_cleanup_schema import (  # noqa: E402
    CLEANUP_TRIGGER_NO_REWRITE_PROOFS,
)
from scripts.factory_pr_delivery_journal_completed import (  # noqa: E402
    _COMPLETED_UPDATE,
    persist_completed_receipt,
)
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_scheduler import (  # noqa: E402
    SchedulerCompletionAuthority,
)


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def _seed_merged_record(
    tmp_path: Path,
) -> tuple[Path, DeliveryEnvelope, DeliveryJournal, DeliveryJournalRecord]:
    main, envelope = _subject(tmp_path)
    subject = DeliveryJournal(main)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    pushed = subject.pushed(envelope, remote_head="a" * 40)
    assert pushed.committed_head is not None
    _ = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head=pushed.committed_head,
        ci_digest="c" * 64,
    )
    merged = subject.merged(envelope, merged_head=pushed.committed_head)
    return main, envelope, subject, merged


def _authority(
    envelope: DeliveryEnvelope,
) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    return SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=7,
    )


def _seed_prefix(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )
    subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )


def _seed_phase_five_merged(
    tmp_path: Path,
) -> tuple[Path, DeliveryEnvelope, DeliveryJournal, DeliveryJournalRecord]:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    phase_five = subject.scheduler_completed(envelope, authority=authority)
    return main, envelope, subject, phase_five


def _cleanup_row(connection: sqlite3.Connection, request_id: str) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
        "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
        "scheduler_phase_version, cleanup_intent_at_utc, remote_absent_at_utc, "
        "finish_cleanup_at_utc, scheduler_completion_at_utc, "
        "scheduler_completed_at_utc, phase_version "
        "FROM delivery_cleanup WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _lifecycle_row(connection: sqlite3.Connection, request_id: str) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT request_id, request_digest, envelope_digest, issue_number, "
        "assignment_id, worktree_id, lifecycle, reason, accepted_local_head, "
        "committed_head, remote_head, commit_parent, commit_tree, "
        "accepted_diff_sha256, accepted_manifest_sha256, approved_path_sha256, "
        "body_sha256, phase_version, created_at_utc, updated_at_utc, "
        "merge_pr_number, merge_head, merge_ci_digest, merge_intent_at_utc, "
        "terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _terminal_row(connection: sqlite3.Connection, request_id: str) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def test_journal_completed_update_sql_guard_requires_completion_equality() -> None:
    assert (
        "cleanup.scheduler_completed_at_utc = "
        "cleanup.scheduler_completion_at_utc" in _COMPLETED_UPDATE
    )
    assert _COMPLETED_UPDATE.count("?") == 7


def test_journal_completed_imports_do_not_depend_on_scheduler_adapters() -> None:
    source = Path("scripts/factory_pr_delivery_journal_completed.py").read_text()
    assert "factory_pr_delivery_scheduler" not in source
    assert "factory_scheduler" not in source
    assert "factory_pr_delivery_ssh" not in source
    assert "factory_pr_delivery_cleanup" not in source
    assert "factory_pr_delivery_scheduler_completion" not in source


def test_journal_completed_signature_uses_no_caller_timestamp() -> None:
    source = Path("scripts/factory_pr_delivery_journal_completed.py").read_text()
    assert inspect.signature(persist_completed_receipt).parameters.keys() == {
        "root",
        "envelope",
    }
    assert "datetime.now" not in source


def _assert_completed_transition(
    before_cleanup: tuple[object, ...], before_lifecycle: tuple[object, ...],
    before_terminal: tuple[object, ...], after_cleanup: tuple[object, ...],
    after_lifecycle: tuple[object, ...], after_terminal: tuple[object, ...],
    completion: datetime,
) -> None:
    assert isinstance(before_lifecycle[17], int) and isinstance(after_lifecycle[17], int)
    before_parent = before_lifecycle[:17] + before_lifecycle[18:19] + before_lifecycle[20:24]
    after_parent = after_lifecycle[:17] + after_lifecycle[18:19] + after_lifecycle[20:24]
    assert before_parent == after_parent
    assert after_lifecycle[17] == before_lifecycle[17] + 1
    assert after_lifecycle[24:27] == after_terminal
    assert after_cleanup == before_cleanup
    assert after_terminal[0] != before_terminal[0]
    assert after_terminal[1] != before_terminal[1]
    assert after_terminal[2] == completion.isoformat()


def _assert_completed_terminal(
    record: DeliveryJournalRecord, merged: DeliveryJournalRecord, completion: datetime
) -> None:
    assert (record.lifecycle, record.reason, record.updated_at) == (
        "merged",
        "cleanup-pending",
        completion,
    )
    terminal = read_terminal_receipt(record)
    before = read_terminal_receipt(merged)
    assert terminal is not None and before is not None
    excluded = {"lifecycle", "reason", "updated_at"}
    assert terminal.model_dump(exclude=excluded) == before.model_dump(exclude=excluded)
    assert (terminal.lifecycle, terminal.reason, terminal.updated_at) == (
        "completed",
        "completed",
        completion,
    )


def test_journal_completed_transition_preserves_identity_and_uses_stored_completion_timestamp(
    tmp_path: Path,
) -> None:
    _main, envelope, subject, merged = _seed_phase_five_merged(tmp_path)
    request_id = envelope.request.request_id

    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, request_id)
        before_lifecycle = _lifecycle_row(connection, request_id)
        before_terminal = _terminal_row(connection, request_id)
    assert before_cleanup is not None
    assert before_lifecycle is not None
    assert before_terminal is not None
    assert isinstance(before_cleanup[12], str)

    record = subject.completed(envelope)
    completion = datetime.fromisoformat(before_cleanup[12])

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_lifecycle = _lifecycle_row(connection, request_id)
        after_terminal = _terminal_row(connection, request_id)

    assert after_cleanup is not None
    assert after_lifecycle is not None
    assert after_terminal is not None
    _assert_completed_transition(
        before_cleanup, before_lifecycle, before_terminal,
        after_cleanup, after_lifecycle, after_terminal, completion,
    )
    _assert_completed_terminal(record, merged, completion)


def test_journal_completed_replay_uses_existing_row_and_no_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _main, envelope, subject, _ = _seed_phase_five_merged(tmp_path)
    _ = subject.completed(envelope)

    request_id = envelope.request.request_id
    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, request_id)
        before_lifecycle = _lifecycle_row(connection, request_id)
        before_terminal = _terminal_row(connection, request_id)

    def _should_not_persist(
        _connection: sqlite3.Connection,
        *,
        request_id: str,  # noqa: ARG002
        terminal_raw: str,
        terminal_digest: str,
        completed_at: datetime,
        expected_phase: int,
    ) -> int:
        raise AssertionError("_persist_completed_receipt should not run on replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_completed._persist_completed_receipt",
        _should_not_persist,
    )

    record = subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_lifecycle = _lifecycle_row(connection, request_id)
        after_terminal = _terminal_row(connection, request_id)

    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5


@pytest.mark.parametrize("phase", [0, 1, 2, 3, 4])
def test_journal_completed_requires_prefix_phase_conflict(tmp_path: Path, phase: int) -> None:
    _main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    if phase >= 1:
        subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2028, 1, 1, tzinfo=UTC),
        )
    if phase >= 2:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    if phase >= 3:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    if phase >= 4:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 3, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "request-conflict"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle
    assert merged.lifecycle == "merged"


@pytest.mark.parametrize(
    "mutation",
    [
        "corrupt_terminal",
        "mismatched_timestamp",
    ],
)
def test_journal_completed_rejects_invalid_terminal_projection_without_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    _main, envelope, subject, _phase_five = _seed_phase_five_merged(tmp_path)
    request_id = envelope.request.request_id

    with sqlite3.connect(_delivery_database(_main)) as connection:
        if mutation == "corrupt_terminal":
            connection.execute(
                "UPDATE delivery_lifecycle SET terminal_receipt_json = '{}' "
                "WHERE request_id = ?",
                (request_id,),
            )
        else:
            mismatched = datetime(2031, 1, 1, tzinfo=UTC).isoformat()
            connection.execute("DROP TRIGGER trg_delivery_cleanup_no_rewrite_proofs")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "UPDATE delivery_cleanup SET scheduler_completed_at_utc = ? WHERE request_id = ?",
                (mismatched, request_id),
            )
            connection.execute(CLEANUP_TRIGGER_NO_REWRITE_PROOFS)
            connection.execute("PRAGMA ignore_check_constraints = OFF")
        connection.commit()
        before_cleanup = _cleanup_row(connection, request_id)
        before_lifecycle = _lifecycle_row(connection, request_id)
        before_terminal = _terminal_row(connection, request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_terminal = _terminal_row(connection, request_id)
        after_lifecycle = _lifecycle_row(connection, request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_lifecycle is not None
    assert before_cleanup is not None
    if mutation == "mismatched_timestamp":
        assert isinstance(before_cleanup[12], str)
        assert datetime.fromisoformat(before_cleanup[12]) == datetime(2031, 1, 1, tzinfo=UTC)


def test_journal_completed_cas_zero_rowcount_rolls_back_real_partial_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _main, envelope, subject, _phase_five = _seed_phase_five_merged(tmp_path)
    request_id = envelope.request.request_id

    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, request_id)
        before_lifecycle = _lifecycle_row(connection, request_id)
        before_terminal = _terminal_row(connection, request_id)
    assert before_cleanup is not None
    assert before_lifecycle is not None
    assert before_terminal is not None
    assert before_cleanup[11] is not None
    assert isinstance(before_cleanup[11], str)
    assert isinstance(before_lifecycle[17], int)
    prior_phase = before_lifecycle[17]
    completion = datetime.fromisoformat(before_cleanup[11])
    seam_reached = False

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        terminal_raw: str,
        terminal_digest: str,
        completed_at: datetime,
        expected_phase: int,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = ?, terminal_receipt_sha256 = ?, "
            "terminal_at_utc = ?, updated_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (
                terminal_raw,
                terminal_digest,
                completion.isoformat(),
                completion.isoformat(),
                expected_phase + 1,
                request_id,
            ),
        )
        state = connection.execute(
            "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc, "
            "updated_at_utc, phase_version FROM delivery_lifecycle WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if state is None or state != (
            terminal_raw,
            terminal_digest,
            completion.isoformat(),
            completion.isoformat(),
                prior_phase + 1,
        ):
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 0

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_completed._persist_completed_receipt",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_lifecycle = _lifecycle_row(connection, request_id)

    assert seam_reached
    assert exc_info.value.code == "request-conflict"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle


def test_journal_completed_rejects_parent_mutation_on_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _main, envelope, subject, _phase_five = _seed_phase_five_merged(tmp_path)
    request_id = envelope.request.request_id

    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, request_id)
        before_lifecycle = _lifecycle_row(connection, request_id)
    assert before_cleanup is not None
    assert before_lifecycle is not None

    changed_digest = "a" * 64
    if before_lifecycle[1] == changed_digest:
        changed_digest = "b" * 64
    seam_reached = False

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        terminal_raw: str,
        terminal_digest: str,
        completed_at: datetime,
        expected_phase: int,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = ?, terminal_receipt_sha256 = ?, "
            "terminal_at_utc = ?, updated_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (
                terminal_raw,
                terminal_digest,
                completed_at.isoformat(),
                completed_at.isoformat(),
                expected_phase + 1,
                request_id,
            ),
        )
        connection.execute(
            "UPDATE delivery_lifecycle SET request_digest = ? WHERE request_id = ?",
            (changed_digest, request_id),
        )
        state = connection.execute(
            "SELECT request_digest, phase_version FROM delivery_lifecycle WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if state is None or state[0] != changed_digest or state[1] != expected_phase + 1:
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 1

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_completed._persist_completed_receipt",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_lifecycle = _lifecycle_row(connection, request_id)

    assert seam_reached
    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle


def test_journal_completed_rejects_identity_mutation_when_triggered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _main, envelope, subject, _phase_five = _seed_phase_five_merged(tmp_path)
    request_id = envelope.request.request_id

    with sqlite3.connect(_delivery_database(_main)) as connection:
        before_cleanup = _cleanup_row(connection, request_id)
        before_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type = 'trigger' AND name = "
            "'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        before_lifecycle = _lifecycle_row(connection, request_id)
    assert before_cleanup is not None
    assert before_trigger is not None
    assert before_lifecycle is not None
    seam_reached = False

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        terminal_raw: str,
        terminal_digest: str,
        completed_at: datetime,
        expected_phase: int,
    ) -> int:
        nonlocal seam_reached
        connection.execute("DROP TRIGGER trg_delivery_cleanup_immutable_identity")
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = ?, terminal_receipt_sha256 = ?, "
            "terminal_at_utc = ?, updated_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (
                terminal_raw,
                terminal_digest,
                completed_at.isoformat(),
                completed_at.isoformat(),
                expected_phase + 1,
                request_id,
            ),
        )
        connection.execute(
            "UPDATE delivery_cleanup SET remote_branch = 'mutated-branch' WHERE request_id = ?",
            (request_id,),
        )
        state = connection.execute(
            "SELECT remote_branch FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if state is None or state[0] != "mutated-branch":
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 1

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_completed._persist_completed_receipt",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.completed(envelope)

    with sqlite3.connect(_delivery_database(_main)) as connection:
        after_cleanup = _cleanup_row(connection, request_id)
        after_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type = 'trigger' AND name = "
            "'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        after_lifecycle = _lifecycle_row(connection, request_id)

    assert seam_reached
    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_trigger == after_trigger
    assert before_lifecycle == after_lifecycle
