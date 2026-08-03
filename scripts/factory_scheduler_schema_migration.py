from __future__ import annotations

import sqlite3
from functools import cache

from .factory_scheduler_schema import (
    SCHEMA_ID,
    SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
    _initialize_schema,
    _schema_objects,
    validate_schema,
)

PREVIOUS_SCHEMA_ID = "entroping.factory-scheduler-state.v1"
PREVIOUS_SCHEMA_VERSION = 1


def initialize_previous_schema(
    connection: sqlite3.Connection,
    *,
    initialized_at: str,
) -> None:
    _initialize_schema(
        connection,
        statements=_previous_schema_statements(),
        schema_id=PREVIOUS_SCHEMA_ID,
        schema_version=PREVIOUS_SCHEMA_VERSION,
        initialized_at=initialized_at,
    )


def migrate_schema(connection: sqlite3.Connection) -> bool:
    version = connection.execute("PRAGMA user_version").fetchone()
    if version == (SCHEMA_VERSION,):
        validate_schema(connection)
        return False
    _validate_previous_schema(connection)
    _ = connection.execute("BEGIN EXCLUSIVE")
    try:
        for name in (
            "scheduler_assignment_identity_immutable",
            "scheduler_assignments_no_delete",
        ):
            _ = connection.execute(f"DROP TRIGGER {name}")
        for name in (
            "scheduler_active_paid_idx",
            "scheduler_active_free_review_idx",
            "scheduler_active_writer_scope_idx",
            "scheduler_assignment_state_idx",
        ):
            _ = connection.execute(f"DROP INDEX {name}")
        _ = connection.execute(
            "ALTER TABLE scheduler_assignments RENAME TO scheduler_assignments_v1"
        )
        _ = connection.execute(SCHEMA_STATEMENTS[3])
        _ = connection.execute(
            "INSERT INTO scheduler_assignments("
            "id, request_id, request_digest, assignment_id, decision_id, job_id, "
            "issue_number, worktree_id, scope_key, worker_class, access_mode, "
            "reservation_id, authorization_id, lease_owner_id, lease_owner_pid, "
            "lease_owner_start_token, lease_epoch, created_at_utc, state, completed_at_utc) "
            "SELECT id, request_id, request_digest, assignment_id, decision_id, job_id, "
            "issue_number, worktree_id, scope_key, worker_class, access_mode, "
            "reservation_id, NULL, lease_owner_id, lease_owner_pid, "
            "lease_owner_start_token, lease_epoch, created_at_utc, state, completed_at_utc "
            "FROM scheduler_assignments_v1"
        )
        _ = connection.execute("DROP TABLE scheduler_assignments_v1")
        for statement in SCHEMA_STATEMENTS[4:]:
            _ = connection.execute(statement)
        _ = connection.execute(
            "UPDATE scheduler_metadata SET value = ? WHERE key = 'schema_version'",
            (SCHEMA_ID,),
        )
        _ = connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        validate_schema(connection)
        _ = connection.execute("COMMIT")
        return True
    except BaseException:
        if connection.in_transaction:
            _ = connection.execute("ROLLBACK")
        raise


def _validate_previous_schema(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA user_version").fetchone() != (PREVIOUS_SCHEMA_VERSION,):
        raise sqlite3.DatabaseError("scheduler schema version is unsupported")
    metadata = connection.execute(
        "SELECT key, value FROM scheduler_metadata ORDER BY key"
    ).fetchall()
    if metadata != [("schema_version", PREVIOUS_SCHEMA_ID)]:
        raise sqlite3.DatabaseError("scheduler schema metadata is invalid")
    if _schema_objects(connection) != _expected_previous_schema_objects():
        raise sqlite3.DatabaseError("scheduler schema objects are invalid")
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise sqlite3.DatabaseError("scheduler integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise sqlite3.DatabaseError("scheduler foreign keys are invalid")


@cache
def _expected_previous_schema_objects() -> frozenset[tuple[str, str, str]]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        for statement in _previous_schema_statements():
            _ = connection.execute(statement)
        return _schema_objects(connection)
    finally:
        connection.close()


@cache
def _previous_schema_statements() -> tuple[str, ...]:
    paid_check = (
        "CHECK ((worker_class = 'paid' AND "
        "(reservation_id IS NOT NULL OR authorization_id IS NOT NULL)) "
        "OR (worker_class = 'free-local' AND reservation_id IS NULL "
        "AND authorization_id IS NULL)), "
    )
    previous_check = (
        "CHECK ((worker_class = 'paid' AND reservation_id IS NOT NULL) "
        "OR (worker_class = 'free-local' AND reservation_id IS NULL)), "
    )
    return tuple(
        statement.replace("authorization_id TEXT, ", "")
        .replace(paid_check, previous_check)
        .replace("reservation_id, authorization_id, ", "reservation_id, ")
        for statement in SCHEMA_STATEMENTS
    )
