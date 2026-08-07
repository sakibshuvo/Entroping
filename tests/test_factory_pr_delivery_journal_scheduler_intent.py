from __future__ import annotations

import dataclasses
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
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
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_record,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_scheduler import (  # noqa: E402
    SchedulerCompletionAuthority,
)
from scripts.factory_scheduler_storage import readonly_connection  # noqa: E402


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def _seed_merged_record(
    tmp_path: Path,
) -> tuple[Path, DeliveryEnvelope, DeliveryJournal, DeliveryJournalRecord, DeliveryJournalRecord]:
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
    return main, envelope, subject, merged, pushed


def _authority(
    envelope: DeliveryEnvelope, phase_version: int = 7
) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    return SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=phase_version,
    )


def _scheduler_rows(
    main: Path, envelope: DeliveryEnvelope
) -> tuple[tuple[object, ...] | None, tuple[object, ...] | None]:
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = connection.execute(
            "SELECT * FROM scheduler_assignments WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
        execution = connection.execute(
            "SELECT * FROM scheduler_execution_state WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
    return assignment, execution


def _cleanup_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
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


def _terminal_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _lifecycle_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
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


def _mutated_authority(
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    case: str,
) -> SchedulerCompletionAuthority:
    if case == "owner_id":
        return SchedulerCompletionAuthority(
            owner_id="other-" + authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "owner_pid":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid + 1,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "owner_start_token":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token="task_" + authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "owner_epoch":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch + 1,
            phase_version=authority.phase_version,
        )
    return SchedulerCompletionAuthority(
        owner_id=authority.owner_id,
        owner_pid=authority.owner_pid,
        owner_start_token=authority.owner_start_token,
        epoch=authority.epoch,
        phase_version=authority.phase_version + 1,
    )


def _seed_cleanup_prefix(
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


def test_journal_scheduler_completion_persists_phase_four_and_keeps_identity(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged, _pushed = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        assert before_cleanup is not None

    before_assignment, before_execution = _scheduler_rows(main, envelope)
    observed = datetime(2029, 1, 3, tzinfo=UTC)
    record = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=observed,
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        assert after_cleanup is not None

    after_assignment, after_execution = _scheduler_rows(main, envelope)

    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_terminal == (
        merged.terminal_receipt_json,
        merged.terminal_receipt_sha256,
        merged.terminal_at.isoformat() if merged.terminal_at is not None else None,
    )
    assert before_cleanup[0] == envelope.request.request_id
    assert before_cleanup[1] == envelope.orchestration_request.branch
    assert before_cleanup[2] == merged.committed_head
    assert before_cleanup[3] == authority.owner_id
    assert before_cleanup[4] == authority.owner_pid
    assert before_cleanup[5] == authority.owner_start_token
    assert before_cleanup[6] == authority.epoch
    assert before_cleanup[7] == authority.phase_version
    assert after_cleanup[9] is not None
    assert after_cleanup[10] is not None
    assert after_cleanup[11] == observed.astimezone(UTC).isoformat()
    assert after_cleanup[12] is None
    assert after_cleanup[13] == 4
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 4
    assert record.cleanup.scheduler_completion_at == observed.astimezone(UTC)
    assert record.cleanup.scheduler_completed_at is None
    assert before_assignment == after_assignment
    assert before_execution == after_execution


def test_journal_scheduler_completion_replay_is_byte_exact_no_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)

    def _should_not_persist(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        raise AssertionError("_persist_scheduler_completion called during replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_intent._persist_scheduler_completion",
        _should_not_persist,
    )
    record = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 4, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert before == after
    assert before_terminal == after_terminal
    assert before is not None
    assert isinstance(before[11], str)
    assert record.cleanup is not None
    assert record.cleanup.scheduler_completion_at == datetime.fromisoformat(before[11])
    assert record.cleanup.scheduler_completed_at is None


def test_journal_scheduler_completion_replay_requires_timestamp_after_remote_absence(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        assert before_cleanup is not None
        assert isinstance(before_cleanup[10], str)
        finish = datetime.fromisoformat(before_cleanup[10])

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=finish - timedelta(seconds=1),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal


def test_journal_scheduler_completion_replay_preserves_progressed_proof_prefix(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    progressed = datetime(2030, 1, 1, tzinfo=UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completion_at_utc = ?, scheduler_completed_at_utc = ?, "
            "phase_version = ? WHERE request_id = ?",
            (progressed.isoformat(), progressed.isoformat(), 5, envelope.request.request_id),
        )
        connection.commit()
        before = _cleanup_row(connection, envelope.request.request_id)

    record = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=progressed + timedelta(minutes=1),
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert before == after
    assert before is not None
    assert isinstance(before[11], str)
    assert isinstance(before[12], str)
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert record.cleanup.scheduler_completion_at == datetime.fromisoformat(before[11])
    assert record.cleanup.scheduler_completed_at == datetime.fromisoformat(before[12])


@pytest.mark.parametrize(
    "case",
    ["owner_id", "owner_pid", "owner_start_token", "owner_epoch", "phase_version"],
)
def test_journal_scheduler_completion_authority_tuple_mismatch_invalid(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=_mutated_authority(envelope, authority, case),
            observed_at=datetime(2029, 1, 4, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_scheduler_completion_requires_valid_phase_prefix(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    _ = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 4, tzinfo=UTC),
        )

    assert exc_info.value.code == "request-conflict"


def test_journal_scheduler_completion_requires_finish_proof_for_phase_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with sqlite3.connect(_delivery_database(main)) as connection:
        actual_record = read_record(connection, envelope.request.request_id)
    if actual_record is None or actual_record.cleanup is None:
        raise AssertionError("precondition missing cleanup row")

    mutated_record = dataclasses.replace(
        actual_record,
        cleanup=actual_record.cleanup.model_copy(
            update={"phase_version": 3, "finish_cleanup_at": None}
        ),
    )

    def _fake_read_record(
        _connection: sqlite3.Connection,
        request_id: str,
    ) -> object:
        assert request_id == envelope.request.request_id
        return mutated_record

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_intent.read_record",
        _fake_read_record,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 3, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before is not None
    assert after is not None
    assert before[10] is not None
    assert before[13] == 3
    assert after[10] is not None
    assert after[13] == 3
    assert before == after


def test_journal_scheduler_completion_rejects_malformed_cleanup_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            ("not-a-time", 4, envelope.request.request_id),
        )
        connection.commit()
        corrupted = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 4, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert corrupted == after_cleanup


def test_journal_scheduler_completion_rejects_corrupted_terminal_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = '{}' WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        connection.commit()
        corrupted = _terminal_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 4, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert corrupted == after_terminal


def test_journal_scheduler_completion_cas_rolls_back_real_partial_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    seam_reached = False
    observed = datetime(2029, 1, 4, tzinfo=UTC)

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        state = connection.execute(
            "SELECT scheduler_completion_at_utc, phase_version "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if state is None or state[0] != observed.isoformat() or state[1] != 4:
            raise AssertionError("CAS seam mutation not applied")
        seam_reached = True
        return 0

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_intent._persist_scheduler_completion",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=observed,
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert seam_reached
    assert exc_info.value.code == "request-conflict"
    assert before == after


def test_journal_scheduler_completion_cas_with_parent_request_digest_mutation_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    changed_digest = "a" * 64
    assert changed_digest != envelope.request.request_digest
    seam_reached = False
    observed = datetime(2029, 1, 4, tzinfo=UTC)

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        connection.execute(
            "UPDATE delivery_lifecycle SET request_digest = ? WHERE request_id = ?",
            (changed_digest, request_id),
        )
        cleanup_state = connection.execute(
            "SELECT scheduler_completion_at_utc, phase_version "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        lifecycle_state = connection.execute(
            "SELECT request_digest FROM delivery_lifecycle WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if (
            cleanup_state is None
            or lifecycle_state is None
            or cleanup_state[0] != observed.isoformat()
            or cleanup_state[1] != 4
            or lifecycle_state[0] != changed_digest
        ):
            raise AssertionError("CAS seam mutation not applied")
        nonlocal seam_reached
        seam_reached = True
        return 1

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_intent._persist_scheduler_completion",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=observed,
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert seam_reached
    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle


def test_journal_scheduler_completion_rejects_cleanup_identity_mutation_on_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    seam_reached = False
    observed = datetime(2029, 1, 4, tzinfo=UTC)

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        nonlocal seam_reached
        connection.execute("DROP TRIGGER trg_delivery_cleanup_immutable_identity")
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        connection.execute(
            "UPDATE delivery_cleanup SET remote_branch = ? WHERE request_id = ?",
            ("mutated-branch", request_id),
        )
        mutated = connection.execute(
            "SELECT remote_branch, scheduler_completion_at_utc, phase_version "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if (
            mutated is None
            or mutated[0] != "mutated-branch"
            or datetime.fromisoformat(mutated[1]) != observed
            or mutated[2] != 4
        ):
            raise AssertionError("mutation did not apply")
        seam_reached = True
        return 1

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert before_trigger is not None

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_intent._persist_scheduler_completion",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=observed,
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert seam_reached
    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle
    assert after_trigger is not None
    assert after_trigger == before_trigger


def test_journal_scheduler_completion_rejects_bad_authority_object(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )
    object.__setattr__(authority, "owner_id", None)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 4, tzinfo=UTC),
        )
    assert exc_info.value.code == "journal-invalid"


def test_journal_scheduler_completion_wrong_lifecycle_is_request_conflict(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_lifecycle SET lifecycle = 'uncertain', reason = 'interrupted' "
            "WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        connection.commit()
        before = _lifecycle_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _lifecycle_row(connection, envelope.request.request_id)
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)

    assert before is not None
    assert before[6] == "uncertain"
    assert before == after
    assert before_cleanup == after_cleanup
    assert exc_info.value.code == "request-conflict"


def test_journal_scheduler_completion_rejects_naive_observed_at(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 4),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
