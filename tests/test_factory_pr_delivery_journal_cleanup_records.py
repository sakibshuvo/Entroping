from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

from scripts.factory_orchestration_models import Commit
from scripts.factory_pr_delivery_io import load_delivery_envelope
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_journal_cleanup_records import read_cleanup_record
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_record,
    validate_record,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _cleanup_row() -> tuple[object, ...]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (
        "delivery_" + ("a" * 64),
        "main",
        "b" * 40,
        "owner-id",
        123,
        "proc_" + ("b" * 64),
        123,
        1,
        base.isoformat(),
        None,
        None,
        None,
        None,
        1,
    )


def _cleanup_row_full_base(base: datetime) -> list[object]:
    row = list(_cleanup_row())
    row[8] = base.isoformat()
    row[10] = (base + timedelta(minutes=1)).isoformat()
    row[9] = (base + timedelta(minutes=2)).isoformat()
    row[11] = (base + timedelta(minutes=3)).isoformat()
    row[12] = (base + timedelta(minutes=3)).isoformat()
    row[13] = 5
    return row


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def _seed_merged_record(
    tmp_path: Path,
) -> tuple[Path, DeliveryEnvelope, DeliveryJournalRecord, DeliveryJournalRecord]:
    main, envelope = _subject(tmp_path)
    subject = DeliveryJournal(main)
    _ = subject.prepare(envelope)
    committed_head = "a" * 40
    _ = subject.commit_intent(
        envelope,
        committed_head=committed_head,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    pushed = subject.pushed(envelope, remote_head=committed_head)
    _ = subject.merge_intent(
        envelope,
        pr_number=123_456,
        merge_head=committed_head,
        ci_digest="c" * 64,
    )
    merged = subject.merged(envelope, merged_head=committed_head)
    return main, envelope, merged, pushed


def _write_cleanup_row(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    branch: str,
    committed_head: Commit,
    owner_id: str,
    owner_pid: int,
    owner_token: str,
    owner_epoch: int,
    remote_branch: str | None = None,
    expected_remote_head: Commit | None = None,
    cleanup_owner_id: str | None = None,
    cleanup_owner_pid: int | None = None,
    cleanup_owner_token: str | None = None,
    cleanup_owner_epoch: int | None = None,
    intent_at: datetime,
    remote_absent_at: datetime | None,
    finish_cleanup_at: datetime | None,
    scheduler_completion_at: datetime | None,
    scheduler_completed_at: datetime | None,
    phase_version: int,
    scheduler_phase_version: int = 7,
) -> None:
    connection.execute(
        "INSERT INTO delivery_cleanup("
        "request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
        "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
        "scheduler_phase_version, cleanup_intent_at_utc, remote_absent_at_utc, "
        "finish_cleanup_at_utc, scheduler_completion_at_utc, scheduler_completed_at_utc, "
        "phase_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            request_id,
            remote_branch or branch,
            expected_remote_head or committed_head,
            cleanup_owner_id or owner_id,
            cleanup_owner_pid if cleanup_owner_pid is not None else owner_pid,
            cleanup_owner_token or owner_token,
            cleanup_owner_epoch or owner_epoch,
            scheduler_phase_version,
            intent_at.isoformat(),
            remote_absent_at.isoformat() if remote_absent_at is not None else None,
            finish_cleanup_at.isoformat() if finish_cleanup_at is not None else None,
            scheduler_completion_at.isoformat()
            if scheduler_completion_at is not None
            else None,
            scheduler_completed_at.isoformat() if scheduler_completed_at is not None else None,
            phase_version,
        ),
    )


def test_journal_records_cleanup_row_absent_projects_none(tmp_path: Path) -> None:
    main, envelope = _subject(tmp_path)
    subject = DeliveryJournal(main)
    _ = subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert record.cleanup is None
    validate_record(envelope, record)


def test_journal_records_cleanup_record_parses_valid_row() -> None:
    row = _cleanup_row()
    record = read_cleanup_record(row)
    assert record.phase_version == 1


