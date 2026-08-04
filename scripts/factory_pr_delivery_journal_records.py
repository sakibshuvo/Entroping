"""Strict value-free row projection for the delivery journal."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from scripts.factory_pr_delivery_models import (
    DeliveryEnvelope,
    DeliveryLifecycle,
    approved_path_digest,
)

type JournalReason = Literal["none", "committed", "pushed", "interrupted"]


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
    lifecycle: DeliveryLifecycle
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


def read_record(connection: sqlite3.Connection, request_id: str) -> DeliveryJournalRecord | None:
    row = connection.execute(
        "SELECT request_id, request_digest, envelope_digest, issue_number, assignment_id, "
        "worktree_id, lifecycle, reason, accepted_local_head, committed_head, remote_head, "
        "commit_parent, commit_tree, accepted_diff_sha256, accepted_manifest_sha256, "
        "approved_path_sha256, body_sha256, phase_version, created_at_utc, updated_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        lifecycle: DeliveryLifecycle = row[6]
        reason: JournalReason = row[7]
        created = datetime.fromisoformat(row[18])
        updated = datetime.fromisoformat(row[19])
        if lifecycle not in {
            "prepared",
            "commit-intent",
            "committed",
            "push-intent",
            "pushed",
            "uncertain",
        } or reason not in {"none", "committed", "pushed", "interrupted"}:
            raise ValueError
        return DeliveryJournalRecord(
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
        )
    except (IndexError, TypeError, ValueError):
        raise DeliveryJournalError("journal-invalid") from None


def validate_record(envelope: DeliveryEnvelope, record: DeliveryJournalRecord) -> None:
    receipt = envelope.orchestration_receipt
    request = envelope.orchestration_request
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
        or (record.lifecycle == "uncertain") != (record.reason == "interrupted")
    ):
        raise DeliveryJournalError("journal-invalid")
