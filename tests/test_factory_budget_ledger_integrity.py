from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_budget_ledger_integrity as ledger_integrity  # noqa: E402
from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
)


def _period(
    *,
    starts_on: date = date(2026, 7, 1),
    cash_cap_microcents: int = 20_000_000_000,
    emergency_reserve_microcents: int = 2_000_000_000,
    currency: str = "USD",
    policy_id: str = "monthly-budget",
    policy_revision: int = 1,
    reserve_idempotency_key: str = "reserve-2026-07-v1",
) -> BudgetPeriodConfig:
    return BudgetPeriodConfig(
        starts_on=starts_on,
        cash_cap_microcents=cash_cap_microcents,
        emergency_reserve_microcents=emergency_reserve_microcents,
        currency=currency,
        policy_id=policy_id,
        policy_revision=policy_revision,
        reserve_idempotency_key=reserve_idempotency_key,
    )


def test_global_ledger_entry_limit_rejects_additional_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    monkeypatch.setattr(ledger_integrity, "MAX_LEDGER_ENTRIES", 1)

    with pytest.raises(FactoryBudgetLedgerError, match="global ledger entry limit reached"):
        ledger.record_entry(
            LedgerEntryInput(
                idempotency_key="provider-charge-over-global-limit",
                kind="provider_charge",
                direction="debit",
                amount_microcents=1,
                occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                currency="USD",
                source_id="openai",
            )
        )


def test_global_period_limit_rejects_additional_periods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    monkeypatch.setattr(ledger_integrity, "MAX_BUDGET_PERIODS", 1)

    with pytest.raises(FactoryBudgetLedgerError, match="global budget period limit reached"):
        ledger.initialize_period(
            _period(starts_on=date(2026, 8, 1), reserve_idempotency_key="reserve-2026-08-v1")
        )


def test_open_rejects_future_schema_without_mutating_database(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute("PRAGMA user_version = 4")
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema version is unsupported"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_unexpected_trigger_without_executing_it(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute(
            "CREATE TRIGGER unexpected AFTER INSERT ON budget_periods BEGIN SELECT 1; END"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema objects are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_same_name_schema_drift_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute("DROP TRIGGER ledger_entries_no_update")
        connection.execute(
            "CREATE TRIGGER ledger_entries_no_update "
            "BEFORE UPDATE ON ledger_entries BEGIN SELECT 1; END"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema objects are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_unexpected_schema_metadata_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        _ = connection.execute(
            "INSERT INTO ledger_metadata(key, value) VALUES ('unexpected', 'value')"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema metadata is invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_partial_v3_schema_without_migrating_or_mutating(
    tmp_path: Path,
) -> None:
    state = tmp_path / ".entroping" / "factory-budget"
    state.mkdir(parents=True)
    os.chmod(state.parent, 0o700)
    os.chmod(state, 0o700)
    db_path = state / "ledger.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE ledger_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO ledger_metadata(key, value) VALUES (?, ?)",
            ("schema_version", "entroping.factory-budget-ledger.v3"),
        )
        connection.execute("PRAGMA user_version = 3")
    os.chmod(db_path, 0o600)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema objects are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_database_enforces_immutable_ledger_entries(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())

    with sqlite3.connect(ledger.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE ledger_entries SET amount_microcents = 1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM ledger_entries")

    assert ledger.period_summary(date(2026, 7, 1)).entry_count == 1


def test_database_prevents_reviewed_period_authority_tampering(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())

    with (
        sqlite3.connect(ledger.db_path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="authority is immutable"),
    ):
        connection.execute(
            "UPDATE budget_periods SET cash_cap_microcents = 200000000000, policy_revision = 99"
        )

    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.cash_cap_microcents == 20_000_000_000
    assert summary.policy_revision == 1


def test_open_rejects_cached_balance_drift_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    with sqlite3.connect(ledger.db_path) as connection:
        _ = connection.execute("UPDATE budget_periods SET net_spent_microcents = -1")
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="ledger balances are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_refund_that_references_reserve_allocation(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    with sqlite3.connect(ledger.db_path) as connection:
        period_id, reserve_id = connection.execute(
            """
            SELECT p.id, e.id
            FROM budget_periods AS p
            JOIN ledger_entries AS e ON e.period_id = p.id
            WHERE e.kind = 'emergency_reserve_allocation'
            """
        ).fetchone()
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'refund', 'credit', 1, ?, 'USD', ?, ?)
            """,
            (
                "a" * 64,
                period_id,
                "2026-07-15T00:00:00.000000Z",
                "monthly-budget",
                reserve_id,
            ),
        )
        _ = connection.execute(
            "UPDATE budget_periods SET net_spent_microcents = -1, entry_count = 2"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="ledger entries are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_noncanonical_entry_timestamp(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    with sqlite3.connect(ledger.db_path) as connection:
        period_id = connection.execute("SELECT id FROM budget_periods").fetchone()[0]
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'manual_adjustment', 'debit', 1, ?, 'USD', ?, NULL)
            """,
            ("b" * 64, period_id, "2026-07-99T99:99:99Z", "maintainer"),
        )
        _ = connection.execute(
            "UPDATE budget_periods SET net_spent_microcents = 1, entry_count = 2"
        )

    with pytest.raises(FactoryBudgetLedgerError, match="ledger timestamps are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)
