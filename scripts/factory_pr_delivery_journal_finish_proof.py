"""SQLite writer for durable finish-cleanup proof persistence."""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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

_FINISH_UPDATE = (
    "UPDATE delivery_cleanup "
    "SET finish_cleanup_at_utc = ?, phase_version = phase_version + 1 "
    "WHERE request_id = ? "
    "AND phase_version = 1 "
    "AND remote_absent_at_utc IS NULL "
    "AND finish_cleanup_at_utc IS NULL "
    "AND scheduler_completion_at_utc IS NULL "
    "AND scheduler_completed_at_utc IS NULL"
)


def persist_finish_cleaned(
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
            if terminal.lifecycle != "merged" or terminal.reason != "cleanup-pending":
                raise DeliveryJournalError("journal-invalid")
            if not isinstance(authority, SchedulerCompletionAuthority):
                raise DeliveryJournalError("journal-invalid")

            request = envelope.orchestration_request
            if (
                record.committed_head is None
                or record.remote_head is None
                or record.merge_head is None
                or record.cleanup.request_id != envelope.request.request_id
                or record.cleanup.remote_branch != request.branch
                or record.cleanup.expected_remote_head != record.committed_head
                or record.cleanup.expected_remote_head != record.remote_head
                or record.cleanup.expected_remote_head != record.merge_head
                or record.cleanup.scheduler_phase_version != authority.phase_version
                or record.cleanup.scheduler_owner_id != authority.owner_id
                or record.cleanup.scheduler_owner_pid != authority.owner_pid
                or record.cleanup.scheduler_owner_start_token != authority.owner_start_token
                or record.cleanup.scheduler_owner_epoch != authority.epoch
                or authority.owner_id != request.scheduler_owner_id
                or authority.owner_pid != request.scheduler_owner_pid
                or authority.owner_start_token != request.scheduler_owner_start_token
                or authority.epoch != request.scheduler_owner_epoch
            ):
                raise DeliveryJournalError("journal-invalid")

            if observed_utc < record.cleanup.cleanup_intent_at:
                raise DeliveryJournalError("journal-invalid")

            if (
                record.cleanup.phase_version >= 2
                and record.cleanup.finish_cleanup_at is not None
            ):
                connection.execute("COMMIT")
                return record

            if (
                record.cleanup.phase_version != 1
                or record.cleanup.remote_absent_at is not None
                or record.cleanup.finish_cleanup_at is not None
                or record.cleanup.scheduler_completion_at is not None
                or record.cleanup.scheduler_completed_at is not None
            ):
                raise DeliveryJournalError("journal-invalid")

            changed = _persist_finish_cleaned(
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
            if not _cleanup_immutable_fields_match(record, updated):
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.finish_cleanup_at != observed_utc:
                raise DeliveryJournalError("journal-invalid")
            if (
                updated.cleanup.phase_version != 2
                or updated.cleanup.cleanup_intent_at != record.cleanup.cleanup_intent_at
                or updated.cleanup.remote_absent_at is not None
                or updated.cleanup.finish_cleanup_at is None
                or updated.cleanup.scheduler_completion_at is not None
                or updated.cleanup.scheduler_completed_at is not None
                or updated.cleanup.scheduler_owner_id != record.cleanup.scheduler_owner_id
                or updated.cleanup.scheduler_owner_pid != record.cleanup.scheduler_owner_pid
                or updated.cleanup.scheduler_owner_start_token
                != record.cleanup.scheduler_owner_start_token
                or updated.cleanup.scheduler_owner_epoch != record.cleanup.scheduler_owner_epoch
                or updated.cleanup.scheduler_phase_version != record.cleanup.scheduler_phase_version
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


def _persist_finish_cleaned(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    observed_at: datetime,
) -> int:
    return connection.execute(_FINISH_UPDATE, (observed_at.isoformat(), request_id)).rowcount


def _normalize_observed(observed_at: datetime) -> datetime:
    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise DeliveryJournalError("journal-invalid")
    return observed_at.astimezone(UTC)


def _cleanup_immutable_fields_match(
    original: DeliveryJournalRecord,
    updated: DeliveryJournalRecord,
) -> bool:
    if original.cleanup is None or updated.cleanup is None:
        return False
    return (
        original.cleanup.request_id == updated.cleanup.request_id
        and original.cleanup.remote_branch == updated.cleanup.remote_branch
        and original.cleanup.expected_remote_head == updated.cleanup.expected_remote_head
        and original.cleanup.scheduler_owner_id == updated.cleanup.scheduler_owner_id
        and original.cleanup.scheduler_owner_pid == updated.cleanup.scheduler_owner_pid
        and original.cleanup.scheduler_owner_start_token
        == updated.cleanup.scheduler_owner_start_token
        and original.cleanup.scheduler_owner_epoch == updated.cleanup.scheduler_owner_epoch
        and original.cleanup.scheduler_phase_version
        == updated.cleanup.scheduler_phase_version
        and original.cleanup.cleanup_intent_at == updated.cleanup.cleanup_intent_at
        and original.cleanup.remote_absent_at == updated.cleanup.remote_absent_at
    )
