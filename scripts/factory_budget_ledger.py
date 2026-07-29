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
    migrate_ledger,
    prepare_ledger,
    readonly_connection,
    writable_connection,
)
from .factory_budget_reconciliation import (
    reconcile_manual_debit,
    reconcile_no_charge,
)
from .factory_budget_reservation_models import (
    CostReservationReceipt,
    CostReservationRequest,
    ManualReconciliationInput,
    NoChargeReconciliationInput,
    PriceTerm,
    PriceUnit,
    SettlementOutcome,
    SettlementReceipt,
    UncertaintyReason,
    UsageEnvelope,
)
from .factory_budget_reservations import (
    reservation_for_job,
    reserve_for_dispatch,
)
from .factory_budget_settlement import settle_reservation
from .factory_budget_uncertainty import mark_reservation_uncertain


class FactoryBudgetLedger:
    project_root: Path
    db_path: Path

    def __init__(self, project_root: Path, db_path: Path) -> None:
        self.project_root = project_root
        self.db_path = db_path

    @classmethod
    def open_project(cls, project_root: Path) -> FactoryBudgetLedger:
        db_path = prepare_ledger(project_root)
        return cls(db_path.parents[2], db_path)

    @classmethod
    def migrate_project(cls, project_root: Path) -> bool:
        return migrate_ledger(project_root)

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

    def reserve_for_dispatch(
        self,
        request: CostReservationRequest,
    ) -> CostReservationReceipt:
        with writable_connection(self.project_root) as connection:
            return reserve_for_dispatch(connection, request)

    def reservation_for_job(self, job_id: str) -> CostReservationReceipt | None:
        with readonly_connection(self.project_root) as connection:
            return reservation_for_job(connection, job_id)

    @classmethod
    def reservation_for_job_readonly(
        cls,
        project_root: Path,
        job_id: str,
    ) -> CostReservationReceipt | None:
        with readonly_connection(project_root) as connection:
            return reservation_for_job(connection, job_id)

    def settle_reservation(self, receipt: SettlementReceipt) -> SettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return settle_reservation(connection, receipt)

    def mark_reservation_uncertain(
        self,
        reservation_id: str,
        *,
        idempotency_key: str,
        reason: UncertaintyReason,
        occurred_at: datetime,
        evidence_digest: str,
    ) -> SettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return mark_reservation_uncertain(
                connection,
                reservation_id,
                idempotency_key=idempotency_key,
                reason=reason,
                occurred_at=occurred_at,
                evidence_digest=evidence_digest,
            )

    def reconcile_no_charge(
        self,
        command: NoChargeReconciliationInput,
    ) -> SettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return reconcile_no_charge(connection, command)

    def reconcile_manual_debit(
        self,
        command: ManualReconciliationInput,
    ) -> SettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return reconcile_manual_debit(connection, command)

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
    "CostReservationReceipt",
    "CostReservationRequest",
    "FactoryBudgetLedger",
    "FactoryBudgetLedgerError",
    "LedgerEntryInput",
    "LedgerEntryReceipt",
    "ManualReconciliationInput",
    "NoChargeReconciliationInput",
    "PeriodInitialization",
    "PriceTerm",
    "PriceUnit",
    "SettlementOutcome",
    "SettlementReceipt",
    "UsageEnvelope",
]


if __name__ == "__main__":
    from .factory_budget_ledger_cli import main

    raise SystemExit(main())
