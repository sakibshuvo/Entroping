from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from scripts.factory_retry_policy import RetryPolicy
from scripts.factory_scheduler_execution_models import (
    ExecutionState,
    RecoveryDecision,
    RecoveryReceipt,
    RecoveryRequest,
    TerminalOutcome,
)
from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import text_value
from scripts.factory_scheduler_receipts import iso_utc


def recovery_request_digest(
    request: RecoveryRequest,
    *,
    owner: LeaseOwner,
    lease_seconds: int,
    policy: RetryPolicy,
) -> str:
    payload = {
        "request": request.model_dump(mode="json"),
        "owner_id": owner.owner_id,
        "lease_seconds": lease_seconds,
        "retry_policy": policy.model_dump(mode="json"),
    }
    return _digest(payload)


def replay_recovery_receipt(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    request_digest: str,
) -> RecoveryReceipt | None:
    row = connection.execute(
        "SELECT request_digest, receipt_json FROM scheduler_recovery_receipts WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    if text_value(row[0]) != request_digest:
        raise ValueError("recovery request id conflicts with stored evidence")
    return RecoveryReceipt.model_validate_json(text_value(row[1]), strict=True)


def make_recovery_receipt(
    *,
    request: RecoveryRequest,
    execution: ExecutionState,
    decision: RecoveryDecision,
    reason: str,
    authoritative: bool,
    observed_at: datetime,
    terminal_outcome: TerminalOutcome | None = None,
) -> RecoveryReceipt:
    model_material = {
        "request_id": request.request_id,
        "assignment_id": execution.assignment_id,
        "decision": decision,
        "reason": reason,
        "authoritative": authoritative,
        "phase": execution.phase,
        "phase_version": execution.phase_version,
        "attempt_count": execution.attempt_count,
        "retry_not_before": execution.retry_not_before,
        "terminal_outcome": terminal_outcome or execution.terminal_outcome,
        "lease_owner_id": execution.lease_owner_id,
        "lease_epoch": execution.lease_epoch,
        "observed_at": observed_at,
    }
    digest_material = {
        **model_material,
        "retry_not_before": (
            None if execution.retry_not_before is None else iso_utc(execution.retry_not_before)
        ),
        "observed_at": iso_utc(observed_at),
    }
    return RecoveryReceipt.model_validate(
        {
            **model_material,
            "receipt_id": f"recovery_{_digest(digest_material)}",
            "paid_work_authorized": False,
        },
        strict=True,
    )


def store_recovery_receipt(
    connection: sqlite3.Connection,
    *,
    request_digest: str,
    receipt: RecoveryReceipt,
) -> None:
    count = connection.execute("SELECT COUNT(*) FROM scheduler_recovery_receipts").fetchone()
    if count is None or not isinstance(count[0], int):
        raise sqlite3.DatabaseError("scheduler recovery receipt count is invalid")
    if count[0] >= 10_000:
        raise ValueError("scheduler recovery receipt capacity reached")
    serialized = json.dumps(
        receipt.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized.encode("utf-8")) > 4_096:
        raise ValueError("scheduler recovery receipt exceeds storage bound")
    _ = connection.execute(
        "INSERT INTO scheduler_recovery_receipts("
        "request_id, request_digest, receipt_id, assignment_id, created_at_utc, "
        "receipt_json) VALUES (?, ?, ?, ?, ?, ?)",
        (
            receipt.request_id,
            request_digest,
            receipt.receipt_id,
            receipt.assignment_id,
            iso_utc(receipt.observed_at),
            serialized,
        ),
    )


def _digest(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
