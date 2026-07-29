from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
)
from scripts.factory_budget_ledger_migration import initialize_legacy_schema  # noqa: E402
from scripts.factory_budget_ledger_models import idempotency_digest  # noqa: E402
from scripts.factory_budget_ledger_rows import integer_row  # noqa: E402


def _legacy_ledger(tmp_path: Path, *, corrupt_balance: bool = False) -> Path:
    state = tmp_path / ".entroping" / "factory-budget"
    state.mkdir(parents=True)
    os.chmod(state.parent, 0o700)
    os.chmod(state, 0o700)
    db_path = state / "ledger.sqlite3"
    with sqlite3.connect(db_path, autocommit=True) as connection:
        initialize_legacy_schema(connection)
        _ = connection.execute(
            """
            INSERT INTO budget_periods(
                period_start_utc, period_end_utc, currency,
                cash_cap_microcents, emergency_reserve_microcents,
                policy_id, policy_revision, net_spent_microcents, entry_count
            ) VALUES ('2026-07-01T00:00:00Z', '2026-08-01T00:00:00Z',
                'USD', 100, 20, 'monthly-budget', 1, ?, 2)
            """,
            (11 if corrupt_balance else 10,),
        )
        period_id = integer_row(
            connection.execute("SELECT id FROM budget_periods"),
            detail="legacy test period id is invalid",
        )
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'emergency_reserve_allocation', 'allocation',
                20, '2026-07-01T00:00:00Z', 'USD', 'monthly-budget', NULL)
            """,
            (idempotency_digest("reserve-2026-07-v1"), period_id),
        )
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'provider_charge', 'debit',
                10, '2026-07-15T12:00:00.000000Z', 'USD', 'deepseek', NULL)
            """,
            (idempotency_digest("legacy-charge-1"), period_id),
        )
    os.chmod(db_path, 0o600)
    return db_path


def test_explicit_v1_migration_preserves_entries_and_is_idempotent(tmp_path: Path) -> None:
    db_path = _legacy_ledger(tmp_path)

    assert FactoryBudgetLedger.migrate_project(tmp_path) is True
    assert FactoryBudgetLedger.migrate_project(tmp_path) is False

    ledger = FactoryBudgetLedger.open_project(tmp_path)
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.net_spent_microcents == 10
    assert summary.active_reserved_microcents == 0
    assert summary.available_paid_microcents == 70
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM cost_reservations"
        ).fetchone() == (0,)


def test_failed_v1_migration_rolls_back_schema_and_metadata(tmp_path: Path) -> None:
    db_path = _legacy_ledger(tmp_path, corrupt_balance=True)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger balances are invalid"):
        _ = FactoryBudgetLedger.migrate_project(tmp_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT value FROM ledger_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("entroping.factory-budget-ledger.v1",)
        assert connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name = 'cost_reservations'"
        ).fetchone() is None


def test_migration_cli_reports_sanitized_result(tmp_path: Path) -> None:
    _ = _legacy_ledger(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_budget_ledger",
            "migrate",
            "--repo",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "ledger_schema_version": "entroping.factory-budget-ledger.v2",
        "migrated": True,
        "schema_version": "entroping.factory-budget-migration.v1",
    }