@pytest.mark.parametrize(
    "remote_absent,finish,scheduler_completion,scheduler_completed,expected_phase",
    [
        (None, None, None, None, 1),
        (None, timedelta(minutes=1), None, None, 2),
        (timedelta(minutes=2), timedelta(minutes=1), None, None, 3),
        (timedelta(minutes=2), timedelta(minutes=1), timedelta(minutes=3), None, 4),
        (
            timedelta(minutes=2),
            timedelta(minutes=1),
            timedelta(minutes=3),
            timedelta(minutes=3),
            5,
        ),
    ],
)
def test_journal_records_cleanup_projection_partial_prefix_stages(
    tmp_path: Path,
    remote_absent: timedelta | None,
    finish: timedelta | None,
    scheduler_completion: timedelta | None,
    scheduler_completed: timedelta | None,
    expected_phase: int,
) -> None:
    main, envelope, merged, _ = _seed_merged_record(tmp_path)
    assert merged.committed_head is not None
    request = envelope.orchestration_request
    base = (merged.updated_at if merged.updated_at is not None else datetime.now(UTC))
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(
            connection,
            request_id=merged.request_id,
            branch=request.branch,
            committed_head=merged.committed_head,
            owner_id=request.scheduler_owner_id,
            owner_pid=request.scheduler_owner_pid,
            owner_token=request.scheduler_owner_start_token,
            owner_epoch=request.scheduler_owner_epoch,
            intent_at=base,
            remote_absent_at=(base + remote_absent) if remote_absent is not None else None,
            finish_cleanup_at=(base + finish) if finish is not None else None,
            scheduler_completion_at=(base + scheduler_completion)
            if scheduler_completion is not None
            else None,
            scheduler_completed_at=(base + scheduler_completed)
            if scheduler_completed is not None
            else None,
            phase_version=expected_phase,
        )
        record = read_record(connection, envelope.request.request_id)

    assert record is not None
    assert record.cleanup is not None
    assert record.cleanup.phase_version == expected_phase
    assert record.cleanup.scheduler_phase_version == 7
    assert record.cleanup.request_id == merged.request_id
    assert record.cleanup.remote_branch == request.branch
    assert record.cleanup.expected_remote_head == merged.committed_head
    assert record.cleanup.scheduler_owner_id == request.scheduler_owner_id
    assert record.cleanup.scheduler_owner_pid == request.scheduler_owner_pid
    assert record.cleanup.scheduler_owner_start_token == request.scheduler_owner_start_token
    assert record.cleanup.scheduler_owner_epoch == request.scheduler_owner_epoch
    validate_record(envelope, record)


def _mutate_request_id(row: list[object]) -> None:
    row[0] = "delivery_" + ("a" * 10)


def _mutate_remote_branch(row: list[object]) -> None:
    row[1] = "bad branch"


def _mutate_remote_branch_too_long(row: list[object]) -> None:
    row[1] = "feature/" + ("a" * 154)


def _mutate_owner_id_too_long(row: list[object]) -> None:
    row[3] = "a" * 129


def _mutate_owner_pid_zero(row: list[object]) -> None:
    row[4] = 0


def _mutate_owner_pid_bool(row: list[object]) -> None:
    row[4] = True


def _mutate_owner_token(row: list[object]) -> None:
    row[5] = "proc_" + ("b" * 63)


def _mutate_remote_head_short(row: list[object]) -> None:
    row[2] = "x" * 39


def _mutate_intent_non_string(row: list[object]) -> None:
    row[8] = 123


def _mutate_intent_naive(row: list[object]) -> None:
    row[8] = "2026-01-01T00:00:00"


def _mutate_scheduler_phase_version_zero(row: list[object]) -> None:
    row[7] = 0


@pytest.mark.parametrize(
    "mutator",
    [
        _mutate_request_id,
        _mutate_remote_branch,
        _mutate_remote_branch_too_long,
        _mutate_owner_id_too_long,
        _mutate_owner_pid_zero,
        _mutate_owner_pid_bool,
        _mutate_owner_token,
        _mutate_remote_head_short,
        _mutate_intent_non_string,
        _mutate_intent_naive,
        _mutate_scheduler_phase_version_zero,
    ],
)
def test_journal_records_cleanup_malformed_fields_fail_closed(
    mutator: Callable[[list[object]], None],
) -> None:
    row = list(_cleanup_row())
    mutator(row)
    with pytest.raises(ValueError):
        read_cleanup_record(tuple(row))


def test_journal_records_cleanup_parser_rejects_short_row() -> None:
    with pytest.raises(ValueError):
        read_cleanup_record(_cleanup_row()[:-1])


def _mutate_missing_remote_with_later_proof(row: list[object]) -> None:
    row[9] = None
    row[13] = 4


def _mutate_missing_finish_with_later_proof(row: list[object]) -> None:
    row[10] = None
    row[13] = 4


def _mutate_missing_completion_with_completed_proof(row: list[object]) -> None:
    row[11] = None
    row[13] = 4


def _mutate_remote_before_intent(row: list[object]) -> None:
    assert isinstance(row[8], str)
    base = datetime.fromisoformat(row[8])
    row[9] = (base - timedelta(minutes=1)).isoformat()


def _mutate_remote_before_finish(row: list[object]) -> None:
    assert isinstance(row[10], str)
    row[9] = (datetime.fromisoformat(row[10]) - timedelta(seconds=1)).isoformat()


def _mutate_completion_before_finish(row: list[object]) -> None:
    assert isinstance(row[9], str)
    row[11] = (datetime.fromisoformat(row[9]) - timedelta(minutes=1)).isoformat()
    row[12] = row[11]


