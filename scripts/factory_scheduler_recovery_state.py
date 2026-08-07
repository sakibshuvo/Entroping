from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from scripts.factory_scheduler_execution_models import ExecutionState, RecoveryRequest
from scripts.factory_scheduler_execution_transaction import update_execution_row
from scripts.factory_scheduler_lease_transaction import (
    lease_expiration,
    recovery_epoch,
    renew_execution_leases,
    store_lease,
)
from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import clock
from scripts.factory_scheduler_receipts import iso_utc
from scripts.factory_scheduler_recovery_decision import RecoveryTransition
from scripts.factory_scheduler_transaction_control import update_clock


def apply_recovery_transition(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    execution: ExecutionState,
    transition: RecoveryTransition,
    owner: LeaseOwner,
    observed_at: datetime,
    lease_seconds: int,
) -> ExecutionState:
    _clock_at, last_epoch = clock(connection)
    epoch = recovery_epoch(connection, owner=owner, last_epoch=last_epoch)
    expires_at = lease_expiration(observed_at, lease_seconds)
    if isinstance(epoch, str) or expires_at is None:
        raise ValueError("recovery lease cannot advance")
    store_lease(connection, owner, epoch, observed_at, expires_at)
    renew_execution_leases(
        connection,
        owner=owner,
        epoch=epoch,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    updated = update_execution_row(
        connection,
        execution=execution,
        phase=transition.phase,
        observed_at=observed_at,
        owner=owner,
        epoch=epoch,
        lease_expires_at=expires_at,
        attempt_count=transition.attempt_count,
        retry_not_before=transition.retry_not_before,
        failure_code=None if transition.decision == "resumed" else transition.reason,
        terminal_outcome=transition.terminal_outcome,
        evidence_digest=snapshot_digest(request),
    )
    if transition.phase in {"completed", "failed"}:
        cursor = connection.execute(
            "UPDATE scheduler_assignments SET state = 'completed', completed_at_utc = ? "
            "WHERE assignment_id = ? AND state = 'active'",
            (iso_utc(observed_at), request.assignment_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("recovery terminalization lost its compare-and-swap")
    update_clock(connection, observed_at, epoch=epoch)
    return updated


def project_recovery_transition(
    *,
    execution: ExecutionState,
    transition: RecoveryTransition,
    request: RecoveryRequest,
    owner: LeaseOwner,
    epoch: int,
    lease_expires_at: datetime,
    observed_at: datetime,
) -> ExecutionState:
    start_marker = owner.process_start_token
    return ExecutionState.model_validate(
        {
            **execution.model_dump(),
            "phase": transition.phase,
            "phase_version": execution.phase_version + 1,
            "attempt_count": transition.attempt_count,
            "lease_owner_id": owner.owner_id,
            "lease_owner_pid": owner.pid,
            "lease_owner_start_token": start_marker,
            "lease_epoch": epoch,
            "lease_expires_at": lease_expires_at,
            "phase_changed_at": observed_at,
            "worker_heartbeat_at": observed_at,
            "retry_not_before": transition.retry_not_before,
            "failure_code": (None if transition.decision == "resumed" else transition.reason),
            "terminal_outcome": transition.terminal_outcome,
            "evidence_digest": snapshot_digest(request),
        },
        strict=True,
    )


def snapshot_digest(request: RecoveryRequest) -> str:
    payload = [snapshot.model_dump(mode="json") for snapshot in request.snapshots]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
