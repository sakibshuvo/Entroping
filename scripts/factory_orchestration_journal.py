"""Separate private lifecycle journal; scheduler admission remains authoritative."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from scripts.factory_orchestration_errors import OrchestrationJournalError
from scripts.factory_orchestration_journal_storage import journal_connection
from scripts.factory_orchestration_models import (
    Lifecycle,
    OrchestrationReceipt,
    OrchestrationRequest,
)

type JournalReason = Literal["none", "interrupted"]
_ACTIVE = ("prepared", "applying", "applied", "gating", "uncertain")
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "prepared": ("applying", "cancelled", "failed", "uncertain"),
    "applying": ("applied", "failed", "cancelled", "uncertain"),
    "applied": ("gating", "failed", "cancelled", "uncertain"),
    "gating": ("accepted", "failed", "cancelled", "uncertain"),
}
_LIFECYCLE: TypeAdapter[Lifecycle] = TypeAdapter(Lifecycle)
_REASON: TypeAdapter[JournalReason] = TypeAdapter(JournalReason)


@dataclass(frozen=True, slots=True)
class JournalRecord:
    request_id: str
    request_digest: str
    issue_number: int
    worktree_id: str
    lifecycle: Lifecycle
    reason: JournalReason
    receipt: OrchestrationReceipt | None
    created_at: datetime
    updated_at: datetime


class OrchestrationJournal:
    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def prepare(self, request: OrchestrationRequest) -> JournalRecord:
        with journal_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = _read(connection, request.request_id)
            if existing is not None:
                if existing.request_digest != request.request_digest:
                    connection.execute("ROLLBACK")
                    raise OrchestrationJournalError("request-conflict")
                _validate_record(request, existing)
                if existing.lifecycle == "uncertain":
                    connection.execute("ROLLBACK")
                    raise OrchestrationJournalError("uncertain-recovery-required")
                if existing.lifecycle in {"applying", "applied", "gating"}:
                    connection.execute(
                        "UPDATE orchestration_lifecycle SET lifecycle = 'uncertain', "
                        "reason = 'interrupted', updated_at_utc = ? WHERE request_id = ?",
                        (_now(), request.request_id),
                    )
                    connection.execute("COMMIT")
                    raise OrchestrationJournalError("uncertain-recovery-required")
                connection.execute("COMMIT")
                return existing
            overlap = connection.execute(
                "SELECT request_digest FROM orchestration_lifecycle "
                "WHERE (issue_number = ? OR worktree_id = ?) "
                f"AND lifecycle IN ({','.join('?' for _ in _ACTIVE)}) LIMIT 1",
                (request.issue_number, request.worktree_id, *_ACTIVE),
            ).fetchone()
            if overlap is not None:
                connection.execute("ROLLBACK")
                if overlap[0] == request.request_digest:
                    raise OrchestrationJournalError("journal-invalid")
                raise OrchestrationJournalError("authority-mismatch")
            connection.execute(
                "INSERT INTO orchestration_lifecycle("
                "request_id, request_digest, issue_number, worktree_id, lifecycle, reason, "
                "created_at_utc, updated_at_utc"
                ") VALUES (?, ?, ?, ?, 'prepared', 'none', ?, ?)",
                (
                    request.request_id,
                    request.request_digest,
                    request.issue_number,
                    request.worktree_id,
                    _now(),
                    _now(),
                ),
            )
            connection.execute("COMMIT")
            record = _read(connection, request.request_id)
            if record is None:
                raise OrchestrationJournalError("journal-invalid")
            return record

    def terminal_receipt(self, request: OrchestrationRequest) -> OrchestrationReceipt | None:
        """Return only an exact durable terminal replay without changing lifecycle."""

        with journal_connection(self._root) as connection:
            connection.execute("BEGIN")
            existing = _read(connection, request.request_id)
            connection.execute("COMMIT")
        if existing is None:
            return None
        if existing.request_digest != request.request_digest:
            raise OrchestrationJournalError("request-conflict")
        _validate_record(request, existing)
        if existing.lifecycle == "uncertain":
            raise OrchestrationJournalError("uncertain-recovery-required")
        if existing.lifecycle in {"accepted", "failed", "cancelled"}:
            if existing.receipt is None:
                raise OrchestrationJournalError("journal-invalid")
            return existing.receipt
        return None

    def transition(
        self,
        request: OrchestrationRequest,
        *,
        expected: Lifecycle,
        lifecycle: Lifecycle,
        reason: JournalReason = "none",
        receipt: OrchestrationReceipt | None = None,
    ) -> JournalRecord:
        if lifecycle not in _TRANSITIONS.get(expected, ()):
            raise OrchestrationJournalError("journal-invalid")
        if lifecycle in {"accepted", "failed", "cancelled"} and receipt is None:
            raise OrchestrationJournalError("journal-invalid")
        if receipt is not None and receipt.lifecycle != lifecycle:
            raise OrchestrationJournalError("journal-invalid")
        if receipt is not None and not _receipt_matches(request, receipt):
            raise OrchestrationJournalError("journal-invalid")
        with journal_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = _read(connection, request.request_id)
            if (
                record is None
                or record.request_digest != request.request_digest
                or record.lifecycle != expected
            ):
                connection.execute("ROLLBACK")
                raise OrchestrationJournalError("request-conflict")
            _validate_record(request, record)
            changed = connection.execute(
                "UPDATE orchestration_lifecycle SET lifecycle = ?, reason = ?, receipt_json = ?, "
                "updated_at_utc = ? "
                "WHERE request_id = ? AND request_digest = ? AND lifecycle = ?",
                (
                    lifecycle,
                    reason,
                    None if receipt is None else receipt.model_dump_json(),
                    _now(),
                    request.request_id,
                    request.request_digest,
                    expected,
                ),
            ).rowcount
            if changed != 1:
                connection.execute("ROLLBACK")
                raise OrchestrationJournalError("request-conflict")
            connection.execute("COMMIT")
            updated = _read(connection, request.request_id)
            if updated is None:
                raise OrchestrationJournalError("journal-invalid")
            return updated


def _read(connection: sqlite3.Connection, request_id: str) -> JournalRecord | None:
    row = connection.execute(
        "SELECT request_id, request_digest, issue_number, worktree_id, lifecycle, reason, "
        "receipt_json, created_at_utc, updated_at_utc "
        "FROM orchestration_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = (
            None
            if row[6] is None
            else OrchestrationReceipt.model_validate_json(row[6], strict=True)
        )
        lifecycle = _LIFECYCLE.validate_python(row[4], strict=True)
        reason = _REASON.validate_python(row[5], strict=True)
        created = datetime.fromisoformat(row[7])
        updated = datetime.fromisoformat(row[8])
        if created.tzinfo is None or updated.tzinfo is None or updated < created:
            raise ValueError
        return JournalRecord(
            request_id=row[0],
            request_digest=row[1],
            issue_number=row[2],
            worktree_id=row[3],
            lifecycle=lifecycle,
            reason=reason,
            receipt=receipt,
            created_at=created,
            updated_at=updated,
        )
    except (IndexError, TypeError, ValueError, ValidationError) as exc:
        raise OrchestrationJournalError("journal-invalid") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_record(request: OrchestrationRequest, record: JournalRecord) -> None:
    terminal = record.lifecycle in {"accepted", "failed", "cancelled"}
    uncertain = record.lifecycle == "uncertain"
    if (
        record.request_id != request.request_id
        or record.issue_number != request.issue_number
        or record.worktree_id != request.worktree_id
        or terminal != (record.receipt is not None)
        or (record.receipt is not None and record.receipt.lifecycle != record.lifecycle)
        or uncertain != (record.reason == "interrupted")
        or (record.receipt is not None and not _receipt_matches(request, record.receipt))
    ):
        raise OrchestrationJournalError("journal-invalid")


def _receipt_matches(
    request: OrchestrationRequest,
    receipt: OrchestrationReceipt,
) -> bool:
    return (
        receipt.request_id == request.request_id
        and receipt.request_digest == request.request_digest
        and receipt.issue_number == request.issue_number
        and receipt.job_id == request.job_id
        and receipt.assignment_id == request.assignment_id
        and receipt.scheduler_owner_id == request.scheduler_owner_id
        and receipt.scheduler_owner_epoch == request.scheduler_owner_epoch
        and receipt.selector_digest == request.selector_digest
        and receipt.selection_digest == request.selection_digest
        and receipt.worktree_id == request.worktree_id
        and receipt.worktree_path_sha256
        == hashlib.sha256(str(Path(request.worktree_path).resolve()).encode()).hexdigest()
        and receipt.branch == request.branch
        and receipt.verification_lane == request.verification_lane
        and receipt.proposal_sha256 == request.proposal_sha256
        and receipt.allowed_scope_digest == request.allowed_scope_digest
        and receipt.base_commit == request.base_commit
    )
