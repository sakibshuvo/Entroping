from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

type SqliteScalar = str | bytes | int | float | None


def validate_scheduler_authority(
    connection: sqlite3.Connection, observed_at: datetime
) -> datetime | None:
    """Validate canonical scheduler timestamps and return the current lease expiry."""

    clock = connection.execute(
        "SELECT last_observed_at_utc FROM scheduler_clock WHERE id = 1"
    ).fetchone()
    if clock is None or _canonical_utc(clock[0]) > observed_at:
        raise ValueError("scheduler clock authority is unsafe")
    lease = connection.execute(
        "SELECT acquired_at_utc, heartbeat_at_utc, expires_at_utc FROM scheduler_lease WHERE id = 1"
    ).fetchone()
    lease_expiry: datetime | None = None
    if lease is not None:
        _ = _canonical_utc(lease[0])
        _ = _canonical_utc(lease[1])
        lease_expiry = _canonical_utc(lease[2])
    for execution in connection.execute(
        "SELECT lease_expires_at_utc, phase_changed_at_utc, "
        "worker_heartbeat_at_utc, retry_not_before_utc "
        "FROM scheduler_execution_state"
    ):
        _ = _canonical_utc(execution[0])
        _ = _canonical_utc(execution[1])
        _ = _canonical_utc(execution[2])
        if execution[3] is not None:
            _ = _canonical_utc(execution[3])
    return lease_expiry


def _canonical_utc(raw: SqliteScalar) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("scheduler timestamp is not canonical UTC")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("scheduler timestamp is not canonical UTC")
    canonical = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != raw:
        raise ValueError("scheduler timestamp is not canonical UTC")
    return value
