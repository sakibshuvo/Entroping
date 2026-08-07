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


def _authority(envelope: DeliveryEnvelope, phase_version: int = 7) -> SchedulerCompletionAuthority:
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


def _seed_pre_merge_pushed(
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
    return main, envelope, subject, pushed


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
            owner_start_token="proc_" + ("a" * 64),
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


def _seed_finish_prefix(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    *,
    intent_at: datetime = datetime(2028, 1, 1, tzinfo=UTC),
    finish_at: datetime = datetime(2029, 1, 1, tzinfo=UTC),
) -> None:
    subject.cleanup_intent(envelope, authority=authority, observed_at=intent_at)
    subject.finish_cleaned(envelope, authority=authority, observed_at=finish_at)


def test_journal_cleanup_remote_absent_persists_phase_three_and_keeps_identity(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged, _pushed = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        terminal_before = _terminal_row(connection, envelope.request.request_id)
    _seed_finish_prefix(subject, envelope, authority)
    observed = datetime(2029, 1, 1, 12, tzinfo=UTC)
    record = subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=observed,
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        terminal_after = _terminal_row(connection, envelope.request.request_id)
        row = _cleanup_row(connection, envelope.request.request_id)

    assert terminal_before is not None
    assert terminal_after is not None
    assert terminal_before == terminal_after
    assert terminal_before[0] == merged.terminal_receipt_json
    assert row is not None
    assert row[0] == envelope.request.request_id
    assert row[1] == envelope.orchestration_request.branch
    assert row[2] == merged.committed_head
    assert row[3] == authority.owner_id
    assert row[4] == authority.owner_pid
    assert row[5] == authority.owner_start_token
    assert row[6] == authority.epoch
    assert row[7] == authority.phase_version
    assert row[9] == observed.astimezone(UTC).isoformat()
    assert row[10] == datetime(2029, 1, 1, tzinfo=UTC).isoformat()
    assert row[11] is None
    assert row[12] is None
    assert row[13] == 3
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 3
    assert record.cleanup.remote_absent_at == observed.astimezone(UTC)
    assert record.cleanup.scheduler_phase_version == authority.phase_version


def test_journal_cleanup_remote_absent_replay_is_byte_exact_no_update(tmp_path: Path) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(subject, envelope, authority)
    _ = subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    record = subject.read(envelope)
    assert record is not None
    assert record.cleanup is not None
    assert before == after
    assert before is not None
    assert record.cleanup.remote_absent_at is not None
    assert record.cleanup.remote_absent_at.isoformat() == before[9]
    assert record.cleanup.phase_version == 3


def test_journal_cleanup_remote_absent_replay_preserves_progressed_prefix(tmp_path: Path) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    intent_at = datetime(2030, 1, 1, tzinfo=UTC)
    _seed_finish_prefix(
        subject,
        envelope,
        authority,
        intent_at=intent_at,
        finish_at=intent_at,
    )
    first = subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=intent_at + timedelta(minutes=1),
    )
    assert first.cleanup is not None
    progressed = intent_at + timedelta(minutes=5)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ?, "
            "phase_version = ? "
            "WHERE request_id = ?",
            (
                (progressed + timedelta(minutes=1)).isoformat(),
                4,
                envelope.request.request_id,
            ),
        )
        connection.commit()
        before = _cleanup_row(connection, envelope.request.request_id)
    with sqlite3.connect(_delivery_database(main)) as connection:
        failed = datetime(2031, 1, 1, tzinfo=UTC)
        record = subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=failed,
        )
        after = _cleanup_row(connection, envelope.request.request_id)
    assert before == after
    assert before is not None
    assert isinstance(before[9], str)
    assert isinstance(before[10], str)
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 4
    assert record.cleanup.remote_absent_at == datetime.fromisoformat(before[9])
    assert record.cleanup.finish_cleanup_at == datetime.fromisoformat(before[10])
    assert isinstance(before[11], str)
    assert record.cleanup.scheduler_completion_at == datetime.fromisoformat(before[11])
    assert record.cleanup.scheduler_completed_at is None


