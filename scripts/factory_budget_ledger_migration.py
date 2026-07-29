from __future__ import annotations

import sqlite3
from functools import cache

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_rows import integer_row, metadata_rows, schema_objects
from .factory_budget_ledger_schema import (
    BASE_SCHEMA_STATEMENTS,
    LEDGER_SCHEMA_ID,
    LEDGER_SCHEMA_VERSION,
    LEGACY_LEDGER_SCHEMA_ID,
    LEGACY_LEDGER_SCHEMA_VERSION,
    validate_schema,
)
from .factory_budget_reservation_schema import RESERVATION_SCHEMA_STATEMENTS


def initialize_legacy_schema(connection: sqlite3.Connection) -> None:
    _ = connection.execute("BEGIN EXCLUSIVE")
    committed = False
    try:
        for statement in BASE_SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        _ = connection.execute(
            "INSERT INTO ledger_metadata(key, value) VALUES ('schema_version', ?)",
            (LEGACY_LEDGER_SCHEMA_ID,),
        )
        _ = connection.execute(f"PRAGMA user_version = {LEGACY_LEDGER_SCHEMA_VERSION}")
        _ = connection.execute("COMMIT")
        committed = True
    finally:
        if not committed and connection.in_transaction:
            _ = connection.execute("ROLLBACK")


def migrate_schema_v1_to_v2(connection: sqlite3.Connection) -> bool:
    version = integer_row(
        connection.execute("PRAGMA user_version"),
        detail="ledger schema version is invalid",
    )
    if version == LEDGER_SCHEMA_VERSION:
        validate_schema(connection)
        return False
    _validate_legacy_schema(connection)
    _ = connection.execute("BEGIN EXCLUSIVE")
    committed = False
    try:
        for statement in RESERVATION_SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        _ = connection.execute(
            "UPDATE ledger_metadata SET value = ? WHERE key = 'schema_version'",
            (LEDGER_SCHEMA_ID,),
        )
        _ = connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")
        validate_schema(connection)
        _ = connection.execute("COMMIT")
        committed = True
        return True
    finally:
        if not committed and connection.in_transaction:
            _ = connection.execute("ROLLBACK")


def _validate_legacy_schema(connection: sqlite3.Connection) -> None:
    version = integer_row(
        connection.execute("PRAGMA user_version"),
        detail="ledger schema version is invalid",
    )
    if version != LEGACY_LEDGER_SCHEMA_VERSION:
        raise FactoryBudgetLedgerError("schema", "ledger schema version is unsupported")
    metadata = metadata_rows(connection.execute("SELECT key, value FROM ledger_metadata"))
    if metadata != [("schema_version", LEGACY_LEDGER_SCHEMA_ID)]:
        raise FactoryBudgetLedgerError("schema", "ledger schema metadata is invalid")
    if _schema_objects(connection) != _expected_legacy_schema_objects():
        raise FactoryBudgetLedgerError("schema", "ledger schema objects are invalid")
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise FactoryBudgetLedgerError("integrity", "ledger integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise FactoryBudgetLedgerError("integrity", "ledger foreign keys are invalid")


def _schema_objects(connection: sqlite3.Connection) -> frozenset[tuple[str, str, str]]:
    return schema_objects(
        connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            """
        ),
        maximum_rows=len(BASE_SCHEMA_STATEMENTS),
    )


@cache
def _expected_legacy_schema_objects() -> frozenset[tuple[str, str, str]]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        for statement in BASE_SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        return _schema_objects(connection)
    finally:
        connection.close()
