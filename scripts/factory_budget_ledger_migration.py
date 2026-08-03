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
    PREVIOUS_LEDGER_SCHEMA_ID,
    PREVIOUS_LEDGER_SCHEMA_VERSION,
    validate_schema,
)
from .factory_budget_reservation_schema import RESERVATION_SCHEMA_STATEMENTS
from .factory_quota_schema import QUOTA_SCHEMA_STATEMENTS


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


def migrate_schema_to_v3(connection: sqlite3.Connection) -> bool:
    version = integer_row(
        connection.execute("PRAGMA user_version"),
        detail="ledger schema version is invalid",
    )
    if version == LEDGER_SCHEMA_VERSION:
        validate_schema(connection)
        return False
    if version == LEGACY_LEDGER_SCHEMA_VERSION:
        _validate_legacy_schema(connection)
        _migrate_to_v3(
            connection,
            RESERVATION_SCHEMA_STATEMENTS + QUOTA_SCHEMA_STATEMENTS,
        )
    else:
        _validate_v2_schema(connection)
        _migrate_to_v3(connection, QUOTA_SCHEMA_STATEMENTS)
    return True


def _migrate_to_v3(
    connection: sqlite3.Connection,
    statements: tuple[str, ...],
) -> None:
    _ = connection.execute("BEGIN EXCLUSIVE")
    committed = False
    try:
        for statement in statements:
            _ = connection.execute(statement)
        _ = connection.execute(
            "UPDATE ledger_metadata SET value = ? WHERE key = 'schema_version'",
            (LEDGER_SCHEMA_ID,),
        )
        _ = connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")
        validate_schema(connection)
        _ = connection.execute("COMMIT")
        committed = True
    finally:
        if not committed and connection.in_transaction:
            _ = connection.execute("ROLLBACK")


def _validate_v2_schema(connection: sqlite3.Connection) -> None:
    version = integer_row(
        connection.execute("PRAGMA user_version"),
        detail="ledger schema version is invalid",
    )
    if version != PREVIOUS_LEDGER_SCHEMA_VERSION:
        raise FactoryBudgetLedgerError("schema", "ledger schema version is unsupported")
    metadata = metadata_rows(connection.execute("SELECT key, value FROM ledger_metadata"))
    if metadata != [("schema_version", PREVIOUS_LEDGER_SCHEMA_ID)]:
        raise FactoryBudgetLedgerError("schema", "ledger schema metadata is invalid")
    expected = _expected_v2_schema_objects()
    statement_count = len(BASE_SCHEMA_STATEMENTS + RESERVATION_SCHEMA_STATEMENTS)
    if _schema_objects(connection, statement_count) != expected:
        raise FactoryBudgetLedgerError("schema", "ledger schema objects are invalid")
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise FactoryBudgetLedgerError("integrity", "ledger integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise FactoryBudgetLedgerError("integrity", "ledger foreign keys are invalid")


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


def _schema_objects(
    connection: sqlite3.Connection,
    maximum_rows: int = len(BASE_SCHEMA_STATEMENTS),
) -> frozenset[tuple[str, str, str]]:
    return schema_objects(
        connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            """
        ),
        maximum_rows=maximum_rows,
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


@cache
def _expected_v2_schema_objects() -> frozenset[tuple[str, str, str]]:
    statements = BASE_SCHEMA_STATEMENTS + RESERVATION_SCHEMA_STATEMENTS
    connection = sqlite3.connect(":memory:", autocommit=True)
    try:
        for statement in statements:
            _ = connection.execute(statement)
        return _schema_objects(connection, len(statements))
    finally:
        connection.close()
