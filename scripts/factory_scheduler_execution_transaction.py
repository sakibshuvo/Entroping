from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.factory_scheduler_execution_models import (
    ExecutionPhase,
    ExecutionState,
    TerminalOutcome,
)
from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import clock, read_execution
from scripts.factory_scheduler_receipts import iso_utc
from scripts.factory_scheduler_transaction_control import rollback_transaction, update_clock
from scripts.factory_scheduler_validation import aware_utc

_ALLOWED_TRANSITIONS: dict[ExecutionPhase, frozenset[ExecutionPhase]] = {
    "never-dispatched": frozenset({"dispatch-intent"}),
    "dispatch-intent": frozenset({"dispatched"}),
    "dispatched": frozenset({"completed-unsettled"}),
    "completed-unsettled": frozenset(),
    "retry-wait": frozenset(),
    "uncertain": frozenset(),
    "completed": frozenset(),
    "failed": frozenset(),
}


def transition_execution(
    connection: sqlite3.Connection,
    *,
    assignment_id: str,
    owner: LeaseOwner,
    epoch: int,
    expected_phase_version: int,
    target_phase: ExecutionPhase,
    observed_at: datetime,
    evidence_digest: str,
) -> ExecutionState:
    observed = aware_utc(observed_at)
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        clock_at, _last_epoch = clock(connection)
        if observed < clock_at:
            raise ValueError("execution transition clock rollback")
        execution = read_execution(connection, assignment_id=assignment_id)
        if execution is None:
            raise ValueError("scheduler execution state not found")
        if (
            execution.lease_owner_id,
            execution.lease_owner_pid,
            execution.lease_owner_start_token,
            execution.lease_epoch,
        ) != (owner.owner_id, owner.pid, owner.process_start_token, epoch):
            raise ValueError("scheduler execution authority is stale")
        if execution.phase_version != expected_phase_version:
            raise ValueError("scheduler execution phase version is stale")
        if target_phase not in _ALLOWED_TRANSITIONS[execution.phase]:
            raise ValueError("scheduler execution transition is invalid")
        updated = update_execution_row(
            connection,
            execution=execution,
            phase=target_phase,
            observed_at=observed,
            evidence_digest=evidence_digest,
            terminal_outcome="completed" if target_phase == "completed" else None,
        )
        if target_phase == "completed":
            _ = connection.execute(
                "UPDATE scheduler_assignments SET state = 'completed', completed_at_utc = ? "
                "WHERE assignment_id = ? AND state = 'active'",
                (iso_utc(observed), assignment_id),
            )
        update_clock(connection, observed)
        _ = connection.execute("COMMIT")
        return updated
    except BaseException:
        rollback_transaction(connection)
        raise


def update_execution_row(
    connection: sqlite3.Connection,
    *,
    execution: ExecutionState,
    phase: ExecutionPhase,
    observed_at: datetime,
    owner: LeaseOwner | None = None,
    epoch: int | None = None,
    lease_expires_at: datetime | None = None,
    worker_heartbeat_at: datetime | None = None,
    attempt_count: int | None = None,
    retry_not_before: datetime | None = None,
    failure_code: str | None = None,
    terminal_outcome: TerminalOutcome | None = None,
    evidence_digest: str | None = None,
) -> ExecutionState:
    start_marker = execution.lease_owner_start_token
    effective_owner = owner or LeaseOwner(
        owner_id=execution.lease_owner_id,
        pid=execution.lease_owner_pid,
        process_start_token=start_marker,
    )
    effective_epoch = execution.lease_epoch if epoch is None else epoch
    effective_expiration = (
        execution.lease_expires_at if lease_expires_at is None else lease_expires_at
    )
    effective_heartbeat = aware_utc(
        observed_at if worker_heartbeat_at is None else worker_heartbeat_at
    )
    effective_attempts = execution.attempt_count if attempt_count is None else attempt_count
    version = execution.phase_version + 1
    cursor = connection.execute(
        "UPDATE scheduler_execution_state SET phase = ?, phase_version = ?, "
        "attempt_count = ?, lease_owner_id = ?, lease_owner_pid = ?, "
        "lease_owner_start_token = ?, lease_epoch = ?, phase_changed_at_utc = ?, "
        "lease_expires_at_utc = ?, worker_heartbeat_at_utc = ?, "
        "retry_not_before_utc = ?, failure_code = ?, "
        "terminal_outcome = ?, evidence_digest = ? "
        "WHERE assignment_id = ? AND phase_version = ?",
        (
            phase,
            version,
            effective_attempts,
            effective_owner.owner_id,
            effective_owner.pid,
            effective_owner.process_start_token,
            effective_epoch,
            iso_utc(observed_at),
            iso_utc(effective_expiration),
            iso_utc(effective_heartbeat),
            None if retry_not_before is None else iso_utc(retry_not_before),
            failure_code,
            terminal_outcome,
            evidence_digest,
            execution.assignment_id,
            execution.phase_version,
        ),
    )
    if cursor.rowcount != 1:
        raise ValueError("scheduler execution transition lost its compare-and-swap")
    updated = read_execution(connection, assignment_id=execution.assignment_id)
    if updated is None:
        raise sqlite3.DatabaseError("scheduler execution state disappeared")
    return updated
