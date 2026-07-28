from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    LedgerEntryInput,
)


def _initialized_ledger(project_root: Path) -> FactoryBudgetLedger:
    ledger = FactoryBudgetLedger.open_project(project_root)
    ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(2026, 7, 1),
            cash_cap_microcents=20_000_000_000,
            emergency_reserve_microcents=2_000_000_000,
            currency="USD",
            policy_id="monthly-budget",
            policy_revision=1,
            reserve_idempotency_key="reserve-2026-07-v1",
        )
    )
    ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="provider-charge-1",
            kind="provider_charge",
            direction="debit",
            amount_microcents=1_000_000_000,
            occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
            currency="USD",
            source_id="openai",
        )
    )
    return ledger


def _run(project_root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_budget_ledger",
            command,
            "--repo",
            str(project_root),
            "--period",
            "2026-07-01",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_balance_summary_is_a_sanitized_admission_view(tmp_path: Path) -> None:
    ledger = _initialized_ledger(tmp_path)

    balance = ledger.balance_summary(date(2026, 7, 1))

    assert balance.period_start_utc == "2026-07-01T00:00:00Z"
    assert balance.currency == "USD"
    assert balance.paid_limit_microcents == 18_000_000_000
    assert balance.net_spent_microcents == 1_000_000_000
    assert balance.available_paid_microcents == 17_000_000_000
    assert balance.paid_dispatch_permitted is True
    assert not hasattr(balance, "source_id")
    assert not hasattr(balance, "idempotency_key")


def test_summary_cli_outputs_only_the_bounded_period_view(tmp_path: Path) -> None:
    ledger = _initialized_ledger(tmp_path)
    before = ledger.db_path.stat().st_mtime_ns

    result = _run(tmp_path, "summary")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "cash_cap_microcents": 20_000_000_000,
        "currency": "USD",
        "emergency_reserve_microcents": 2_000_000_000,
        "entry_count": 2,
        "net_spent_microcents": 1_000_000_000,
        "period_end_utc": "2026-08-01T00:00:00Z",
        "period_start_utc": "2026-07-01T00:00:00Z",
        "policy_id": "monthly-budget",
        "policy_revision": 1,
        "schema_version": "entroping.factory-budget-period-summary.v1",
        "available_paid_microcents": 17_000_000_000,
    }
    assert ledger.db_path.stat().st_mtime_ns == before


def test_balance_cli_outputs_only_admission_fields(tmp_path: Path) -> None:
    ledger = _initialized_ledger(tmp_path)

    result = _run(tmp_path, "balance")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "available_paid_microcents": 17_000_000_000,
        "currency": "USD",
        "net_spent_microcents": 1_000_000_000,
        "paid_dispatch_permitted": True,
        "paid_limit_microcents": 18_000_000_000,
        "period_start_utc": "2026-07-01T00:00:00Z",
        "schema_version": "entroping.factory-budget-balance.v1",
    }
    assert "openai" not in result.stdout
    assert "provider-charge-1" not in result.stdout
    assert ledger.db_path.stat().st_mtime_ns > 0


def test_readonly_cli_missing_state_fails_without_creating_it(tmp_path: Path) -> None:
    result = _run(tmp_path, "balance")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "factory_budget_ledger: missing: ledger database not found\n"
    assert not (tmp_path / ".entroping").exists()


def test_cli_rejects_non_month_boundary_without_echoing_path(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_budget_ledger",
            "summary",
            "--repo",
            str(tmp_path),
            "--period",
            "2026-07-02",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "period must use YYYY-MM-01" in result.stderr
    assert str(tmp_path) not in result.stderr
