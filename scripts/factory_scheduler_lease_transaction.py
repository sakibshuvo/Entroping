from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

from scripts.factory_scheduler_models import DecisionReceipt, LeaseOwner
from scripts.factory_scheduler_queries import active_count, clock, counts, lease_row
from scripts.factory_scheduler_receipts import (
    decision_receipt,
    iso_utc,
    parse_utc,
)
from scripts.factory_scheduler_transaction_control import (
    finish_transaction,
    heartbeat_blocked_receipt,
    rollback_transaction,
    update_clock,
)
from scripts.factory_scheduler_validation import MAX_LEASE_EPOCH, aware_utc

HealthCheck = Callable[[LeaseOwner], bool | None]


def heartbeat_lease(
    connection: sqlite3.Connection,
    *,
    owner: LeaseOwner,
    epoch: int,
    as_of: datetime,
    lease_seconds: int,
) -> DecisionReceipt:
    observed_at = aware_utc(as_of)
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        clock_at, _last_epoch = clock(connection)
        if observed_at < clock_at:
            return finish_transaction(
                connection,
                plan_only=False,
                receipt=heartbeat_blocked_receipt(
                    connection,
                    observed_at,
                    "clock-rollback",
                ),
            )
        lease = lease_row(connection)
        if lease is None or lease[:4] != (
            owner.owner_id,
            owner.pid,
            owner.process_start_token,
            epoch,
        ):
            return finish_transaction(
                connection,
                plan_only=False,
                receipt=heartbeat_blocked_receipt(
                    connection,
                    observed_at,
                    "stale-lease-epoch",
                ),
            )
        expires_at = lease_expiration(observed_at, lease_seconds)
        if expires_at is None:
            return finish_transaction(
                connection,
                plan_only=False,
                receipt=heartbeat_blocked_receipt(
                    connection,
                    observed_at,
                    "state-invalid",
                ),
            )
        _ = connection.execute(
            "UPDATE scheduler_lease SET heartbeat_at_utc = ?, expires_at_utc = ? "
            "WHERE id = 1 AND owner_id = ? AND epoch = ?",
            (iso_utc(observed_at), iso_utc(expires_at), owner.owner_id, epoch),
        )
        renew_execution_leases(
            connection,
            owner=owner,
            epoch=epoch,
            observed_at=observed_at,
            expires_at=expires_at,
        )
        update_clock(connection, observed_at)
        receipt = decision_receipt(
            request=None,
            owner=owner,
            epoch=epoch,
            observed_at=observed_at,
            decision="heartbeat",
            reason="lease-renewed",
            authoritative=True,
            counts=counts(connection, None),
        )
        return finish_transaction(connection, plan_only=False, receipt=receipt)
    except BaseException:
        rollback_transaction(connection)
        raise


def lease_epoch(
    connection: sqlite3.Connection,
    *,
    owner: LeaseOwner,
    as_of: datetime,
    last_epoch: int,
    owner_health: HealthCheck,
) -> int | str:
    lease = lease_row(connection)
    if lease is None:
        return next_epoch(last_epoch)
    stored_owner = LeaseOwner(
        owner_id=lease[0],
        pid=lease[1],
        process_start_token=lease[2],
    )
    if stored_owner == owner:
        return lease[3]
    if as_of < parse_utc(lease[6]):
        return "lease-held"
    health = owner_health(stored_owner)
    if health is True:
        return "lease-owner-healthy"
    if health is not False:
        return "lease-owner-health-unknown"
    if active_count(connection) > 0:
        return "recovery-required"
    return next_epoch(last_epoch)


def recovery_epoch(
    connection: sqlite3.Connection,
    *,
    owner: LeaseOwner,
    last_epoch: int,
) -> int | str:
    lease = lease_row(connection)
    if lease is not None and lease[:3] == (
        owner.owner_id,
        owner.pid,
        owner.process_start_token,
    ):
        return lease[3]
    return next_epoch(last_epoch)


def renew_execution_leases(
    connection: sqlite3.Connection,
    *,
    owner: LeaseOwner,
    epoch: int,
    observed_at: datetime,
    expires_at: datetime,
) -> None:
    _ = connection.execute(
        "UPDATE scheduler_execution_state SET worker_heartbeat_at_utc = ?, "
        "lease_expires_at_utc = ? "
        "WHERE lease_owner_id = ? AND lease_owner_pid = ? "
        "AND lease_owner_start_token = ? AND lease_epoch = ? "
        "AND phase NOT IN ('completed', 'failed')",
        (
            iso_utc(observed_at),
            iso_utc(expires_at),
            owner.owner_id,
            owner.pid,
            owner.process_start_token,
            epoch,
        ),
    )


def next_epoch(last_epoch: int) -> int | str:
    if last_epoch >= MAX_LEASE_EPOCH:
        return "state-invalid"
    return last_epoch + 1


def lease_expiration(observed_at: datetime, lease_seconds: int) -> datetime | None:
    try:
        return observed_at + timedelta(seconds=lease_seconds)
    except OverflowError:
        return None


def store_lease(
    connection: sqlite3.Connection,
    owner: LeaseOwner,
    epoch: int,
    acquired_at: datetime,
    expires_at: datetime,
) -> None:
    _ = connection.execute("DELETE FROM scheduler_lease")
    _ = connection.execute(
        "INSERT INTO scheduler_lease(id, owner_id, owner_pid, owner_start_token, "
        "epoch, acquired_at_utc, heartbeat_at_utc, expires_at_utc) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        (
            owner.owner_id,
            owner.pid,
            owner.process_start_token,
            epoch,
            iso_utc(acquired_at),
            iso_utc(acquired_at),
            iso_utc(expires_at),
        ),
    )
