from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .factory_budget_ledger_entries import record_entry
from .factory_budget_ledger_models import (
    BudgetBalanceSummary,
    BudgetPeriodConfig,
    BudgetPeriodSummary,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
    LedgerEntryReceipt,
    PeriodInitialization,
    canonical_utc_month,
)
from .factory_budget_ledger_periods import initialize_period, period_summary
from .factory_budget_ledger_reporting import balance_from_period
from .factory_budget_ledger_storage import (
    prepare_ledger,
    readonly_connection,
    writable_connection,
)


class FactoryBudgetLedger:
    project_root: Path
    db_path: Path

    def __init__(self, project_root: Path, db_path: Path) -> None:
        self.project_root = project_root
        self.db_path = db_path

    @classmethod
    def open_project(cls, project_root: Path) -> FactoryBudgetLedger:
        db_path = prepare_ledger(project_root)
        return cls(project_root, db_path)

    @classmethod
    def period_summary_readonly(
        cls,
        project_root: Path,
        starts_on: date,
    ) -> BudgetPeriodSummary:
        with readonly_connection(project_root) as connection:
            return period_summary(connection, starts_on)

    def initialize_period(self, config: BudgetPeriodConfig) -> PeriodInitialization:
        with writable_connection(self.project_root) as connection:
            return initialize_period(connection, config)

    def period_summary(self, starts_on: date) -> BudgetPeriodSummary:
        with readonly_connection(self.project_root) as connection:
            return period_summary(connection, starts_on)

    def period_summary_for(self, value: datetime) -> BudgetPeriodSummary:
        return self.period_summary(canonical_utc_month(value))

    def record_entry(self, entry: LedgerEntryInput) -> LedgerEntryReceipt:
        with writable_connection(self.project_root) as connection:
            return record_entry(connection, entry)

    @classmethod
    def balance_summary_readonly(
        cls,
        project_root: Path,
        starts_on: date,
    ) -> BudgetBalanceSummary:
        return balance_from_period(cls.period_summary_readonly(project_root, starts_on))

    def balance_summary(self, starts_on: date) -> BudgetBalanceSummary:
        return balance_from_period(self.period_summary(starts_on))


__all__ = [
    "BudgetBalanceSummary",
    "BudgetPeriodConfig",
    "BudgetPeriodSummary",
    "FactoryBudgetLedger",
    "FactoryBudgetLedgerError",
    "LedgerEntryInput",
    "LedgerEntryReceipt",
    "PeriodInitialization",
]


if __name__ == "__main__":
    from .factory_budget_ledger_cli import main

    raise SystemExit(main())
