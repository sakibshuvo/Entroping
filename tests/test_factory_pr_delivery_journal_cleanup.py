from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_receipts import (  # noqa: E402
    decode_delivery_receipt,
    encode_delivery_receipt,
)
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority  # noqa: E402


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


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


def _terminal_triple(
    connection: sqlite3.Connection,
    request_id: str,
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _mutate_authority(
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    case: str,
) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    if case == "owner_id":
        return replace(authority, owner_id="other-owner")
    if case == "owner_pid":
        return replace(authority, owner_pid=request.scheduler_owner_pid + 1)
    if case == "owner_start_token":
        return replace(authority, owner_start_token="proc_" + ("a" * 64))
    if case == "owner_epoch":
        return replace(authority, epoch=request.scheduler_owner_epoch + 1)
    if case == "phase_version":
        return replace(authority, phase_version=authority.phase_version + 1)
    raise AssertionError(case)


def _assert_terminal_unchanged(
    before: tuple[object, ...] | None,
    after: tuple[object, ...] | None,
    merged: DeliveryJournalRecord,
) -> None:
    assert before is not None
    assert before == after
    assert before[0] == merged.terminal_receipt_json
    assert before[1] == merged.terminal_receipt_sha256
    assert merged.terminal_at is not None
    assert before[2] == merged.terminal_at.isoformat()


def _assert_cleanup_intent_row(
    row: tuple[object, ...] | None,
    envelope: DeliveryEnvelope,
    merged: DeliveryJournalRecord,
    authority: SchedulerCompletionAuthority,
    expected: datetime,
) -> None:
    assert row is not None
    assert row[:8] == (
        envelope.request.request_id,
        envelope.orchestration_request.branch,
        merged.committed_head,
        authority.owner_id,
        authority.owner_pid,
        authority.owner_start_token,
        authority.epoch,
        authority.phase_version,
    )
    assert row[8:] == (expected.isoformat(), None, None, None, None, 1)


def _assert_cleanup_intent_projection(
    record: DeliveryJournalRecord,
    merged: DeliveryJournalRecord,
    expected: datetime,
) -> None:
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 1
    assert record.cleanup.cleanup_intent_at == expected
    assert record.cleanup.remote_absent_at is None
    assert record.cleanup.finish_cleanup_at is None
    assert record.cleanup.scheduler_completion_at is None
    assert record.cleanup.scheduler_completed_at is None
    assert record.terminal_receipt_json == merged.terminal_receipt_json
    assert record.terminal_receipt_sha256 == merged.terminal_receipt_sha256


def test_journal_cleanup_intent_persists_cleanup_intent_row(tmp_path: Path) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    observed_at = datetime(2030, 1, 1, tzinfo=UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_terminal = _terminal_triple(connection, envelope.request.request_id)
    record = subject.cleanup_intent(envelope, authority=authority, observed_at=observed_at)
    with sqlite3.connect(_delivery_database(main)) as connection:
        after_terminal = _terminal_triple(connection, envelope.request.request_id)

    expected = observed_at.astimezone(UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        row = _cleanup_row(connection, envelope.request.request_id)
    _assert_terminal_unchanged(before_terminal, after_terminal, merged)
    _assert_cleanup_intent_row(row, envelope, merged, authority, expected)
    _assert_cleanup_intent_projection(record, merged, expected)


def test_journal_cleanup_intent_rejects_terminal_receipt_projection_mismatch(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    assert merged.terminal_receipt_json is not None
    assert merged.terminal_receipt_sha256 is not None
    merged_terminal = decode_delivery_receipt(
        merged.terminal_receipt_json,
        merged.terminal_receipt_sha256,
    ).model_copy(update={"lifecycle": "completed", "reason": "completed"})
    completed_json, completed_digest = encode_delivery_receipt(merged_terminal)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = ?, terminal_receipt_sha256 = ? "
            "WHERE request_id = ?",
            (completed_json, completed_digest, envelope.request.request_id),
        )
        connection.commit()
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        assert _cleanup_row(connection, envelope.request.request_id) is None
    assert exc_info.value.code == "journal-invalid"


def test_journal_cleanup_intent_rejects_malformed_authority_object(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(
            envelope,
            authority=object(),  # type: ignore[arg-type]
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        assert _cleanup_row(connection, envelope.request.request_id) is None
    assert exc_info.value.code == "journal-invalid"


def test_journal_cleanup_intent_replay_is_byte_equivalent_no_mutation(tmp_path: Path) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    first_seen = datetime(2029, 1, 1, tzinfo=UTC)
    _ = subject.cleanup_intent(envelope, authority=authority, observed_at=first_seen)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    second_seen = datetime(2030, 1, 1, tzinfo=UTC)
    second = subject.cleanup_intent(envelope, authority=authority, observed_at=second_seen)
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert before is not None
    assert after == before
    assert second.cleanup is not None
    assert second.cleanup.phase_version == 1
    assert second.cleanup.cleanup_intent_at == first_seen
    assert isinstance(before[8], str)
    assert second.cleanup.cleanup_intent_at == datetime.fromisoformat(before[8])
    assert second.terminal_receipt_json == merged.terminal_receipt_json
    assert second.cleanup is not None
    assert second.cleanup.scheduler_phase_version == authority.phase_version


def test_journal_cleanup_intent_replay_preserves_progressed_cleanup_proofs(tmp_path: Path) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    first_seen = datetime(2030, 1, 1, tzinfo=UTC)
    before_record = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=first_seen,
    )
    assert before_record.cleanup is not None
    progress = first_seen + timedelta(minutes=10)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_cleanup SET remote_absent_at_utc = ?, finish_cleanup_at_utc = ?, "
            "phase_version = ? WHERE request_id = ?",
            (
                (progress + timedelta(minutes=1)).isoformat(),
                progress.isoformat(),
                3,
                envelope.request.request_id,
            ),
        )
        connection.commit()
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    after_record = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2031, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert before is not None
    assert after == before
    assert before_record.cleanup is not None
    assert after_record.cleanup is not None
    assert after_record.cleanup.phase_version == 3
    assert isinstance(before[9], str)
    assert isinstance(before[10], str)
    assert after_record.cleanup.remote_absent_at == datetime.fromisoformat(before[9])
    assert after_record.cleanup.finish_cleanup_at == datetime.fromisoformat(before[10])


@pytest.mark.parametrize(
    "case",
    ["owner_id", "owner_pid", "owner_start_token", "owner_epoch", "phase_version"],
)
def test_journal_cleanup_intent_mismatched_owner_snapshot_fails_without_mutation(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _ = subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    before_authority = _mutate_authority(envelope, authority, case)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(
            envelope,
            authority=before_authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert before == after


@pytest.mark.parametrize(
    "observed_at",
    [
        datetime(2026, 1, 1),
        datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
    ],
)
def test_journal_cleanup_intent_invalid_observed_timestamp_rejected(
    tmp_path: Path,
    observed_at: datetime,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(envelope, authority=authority, observed_at=observed_at)
    assert exc_info.value.code == "journal-invalid"
    with sqlite3.connect(_delivery_database(main)) as connection:
        record = _cleanup_row(connection, envelope.request.request_id)
        assert record is None
    assert merged.terminal_receipt_json is not None


def test_journal_cleanup_intent_rejects_non_merge_lifecycle(tmp_path: Path) -> None:
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
    _ = subject.pushed(envelope, remote_head="a" * 40)
    authority = _authority(envelope)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    assert exc_info.value.code == "request-conflict"
    with sqlite3.connect(_delivery_database(main)) as connection:
        assert _cleanup_row(connection, envelope.request.request_id) is None


def test_journal_cleanup_intent_cas_failure_rolls_back_no_cleanup_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate a concurrent update between read and insert.
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)

    def _conflicting_insert(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        remote_branch: str,
        expected_remote_head: str,
        scheduler_owner_id: str,
        scheduler_owner_pid: int,
        scheduler_owner_start_token: str,
        scheduler_owner_epoch: int,
        scheduler_phase_version: int,
        cleanup_intent_at: datetime,
        phase_version: int,
        request_id_guard: str,
        phase_guard: int,
    ) -> int:
        assert request_id_guard == request_id
        assert phase_guard == merged.phase_version
        connection.execute(
            "INSERT INTO delivery_cleanup("
            "request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
            "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
            "scheduler_phase_version, cleanup_intent_at_utc, remote_absent_at_utc, "
            "finish_cleanup_at_utc, scheduler_completion_at_utc, "
            "scheduler_completed_at_utc, phase_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                remote_branch,
                expected_remote_head,
                scheduler_owner_id,
                scheduler_owner_pid,
                scheduler_owner_start_token,
                scheduler_owner_epoch,
                scheduler_phase_version,
                cleanup_intent_at.isoformat(),
                None,
                None,
                None,
                None,
                phase_version,
            ),
        )
        return 0

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_cleanup._insert_cleanup_row",
        _conflicting_insert,
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    assert exc_info.value.code == "request-conflict"
    with sqlite3.connect(_delivery_database(main)) as connection:
        assert _cleanup_row(connection, envelope.request.request_id) is None
