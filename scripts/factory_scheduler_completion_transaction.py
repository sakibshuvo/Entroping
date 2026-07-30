from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import clock, integer_value, text_value
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
    completed_at: datetime,
) -> None:
    observed_at = aware_utc(completed_at)
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        clock_at, _last_epoch = clock(connection)
        if observed_at < clock_at:
            raise ValueError("completion clock rollback")
        row = connection.execute(
            "SELECT state, completed_at_utc, lease_owner_id, lease_owner_pid, "
            "lease_owner_start_token, lease_epoch "
            "FROM scheduler_assignments WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()
        if row is None:
            raise ValueError("scheduler assignment not found")
        stored_authority = (
            text_value(row[2]),
            integer_value(row[3]),
            text_value(row[4]),
            integer_value(row[5]),
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
            _ = connection.execute(
                "UPDATE scheduler_assignments SET state = 'completed', "
                "completed_at_utc = ? WHERE assignment_id = ? AND state = 'active'",
                (iso_utc(observed_at), assignment_id),
            )
            update_clock(connection, observed_at)
        elif row[:2] != ("completed", iso_utc(observed_at)):
            raise ValueError("assignment completion conflicts with stored evidence")
        _ = connection.execute("COMMIT")
    except BaseException:
        rollback_transaction(connection)
        raise
