"""SQLite writer for durable scheduler completion proof persistence."""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal_cleanup_records import DeliveryCleanupRecord
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

_SCHEDULER_COMPLETION_UPDATE = (
    "UPDATE delivery_cleanup "
    "SET scheduler_completion_at_utc = ?, phase_version = phase_version + 1 "
    "WHERE request_id = ? "
    "AND phase_version = 3 "
    "AND finish_cleanup_at_utc IS NOT NULL "
    "AND remote_absent_at_utc IS NOT NULL "
    "AND scheduler_completion_at_utc IS NULL "
    "AND scheduler_completed_at_utc IS NULL"
)


def persist_scheduler_completion_intent(
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
            if record.cleanup is None:
                raise DeliveryJournalError("request-conflict")

            terminal = read_terminal_receipt(record)
            if terminal is None:
                raise DeliveryJournalError("journal-invalid")
            if (terminal.lifecycle, terminal.reason) != ("merged", "cleanup-pending"):
                raise DeliveryJournalError("journal-invalid")

            _validate_authority(envelope, authority)
            cleanup = record.cleanup
            remote_absent_at = cleanup.remote_absent_at
            request = envelope.orchestration_request
            if (
                cleanup.request_id != envelope.request.request_id
                or cleanup.remote_branch != request.branch
                or cleanup.expected_remote_head != record.committed_head
                or cleanup.expected_remote_head != record.remote_head
                or cleanup.expected_remote_head != record.merge_head
                or cleanup.scheduler_owner_id != authority.owner_id
                or cleanup.scheduler_owner_pid != authority.owner_pid
                or cleanup.scheduler_owner_start_token != authority.owner_start_token
                or cleanup.scheduler_owner_epoch != authority.epoch
                or cleanup.scheduler_phase_version != authority.phase_version
            ):
                raise DeliveryJournalError("journal-invalid")

            if (
                cleanup.phase_version >= 4
                and cleanup.scheduler_completion_at is not None
            ):
                if remote_absent_at is None:
                    raise DeliveryJournalError("journal-invalid")
                if observed_utc < remote_absent_at:
                    raise DeliveryJournalError("journal-invalid")
                connection.execute("COMMIT")
                return record

            if cleanup.phase_version < 3:
                raise DeliveryJournalError("request-conflict")
            if cleanup.phase_version == 3 and remote_absent_at is None:
                raise DeliveryJournalError("request-conflict")
            if cleanup.phase_version > 3:
                raise DeliveryJournalError("journal-invalid")
            if remote_absent_at is None:
                raise DeliveryJournalError("journal-invalid")
            if observed_utc < remote_absent_at:
                raise DeliveryJournalError("journal-invalid")
            if (
                cleanup.remote_absent_at is None
                or cleanup.finish_cleanup_at is None
                or cleanup.scheduler_completion_at is not None
                or cleanup.scheduler_completed_at is not None
            ):
                raise DeliveryJournalError("journal-invalid")

            changed = _persist_scheduler_completion(
                connection,
                request_id=record.request_id,
                observed_at=observed_utc,
            )
            if changed != 1:
                raise DeliveryJournalError("request-conflict")

            updated = read_record(connection, record.request_id)
            if updated is None or updated.cleanup is None:
                raise DeliveryJournalError("journal-invalid")
            validate_record(envelope, updated)
            if dataclasses.replace(updated, cleanup=record.cleanup) != record:
                raise DeliveryJournalError("journal-invalid")
            if not _cleanup_immutable_fields_match(cleanup, updated.cleanup):
                raise DeliveryJournalError("journal-invalid")
            if (
                updated.cleanup.phase_version != 4
                or updated.cleanup.scheduler_completion_at != observed_utc
                or updated.cleanup.scheduler_completed_at is not None
            ):
                raise DeliveryJournalError("journal-invalid")
            if read_terminal_receipt(updated) != terminal:
                raise DeliveryJournalError("journal-invalid")

            connection.execute("COMMIT")
            return updated
        except DeliveryJournalError:
            connection.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
            raise DeliveryJournalError("journal-invalid") from None


def _persist_scheduler_completion(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    observed_at: datetime,
) -> int:
    return connection.execute(
        _SCHEDULER_COMPLETION_UPDATE,
        (observed_at.isoformat(), request_id),
    ).rowcount


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


def _cleanup_immutable_fields_match(
    original: DeliveryCleanupRecord,
    updated: DeliveryCleanupRecord,
) -> bool:
    return (
        original.request_id == updated.request_id
        and original.remote_branch == updated.remote_branch
        and original.expected_remote_head == updated.expected_remote_head
        and original.scheduler_owner_id == updated.scheduler_owner_id
        and original.scheduler_owner_pid == updated.scheduler_owner_pid
        and original.scheduler_owner_start_token == updated.scheduler_owner_start_token
        and original.scheduler_owner_epoch == updated.scheduler_owner_epoch
        and original.scheduler_phase_version == updated.scheduler_phase_version
        and original.cleanup_intent_at == updated.cleanup_intent_at
        and original.remote_absent_at == updated.remote_absent_at
        and original.finish_cleanup_at == updated.finish_cleanup_at
    )


def _normalize_observed(observed_at: datetime) -> datetime:
    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise DeliveryJournalError("journal-invalid")
    return observed_at.astimezone(UTC)
