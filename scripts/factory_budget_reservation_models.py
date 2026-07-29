from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from .factory_budget_ledger_models import (
    SIGNED_64_BIT_MAX,
    FactoryBudgetLedgerError,
    canonical_occurred_at,
    canonical_utc_month,
    month_boundary,
)
from .factory_budget_reservation_validation import (
    canonical_digest,
    require_identifier,
    require_non_negative_int,
    require_positive_int,
)

type PriceUnit = Literal["request", "input_token", "output_token", "minute"]
type ReservationState = Literal[
    "dispatching",
    "uncertain",
    "settled",
    "reconciled",
]
type UncertaintyReason = Literal[
    "actual_exceeds_reservation",
    "job_mismatch",
    "malformed_receipt",
    "model_mismatch",
    "partial_receipt",
    "provider_mismatch",
    "provider_session_conflict",
    "run_mismatch",
    "worker_interrupted",
    "zero_usage_receipt",
]


@dataclass(frozen=True, slots=True)
class UsageEnvelope:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    minutes: int = 0

    def quantity_for(self, unit: PriceUnit) -> int:
        if unit == "request":
            return self.requests
        if unit == "input_token":
            return self.input_tokens
        if unit == "output_token":
            return self.output_tokens
        return self.minutes

    def validate(self) -> None:
        for label, value in (
            ("request ceiling", self.requests),
            ("input-token ceiling", self.input_tokens),
            ("output-token ceiling", self.output_tokens),
            ("minute ceiling", self.minutes),
        ):
            require_non_negative_int(value, label)


@dataclass(frozen=True, slots=True)
class PriceTerm:
    snapshot_id: str
    unit: PriceUnit
    quantity: int
    price_microcents: int
    observed_at: datetime
    expires_at: datetime

    def validate_at(self, as_of: datetime) -> None:
        require_identifier(self.snapshot_id, "price snapshot id")
        require_positive_int(self.quantity, "price quantity")
        require_positive_int(self.price_microcents, "price")
        observed = canonical_occurred_at(self.observed_at)
        expires = canonical_occurred_at(self.expires_at)
        current = canonical_occurred_at(as_of)
        if not observed <= current < expires:
            raise FactoryBudgetLedgerError("price", "price term is stale or not yet observed")

    @property
    def observed_at_utc(self) -> str:
        return canonical_occurred_at(self.observed_at)

    @property
    def expires_at_utc(self) -> str:
        return canonical_occurred_at(self.expires_at)


@dataclass(frozen=True, slots=True)
class CostReservationRequest:
    idempotency_key: str
    job_id: str
    provider_lane_id: str
    provider_id: str
    model_id: str
    requested_model: str
    cost_policy_lane_id: str
    policy_id: str
    policy_revision: int
    occurred_at: datetime
    usage_envelope: UsageEnvelope
    price_terms: tuple[PriceTerm, ...]

    def validate(self) -> None:
        for label, value in (
            ("idempotency key", self.idempotency_key),
            ("job id", self.job_id),
            ("provider lane id", self.provider_lane_id),
            ("provider id", self.provider_id),
            ("cost model id", self.model_id),
            ("requested model", self.requested_model),
            ("cost policy lane id", self.cost_policy_lane_id),
            ("policy id", self.policy_id),
        ):
            require_identifier(value, label)
        require_positive_int(self.policy_revision, "policy revision")
        _ = canonical_occurred_at(self.occurred_at)
        self.usage_envelope.validate()
        if not self.price_terms:
            raise FactoryBudgetLedgerError("price", "reservation requires price terms")
        snapshot_ids: set[str] = set()
        units: set[PriceUnit] = set()
        for term in self.price_terms:
            term.validate_at(self.occurred_at)
            if term.snapshot_id in snapshot_ids:
                raise FactoryBudgetLedgerError("price", "duplicate price snapshot id")
            if term.unit in units:
                raise FactoryBudgetLedgerError("price", "duplicate price unit")
            if self.usage_envelope.quantity_for(term.unit) <= 0:
                raise FactoryBudgetLedgerError("price", "priced usage ceiling must be positive")
            snapshot_ids.add(term.snapshot_id)
            units.add(term.unit)
        _ = self.worst_case_microcents

    @property
    def occurred_at_utc(self) -> str:
        return canonical_occurred_at(self.occurred_at)

    @property
    def period_start_utc(self) -> str:
        return month_boundary(canonical_utc_month(self.occurred_at))

    @property
    def worst_case_microcents(self) -> int:
        return priced_cost(self.usage_envelope, self.price_terms)

    @property
    def pricing_digest(self) -> str:
        payload = [
            {
                "expires_at_utc": term.expires_at_utc,
                "observed_at_utc": term.observed_at_utc,
                "price_microcents": term.price_microcents,
                "quantity": term.quantity,
                "snapshot_id": term.snapshot_id,
                "unit": term.unit,
            }
            for term in sorted(self.price_terms, key=lambda item: item.unit)
        ]
        return canonical_digest(payload)


@dataclass(frozen=True, slots=True)
class SettlementReceipt:
    idempotency_key: str
    reservation_id: str
    job_id: str
    provider_lane_id: str
    provider_id: str
    model_id: str
    requested_model: str
    provider_session_digest: str
    input_tokens: int
    output_tokens: int
    requests: int
    minutes: int
    occurred_at: datetime

    @property
    def usage(self) -> UsageEnvelope:
        return UsageEnvelope(
            requests=self.requests,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            minutes=self.minutes,
        )


@dataclass(frozen=True, slots=True)
class NoChargeReconciliationInput:
    idempotency_key: str
    reservation_id: str
    evidence_digest: str
    occurred_at: datetime
    reason: Literal["provider_confirmed_no_charge", "verified_never_dispatched"]


@dataclass(frozen=True, slots=True)
class ManualReconciliationInput:
    idempotency_key: str
    reservation_id: str
    evidence_digest: str
    amount_microcents: int
    occurred_at: datetime
    source_id: str


@dataclass(frozen=True, slots=True)
class CostReservationReceipt:
    created: bool
    reservation_id: str
    state: ReservationState
    held_microcents: int
    actual_microcents: int | None
    reason: str | None
    period_start_utc: str
    pricing_digest: str

    def with_created(self, created: bool) -> CostReservationReceipt:
        return replace(self, created=created)


@dataclass(frozen=True, slots=True)
class SettlementOutcome:
    created: bool
    reservation_id: str
    state: ReservationState
    held_microcents: int
    actual_microcents: int | None
    reason: str | None
    entry_id: int | None


def priced_cost(
    usage: UsageEnvelope,
    terms: tuple[PriceTerm, ...],
    *,
    require_positive: bool = True,
) -> int:
    total = 0
    for term in terms:
        count = usage.quantity_for(term.unit)
        require_non_negative_int(count, "usage quantity")
        if count > SIGNED_64_BIT_MAX // term.price_microcents:
            raise FactoryBudgetLedgerError(
                "amount",
                "priced usage exceeds the signed 64-bit boundary",
            )
        product = count * term.price_microcents
        line = (product + term.quantity - 1) // term.quantity
        if line > SIGNED_64_BIT_MAX - total:
            raise FactoryBudgetLedgerError(
                "amount",
                "priced cost exceeds the signed 64-bit boundary",
            )
        total += line
    if require_positive and total <= 0:
        raise FactoryBudgetLedgerError("amount", "priced cost must be positive")
    return total
