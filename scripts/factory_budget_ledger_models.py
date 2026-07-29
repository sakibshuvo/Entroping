from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import override

SIGNED_64_BIT_MAX = (2**63) - 1
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
type LedgerScalarInput = None | bool | int | float | str | bytes | date | datetime


class FactoryBudgetLedgerError(RuntimeError):
    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class BudgetPeriodConfig:
    starts_on: date
    cash_cap_microcents: int
    emergency_reserve_microcents: int
    currency: str
    policy_id: str
    policy_revision: int
    reserve_idempotency_key: str

    def __post_init__(self) -> None:
        if type(self.starts_on) is not date:
            raise FactoryBudgetLedgerError("period", "period start must be a date")
        if self.starts_on.day != 1:
            raise FactoryBudgetLedgerError("period", "period must start on day 1")
        if self.starts_on == date.max.replace(day=1):
            raise FactoryBudgetLedgerError("period", "period end is not representable")
        _require_microcents(self.cash_cap_microcents, "cash cap", positive=True)
        _require_microcents(
            self.emergency_reserve_microcents,
            "emergency reserve",
            positive=True,
        )
        if self.emergency_reserve_microcents >= self.cash_cap_microcents:
            raise FactoryBudgetLedgerError(
                "period",
                "emergency reserve must be less than the cash cap",
            )
        if self.currency != "USD":
            raise FactoryBudgetLedgerError("currency", "currency must be USD")
        _require_identifier(self.policy_id, "policy id")
        _require_positive_int(self.policy_revision, "policy revision")
        _require_identifier(self.reserve_idempotency_key, "idempotency key")

    @property
    def period_start_utc(self) -> str:
        return month_boundary(self.starts_on)

    @property
    def period_end_utc(self) -> str:
        if self.starts_on.month == 12:
            following = date(self.starts_on.year + 1, 1, 1)
        else:
            following = date(self.starts_on.year, self.starts_on.month + 1, 1)
        return month_boundary(following)


@dataclass(frozen=True, slots=True)
class BudgetPeriodSummary:
    period_start_utc: str
    period_end_utc: str
    currency: str
    cash_cap_microcents: int
    emergency_reserve_microcents: int
    net_spent_microcents: int
    active_reserved_microcents: int
    available_paid_microcents: int
    entry_count: int
    policy_id: str
    policy_revision: int


@dataclass(frozen=True, slots=True)
class BudgetBalanceSummary:
    period_start_utc: str
    currency: str
    paid_limit_microcents: int
    net_spent_microcents: int
    available_paid_microcents: int
    paid_dispatch_permitted: bool


@dataclass(frozen=True, slots=True)
class PeriodInitialization:
    created: bool
    summary: BudgetPeriodSummary


@dataclass(frozen=True, slots=True)
class LedgerEntryInput:
    idempotency_key: str
    kind: str
    direction: str
    amount_microcents: int
    occurred_at: datetime
    currency: str
    source_id: str
    reference_idempotency_key: str | None = None

    def validate(self) -> None:
        _require_identifier(self.idempotency_key, "idempotency key")
        _require_identifier(self.source_id, "source id")
        _require_microcents(self.amount_microcents, "amount", positive=True)
        if self.currency != "USD":
            raise FactoryBudgetLedgerError("currency", "currency must be USD")
        _ = canonical_occurred_at(self.occurred_at)
        if self.kind in {"fixed_subscription_charge", "provider_charge"}:
            if self.direction != "debit":
                raise FactoryBudgetLedgerError("entry", "charge entries must be debits")
            if self.reference_idempotency_key is not None:
                raise FactoryBudgetLedgerError(
                    "entry",
                    "charge entries cannot reference another entry",
                )
            return
        if self.kind == "refund":
            if self.direction != "credit":
                raise FactoryBudgetLedgerError("entry", "refund entries must be credits")
            if self.reference_idempotency_key is None:
                raise FactoryBudgetLedgerError("entry", "refund entries require a charge reference")
            _require_identifier(self.reference_idempotency_key, "refund reference")
            return
        if self.kind == "manual_adjustment":
            if self.direction not in {"debit", "credit"}:
                raise FactoryBudgetLedgerError(
                    "entry",
                    "manual adjustments require an explicit debit or credit",
                )
            if self.reference_idempotency_key is not None:
                raise FactoryBudgetLedgerError(
                    "entry",
                    "manual adjustments cannot reference another entry",
                )
            return
        raise FactoryBudgetLedgerError("entry", "ledger entry kind is unsupported")

    @property
    def occurred_at_utc(self) -> str:
        return canonical_occurred_at(self.occurred_at)

    @property
    def period_starts_on(self) -> date:
        return canonical_utc_month(self.occurred_at)


@dataclass(frozen=True, slots=True)
class LedgerEntryReceipt:
    created: bool
    entry_id: int
    idempotency_digest: str
    kind: str
    direction: str
    amount_microcents: int
    occurred_at_utc: str
    summary: BudgetPeriodSummary


def canonical_utc_month(value: LedgerScalarInput) -> date:
    normalized = _require_offset_datetime(value)
    return date(normalized.year, normalized.month, 1)


def canonical_occurred_at(value: LedgerScalarInput) -> str:
    normalized = _require_offset_datetime(value)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_offset_datetime(value: LedgerScalarInput) -> datetime:
    if not isinstance(value, datetime):
        raise FactoryBudgetLedgerError("timestamp", "timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FactoryBudgetLedgerError("timestamp", "timestamp must include a UTC offset")
    return value.astimezone(UTC)


def idempotency_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def month_boundary(value: date) -> str:
    return f"{value.isoformat()}T00:00:00Z"


def _require_identifier(value: LedgerScalarInput, label: str) -> None:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise FactoryBudgetLedgerError(
            "identifier",
            f"{label} must be a bounded lowercase identifier",
        )


def _require_microcents(value: LedgerScalarInput, label: str, *, positive: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FactoryBudgetLedgerError("amount", f"{label} must be an integer")
    minimum = 1 if positive else 0
    if value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise FactoryBudgetLedgerError("amount", f"{label} must be {qualifier}")
    if value > SIGNED_64_BIT_MAX:
        raise FactoryBudgetLedgerError(
            "amount",
            f"{label} exceeds the signed 64-bit boundary",
        )


def _require_positive_int(value: LedgerScalarInput, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FactoryBudgetLedgerError("integer", f"{label} must be a positive integer")
    if value > SIGNED_64_BIT_MAX:
        raise FactoryBudgetLedgerError(
            "integer",
            f"{label} exceeds the signed 64-bit boundary",
        )
