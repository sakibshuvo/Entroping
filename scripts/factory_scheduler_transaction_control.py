from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.factory_scheduler_models import AssignmentRequest, DecisionReceipt
from scripts.factory_scheduler_queries import counts, lease_row
from scripts.factory_scheduler_receipts import decision_receipt, iso_utc


def update_clock(
    connection: sqlite3.Connection,
    observed_at: datetime,
    *,
    epoch: int | None = None,
) -> None:
    if epoch is None:
        _ = connection.execute(
            "UPDATE scheduler_clock SET last_observed_at_utc = ? WHERE id = 1",
            (iso_utc(observed_at),),
        )
        return
    _ = connection.execute(
        "UPDATE scheduler_clock SET last_observed_at_utc = ?, last_epoch = ? WHERE id = 1",
        (iso_utc(observed_at), epoch),
    )


def blocked_receipt(
    connection: sqlite3.Connection,
    *,
    request: AssignmentRequest,
    observed_at: datetime,
    reason: str,
) -> DecisionReceipt:
    lease = lease_row(connection)
    return decision_receipt(
        request=request,
        owner=None,
        epoch=None if lease is None else lease[3],
        observed_at=observed_at,
        decision="blocked",
        reason=reason,
        authoritative=True,
        counts=counts(connection, request.scope_key),
        lease_owner_id=None if lease is None else lease[0],
    )


def heartbeat_blocked_receipt(
    connection: sqlite3.Connection,
    observed_at: datetime,
    reason: str,
) -> DecisionReceipt:
    lease = lease_row(connection)
    return decision_receipt(
        request=None,
        owner=None,
        epoch=None if lease is None else lease[3],
        observed_at=observed_at,
        decision="blocked",
        reason=reason,
        authoritative=True,
        counts=counts(connection, None),
        lease_owner_id=None if lease is None else lease[0],
    )


def finish_transaction(
    connection: sqlite3.Connection,
    *,
    plan_only: bool,
    receipt: DecisionReceipt,
) -> DecisionReceipt:
    if not plan_only and connection.in_transaction:
        _ = connection.execute("COMMIT")
    return receipt


def rollback_transaction(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
