"""SQLite writer for durable cleanup-intent persistence."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal_cleanup_records import (
    DeliveryCleanupRecord,
    read_cleanup_record,
)
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_record,
    read_terminal_receipt,
    validate_record,
)
from scripts.factory_pr_delivery_journal_storage import journal_connection
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority

_INSERT_CLEANUP = (
    "INSERT INTO delivery_cleanup("
    "request_id, remote_branch, expected_remote_head, scheduler_owner_id,"
    " scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch,"
    " scheduler_phase_version, cleanup_intent_at_utc, remote_absent_at_utc,"
    " finish_cleanup_at_utc, scheduler_completion_at_utc,"
    " scheduler_completed_at_utc, phase_version"
    ") SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS("
    "SELECT 1 FROM delivery_lifecycle "
    "WHERE request_id = ? AND lifecycle = 'merged' AND reason = 'cleanup-pending' "
    "AND phase_version = ?"
    ")"
)


def persist_cleanup_intent(
    root: Path,
    envelope: DeliveryEnvelope,
    *,
    authority: SchedulerCompletionAuthority,
    observed_at: datetime,
) -> DeliveryJournalRecord:
    observed_utc = _normalize_observed(observed_at)
    with journal_connection(root) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            record = read_record(connection, envelope.request.request_id)
            if (
                record is None
                or record.lifecycle != "merged"
                or record.reason != "cleanup-pending"
            ):
                raise DeliveryJournalError("request-conflict")

            validate_record(envelope, record)
            request = envelope.orchestration_request
            _validate_authority(envelope, authority)

            terminal = read_terminal_receipt(record)
            if terminal is None:
                raise DeliveryJournalError("journal-invalid")
            if (terminal.lifecycle, terminal.reason) != ("merged", "cleanup-pending"):
                raise DeliveryJournalError("journal-invalid")
            if record.committed_head is None or record.merge_head is None:
                raise DeliveryJournalError("journal-invalid")
            if (
                record.remote_head is None
                or record.committed_head != record.remote_head
                or record.committed_head != record.merge_head
            ):
                raise DeliveryJournalError("journal-invalid")

            terminal_updated = terminal.updated_at.astimezone(UTC)
            if observed_utc < terminal_updated:
                raise DeliveryJournalError("journal-invalid")

            expected = _prepare_cleanup_record(
                envelope=envelope,
                authority=authority,
                expected_remote_head=record.committed_head,
                observed_utc=observed_utc,
            )

            if record.cleanup is not None:
                _validate_replay_match(record, expected, authority)
                connection.execute("COMMIT")
                return record

            start_marker = expected.scheduler_owner_start_token
            changed = _insert_cleanup_row(
                connection,
                request_id=record.request_id,
                remote_branch=expected.remote_branch,
                expected_remote_head=expected.expected_remote_head,
                scheduler_owner_id=expected.scheduler_owner_id,
                scheduler_owner_pid=expected.scheduler_owner_pid,
                scheduler_owner_start_token=start_marker,
                scheduler_owner_epoch=expected.scheduler_owner_epoch,
                scheduler_phase_version=expected.scheduler_phase_version,
                cleanup_intent_at=expected.cleanup_intent_at,
                phase_version=1,
                request_id_guard=record.request_id,
                phase_guard=record.phase_version,
            )
            if changed != 1:
                raise DeliveryJournalError("request-conflict")

            updated = read_record(connection, record.request_id)
            if updated is None or updated.cleanup is None:
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.cleanup_intent_at != expected.cleanup_intent_at:
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.phase_version != 1:
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.request_id != envelope.request.request_id:
                raise DeliveryJournalError("journal-invalid")
            if (
                updated.cleanup.remote_branch != request.branch
                or updated.cleanup.expected_remote_head != record.committed_head
                or updated.cleanup.scheduler_owner_id != authority.owner_id
                or updated.cleanup.scheduler_owner_pid != authority.owner_pid
                or (
                    updated.cleanup.scheduler_owner_start_token
                    != authority.owner_start_token
                )
                or updated.cleanup.scheduler_owner_epoch != authority.epoch
                or updated.cleanup.scheduler_phase_version != authority.phase_version
            ):
                raise DeliveryJournalError("journal-invalid")

            updated_terminal = read_terminal_receipt(updated)
            if (
                updated_terminal is None
                or updated_terminal != terminal
            ):
                raise DeliveryJournalError("journal-invalid")

            connection.execute("COMMIT")
            return updated
        except DeliveryJournalError:
            connection.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
            raise DeliveryJournalError("journal-invalid") from None


def _insert_cleanup_row(
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
    values = (
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
        request_id_guard,
        phase_guard,
    )
    return connection.execute(_INSERT_CLEANUP, values).rowcount


def _prepare_cleanup_record(
    *,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    expected_remote_head: str,
    observed_utc: datetime,
) -> DeliveryCleanupRecord:
    request = envelope.orchestration_request
    row = (
        envelope.request.request_id,
        request.branch,
        expected_remote_head,
        authority.owner_id,
        authority.owner_pid,
        authority.owner_start_token,
        authority.epoch,
        authority.phase_version,
        observed_utc.isoformat(),
        None,
        None,
        None,
        None,
        1,
    )
    return read_cleanup_record(row)


def _normalize_observed(observed_at: datetime) -> datetime:
    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise DeliveryJournalError("journal-invalid")
    return observed_at.astimezone(UTC)


def _validate_authority(
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    if not isinstance(authority, SchedulerCompletionAuthority):
        raise DeliveryJournalError("journal-invalid")
    request = envelope.orchestration_request
    if (
        authority.owner_id != request.scheduler_owner_id
        or authority.owner_pid != request.scheduler_owner_pid
        or authority.owner_start_token != request.scheduler_owner_start_token
        or authority.epoch != request.scheduler_owner_epoch
    ):
        raise DeliveryJournalError("journal-invalid")


def _validate_replay_match(
    record: DeliveryJournalRecord,
    expected: DeliveryCleanupRecord,
    authority: SchedulerCompletionAuthority,
) -> None:
    cleanup = record.cleanup
    if cleanup is None:
        raise ValueError("cleanup replay requires persisted cleanup row")
    if cleanup.request_id != expected.request_id:
        raise DeliveryJournalError("journal-invalid")
    if (
        cleanup.remote_branch != expected.remote_branch
        or cleanup.expected_remote_head != expected.expected_remote_head
        or cleanup.scheduler_owner_id != authority.owner_id
        or cleanup.scheduler_owner_pid != authority.owner_pid
        or cleanup.scheduler_owner_start_token != authority.owner_start_token
        or cleanup.scheduler_owner_epoch != authority.epoch
        or cleanup.scheduler_phase_version != authority.phase_version
    ):
        raise DeliveryJournalError("journal-invalid")
