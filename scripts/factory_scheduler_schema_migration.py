from __future__ import annotations

import sqlite3
from datetime import timedelta
from functools import cache

from .factory_scheduler_receipts import iso_utc, parse_utc
from .factory_scheduler_schema import (
    SCHEMA_ID,
    SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
    V2_SCHEMA_STATEMENT_COUNT,
    _initialize_schema,
    _schema_objects,
    validate_schema,
)
from .factory_scheduler_validation import MAX_LEASE_SECONDS

PREVIOUS_SCHEMA_ID = "entroping.factory-scheduler-state.v2"
PREVIOUS_SCHEMA_VERSION = 2
LEGACY_SCHEMA_ID = "entroping.factory-scheduler-state.v1"
LEGACY_SCHEMA_VERSION = 1


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


def initialize_legacy_schema(
    connection: sqlite3.Connection,
    *,
    initialized_at: str,
) -> None:
    _initialize_schema(
        connection,
        statements=_legacy_schema_statements(),
        schema_id=LEGACY_SCHEMA_ID,
        schema_version=LEGACY_SCHEMA_VERSION,
        initialized_at=initialized_at,
    )


def migrate_schema(connection: sqlite3.Connection) -> bool:
    version = connection.execute("PRAGMA user_version").fetchone()
    if version == (SCHEMA_VERSION,):
        validate_schema(connection)
        return False
    if version == (PREVIOUS_SCHEMA_VERSION,):
        _validate_schema_version(
            connection,
            schema_id=PREVIOUS_SCHEMA_ID,
            expected_objects=_expected_previous_schema_objects(),
        )
    elif version == (LEGACY_SCHEMA_VERSION,):
        _validate_schema_version(
            connection,
            schema_id=LEGACY_SCHEMA_ID,
            expected_objects=_expected_legacy_schema_objects(),
        )
    else:
        raise sqlite3.DatabaseError("scheduler schema version is unsupported")

    _ = connection.execute("BEGIN EXCLUSIVE")
    try:
        if version == (LEGACY_SCHEMA_VERSION,):
            _upgrade_legacy_assignments(connection)
        for statement in SCHEMA_STATEMENTS[V2_SCHEMA_STATEMENT_COUNT:]:
            _ = connection.execute(statement)
        _initialize_execution_rows(connection)
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


def _upgrade_legacy_assignments(connection: sqlite3.Connection) -> None:
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
    _ = connection.execute("ALTER TABLE scheduler_assignments RENAME TO scheduler_assignments_v1")
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
    for statement in SCHEMA_STATEMENTS[4:V2_SCHEMA_STATEMENT_COUNT]:
        _ = connection.execute(statement)


def _initialize_execution_rows(connection: sqlite3.Connection) -> None:
    assignments = connection.execute(
        "SELECT assignment_id, lease_owner_id, lease_owner_pid, "
        "lease_owner_start_token, lease_epoch, created_at_utc, state, "
        "completed_at_utc FROM scheduler_assignments ORDER BY id"
    ).fetchall()
    lease = connection.execute(
        "SELECT owner_id, owner_pid, owner_start_token, epoch, expires_at_utc "
        "FROM scheduler_lease WHERE id = 1"
    ).fetchone()
    rows: list[tuple[object, ...]] = []
    for assignment in assignments:
        created_at = parse_utc(str(assignment[5]))
        matching_lease = lease is not None and lease[:4] == assignment[1:5]
        expiration = (
            parse_utc(str(lease[4]))
            if matching_lease
            else created_at + timedelta(seconds=MAX_LEASE_SECONDS)
        )
        terminal = assignment[6] == "completed"
        rows.append(
            (
                assignment[0],
                "completed" if terminal else "uncertain",
                assignment[1],
                assignment[2],
                assignment[3],
                assignment[4],
                iso_utc(expiration),
                assignment[7] or assignment[5],
                assignment[5],
                None if terminal else "legacy-active-assignment",
                "completed" if terminal else None,
            )
        )
    connection.executemany(
        "INSERT INTO scheduler_execution_state("
        "assignment_id, phase, phase_version, attempt_count, lease_owner_id, "
        "lease_owner_pid, lease_owner_start_token, lease_epoch, lease_expires_at_utc, "
        "phase_changed_at_utc, worker_heartbeat_at_utc, retry_not_before_utc, "
        "failure_code, terminal_outcome, "
        "evidence_digest) "
        "VALUES (?, ?, 1, 1, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)",
        rows,
    )


def _validate_schema_version(
    connection: sqlite3.Connection,
    *,
    schema_id: str,
    expected_objects: frozenset[tuple[str, str, str]],
) -> None:
    metadata = connection.execute(
        "SELECT key, value FROM scheduler_metadata ORDER BY key"
    ).fetchall()
    if metadata != [("schema_version", schema_id)]:
        raise sqlite3.DatabaseError("scheduler schema metadata is invalid")
    if _schema_objects(connection) != expected_objects:
        raise sqlite3.DatabaseError("scheduler schema objects are invalid")
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise sqlite3.DatabaseError("scheduler integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise sqlite3.DatabaseError("scheduler foreign keys are invalid")


@cache
def _expected_previous_schema_objects() -> frozenset[tuple[str, str, str]]:
    return _expected_objects(_previous_schema_statements())


@cache
def _expected_legacy_schema_objects() -> frozenset[tuple[str, str, str]]:
    return _expected_objects(_legacy_schema_statements())


def _expected_objects(
    statements: tuple[str, ...],
) -> frozenset[tuple[str, str, str]]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        for statement in statements:
            _ = connection.execute(statement)
        return _schema_objects(connection)
    finally:
        connection.close()


@cache
def _previous_schema_statements() -> tuple[str, ...]:
    return SCHEMA_STATEMENTS[:V2_SCHEMA_STATEMENT_COUNT]


@cache
def _legacy_schema_statements() -> tuple[str, ...]:
    paid_check = (
        "CHECK ((worker_class = 'paid' AND "
        "(reservation_id IS NOT NULL OR authorization_id IS NOT NULL)) "
        "OR (worker_class = 'free-local' AND reservation_id IS NULL "
        "AND authorization_id IS NULL)), "
    )
    legacy_check = (
        "CHECK ((worker_class = 'paid' AND reservation_id IS NOT NULL) "
        "OR (worker_class = 'free-local' AND reservation_id IS NULL)), "
    )
    return tuple(
        statement.replace("authorization_id TEXT, ", "")
        .replace(paid_check, legacy_check)
        .replace("reservation_id, authorization_id, ", "reservation_id, ")
        for statement in _previous_schema_statements()
    )
