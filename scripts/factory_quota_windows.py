from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from .factory_budget_ledger_models import (
    SIGNED_64_BIT_MAX,
    FactoryBudgetLedgerError,
    canonical_occurred_at,
)
from .factory_budget_reservation_models import UsageEnvelope
from .factory_budget_reservation_validation import require_identifier

type QuotaUnit = Literal["requests", "input_tokens", "output_tokens", "tokens"]
type WindowKind = Literal["rolling", "calendar_month", "subscription_cycle"]


@dataclass(frozen=True, slots=True)
class QuotaWindow:
    kind: WindowKind
    starts_at: datetime | None
    ends_at: datetime | None
    cycle_id: str | None

    def validate(self) -> None:
        if self.starts_at is None or self.ends_at is None:
            raise FactoryBudgetLedgerError(
                "window",
                "quota authority requires explicit window bounds",
            )
        starts = canonical_occurred_at(self.starts_at)
        ends = canonical_occurred_at(self.ends_at)
        if starts >= ends:
            raise FactoryBudgetLedgerError("window", "quota window must be half-open")
        if self.kind == "subscription_cycle":
            if self.cycle_id is None:
                raise FactoryBudgetLedgerError("window", "subscription cycle id is missing")
            require_identifier(self.cycle_id, "subscription cycle id")
        elif self.cycle_id is not None:
            raise FactoryBudgetLedgerError("window", "quota window cycle id is invalid")

    def contains(self, value: datetime) -> bool:
        self.validate()
        if self.starts_at is None or self.ends_at is None:
            return False
        normalized = value.astimezone(UTC)
        return self.starts_at.astimezone(UTC) <= normalized < self.ends_at.astimezone(UTC)

    @property
    def starts_at_utc(self) -> str:
        if self.starts_at is None:
            raise FactoryBudgetLedgerError("window", "quota window start is missing")
        return canonical_occurred_at(self.starts_at)

    @property
    def ends_at_utc(self) -> str:
        if self.ends_at is None:
            raise FactoryBudgetLedgerError("window", "quota window end is missing")
        return canonical_occurred_at(self.ends_at)


def quota_units(usage: UsageEnvelope) -> dict[QuotaUnit, int]:
    usage.validate()
    combined = usage.input_tokens + usage.output_tokens
    if combined > SIGNED_64_BIT_MAX:
        raise FactoryBudgetLedgerError("amount", "combined token usage exceeds signed boundary")
    return {
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "tokens": combined,
    }


def utc_month_window(value: datetime) -> QuotaWindow:
    normalized = value.astimezone(UTC)
    start = datetime(normalized.year, normalized.month, 1, tzinfo=UTC)
    if normalized.month == 12:
        end = datetime(normalized.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(normalized.year, normalized.month + 1, 1, tzinfo=UTC)
    return QuotaWindow("calendar_month", start, end, None)


def subscription_cycle_window(
    value: datetime,
    *,
    renewal_month: int,
    renewal_day: int,
    cycle_id: str,
) -> QuotaWindow:
    normalized = value.astimezone(UTC)
    current = _annual_boundary(normalized.year, renewal_month, renewal_day)
    start_year = normalized.year if normalized >= current else normalized.year - 1
    start = _annual_boundary(start_year, renewal_month, renewal_day)
    end = _annual_boundary(start_year + 1, renewal_month, renewal_day)
    return QuotaWindow("subscription_cycle", start, end, cycle_id)


def monthly_subscription_cycle_window(
    value: datetime,
    *,
    renewal_day: int,
    cycle_id: str,
) -> QuotaWindow:
    normalized = value.astimezone(UTC)
    current = _monthly_boundary(normalized.year, normalized.month, renewal_day)
    if normalized >= current:
        start = current
        end = _monthly_boundary(*_next_month(normalized.year, normalized.month), renewal_day)
    else:
        previous_year, previous_month = _previous_month(normalized.year, normalized.month)
        start = _monthly_boundary(previous_year, previous_month, renewal_day)
        end = current
    return QuotaWindow("subscription_cycle", start, end, cycle_id)


def fixed_interval_subscription_cycle_window(
    value: datetime,
    *,
    anchor_on: date,
    interval_days: int,
    cycle_id: str,
) -> QuotaWindow:
    normalized = value.astimezone(UTC)
    anchor = datetime.combine(anchor_on, datetime.min.time(), tzinfo=UTC)
    if interval_days <= 0:
        raise FactoryBudgetLedgerError("window", "fixed renewal interval is invalid")
    if normalized < anchor:
        raise FactoryBudgetLedgerError("window", "subscription cycle has not started")
    interval = timedelta(days=interval_days)
    elapsed_cycles = (normalized - anchor) // interval
    start = anchor + elapsed_cycles * interval
    return QuotaWindow("subscription_cycle", start, start + interval, cycle_id)


def canonical_subscription_cycle_id(subscription_id: str, start: datetime) -> str:
    require_identifier(subscription_id, "subscription id")
    normalized = start.astimezone(UTC)
    return f"{subscription_id}-{normalized:%Y-%m-%d}"


def _annual_boundary(year: int, month: int, day: int) -> datetime:
    if month < 1 or month > 12 or day < 1 or day > 31:
        raise FactoryBudgetLedgerError("window", "annual renewal boundary is invalid")
    bounded_day = min(day, calendar.monthrange(year, month)[1])
    return datetime(year, month, bounded_day, tzinfo=UTC)


def _monthly_boundary(year: int, month: int, day: int) -> datetime:
    if day < 1 or day > 31:
        raise FactoryBudgetLedgerError("window", "monthly renewal boundary is invalid")
    bounded_day = min(day, calendar.monthrange(year, month)[1])
    return datetime(year, month, bounded_day, tzinfo=UTC)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)
