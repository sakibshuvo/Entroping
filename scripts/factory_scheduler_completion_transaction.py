from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.factory_scheduler_execution_transaction import update_execution_row
from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import clock, read_execution
from scripts.factory_scheduler_receipts import iso_utc
from scripts.factory_scheduler_transaction_control import (
    rollback_transaction,
    update_clock,
)
from scripts.factory_scheduler_validation import aware_utc


def complete_assignment(
    connection: sqlite3.Connection,
    *,
    assignment_id: str,
    owner: LeaseOwner,
    epoch: int,
    expected_phase_version: int,
    completed_at: datetime,
) -> None:
    observed_at = aware_utc(completed_at)
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        clock_at, _last_epoch = clock(connection)
        if observed_at < clock_at:
            raise ValueError("completion clock rollback")
        row = connection.execute(
            "SELECT state, completed_at_utc FROM scheduler_assignments WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()
        if row is None:
            raise ValueError("scheduler assignment not found")
        execution = read_execution(connection, assignment_id=assignment_id)
        if execution is None:
            raise ValueError("scheduler execution state not found")
        stored_authority = (
            execution.lease_owner_id,
            execution.lease_owner_pid,
            execution.lease_owner_start_token,
            execution.lease_epoch,
        )
        requested_authority = (
            owner.owner_id,
            owner.pid,
            owner.process_start_token,
            epoch,
        )
        if stored_authority != requested_authority:
            raise ValueError("assignment authority is stale")
        if row[0] == "active":
            if execution.phase != "completed-unsettled":
                raise ValueError("assignment has not reached completed-unsettled")
            if execution.phase_version != expected_phase_version:
                raise ValueError("assignment completion phase version is stale")
            _ = connection.execute(
                "UPDATE scheduler_assignments SET state = 'completed', "
                "completed_at_utc = ? WHERE assignment_id = ? AND state = 'active'",
                (iso_utc(observed_at), assignment_id),
            )
            _ = update_execution_row(
                connection,
                execution=execution,
                phase="completed",
                observed_at=observed_at,
                worker_heartbeat_at=execution.worker_heartbeat_at,
                terminal_outcome="completed",
                evidence_digest=execution.evidence_digest,
            )
            update_clock(connection, observed_at)
        elif (
            row[:2] != ("completed", iso_utc(observed_at))
            or execution.phase != "completed"
            or execution.phase_version != expected_phase_version + 1
        ):
            raise ValueError("assignment completion conflicts with stored evidence")
        _ = connection.execute("COMMIT")
    except BaseException:
        rollback_transaction(connection)
        raise
