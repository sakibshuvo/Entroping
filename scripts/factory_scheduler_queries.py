from __future__ import annotations

import sqlite3
from datetime import datetime

from pydantic import TypeAdapter

from scripts.factory_scheduler_models import (
    AssignmentRequest,
    SchedulerSnapshot,
    StoredAssignment,
)
from scripts.factory_scheduler_receipts import parse_utc

type LeaseRow = tuple[str, int, str, int, str, str, str]
type ReplayRow = tuple[str, str, str, str, int, str, int, str]
_INT = TypeAdapter(int)
_TEXT = TypeAdapter(str)


def clock(connection: sqlite3.Connection) -> tuple[datetime, int]:
    row = connection.execute(
        "SELECT last_observed_at_utc, last_epoch FROM scheduler_clock WHERE id = 1"
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("scheduler clock is missing")
    return parse_utc(text_value(row[0])), integer_value(row[1])


def lease_row(connection: sqlite3.Connection) -> LeaseRow | None:
    row = connection.execute(
        "SELECT owner_id, owner_pid, owner_start_token, epoch, acquired_at_utc, "
        "heartbeat_at_utc, expires_at_utc FROM scheduler_lease WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return (
        text_value(row[0]),
        integer_value(row[1]),
        text_value(row[2]),
        integer_value(row[3]),
        text_value(row[4]),
        text_value(row[5]),
        text_value(row[6]),
    )


def counts(
    connection: sqlite3.Connection,
    scope_key: str | None,
) -> tuple[int, int, int]:
    paid = count_row(
        connection.execute(
            "SELECT COUNT(*) FROM scheduler_assignments "
            "WHERE state = 'active' AND worker_class = 'paid'"
        ).fetchone()
    )
    free = count_row(
        connection.execute(
            "SELECT COUNT(*) FROM scheduler_assignments WHERE state = 'active' "
            "AND worker_class = 'free-local' AND access_mode = 'read-only'"
        ).fetchone()
    )
    writers = 0
    if scope_key is not None:
        writers = count_row(
            connection.execute(
                "SELECT COUNT(*) FROM scheduler_assignments WHERE state = 'active' "
                "AND access_mode = 'write' AND scope_key = ? COLLATE NOCASE",
                (scope_key,),
            ).fetchone()
        )
    return paid, free, writers


def active_count(connection: sqlite3.Connection) -> int:
    return count_row(
        connection.execute(
            "SELECT COUNT(*) FROM scheduler_assignments WHERE state = 'active'"
        ).fetchone()
    )


def replay_row(
    connection: sqlite3.Connection,
    *,
    request_id: str,
) -> ReplayRow | None:
    row = connection.execute(
        "SELECT request_digest, assignment_id, decision_id, lease_owner_id, "
        "lease_owner_pid, lease_owner_start_token, lease_epoch, created_at_utc "
        "FROM scheduler_assignments WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    return (
        text_value(row[0]),
        text_value(row[1]),
        text_value(row[2]),
        text_value(row[3]),
        integer_value(row[4]),
        text_value(row[5]),
        integer_value(row[6]),
        text_value(row[7]),
    )


def read_snapshot(connection: sqlite3.Connection | None) -> SchedulerSnapshot:
    if connection is None:
        return SchedulerSnapshot(
            active_assignment_count=0,
            active_paid=0,
            active_free_reviews=0,
            active_writer_count=0,
            lease_owner_id=None,
            lease_epoch=None,
            lease_expires_at=None,
        )
    lease = lease_row(connection)
    paid, free, _writers = counts(connection, None)
    writer_count = count_row(
        connection.execute(
            "SELECT COUNT(*) FROM scheduler_assignments "
            "WHERE state = 'active' AND access_mode = 'write'"
        ).fetchone()
    )
    return SchedulerSnapshot(
        active_assignment_count=active_count(connection),
        active_paid=paid,
        active_free_reviews=free,
        active_writer_count=writer_count,
        lease_owner_id=None if lease is None else lease[0],
        lease_epoch=None if lease is None else lease[3],
        lease_expires_at=None if lease is None else parse_utc(lease[6]),
    )


def read_assignment(
    connection: sqlite3.Connection,
    *,
    job_id: str,
) -> StoredAssignment | None:
    row = connection.execute(
        "SELECT request_id, request_digest, assignment_id, decision_id, job_id, "
        "issue_number, worktree_id, worker_class, access_mode, reservation_id, "
        "lease_owner_id, lease_owner_pid, lease_owner_start_token, lease_epoch, "
        "created_at_utc, state, completed_at_utc "
        "FROM scheduler_assignments WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    request = AssignmentRequest.model_validate(
        {
            "request_id": text_value(row[0]),
            "job_id": text_value(row[4]),
            "issue_number": integer_value(row[5]),
            "worktree_id": text_value(row[6]),
            "worker_class": text_value(row[7]),
            "access_mode": text_value(row[8]),
            "reservation_id": None if row[9] is None else text_value(row[9]),
        },
        strict=True,
    )
    completed = None if row[16] is None else parse_utc(text_value(row[16]))
    return StoredAssignment.model_validate(
        {
            "request": request,
            "request_digest": text_value(row[1]),
            "assignment_id": text_value(row[2]),
            "decision_id": text_value(row[3]),
            "lease_owner_id": text_value(row[10]),
            "lease_owner_pid": integer_value(row[11]),
            "lease_owner_start_token": text_value(row[12]),
            "lease_epoch": integer_value(row[13]),
            "created_at": parse_utc(text_value(row[14])),
            "state": text_value(row[15]),
            "completed_at": completed,
        },
        strict=True,
    )


def text_value(value: object) -> str:
    return _TEXT.validate_python(value, strict=True)


def integer_value(value: object) -> int:
    return _INT.validate_python(value, strict=True)


def count_row(row: tuple[object, ...] | None) -> int:
    if row is None or len(row) != 1:
        raise sqlite3.DatabaseError("scheduler count row is invalid")
    return integer_value(row[0])
