from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import cast

from scripts.factory_scheduler_execution_models import ExecutionState, RecoveryRequest
from scripts.factory_scheduler_models import LeaseOwner, WorkerClass
from scripts.factory_scheduler_queries import lease_row, read_execution, text_value
from scripts.factory_scheduler_receipts import parse_utc
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState

type HealthCheck = Callable[[LeaseOwner], bool | None]


def recovery_context(
    connection: sqlite3.Connection,
    assignment_id: str,
) -> tuple[ExecutionState, WorkerClass, str, datetime]:
    execution = read_execution(connection, assignment_id=assignment_id)
    if execution is None:
        raise ValueError("scheduler execution state not found")
    row = connection.execute(
        "SELECT worker_class, job_id, created_at_utc, state "
        "FROM scheduler_assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    if row is None:
        raise ValueError("scheduler assignment not found")
    worker_class = text_value(row[0])
    if worker_class not in {"paid", "free-local"}:
        raise sqlite3.DatabaseError("scheduler assignment worker class is invalid")
    if text_value(row[3]) != (
        "completed" if execution.phase in {"completed", "failed"} else "active"
    ):
        raise sqlite3.DatabaseError("assignment and execution states are inconsistent")
    return (
        execution,
        cast(WorkerClass, worker_class),
        text_value(row[1]),
        parse_utc(text_value(row[2])),
    )


def recovery_authority_blocker(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    execution: ExecutionState,
    owner: LeaseOwner,
    observed_at: datetime,
    owner_health: HealthCheck,
    worker_class: WorkerClass,
    settlement_authority: SettlementAuthorityState,
) -> str | None:
    if request.expected_epoch != execution.lease_epoch:
        return "stale-lease-epoch"
    lease = lease_row(connection)
    if lease is None:
        return "state-invalid"
    start_marker = execution.lease_owner_start_token
    execution_owner = LeaseOwner(
        owner_id=execution.lease_owner_id,
        pid=execution.lease_owner_pid,
        process_start_token=start_marker,
    )
    if owner == execution_owner:
        return "recovery-owner-conflict"
    if observed_at < execution.lease_expires_at:
        return "lease-held"
    health = owner_health(execution_owner)
    if health is True:
        return "lease-owner-healthy"
    if health is not False:
        return "lease-owner-health-unknown"
    lease_owner = LeaseOwner(
        owner_id=lease[0],
        pid=lease[1],
        process_start_token=lease[2],
    )
    execution_lease = (
        execution_owner.owner_id,
        execution_owner.pid,
        execution_owner.process_start_token,
        execution.lease_epoch,
    )
    if lease[:4] == execution_lease:
        if parse_utc(lease[6]) != execution.lease_expires_at:
            return "state-invalid"
    elif lease_owner != owner:
        if observed_at < parse_utc(lease[6]):
            return "lease-held"
        health = owner_health(lease_owner)
        if health is True:
            return "lease-owner-healthy"
        if health is not False:
            return "lease-owner-health-unknown"
    if (
        execution.phase == "retry-wait"
        and execution.retry_not_before is not None
        and observed_at < execution.retry_not_before
    ):
        return "retry-not-due"
    return settlement_authority_blocker(
        request,
        worker_class=worker_class,
        settlement_authority=settlement_authority,
    )


def settlement_authority_blocker(
    request: RecoveryRequest,
    *,
    worker_class: WorkerClass,
    settlement_authority: SettlementAuthorityState,
) -> str | None:
    if worker_class == "free-local":
        return None if request.settlement_state == "not-required" else "settlement-state-invalid"
    if settlement_authority == "unavailable":
        return "settlement-authority-unavailable"
    if settlement_authority in {"invalid", "launched"}:
        return "settlement-authority-conflict"
    if request.dispatch_state == "not-dispatched":
        expected: SettlementAuthorityState = (
            "settled" if request.settlement_state == "settled" else "dispatching"
        )
    elif request.settlement_state == "settled":
        expected = "settled"
    elif request.settlement_state == "uncertain":
        expected = "uncertain"
    else:
        return "settlement-authority-conflict"
    return None if settlement_authority == expected else "settlement-authority-conflict"
