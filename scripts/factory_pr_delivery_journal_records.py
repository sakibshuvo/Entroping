"""Strict value-free row projection for the delivery journal."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from scripts.factory_pr_delivery_journal_cleanup_records import (
    DeliveryCleanupRecord,
    read_cleanup_record,
)
from scripts.factory_pr_delivery_journal_record_validation import (
    JournalLifecycle,
    JournalReason,
    validate_journal_record_shape,
)
from scripts.factory_pr_delivery_models import (
    DeliveryEnvelope,
    approved_path_digest,
)
from scripts.factory_pr_delivery_receipts import DeliveryReceipt, decode_delivery_receipt

__all__ = [
    "DeliveryJournalError",
    "DeliveryJournalRecord",
    "JournalLifecycle",
    "JournalReason",
    "read_record",
    "read_terminal_receipt",
    "validate_record",
]


class DeliveryJournalError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class DeliveryJournalRecord:
    request_id: str
    request_digest: str
    envelope_digest: str
    issue_number: int
    assignment_id: str
    worktree_id: str
    lifecycle: JournalLifecycle
    reason: JournalReason
    accepted_local_head: str
    committed_head: str | None
    remote_head: str | None
    commit_parent: str | None
    commit_tree: str | None
    accepted_diff_sha256: str
    accepted_manifest_sha256: str
    approved_path_sha256: str
    body_sha256: str
    phase_version: int
    created_at: datetime
    updated_at: datetime
    merge_pr_number: int | None
    merge_head: str | None
    merge_ci_digest: str | None
    merge_intent_at: datetime | None
    terminal_receipt_json: str | None
    terminal_receipt_sha256: str | None
    terminal_at: datetime | None
    cleanup: DeliveryCleanupRecord | None


def read_record(connection: sqlite3.Connection, request_id: str) -> DeliveryJournalRecord | None:
    row = connection.execute(
        "SELECT lifecycle.request_id, lifecycle.request_digest, lifecycle.envelope_digest, "
        "lifecycle.issue_number, lifecycle.assignment_id, lifecycle.worktree_id, "
        "lifecycle.lifecycle, lifecycle.reason, lifecycle.accepted_local_head, "
        "lifecycle.committed_head, lifecycle.remote_head, lifecycle.commit_parent, "
        "lifecycle.commit_tree, lifecycle.accepted_diff_sha256, "
        "lifecycle.accepted_manifest_sha256, lifecycle.approved_path_sha256, "
        "lifecycle.body_sha256, lifecycle.phase_version, lifecycle.created_at_utc, "
        "lifecycle.updated_at_utc, lifecycle.merge_pr_number, lifecycle.merge_head, "
        "lifecycle.merge_ci_digest, lifecycle.merge_intent_at_utc, "
        "lifecycle.terminal_receipt_json, lifecycle.terminal_receipt_sha256, "
        "lifecycle.terminal_at_utc, "
        "cleanup.request_id, cleanup.remote_branch, cleanup.expected_remote_head, "
        "cleanup.scheduler_owner_id, cleanup.scheduler_owner_pid, "
        "cleanup.scheduler_owner_start_token, cleanup.scheduler_owner_epoch, "
        "cleanup.scheduler_phase_version, cleanup.cleanup_intent_at_utc, "
        "cleanup.remote_absent_at_utc, cleanup.finish_cleanup_at_utc, "
        "cleanup.scheduler_completion_at_utc, cleanup.scheduler_completed_at_utc, "
        "cleanup.phase_version "
        "FROM delivery_lifecycle AS lifecycle "
        "LEFT JOIN delivery_cleanup AS cleanup ON cleanup.request_id = lifecycle.request_id "
        "WHERE lifecycle.request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        lifecycle: JournalLifecycle = row[6]
        reason: JournalReason = row[7]
        created = datetime.fromisoformat(row[18])
        updated = datetime.fromisoformat(row[19])
        record = DeliveryJournalRecord(
            request_id=row[0],
            request_digest=row[1],
            envelope_digest=row[2],
            issue_number=row[3],
            assignment_id=row[4],
            worktree_id=row[5],
            lifecycle=lifecycle,
            reason=reason,
            accepted_local_head=row[8],
            committed_head=row[9],
            remote_head=row[10],
            commit_parent=row[11],
            commit_tree=row[12],
            accepted_diff_sha256=row[13],
            accepted_manifest_sha256=row[14],
            approved_path_sha256=row[15],
            body_sha256=row[16],
            phase_version=row[17],
            created_at=created,
            updated_at=updated,
            merge_pr_number=row[20],
            merge_head=row[21],
            merge_ci_digest=row[22],
            merge_intent_at=(
                datetime.fromisoformat(row[23]) if row[23] is not None else None
            ),
            terminal_receipt_json=row[24],
            terminal_receipt_sha256=row[25],
            terminal_at=(datetime.fromisoformat(row[26]) if row[26] is not None else None),
            cleanup=(
                None if all(value is None for value in row[27:]) else read_cleanup_record(row[27:])
            ),
        )
        _validate_shape(record)
        _ = read_terminal_receipt(record)
        return record
    except (DeliveryJournalError, IndexError, TypeError, ValueError):
        raise DeliveryJournalError("journal-invalid") from None


def validate_record(envelope: DeliveryEnvelope, record: DeliveryJournalRecord) -> None:
    try:
        _validate_shape(record)
    except (TypeError, ValueError, KeyError):
        raise DeliveryJournalError("journal-invalid") from None
    receipt = envelope.orchestration_receipt
    request = envelope.orchestration_request
    _ = read_terminal_receipt(record)
    if (
        record.request_id != envelope.request.request_id
        or record.request_digest != envelope.request.request_digest
        or record.envelope_digest != envelope.envelope_digest
        or record.issue_number != request.issue_number
        or record.assignment_id != request.assignment_id
        or record.worktree_id != request.worktree_id
        or record.accepted_local_head != request.base_commit
        or record.accepted_diff_sha256 != receipt.diff_sha256
        or record.accepted_manifest_sha256 != receipt.result_manifest_sha256
        or record.approved_path_sha256 != approved_path_digest(receipt.approved_paths)
        or record.body_sha256 != envelope.request.pr_body_sha256
        or record.created_at.tzinfo is None
        or record.updated_at.tzinfo is None
        or record.updated_at < record.created_at
        or (
            record.lifecycle == "uncertain"
            and record.reason not in {"interrupted", "cleanup-pending"}
        )
    ):
        raise DeliveryJournalError("journal-invalid")

    if (
        record.cleanup is not None
        and not (
            record.lifecycle == "merged" and record.reason == "cleanup-pending"
        )
    ):
        raise DeliveryJournalError("journal-invalid")

    if record.cleanup is None:
        return

    if (
        record.cleanup.request_id != record.request_id
        or record.cleanup.request_id != envelope.request.request_id
        or record.cleanup.remote_branch != request.branch
        or record.cleanup.expected_remote_head != record.committed_head
        or record.cleanup.expected_remote_head != record.remote_head
        or record.cleanup.expected_remote_head != record.merge_head
        or record.cleanup.scheduler_owner_id != request.scheduler_owner_id
        or record.cleanup.scheduler_owner_pid != request.scheduler_owner_pid
        or record.cleanup.scheduler_owner_start_token != request.scheduler_owner_start_token
        or record.cleanup.scheduler_owner_epoch != request.scheduler_owner_epoch
    ):
        raise DeliveryJournalError("journal-invalid")


def read_terminal_receipt(record: DeliveryJournalRecord) -> DeliveryReceipt | None:
    if (
        record.terminal_receipt_json is None
        and record.terminal_receipt_sha256 is None
        and record.terminal_at is None
    ):
        return None
    if (
        record.terminal_receipt_json is None
        or record.terminal_receipt_sha256 is None
        or record.terminal_at is None
    ):
        raise DeliveryJournalError("journal-invalid")
    try:
        receipt = decode_delivery_receipt(
            record.terminal_receipt_json, record.terminal_receipt_sha256
        )
    except ValueError:
        raise DeliveryJournalError("journal-invalid") from None
    if (
        record.request_id != receipt.request_id
        or not receipt.authoritative
        or record.accepted_local_head != receipt.accepted_local_head
        or record.committed_head != receipt.committed_head
        or record.remote_head != receipt.remote_head
        or record.merge_pr_number != receipt.pr_number
        or record.merge_ci_digest != receipt.ci_digest
        or record.merge_head != receipt.merge_head
        or record.merge_intent_at != receipt.created_at
        or record.terminal_at != receipt.updated_at
        or (receipt.lifecycle, receipt.reason)
        not in {("merged", "cleanup-pending"), ("completed", "completed")}
    ):
        raise DeliveryJournalError("journal-invalid")
    return receipt


def _validate_shape(record: DeliveryJournalRecord) -> None:
    validate_journal_record_shape(record)
