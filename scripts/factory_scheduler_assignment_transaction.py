from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.factory_scheduler_models import AssignmentRequest, DecisionReceipt, LeaseOwner
from scripts.factory_scheduler_queries import counts, replay_row
from scripts.factory_scheduler_receipts import decision_receipt, iso_utc, parse_utc
from scripts.factory_scheduler_transaction_control import blocked_receipt


def replay_assignment(
    connection: sqlite3.Connection,
    *,
    request: AssignmentRequest,
    request_digest_value: str,
) -> DecisionReceipt | None:
    row = replay_row(connection, request_id=request.request_id)
    if row is None:
        return None
    if row[0] != request_digest_value:
        return blocked_receipt(
            connection,
            request=request,
            observed_at=parse_utc(row[7]),
            reason="request-id-conflict",
        )
    stored_owner = LeaseOwner(
        owner_id=row[3],
        pid=row[4],
        process_start_token=row[5],
    )
    return decision_receipt(
        request=request,
        owner=stored_owner,
        epoch=row[6],
        observed_at=parse_utc(row[7]),
        decision="assigned",
        reason="exact-replay",
        authoritative=True,
        counts=counts(connection, request.scope_key),
        assignment_id=row[1],
        decision_id=row[2],
    )


def insert_assignment(
    connection: sqlite3.Connection,
    *,
    request: AssignmentRequest,
    request_digest: str,
    assignment_id: str,
    decision_id: str,
    owner: LeaseOwner,
    epoch: int,
    created_at: datetime,
) -> None:
    _ = connection.execute(
        "INSERT INTO scheduler_assignments("
        "request_id, request_digest, assignment_id, decision_id, job_id, "
        "issue_number, worktree_id, scope_key, worker_class, access_mode, "
        "reservation_id, authorization_id, lease_owner_id, lease_owner_pid, "
        "lease_owner_start_token, lease_epoch, created_at_utc, state, "
        "completed_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "'active', NULL)",
        (
            request.request_id,
            request_digest,
            assignment_id,
            decision_id,
            request.job_id,
            request.issue_number,
            request.worktree_id,
            request.scope_key,
            request.worker_class,
            request.access_mode,
            request.reservation_id,
            request.authorization_id,
            owner.owner_id,
            owner.pid,
            owner.process_start_token,
            epoch,
            iso_utc(created_at),
        ),
    )