def _mutate_completed_timestamp_mismatch(row: list[object]) -> None:
    assert isinstance(row[11], str)
    row[12] = (datetime.fromisoformat(row[11]) + timedelta(minutes=1)).isoformat()


def _mutate_phase_count_mismatch(row: list[object]) -> None:
    row[13] = 4


@pytest.mark.parametrize(
    "mutator",
    [
        _mutate_missing_remote_with_later_proof,
        _mutate_missing_finish_with_later_proof,
        _mutate_missing_completion_with_completed_proof,
        _mutate_remote_before_intent,
        _mutate_remote_before_finish,
        _mutate_completion_before_finish,
        _mutate_completed_timestamp_mismatch,
        _mutate_phase_count_mismatch,
    ],
)
def test_journal_records_cleanup_timestamp_prefix_phase_fail_closed(
    tmp_path: Path,
    mutator: Callable[[list[object]], None],
) -> None:
    del tmp_path
    base = datetime(2026, 1, 1, tzinfo=UTC)
    cleanup_row = _cleanup_row_full_base(base)
    mutator(cleanup_row)
    with pytest.raises(ValueError):
        read_cleanup_record(tuple(cleanup_row))


@pytest.mark.parametrize(
    "case",
    ["branch", "remote_head", "owner_id", "owner_pid", "owner_token", "owner_epoch"],
)
def test_journal_records_cleanup_cross_binding_mismatches_fail_closed(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, merged, _ = _seed_merged_record(tmp_path)
    assert merged.committed_head is not None
    request = envelope.orchestration_request
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(
            connection,
            request_id=merged.request_id,
            branch=request.branch,
            committed_head=merged.committed_head,
            owner_id=request.scheduler_owner_id,
            owner_pid=request.scheduler_owner_pid,
            owner_token=request.scheduler_owner_start_token,
            owner_epoch=request.scheduler_owner_epoch,
            remote_branch="feature/reject" if case == "branch" else request.branch,
            expected_remote_head=(
                "b" * 40 if case == "remote_head" else merged.committed_head
            ),
            cleanup_owner_id="owner-other" if case == "owner_id" else request.scheduler_owner_id,
            cleanup_owner_pid=(
                request.scheduler_owner_pid + 1
                if case == "owner_pid"
                else request.scheduler_owner_pid
            ),
            cleanup_owner_token=(
                "proc_" + "f" * 64
                if case == "owner_token"
                else request.scheduler_owner_start_token
            ),
            cleanup_owner_epoch=(
                request.scheduler_owner_epoch + 1
                if case == "owner_epoch"
                else request.scheduler_owner_epoch
            ),
            intent_at=base,
            remote_absent_at=base + timedelta(minutes=2),
            finish_cleanup_at=base + timedelta(minutes=1),
            scheduler_completion_at=base + timedelta(minutes=3),
            scheduler_completed_at=base + timedelta(minutes=3),
            phase_version=5,
        )
        record = read_record(connection, envelope.request.request_id)
        assert record is not None
        with pytest.raises(DeliveryJournalError) as exc_info:
            validate_record(envelope, record)
    assert exc_info.value.code == "journal-invalid"


def test_journal_records_cleanup_pre_merge_rows_fail_closed(tmp_path: Path) -> None:
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
    request = envelope.orchestration_request
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(
            connection,
            request_id=pushed.request_id,
            branch=request.branch,
            committed_head=pushed.committed_head,
            owner_id=request.scheduler_owner_id,
            owner_pid=request.scheduler_owner_pid,
            owner_token=request.scheduler_owner_start_token,
            owner_epoch=request.scheduler_owner_epoch,
            intent_at=base,
            remote_absent_at=base + timedelta(minutes=2),
            finish_cleanup_at=base + timedelta(minutes=1),
            scheduler_completion_at=base + timedelta(minutes=3),
            scheduler_completed_at=base + timedelta(minutes=3),
            phase_version=5,
        )
        record = read_record(connection, envelope.request.request_id)
        assert record is not None
    with pytest.raises(DeliveryJournalError) as exc_info:
            validate_record(envelope, record)
    assert exc_info.value.code == "journal-invalid"


def test_journal_records_cleanup_read_has_no_writes(tmp_path: Path) -> None:
    main, envelope = _subject(tmp_path)
    subject = DeliveryJournal(main)
    _ = subject.prepare(envelope)
    writes: list[str] = []

    def trace(statement: str | None) -> None:
        if statement is None:
            return
        prefix = statement.lstrip().upper()
        if prefix.startswith(
            ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE")
        ):
            writes.append(statement)

    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.set_trace_callback(trace)
        record = read_record(connection, envelope.request.request_id)
        connection.set_trace_callback(None)
    assert record is not None
    assert record.cleanup is None
    assert writes == []
