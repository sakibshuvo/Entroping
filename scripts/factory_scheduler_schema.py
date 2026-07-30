from __future__ import annotations

import sqlite3
from functools import cache

SCHEMA_ID = "entroping.factory-scheduler-state.v1"
SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    ("CREATE TABLE scheduler_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT"),
    (
        "CREATE TABLE scheduler_clock ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), "
        "last_observed_at_utc TEXT NOT NULL, "
        "last_epoch INTEGER NOT NULL CHECK (last_epoch >= 0)"
        ") STRICT"
    ),
    (
        "CREATE TABLE scheduler_lease ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), "
        "owner_id TEXT NOT NULL, "
        "owner_pid INTEGER NOT NULL CHECK (owner_pid > 0), "
        "owner_start_token TEXT NOT NULL, "
        "epoch INTEGER NOT NULL CHECK (epoch > 0), "
        "acquired_at_utc TEXT NOT NULL, "
        "heartbeat_at_utc TEXT NOT NULL, "
        "expires_at_utc TEXT NOT NULL, "
        "CHECK (acquired_at_utc <= heartbeat_at_utc), "
        "CHECK (heartbeat_at_utc < expires_at_utc)"
        ") STRICT"
    ),
    (
        "CREATE TABLE scheduler_assignments ("
        "id INTEGER PRIMARY KEY, "
        "request_id TEXT NOT NULL UNIQUE, "
        "request_digest TEXT NOT NULL CHECK (length(request_digest) = 64), "
        "assignment_id TEXT NOT NULL UNIQUE, "
        "decision_id TEXT NOT NULL UNIQUE, "
        "job_id TEXT NOT NULL UNIQUE, "
        "issue_number INTEGER NOT NULL CHECK (issue_number > 0), "
        "worktree_id TEXT NOT NULL, "
        "scope_key TEXT NOT NULL, "
        "worker_class TEXT NOT NULL CHECK (worker_class IN ('paid', 'free-local')), "
        "access_mode TEXT NOT NULL CHECK (access_mode IN ('read-only', 'write')), "
        "reservation_id TEXT, "
        "lease_owner_id TEXT NOT NULL, "
        "lease_owner_pid INTEGER NOT NULL CHECK (lease_owner_pid > 0), "
        "lease_owner_start_token TEXT NOT NULL, "
        "lease_epoch INTEGER NOT NULL CHECK (lease_epoch > 0), "
        "created_at_utc TEXT NOT NULL, "
        "state TEXT NOT NULL CHECK (state IN ('active', 'completed')), "
        "completed_at_utc TEXT, "
        "CHECK ((worker_class = 'paid' AND reservation_id IS NOT NULL) "
        "OR (worker_class = 'free-local' AND reservation_id IS NULL)), "
        "CHECK ((state = 'active' AND completed_at_utc IS NULL) "
        "OR (state = 'completed' AND completed_at_utc IS NOT NULL))"
        ") STRICT"
    ),
    (
        "CREATE UNIQUE INDEX scheduler_active_paid_idx "
        "ON scheduler_assignments((1)) "
        "WHERE state = 'active' AND worker_class = 'paid'"
    ),
    (
        "CREATE UNIQUE INDEX scheduler_active_free_review_idx "
        "ON scheduler_assignments((1)) "
        "WHERE state = 'active' AND worker_class = 'free-local' "
        "AND access_mode = 'read-only'"
    ),
    (
        "CREATE UNIQUE INDEX scheduler_active_writer_scope_idx "
        "ON scheduler_assignments(scope_key COLLATE NOCASE) "
        "WHERE state = 'active' AND access_mode = 'write'"
    ),
    "CREATE INDEX scheduler_assignment_state_idx ON scheduler_assignments(state, id)",
    (
        "CREATE TRIGGER scheduler_assignment_identity_immutable "
        "BEFORE UPDATE OF request_id, request_digest, assignment_id, decision_id, "
        "job_id, issue_number, worktree_id, scope_key, worker_class, access_mode, "
        "reservation_id, lease_owner_id, lease_owner_pid, "
        "lease_owner_start_token, lease_epoch, created_at_utc "
        "ON scheduler_assignments BEGIN "
        "SELECT RAISE(ABORT, 'scheduler assignment identity is immutable'); END"
    ),
    (
        "CREATE TRIGGER scheduler_assignments_no_delete "
        "BEFORE DELETE ON scheduler_assignments BEGIN "
        "SELECT RAISE(ABORT, 'scheduler assignments are durable'); END"
    ),
)


def initialize_schema(connection: sqlite3.Connection, *, initialized_at: str) -> None:
    _ = connection.execute("BEGIN EXCLUSIVE")
    try:
        for statement in SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        _ = connection.execute(
            "INSERT INTO scheduler_metadata(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_ID,),
        )
        _ = connection.execute(
            "INSERT INTO scheduler_clock(id, last_observed_at_utc, last_epoch) VALUES (1, ?, 0)",
            (initialized_at,),
        )
        _ = connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _ = connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            _ = connection.execute("ROLLBACK")
        raise


def validate_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()
    if version != (SCHEMA_VERSION,):
        raise sqlite3.DatabaseError("scheduler schema version is unsupported")
    metadata = connection.execute(
        "SELECT key, value FROM scheduler_metadata ORDER BY key"
    ).fetchall()
    if metadata != [("schema_version", SCHEMA_ID)]:
        raise sqlite3.DatabaseError("scheduler schema metadata is invalid")
    if _schema_objects(connection) != _expected_schema_objects():
        raise sqlite3.DatabaseError("scheduler schema objects are invalid")
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise sqlite3.DatabaseError("scheduler integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise sqlite3.DatabaseError("scheduler foreign keys are invalid")
    if connection.execute("SELECT COUNT(*) FROM scheduler_assignments").fetchone()[0] > 10_000:
        raise sqlite3.DatabaseError("scheduler assignment limit exceeded")


def _schema_objects(connection: sqlite3.Connection) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        connection.execute(
            "SELECT type, name, sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )


@cache
def _expected_schema_objects() -> frozenset[tuple[str, str, str]]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        for statement in SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        return _schema_objects(connection)
    finally:
        connection.close()
