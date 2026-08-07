from __future__ import annotations

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
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority  # noqa: E402


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


def _authority(envelope: DeliveryEnvelope, phase_version: int = 7) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    return SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=phase_version,
    )


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


def _terminal_row(connection: sqlite3.Connection, request_id: str) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
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
            owner_start_token="proc_" + ("b" * 64),
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


def test_journal_finish_proof_persists_phase_two_and_keeps_identity(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged, _pushed = _seed_merged_record(tmp_path)
    authority = _authority(envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    observed = datetime(2029, 1, 2, tzinfo=UTC)
    record = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=observed,
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        row = _cleanup_row(connection, envelope.request.request_id)

    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_terminal == (
        merged.terminal_receipt_json,
        merged.terminal_receipt_sha256,
        merged.terminal_at.isoformat() if merged.terminal_at is not None else None,
    )
    assert row is not None
    assert row[0] == envelope.request.request_id
    assert row[1] == envelope.orchestration_request.branch
    assert row[2] == merged.committed_head
    assert row[3] == authority.owner_id
    assert row[4] == authority.owner_pid
    assert row[5] == authority.owner_start_token
    assert row[6] == authority.epoch
    assert row[7] == authority.phase_version
    assert row[9] is None
    assert row[10] == observed.astimezone(UTC).isoformat()
    assert row[11] is None
    assert row[12] is None
    assert row[13] == 2
    assert record.cleanup is not None
    assert record.cleanup.finish_cleanup_at == observed.astimezone(UTC)
    assert record.cleanup.phase_version == 2
    assert record.cleanup.scheduler_phase_version == authority.phase_version


def test_journal_finish_proof_replay_is_byte_exact_no_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, merged, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    _ = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
        terminal_before = _terminal_row(connection, envelope.request.request_id)

    def _should_not_persist(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        raise AssertionError("_persist_finish_cleaned called during replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_finish_proof._persist_finish_cleaned",
        _should_not_persist,
    )
    record = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
        terminal_after = _terminal_row(connection, envelope.request.request_id)

    assert before == after
    assert terminal_before == terminal_after
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 2
    assert before is not None
    assert isinstance(before[10], str)
    assert record.cleanup.finish_cleanup_at == datetime.fromisoformat(before[10])
    assert record.cleanup.scheduler_completion_at is None
    assert record.cleanup.scheduler_completed_at is None


def test_journal_finish_proof_replay_requires_observed_timestamp_after_cleanup_intent(
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
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        assert before_cleanup is not None
        assert isinstance(before_cleanup[8], str)
        baseline_cleanup_intent = datetime.fromisoformat(before_cleanup[8])

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=baseline_cleanup_intent - timedelta(seconds=1),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal


def test_journal_finish_proof_replay_preserves_progressed_proof_prefix(tmp_path: Path) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    first = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )
    _ = subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )
    progressed = datetime(2030, 1, 1, tzinfo=UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (
                (progressed + timedelta(minutes=1)).isoformat(),
                4,
                envelope.request.request_id,
            ),
        )
        connection.commit()
        before = _cleanup_row(connection, envelope.request.request_id)

    record = subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=progressed + timedelta(minutes=10),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert first.cleanup is not None
    assert record.cleanup is not None
    assert before == after
    assert before is not None
    assert isinstance(before[10], str)
    assert isinstance(before[11], str)
    assert record.cleanup.phase_version == 4
    assert record.cleanup.finish_cleanup_at == datetime.fromisoformat(before[10])
    assert record.cleanup.scheduler_completion_at == datetime.fromisoformat(before[11])


@pytest.mark.parametrize(
    "case",
    ["owner_id", "owner_pid", "owner_start_token", "owner_epoch", "phase_version"],
)
def test_journal_finish_proof_authority_tuple_mismatch_invalid(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    bad = _mutated_authority(envelope, authority, case)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=bad,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_finish_proof_rejects_malformed_authority(tmp_path: Path) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=object(),  # type: ignore[arg-type]
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    assert exc_info.value.code == "journal-invalid"


@pytest.mark.parametrize(
    "observed_at",
    [datetime(2029, 1, 2), datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC)],
)
def test_journal_finish_proof_rejects_invalid_observed_timestamp(
    tmp_path: Path,
    observed_at: datetime,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_finish_proof_rejects_missing_cleanup_intent(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "request-conflict"
    assert before == after


def test_journal_finish_proof_rejects_wrong_ordered_or_malformed_cleanup(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_absent_at_utc = ?, phase_version = 2 "
            "WHERE request_id = ?",
            (datetime(2029, 1, 1, tzinfo=UTC).isoformat(), envelope.request.request_id),
        )
        connection.execute("PRAGMA ignore_check_constraints = OFF")
        connection.commit()
        corrupted_before = _cleanup_row(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert corrupted_before == after

    second_main, second_envelope, second_subject, _, _ = _seed_merged_record(
        tmp_path / "second-malformed-order"
    )
    second_authority = _authority(second_envelope)
    _ = second_subject.cleanup_intent(
        second_envelope,
        authority=second_authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    _ = second_subject.finish_cleaned(
        second_envelope,
        authority=second_authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    _ = second_subject.remote_absent(
        second_envelope,
        authority=second_authority,
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(second_main)) as connection:
        before_second = _cleanup_row(connection, second_envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completion_at_utc = 'not-a-time', "
            "phase_version = 4 "
            "WHERE request_id = ?",
            (second_envelope.request.request_id,),
        )
        connection.commit()
        malformed_second = _cleanup_row(connection, second_envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as completed_exc:
        second_subject.finish_cleaned(
            second_envelope,
            authority=second_authority,
            observed_at=datetime(2029, 1, 3, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(second_main)) as connection:
        malformed = _cleanup_row(connection, second_envelope.request.request_id)
    assert completed_exc.value.code == "journal-invalid"
    assert malformed_second == malformed
    assert before_second is not None


def test_journal_finish_proof_rejects_corrupted_terminal_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = '{}' "
            "WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        connection.commit()
        corrupted = _terminal_row(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert corrupted == after_terminal
    assert before_cleanup == after_cleanup


def test_journal_finish_proof_cas_rolls_back_real_partial_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET finish_cleanup_at_utc = ?, phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        return 0

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_finish_proof._persist_finish_cleaned",
        _fake_update,
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "request-conflict"
    assert before == after


def test_journal_finish_proof_cas_with_cleanup_identity_mutation_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    seam_reached = False

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "DROP TRIGGER trg_delivery_cleanup_immutable_identity",
        )
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET finish_cleanup_at_utc = ?, phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_branch = ? WHERE request_id = ?",
            ("proof-branch-mutated", request_id),
        )
        mutated = connection.execute(
            "SELECT remote_branch, finish_cleanup_at_utc, phase_version "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if (
            mutated is None
            or mutated[0] != "proof-branch-mutated"
            or mutated[1] != observed_at.isoformat()
            or mutated[2] != 2
        ):
            raise AssertionError("finish update mutation did not apply")
        seam_reached = True
        return 1

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'"
        ).fetchone()
        before_lifecycle = connection.execute(
            "SELECT request_digest, lifecycle, reason, phase_version "
            "FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()
    assert before_trigger is not None

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_finish_proof._persist_finish_cleaned",
        _fake_update,
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'"
        ).fetchone()
        after_lifecycle = connection.execute(
            "SELECT request_digest, lifecycle, reason, phase_version "
            "FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()

    assert exc_info.value.code == "journal-invalid"
    assert seam_reached
    assert after_cleanup == before_cleanup
    assert after_lifecycle == before_lifecycle
    assert after_trigger is not None
    assert after_trigger == before_trigger
