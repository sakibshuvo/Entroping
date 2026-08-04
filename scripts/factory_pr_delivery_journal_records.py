"""Strict value-free row projection for the delivery journal."""

from __future__ import annotations

import re
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

_REQUEST_ID = re.compile(r"delivery_[a-f0-9]{64}\Z")
_ASSIGNMENT_ID = re.compile(r"assign_[a-f0-9]{64}\Z")
_WORKTREE_ID = re.compile(r"wt_[a-f0-9]{64}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}\Z")


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
        )
        _validate_shape(record)
        return record
    except (IndexError, TypeError, ValueError):
        raise DeliveryJournalError("journal-invalid") from None


def validate_record(envelope: DeliveryEnvelope, record: DeliveryJournalRecord) -> None:
    try:
        _validate_shape(record)
    except (TypeError, ValueError, KeyError):
        raise DeliveryJournalError("journal-invalid") from None
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


def _validate_shape(record: DeliveryJournalRecord) -> None:
    if (
        not _REQUEST_ID.fullmatch(record.request_id)
        or not _DIGEST.fullmatch(record.request_digest)
        or not _DIGEST.fullmatch(record.envelope_digest)
        or not _ASSIGNMENT_ID.fullmatch(record.assignment_id)
        or not _WORKTREE_ID.fullmatch(record.worktree_id)
        or not _COMMIT.fullmatch(record.accepted_local_head)
        or not _DIGEST.fullmatch(record.accepted_diff_sha256)
        or not _DIGEST.fullmatch(record.accepted_manifest_sha256)
        or not _DIGEST.fullmatch(record.approved_path_sha256)
        or not _DIGEST.fullmatch(record.body_sha256)
        or record.issue_number < 1
        or record.phase_version < 1
        or record.created_at.tzinfo is None
        or record.created_at.utcoffset() is None
        or record.updated_at.tzinfo is None
        or record.updated_at.utcoffset() is None
        or record.updated_at < record.created_at
    ):
        raise ValueError
    for commit in (
        record.committed_head,
        record.remote_head,
        record.commit_parent,
        record.commit_tree,
    ):
        if commit is not None and not _COMMIT.fullmatch(commit):
            raise ValueError
    commit_values = (record.committed_head, record.commit_parent, record.commit_tree)
    committed = record.lifecycle in {"commit-intent", "committed", "push-intent", "pushed"}
    if (committed or any(value is not None for value in commit_values)) and not all(
        value is not None for value in commit_values
    ):
        raise ValueError
    if record.commit_parent is not None and record.commit_parent != record.accepted_local_head:
        raise ValueError
    if record.lifecycle != "pushed" and record.remote_head is not None:
        raise ValueError
    if record.lifecycle == "pushed" and record.remote_head != record.committed_head:
        raise ValueError
    expected_reason: dict[DeliveryLifecycle, JournalReason] = {
        "prepared": "none",
        "commit-intent": "none",
        "committed": "committed",
        "push-intent": "committed",
        "pushed": "pushed",
        "uncertain": "interrupted",
    }
    if record.reason != expected_reason[record.lifecycle]:
        raise ValueError
