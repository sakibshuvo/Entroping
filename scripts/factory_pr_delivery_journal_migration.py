"""Helpers for validating and migrating private PR delivery journal schemas."""

from __future__ import annotations

import sqlite3

from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_DDL,
    CLEANUP_TRIGGER_IMMUTABLE_IDENTITY,
    CLEANUP_TRIGGER_NO_DELETE,
    CLEANUP_TRIGGER_NO_REWRITE_PROOFS,
)
from scripts.factory_pr_delivery_journal_records import DeliveryJournalError

_SCHEMA_VERSION_V1 = 1
_SCHEMA_VERSION_V2 = 2
_SCHEMA_VERSION_V3 = 3

METADATA_DDL_V1 = (
    "CREATE TABLE delivery_metadata(id INTEGER PRIMARY KEY CHECK(id = 1), "
    "schema_version INTEGER NOT NULL CHECK(schema_version = 1)) STRICT"
)
LIFECYCLE_DDL_V1 = (
    "CREATE TABLE delivery_lifecycle("
    "request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, envelope_digest TEXT NOT NULL, "
    "issue_number INTEGER NOT NULL, assignment_id TEXT NOT NULL, worktree_id TEXT NOT NULL, "
    "lifecycle TEXT NOT NULL CHECK(lifecycle IN "
    "('prepared','commit-intent','committed','push-intent','pushed','uncertain')), "
    "reason TEXT NOT NULL CHECK(reason IN ('none','committed','pushed','interrupted')), "
    "accepted_local_head TEXT NOT NULL, committed_head TEXT, remote_head TEXT, "
    "commit_parent TEXT, commit_tree TEXT, accepted_diff_sha256 TEXT NOT NULL, "
    "accepted_manifest_sha256 TEXT NOT NULL, approved_path_sha256 TEXT NOT NULL, "
    "body_sha256 TEXT NOT NULL, phase_version INTEGER NOT NULL CHECK(phase_version > 0), "
    "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL) STRICT"
)

METADATA_DDL_V2 = (
    "CREATE TABLE delivery_metadata(id INTEGER PRIMARY KEY CHECK(id = 1), "
    "schema_version INTEGER NOT NULL CHECK(schema_version = 2)) STRICT"
)
LIFECYCLE_DDL_V2 = (
    "CREATE TABLE delivery_lifecycle("
    "request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, envelope_digest TEXT NOT NULL, "
    "issue_number INTEGER NOT NULL, assignment_id TEXT NOT NULL, worktree_id TEXT NOT NULL, "
    "lifecycle TEXT NOT NULL CHECK(lifecycle IN "
    "('prepared','commit-intent','committed','push-intent','merge-intent','pushed',"
    "'merged','uncertain')), "
    "reason TEXT NOT NULL CHECK(reason IN "
    "('none','committed','pushed','interrupted','merge-intent','cleanup-pending')), "
    "accepted_local_head TEXT NOT NULL, committed_head TEXT, remote_head TEXT, "
    "commit_parent TEXT, commit_tree TEXT, accepted_diff_sha256 TEXT NOT NULL, "
    "accepted_manifest_sha256 TEXT NOT NULL, approved_path_sha256 TEXT NOT NULL, "
    "body_sha256 TEXT NOT NULL, phase_version INTEGER NOT NULL CHECK(phase_version > 0), "
    "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, "
    "merge_pr_number INTEGER, merge_head TEXT, merge_ci_digest TEXT, "
    "merge_intent_at_utc TEXT, terminal_receipt_json TEXT, "
    "terminal_receipt_sha256 TEXT, terminal_at_utc TEXT) STRICT"
)

METADATA_DDL_V3 = (
    "CREATE TABLE delivery_metadata(id INTEGER PRIMARY KEY CHECK(id = 1), "
    "schema_version INTEGER NOT NULL CHECK(schema_version = 3)) STRICT"
)
LIFECYCLE_DDL_V3 = LIFECYCLE_DDL_V2

METADATA_DDL = METADATA_DDL_V3
LIFECYCLE_DDL = LIFECYCLE_DDL_V3


def validate_journal_schema(connection: sqlite3.Connection) -> None:
    while True:
        objects = _schema_objects(connection)

        if objects == _V3_OBJECTS:
            if connection.execute(
                "SELECT schema_version FROM delivery_metadata WHERE id = 1"
            ).fetchone() != (_SCHEMA_VERSION_V3,):
                raise DeliveryJournalError("journal-invalid")
            _validate_foreign_keys(connection)
            return

        if objects == _V2_OBJECTS:
            if connection.execute(
                "SELECT schema_version FROM delivery_metadata WHERE id = 1"
            ).fetchone() != (_SCHEMA_VERSION_V2,):
                raise DeliveryJournalError("journal-invalid")
            migrate_v2_to_v3(connection)
            continue

        if objects == _V1_OBJECTS:
            if connection.execute(
                "SELECT schema_version FROM delivery_metadata WHERE id = 1"
            ).fetchone() != (_SCHEMA_VERSION_V1,):
                raise DeliveryJournalError("journal-invalid")
            migrate_v1_to_v3(connection)
            continue

        raise DeliveryJournalError("journal-invalid")


