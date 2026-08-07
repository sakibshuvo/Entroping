"""SQLite writer for durable completed terminal receipt persistence."""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime
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
from scripts.factory_pr_delivery_receipts import DeliveryReceipt, encode_delivery_receipt

_COMPLETED_UPDATE = (
    "UPDATE delivery_lifecycle SET "
    "terminal_receipt_json = ?, terminal_receipt_sha256 = ?, "
    "terminal_at_utc = ?, updated_at_utc = ?, phase_version = phase_version + 1 "
    "WHERE request_id = ? "
    "AND lifecycle = 'merged' "
    "AND reason = 'cleanup-pending' "
    "AND phase_version = ? "
    "AND EXISTS ("
    "SELECT 1 FROM delivery_cleanup AS cleanup "
    "WHERE cleanup.request_id = ? "
    "AND cleanup.phase_version = 5 "
    "AND cleanup.scheduler_completion_at_utc IS NOT NULL "
    "AND cleanup.scheduler_completed_at_utc = cleanup.scheduler_completion_at_utc"
    ")"
)


def persist_completed_receipt(
    root: Path,
    envelope: DeliveryEnvelope,
) -> DeliveryJournalRecord:
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

            cleanup = record.cleanup
            if cleanup.phase_version in range(0, 5):
                raise DeliveryJournalError("request-conflict")
            if cleanup.phase_version != 5:
                raise DeliveryJournalError("journal-invalid")
            if (
                cleanup.scheduler_completion_at is None
                or cleanup.scheduler_completed_at is None
                or cleanup.scheduler_completion_at != cleanup.scheduler_completed_at
            ):
                raise DeliveryJournalError("journal-invalid")

            terminal = _read_and_validate_terminal_receipt(record)
            completed_at = cleanup.scheduler_completed_at

            if terminal.lifecycle == "completed" and terminal.reason == "completed":
                if terminal.updated_at != completed_at:
                    raise DeliveryJournalError("journal-invalid")
                connection.execute("COMMIT")
                return record

            if (terminal.lifecycle, terminal.reason) != ("merged", "cleanup-pending"):
                raise DeliveryJournalError("journal-invalid")

            completed_receipt = DeliveryReceipt(
                request_id=terminal.request_id,
                lifecycle="completed",
                reason="completed",
                authoritative=True,
                accepted_local_head=terminal.accepted_local_head,
                committed_head=terminal.committed_head,
                remote_head=terminal.remote_head,
                pr_number=terminal.pr_number,
                ci_digest=terminal.ci_digest,
                merge_head=terminal.merge_head,
                created_at=terminal.created_at,
                updated_at=completed_at,
            )
            terminal_raw, terminal_digest = encode_delivery_receipt(completed_receipt)

            changed = _persist_completed_receipt(
                connection,
                request_id=record.request_id,
                terminal_raw=terminal_raw,
                terminal_digest=terminal_digest,
                completed_at=completed_at,
                expected_phase=record.phase_version,
            )
            if changed != 1:
                raise DeliveryJournalError("request-conflict")

            updated = read_record(connection, record.request_id)
            if updated is None or updated.cleanup is None:
                raise DeliveryJournalError("journal-invalid")
            validate_record(envelope, updated)
            if (
                dataclasses.replace(
                    updated,
                    terminal_receipt_json=record.terminal_receipt_json,
                    terminal_receipt_sha256=record.terminal_receipt_sha256,
                    terminal_at=record.terminal_at,
                    updated_at=record.updated_at,
                    phase_version=record.phase_version,
                )
                != record
            ):
                raise DeliveryJournalError("journal-invalid")
            if updated.phase_version != record.phase_version + 1:
                raise DeliveryJournalError("journal-invalid")
            if not _cleanup_immutable_fields_match(cleanup, updated.cleanup):
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.scheduler_completed_at != completed_at:
                raise DeliveryJournalError("journal-invalid")
            if updated.cleanup.scheduler_completion_at != completed_at:
                raise DeliveryJournalError("journal-invalid")
            if read_terminal_receipt(updated) != completed_receipt:
                raise DeliveryJournalError("journal-invalid")

            connection.execute("COMMIT")
            return updated
        except DeliveryJournalError:
            connection.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
            raise DeliveryJournalError("journal-invalid") from None


def _persist_completed_receipt(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    terminal_raw: str,
    terminal_digest: str,
    completed_at: datetime,
    expected_phase: int,
) -> int:
    return connection.execute(
        _COMPLETED_UPDATE,
        (
            terminal_raw,
            terminal_digest,
            completed_at.isoformat(),
            completed_at.isoformat(),
            request_id,
            expected_phase,
            request_id,
        ),
    ).rowcount


def _read_and_validate_terminal_receipt(record: DeliveryJournalRecord) -> DeliveryReceipt:
    terminal = read_terminal_receipt(record)
    if terminal is None:
        raise DeliveryJournalError("journal-invalid")
    return terminal


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
        and original.scheduler_completion_at == updated.scheduler_completion_at
        and original.scheduler_completed_at == updated.scheduler_completed_at
        and original.phase_version == updated.phase_version
    )