@pytest.mark.parametrize(
    "case",
    ["owner_id", "owner_pid", "owner_start_token", "owner_epoch", "phase_version"],
)
def test_journal_cleanup_remote_absent_authority_tuple_mismatch_is_invalid(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(subject, envelope, authority)
    _ = subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    bad = _mutated_authority(envelope, authority, case)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.remote_absent(
            envelope,
            authority=bad,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_cleanup_remote_absent_rejects_malformed_authority(tmp_path: Path) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    _seed_finish_prefix(subject, envelope, _authority(envelope))
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.remote_absent(
            envelope,
            authority=object(),  # type: ignore[arg-type]
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    assert exc_info.value.code == "journal-invalid"


@pytest.mark.parametrize(
    "observed_at",
    [datetime(2029, 1, 1), datetime(2028, 12, 31, 23, 59, 59, tzinfo=UTC)],
)
def test_journal_cleanup_remote_absent_rejects_invalid_observed_timestamp(
    tmp_path: Path,
    observed_at: datetime,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(
        subject,
        envelope,
        authority,
        intent_at=datetime(2028, 1, 1, tzinfo=UTC),
        finish_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_cleanup_remote_absent_requires_cleanup_intent_and_merged_parent(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path / "merged")
    with pytest.raises(DeliveryJournalError) as missing_intent:
        subject.remote_absent(
            envelope,
            authority=_authority(envelope),
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    assert missing_intent.value.code == "request-conflict"

    _, envelope, subject, _pushed = _seed_pre_merge_pushed(tmp_path / "premerge")
    with pytest.raises(DeliveryJournalError) as wrong_lifecycle:
        subject.remote_absent(
            envelope,
            authority=_authority(envelope),
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    assert wrong_lifecycle.value.code == "request-conflict"


def test_journal_cleanup_remote_absent_rejects_invalid_terminal_or_cleanup_shapes(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        terminal_before = _terminal_row(connection, envelope.request.request_id)
        if terminal_before is None:
            raise AssertionError("terminal row missing")
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = ? "
            "WHERE request_id = ?",
            ("{}", envelope.request.request_id),
        )
        connection.commit()
        terminal_corrupted = _terminal_row(connection, envelope.request.request_id)
        cleanup_before = _cleanup_row(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as terminal_case:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    assert terminal_case.value.code == "journal-invalid"
    with sqlite3.connect(_delivery_database(main)) as connection:
        terminal_after_corrupt = _terminal_row(connection, envelope.request.request_id)
        cleanup_after_corrupt = _cleanup_row(connection, envelope.request.request_id)
    assert terminal_after_corrupt == terminal_corrupted
    assert cleanup_after_corrupt == cleanup_before

    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle "
            "SET terminal_receipt_json = ?, terminal_receipt_sha256 = ?, terminal_at_utc = ? "
            "WHERE request_id = ?",
            (
                terminal_before[0],
                terminal_before[1],
                terminal_before[2],
                envelope.request.request_id,
            ),
        )
        connection.commit()
        before = _cleanup_row(connection, envelope.request.request_id)
        if before is None:
            raise AssertionError("cleanup row missing")
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_absent_at_utc = ?, "
            "phase_version = ? WHERE request_id = ?",
            (
                datetime(2031, 1, 1).isoformat(),
                3,
                envelope.request.request_id,
            ),
        )
        before = _cleanup_row(connection, envelope.request.request_id)
        connection.commit()
    with pytest.raises(DeliveryJournalError) as cleanup_case:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
    assert cleanup_case.value.code == "journal-invalid"
    assert before == after


def test_journal_cleanup_remote_absent_cas_rolls_back_partial_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(subject, envelope, authority)

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_absent_at_utc = ?, phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        return 0

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_cleanup_proofs._persist_remote_absent",
        _fake_update,
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        row = _cleanup_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "request-conflict"
    assert row is not None
    assert row[9] is None
    assert row[10] == datetime(2029, 1, 1, tzinfo=UTC).isoformat()
    assert row[13] == 2


def test_journal_cleanup_remote_absent_cas_with_parent_mutation_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_finish_prefix(subject, envelope, authority)

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        observed_at: datetime,
    ) -> int:
        mutated_request_digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        assert mutated_request_digest != envelope.request.request_digest
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_absent_at_utc = ?, phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (observed_at.isoformat(), request_id),
        )
        connection.execute(
            "UPDATE delivery_lifecycle "
            "SET request_digest = ? WHERE request_id = ?",
            (mutated_request_digest, request_id),
        )
        return 1

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        if before_cleanup is None:
            raise AssertionError("cleanup row missing")
        before_lifecycle = connection.execute(
            "SELECT request_digest, lifecycle, reason, accepted_local_head, committed_head, "
            "remote_head, commit_parent, commit_tree, phase_version, terminal_receipt_json, "
            "terminal_receipt_sha256, terminal_at_utc, updated_at_utc "
            "FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()
        if before_lifecycle is None:
            raise AssertionError("lifecycle row missing")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_cleanup_proofs._persist_remote_absent",
        _fake_update,
    )
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = connection.execute(
            "SELECT request_digest, lifecycle, reason, accepted_local_head, committed_head, "
            "remote_head, commit_parent, commit_tree, phase_version, terminal_receipt_json, "
            "terminal_receipt_sha256, terminal_at_utc, updated_at_utc "
            "FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()
    assert exc_info.value.code == "journal-invalid"
    assert after_cleanup == before_cleanup
    assert after_lifecycle == before_lifecycle
