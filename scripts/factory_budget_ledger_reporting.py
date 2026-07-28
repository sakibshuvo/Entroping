from __future__ import annotations

from .factory_budget_ledger_models import BudgetBalanceSummary, BudgetPeriodSummary


def balance_from_period(summary: BudgetPeriodSummary) -> BudgetBalanceSummary:
    return BudgetBalanceSummary(
        period_start_utc=summary.period_start_utc,
        currency=summary.currency,
        paid_limit_microcents=(summary.cash_cap_microcents - summary.emergency_reserve_microcents),
        net_spent_microcents=summary.net_spent_microcents,
        available_paid_microcents=summary.available_paid_microcents,
        paid_dispatch_permitted=summary.available_paid_microcents > 0,
    )
