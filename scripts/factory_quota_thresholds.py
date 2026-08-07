from __future__ import annotations

import sqlite3
from datetime import datetime

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_utc_month,
    month_boundary,
)
from .factory_quota_models import DispatchAuthorizationRequest


def require_cash_threshold(
    connection: sqlite3.Connection,
    request: DispatchAuthorizationRequest,
) -> None:
    row = connection.execute(
        "SELECT cash_cap_microcents, net_spent_microcents, "
        "active_reserved_microcents FROM budget_periods "
        "WHERE period_start_utc = ?",
        (month_boundary(canonical_utc_month(request.decision_at)),),
    ).fetchone()
    if row is None:
        raise FactoryBudgetLedgerError("period", "budget period not found")
    new_hold = (
        0
        if request.cash_reservation is None
        else request.cash_reservation.worst_case_microcents
    )
    _enforce_thresholds(
        cash_cap_microcents=int(row[0]),
        prospective_microcents=max(int(row[1]), 0) + int(row[2]) + new_hold,
        work_purpose=request.work_purpose,
        billing_mode=request.billing_mode,
    )


def require_launch_cash_threshold(
    connection: sqlite3.Connection,
    job_id: str,
    *,
    as_of: str,
) -> None:
    authority = connection.execute(
        "SELECT billing_mode, work_purpose, cash_reservation_id "
        "FROM dispatch_authorizations WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if authority is None:
        raise FactoryBudgetLedgerError("authorization", "dispatch authorization not found")
    if authority[2] is None:
        period_start = month_boundary(
            canonical_utc_month(datetime.fromisoformat(as_of.replace("Z", "+00:00")))
        )
        period = connection.execute(
            "SELECT cash_cap_microcents, net_spent_microcents, "
            "active_reserved_microcents FROM budget_periods WHERE period_start_utc = ?",
            (period_start,),
        ).fetchone()
    else:
        period = connection.execute(
            "SELECT p.cash_cap_microcents, p.net_spent_microcents, "
            "p.active_reserved_microcents FROM budget_periods AS p "
            "JOIN cost_reservations AS r ON r.period_id = p.id WHERE r.id = ?",
            (authority[2],),
        ).fetchone()
    if period is None:
        raise FactoryBudgetLedgerError("period", "budget period not found")
    _enforce_thresholds(
        cash_cap_microcents=int(period[0]),
        prospective_microcents=max(int(period[1]), 0) + int(period[2]),
        work_purpose=str(authority[1]),
        billing_mode=str(authority[0]),
    )


def _enforce_thresholds(
    *,
    cash_cap_microcents: int,
    prospective_microcents: int,
    work_purpose: str,
    billing_mode: str,
) -> None:
    if prospective_microcents * 10_000 >= cash_cap_microcents * 10_000:
        raise FactoryBudgetLedgerError(
            "cash_cap_100",
            "remote paid dispatch stopped at 100 percent",
        )
    if work_purpose == "experiment" and (
        prospective_microcents * 10_000 >= cash_cap_microcents * 8_000
    ):
        raise FactoryBudgetLedgerError(
            "experiment_threshold_80",
            "experiments stopped at 80 percent",
        )
    if billing_mode == "metered" and (
        prospective_microcents * 10_000 >= cash_cap_microcents * 9_000
    ):
        raise FactoryBudgetLedgerError(
            "metered_threshold_90",
            "dispatch restricted to included quota at 90 percent",
        )
