from __future__ import annotations

import sqlite3
from functools import cache

from .factory_budget_ledger_integrity import validate_ledger_integrity
from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_rows import integer_row, metadata_rows, schema_objects

LEDGER_SCHEMA_VERSION = 1
LEDGER_SCHEMA_ID = "entroping.factory-budget-ledger.v1"

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE ledger_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE budget_periods (
        id INTEGER PRIMARY KEY,
        period_start_utc TEXT NOT NULL UNIQUE,
        period_end_utc TEXT NOT NULL,
        currency TEXT NOT NULL CHECK (currency = 'USD'),
        cash_cap_microcents INTEGER NOT NULL CHECK (cash_cap_microcents > 0),
        emergency_reserve_microcents INTEGER NOT NULL
            CHECK (emergency_reserve_microcents > 0),
        policy_id TEXT NOT NULL,
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        net_spent_microcents INTEGER NOT NULL DEFAULT 0,
        entry_count INTEGER NOT NULL DEFAULT 0 CHECK (entry_count >= 0),
        CHECK (period_start_utc < period_end_utc),
        CHECK (emergency_reserve_microcents < cash_cap_microcents)
    ) STRICT
    """,
    """
    CREATE TRIGGER budget_periods_authority_no_update
    BEFORE UPDATE OF
        id,
        period_start_utc,
        period_end_utc,
        currency,
        cash_cap_microcents,
        emergency_reserve_microcents,
        policy_id,
        policy_revision
    ON budget_periods
    BEGIN
        SELECT RAISE(ABORT, 'budget period authority is immutable');
    END
    """,
    """
    CREATE TRIGGER budget_periods_no_delete
    BEFORE DELETE ON budget_periods
    BEGIN
        SELECT RAISE(ABORT, 'budget period authority is immutable');
    END
    """,
    """
    CREATE TABLE ledger_entries (
        id INTEGER PRIMARY KEY,
        idempotency_digest TEXT NOT NULL UNIQUE
            CHECK (length(idempotency_digest) = 64),
        period_id INTEGER NOT NULL REFERENCES budget_periods(id) ON DELETE RESTRICT,
        kind TEXT NOT NULL CHECK (kind IN (
            'fixed_subscription_charge',
            'provider_charge',
            'refund',
            'manual_adjustment',
            'emergency_reserve_allocation'
        )),
        direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit', 'allocation')),
        amount_microcents INTEGER NOT NULL CHECK (amount_microcents > 0),
        occurred_at_utc TEXT NOT NULL,
        currency TEXT NOT NULL CHECK (currency = 'USD'),
        source_id TEXT NOT NULL,
        reference_entry_id INTEGER REFERENCES ledger_entries(id) ON DELETE RESTRICT,
        CHECK (
            (kind IN ('fixed_subscription_charge', 'provider_charge')
                AND direction = 'debit' AND reference_entry_id IS NULL)
            OR (kind = 'refund' AND direction = 'credit'
                AND reference_entry_id IS NOT NULL)
            OR (kind = 'manual_adjustment' AND direction IN ('debit', 'credit')
                AND reference_entry_id IS NULL)
            OR (kind = 'emergency_reserve_allocation' AND direction = 'allocation'
                AND reference_entry_id IS NULL)
        )
    ) STRICT
    """,
    "CREATE INDEX ledger_entries_period_idx ON ledger_entries(period_id, id)",
    "CREATE INDEX ledger_entries_reference_idx ON ledger_entries(reference_entry_id)",
    """
    CREATE TRIGGER ledger_entries_no_update
    BEFORE UPDATE ON ledger_entries
    BEGIN
        SELECT RAISE(ABORT, 'ledger entries are immutable');
    END
    """,
    """
    CREATE TRIGGER ledger_entries_no_delete
    BEFORE DELETE ON ledger_entries
    BEGIN
        SELECT RAISE(ABORT, 'ledger entries are immutable');
    END
    """,
)


def initialize_schema(connection: sqlite3.Connection) -> None:
    _ = connection.execute("BEGIN EXCLUSIVE")
    committed = False
    try:
        for statement in SCHEMA_STATEMENTS:
            _ = connection.execute(statement)
        _ = connection.execute(
            "INSERT INTO ledger_metadata(key, value) VALUES ('schema_version', ?)",
            (LEDGER_SCHEMA_ID,),
        )
        _ = connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")
        _ = connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            _ = connection.execute("ROLLBACK")


def validate_schema(connection: sqlite3.Connection) -> None:
    try:
        version = integer_row(
            connection.execute("PRAGMA user_version"),
            detail="ledger schema version is invalid",
        )
        if version != LEDGER_SCHEMA_VERSION:
            raise FactoryBudgetLedgerError(
                "schema",
                "ledger schema version is unsupported",
            )
        metadata = metadata_rows(
            connection.execute("SELECT key, value FROM ledger_metadata ORDER BY key")
        )
        if metadata != [("schema_version", LEDGER_SCHEMA_ID)]:
            raise FactoryBudgetLedgerError("schema", "ledger schema metadata is invalid")
        if _schema_objects(connection) != _expected_schema_objects():
            raise FactoryBudgetLedgerError("schema", "ledger schema objects are invalid")
        if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            raise FactoryBudgetLedgerError("integrity", "ledger integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise FactoryBudgetLedgerError("integrity", "ledger foreign keys are invalid")
        validate_ledger_integrity(connection)
    except FactoryBudgetLedgerError:
        raise
    except sqlite3.DatabaseError as exc:
        raise FactoryBudgetLedgerError(
            "database",
            "ledger database is malformed",
        ) from exc


def _schema_objects(connection: sqlite3.Connection) -> frozenset[tuple[str, str, str]]:
    return schema_objects(
        connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ),
        maximum_rows=len(SCHEMA_STATEMENTS),
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
