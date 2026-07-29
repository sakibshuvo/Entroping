from __future__ import annotations

import os
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
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


def test_open_project_creates_a_separate_versioned_factory_ledger(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)

    assert ledger.db_path == (tmp_path / ".entroping" / "factory-budget" / "ledger.sqlite3")
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute(
            "SELECT value FROM ledger_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("entroping.factory-budget-ledger.v1",)


def test_initialize_period_records_the_non_spendable_reserve_once(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)

    first = ledger.initialize_period(_period())
    replay = ledger.initialize_period(_period())

    assert first.created is True
    assert replay.created is False
    assert first.summary.period_start_utc == "2026-07-01T00:00:00Z"
    assert first.summary.period_end_utc == "2026-08-01T00:00:00Z"
    assert first.summary.cash_cap_microcents == 20_000_000_000
    assert first.summary.emergency_reserve_microcents == 2_000_000_000
    assert first.summary.net_spent_microcents == 0
    assert first.summary.available_paid_microcents == 18_000_000_000
    assert first.summary.entry_count == 1
    assert replay.summary == first.summary


def test_december_period_ends_at_the_next_utc_year_boundary(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)

    initialized = ledger.initialize_period(
        _period(
            starts_on=date(2026, 12, 1),
            reserve_idempotency_key="reserve-2026-12-v1",
        )
    )

    assert initialized.summary.period_end_utc == "2027-01-01T00:00:00Z"


def test_initialize_period_rejects_conflicting_idempotent_payload(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())

    conflicts = (
        _period(emergency_reserve_microcents=1_000_000_000),
        _period(cash_cap_microcents=19_000_000_000),
        _period(policy_revision=2),
    )
    for conflict in conflicts:
        with pytest.raises(
            FactoryBudgetLedgerError,
            match="idempotency key conflicts with an existing ledger entry",
        ):
            ledger.initialize_period(conflict)

    assert ledger.period_summary(date(2026, 7, 1)).entry_count == 1


def test_open_rejects_corrupt_state_without_replacing_it(tmp_path: Path) -> None:
    state = tmp_path / ".entroping" / "factory-budget"
    state.mkdir(parents=True)
    os.chmod(state.parent, 0o700)
    os.chmod(state, 0o700)
    db_path = state / "ledger.sqlite3"
    original = b"not a sqlite database\n"
    db_path.write_bytes(original)
    os.chmod(db_path, 0o600)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger database is malformed"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert db_path.read_bytes() == original


def test_period_config_rejects_non_utc_month_and_non_usd_currency() -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="period must start on day 1"):
        _period(starts_on=date(2026, 7, 2))

    with pytest.raises(FactoryBudgetLedgerError, match="currency must be USD"):
        _period(currency="CAD")


def test_period_config_rejects_datetime_and_unrepresentable_end_boundary() -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="period start must be a date"):
        _period(starts_on=datetime(2026, 7, 1, tzinfo=UTC))

    with pytest.raises(FactoryBudgetLedgerError, match="period end is not representable"):
        _period(starts_on=date(9999, 12, 1))


def test_period_config_rejects_bool_and_signed_64_bit_overflow() -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="cash cap must be an integer"):
        _period(cash_cap_microcents=True)

    with pytest.raises(FactoryBudgetLedgerError, match="cash cap exceeds"):
        _period(cash_cap_microcents=2**63)


def test_period_config_rejects_zero_emergency_reserve() -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="emergency reserve must be positive"):
        _period(emergency_reserve_microcents=0)


def test_open_project_retains_an_absolute_root_across_cwd_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    ledger = FactoryBudgetLedger.open_project(Path("project"))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    initialized = ledger.initialize_period(_period())

    assert ledger.project_root == project
    assert ledger.db_path == project / ".entroping" / "factory-budget" / "ledger.sqlite3"
    assert initialized.created is True


def test_period_summary_is_read_only_and_requires_existing_state(tmp_path: Path) -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="ledger database not found"):
        FactoryBudgetLedger.period_summary_readonly(tmp_path, date(2026, 7, 1))

    assert not (tmp_path / ".entroping").exists()


def test_period_summary_normalizes_an_offset_timestamp_to_utc_month(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())

    summary = ledger.period_summary_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC).astimezone())

    assert summary.period_start_utc == "2026-07-01T00:00:00Z"