def _canonical_schema(sql: str | None) -> str:
    if sql is None:
        return ""
    normalized = (
        sql.replace('"delivery_lifecycle"', "delivery_lifecycle")
        .replace('"delivery_metadata"', "delivery_metadata")
        .replace('"delivery_cleanup"', "delivery_cleanup")
    )
    return " ".join(normalized.split()).rstrip().rstrip(";")


def _schema_objects(connection: sqlite3.Connection) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (row[0], row[1], row[2], _canonical_schema(row[3]))
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    )


def _validate_foreign_keys(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise DeliveryJournalError("journal-invalid")


_V1_OBJECTS = (
    (
        "table",
        "delivery_lifecycle",
        "delivery_lifecycle",
        _canonical_schema(LIFECYCLE_DDL_V1),
    ),
    (
        "table",
        "delivery_metadata",
        "delivery_metadata",
        _canonical_schema(METADATA_DDL_V1),
    ),
)

_V2_OBJECTS = (
    (
        "table",
        "delivery_lifecycle",
        "delivery_lifecycle",
        _canonical_schema(LIFECYCLE_DDL_V2),
    ),
    (
        "table",
        "delivery_metadata",
        "delivery_metadata",
        _canonical_schema(METADATA_DDL_V2),
    ),
)

_V3_OBJECTS = (
    ("table", "delivery_cleanup", "delivery_cleanup", _canonical_schema(CLEANUP_DDL)),
    (
        "table",
        "delivery_lifecycle",
        "delivery_lifecycle",
        _canonical_schema(LIFECYCLE_DDL_V3),
    ),
    ("table", "delivery_metadata", "delivery_metadata", _canonical_schema(METADATA_DDL_V3)),
    (
        "trigger",
        "trg_delivery_cleanup_immutable_identity",
        "delivery_cleanup",
        _canonical_schema(CLEANUP_TRIGGER_IMMUTABLE_IDENTITY),
    ),
    (
        "trigger",
        "trg_delivery_cleanup_no_delete",
        "delivery_cleanup",
        _canonical_schema(CLEANUP_TRIGGER_NO_DELETE),
    ),
    (
        "trigger",
        "trg_delivery_cleanup_no_rewrite_proofs",
        "delivery_cleanup",
        _canonical_schema(CLEANUP_TRIGGER_NO_REWRITE_PROOFS),
    ),
)


def migrate_v1_to_v3(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            LIFECYCLE_DDL_V2.replace(
                "delivery_lifecycle(",
                "delivery_lifecycle_v2(",
            )
        )
        connection.execute(
            "INSERT INTO delivery_lifecycle_v2("
            "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
            "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,commit_tree,"
            "accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,body_sha256,phase_version,"
            "created_at_utc,updated_at_utc,merge_pr_number,merge_head,merge_ci_digest,merge_intent_at_utc,"
            "terminal_receipt_json,terminal_receipt_sha256,terminal_at_utc) "
            "SELECT "
            "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
            "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,commit_tree,"
            "accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,body_sha256,phase_version,"
            "created_at_utc,updated_at_utc,NULL,NULL,NULL,NULL,NULL,NULL,NULL "
            "FROM delivery_lifecycle"
        )
        connection.execute("DROP TABLE delivery_lifecycle")
        connection.execute("DROP TABLE delivery_metadata")
        connection.execute(METADATA_DDL_V2)
        connection.execute(
            "INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 2)"
        )
        connection.execute(
            "ALTER TABLE delivery_lifecycle_v2 RENAME TO delivery_lifecycle"
        )
        _migrate_v2_schema_to_v3(connection)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise DeliveryJournalError("journal-invalid") from None


def migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        _migrate_v2_schema_to_v3(connection)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise DeliveryJournalError("journal-invalid") from None


def _migrate_v2_schema_to_v3(connection: sqlite3.Connection) -> None:
    connection.execute(CLEANUP_DDL)
    connection.execute(CLEANUP_TRIGGER_IMMUTABLE_IDENTITY)
    connection.execute(CLEANUP_TRIGGER_NO_REWRITE_PROOFS)
    connection.execute(CLEANUP_TRIGGER_NO_DELETE)
    connection.execute(
        "CREATE TABLE delivery_metadata_v3("
        "id INTEGER PRIMARY KEY CHECK(id = 1), "
        "schema_version INTEGER NOT NULL CHECK(schema_version = 3)) STRICT"
    )
    connection.execute(
        "INSERT INTO delivery_metadata_v3(id, schema_version) VALUES (1, 3)"
    )
    connection.execute("DROP TABLE delivery_metadata")
    connection.execute("ALTER TABLE delivery_metadata_v3 RENAME TO delivery_metadata")
