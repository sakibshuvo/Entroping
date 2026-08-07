from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_occurred_at,
)
from .factory_budget_reservation_models import CostReservationRequest, UsageEnvelope
from .factory_budget_reservation_validation import (
    canonical_digest,
    require_identifier,
    require_positive_int,
)
from .factory_quota_evidence import (
    QuotaObservation as _QuotaObservation,
)
from .factory_quota_evidence import (
    QuotaRequirement as QuotaRequirement,
)
from .factory_quota_evidence import (
    TopUpAttestation as TopUpAttestation,
)
from .factory_quota_windows import (
    QuotaUnit as QuotaUnit,
)
from .factory_quota_windows import (
    QuotaWindow as _QuotaWindow,
)
from .factory_quota_windows import (
    quota_units,
)
from .factory_quota_windows import (
    subscription_cycle_window as _subscription_cycle_window,
)
from .factory_quota_windows import (
    utc_month_window as _utc_month_window,
)

QuotaObservation = _QuotaObservation
QuotaWindow = _QuotaWindow
subscription_cycle_window = _subscription_cycle_window
utc_month_window = _utc_month_window

type BillingMode = Literal["metered", "included_quota", "fixed_subscription"]
type WorkPurpose = Literal["experiment", "essential"]


@dataclass(frozen=True, slots=True)
class DispatchAuthorizationRequest:
    idempotency_key: str
    job_id: str
    provider_lane_id: str
    provider_id: str
    cost_policy_lane_id: str
    policy_id: str
    policy_revision: int
    billing_mode: BillingMode
    work_purpose: WorkPurpose
    usage_envelope: UsageEnvelope
    cash_reservation: CostReservationRequest | None
    quota_requirements: tuple[QuotaRequirement, ...]
    top_up_attestation: TopUpAttestation | None
    decision_at: datetime
    expires_at: datetime

    def validate(self) -> None:
        for label, value in (
            ("idempotency key", self.idempotency_key),
            ("job id", self.job_id),
            ("provider lane id", self.provider_lane_id),
            ("provider id", self.provider_id),
            ("cost policy lane id", self.cost_policy_lane_id),
            ("policy id", self.policy_id),
        ):
            require_identifier(value, label)
        require_positive_int(self.policy_revision, "policy revision")
        self.usage_envelope.validate()
        decision = canonical_occurred_at(self.decision_at)
        expires = canonical_occurred_at(self.expires_at)
        if decision >= expires:
            raise FactoryBudgetLedgerError("authorization", "authorization expiry is invalid")
        if self.top_up_attestation is None:
            raise FactoryBudgetLedgerError("top_up", "fresh top-up attestation is required")
        self.top_up_attestation.validate_for(self)
        if self.billing_mode == "metered" and self.cash_reservation is None:
            raise FactoryBudgetLedgerError("cash", "metered authorization requires a cash hold")
        if self.billing_mode != "metered" and self.cash_reservation is not None:
            raise FactoryBudgetLedgerError("cash", "non-metered authorization cannot hold cash")
        if self.cash_reservation is not None:
            self.cash_reservation.validate()
            if (
                self.cash_reservation.job_id != self.job_id
                or self.cash_reservation.provider_lane_id != self.provider_lane_id
                or self.cash_reservation.provider_id != self.provider_id
                or self.cash_reservation.cost_policy_lane_id != self.cost_policy_lane_id
                or self.cash_reservation.policy_id != self.policy_id
                or self.cash_reservation.policy_revision != self.policy_revision
                or self.cash_reservation.occurred_at_utc != decision
                or self.cash_reservation.usage_envelope != self.usage_envelope
            ):
                raise FactoryBudgetLedgerError("cash", "cash reservation identity is mismatched")
        projected = quota_units(self.usage_envelope)
        seen: set[str] = set()
        for requirement in self.quota_requirements:
            require_identifier(requirement.quota_id, "quota id")
            require_positive_int(requirement.limit, "quota limit")
            if requirement.quota_id in seen:
                raise FactoryBudgetLedgerError("quota", "duplicate quota requirement")
            requirement.observation.validate_for(self)
            if (
                requirement.observation.quota_id != requirement.quota_id
                or requirement.observation.unit != requirement.unit
            ):
                raise FactoryBudgetLedgerError("quota", "quota requirement is mismatched")
            if projected[requirement.unit] <= 0:
                raise FactoryBudgetLedgerError("quota", "quota hold must be positive")
            seen.add(requirement.quota_id)

    @property
    def request_digest(self) -> str:
        return canonical_digest(
            {
                "billing_mode": self.billing_mode,
                "cash_reservation": _cash_reservation_payload(self.cash_reservation),
                "cost_policy_lane_id": self.cost_policy_lane_id,
                "decision_at_utc": canonical_occurred_at(self.decision_at),
                "expires_at_utc": canonical_occurred_at(self.expires_at),
                "job_id": self.job_id,
                "policy_id": self.policy_id,
                "policy_revision": self.policy_revision,
                "provider_id": self.provider_id,
                "provider_lane_id": self.provider_lane_id,
                "quota_evidence": tuple(
                    _quota_requirement_payload(item)
                    for item in sorted(self.quota_requirements, key=lambda value: value.quota_id)
                ),
                "top_up_attestation": _attestation_payload(self.top_up_attestation),
                "usage": _usage_payload(self.usage_envelope),
                "work_purpose": self.work_purpose,
            }
        )


def _cash_reservation_payload(request: CostReservationRequest | None) -> object:
    if request is None:
        return None
    return {
        "idempotency_key": request.idempotency_key,
        "job_id": request.job_id,
        "provider_lane_id": request.provider_lane_id,
        "provider_id": request.provider_id,
        "model_id": request.model_id,
        "requested_model": request.requested_model,
        "cost_policy_lane_id": request.cost_policy_lane_id,
        "policy_id": request.policy_id,
        "policy_revision": request.policy_revision,
        "occurred_at_utc": request.occurred_at_utc,
        "usage": _usage_payload(request.usage_envelope),
        "pricing_digest": request.pricing_digest,
    }


def _usage_payload(usage: UsageEnvelope) -> object:
    return {
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "minutes": usage.minutes,
    }


def _quota_requirement_payload(requirement: QuotaRequirement) -> object:
    observation = requirement.observation
    return {
        "quota_id": requirement.quota_id,
        "unit": requirement.unit,
        "limit": requirement.limit,
        "observation": {
            "observation_id": observation.observation_id,
            "quota_id": observation.quota_id,
            "provider_id": observation.provider_id,
            "provider_lane_id": observation.provider_lane_id,
            "policy_id": observation.policy_id,
            "policy_revision": observation.policy_revision,
            "unit": observation.unit,
            "source_kind": observation.source_kind,
            "source_id": observation.source_id,
            "observed_at_utc": observation.observed_at_utc,
            "recorded_at_utc": observation.recorded_at_utc,
            "expires_at_utc": observation.expires_at_utc,
            "window_kind": observation.window.kind,
            "window_start_utc": observation.window.starts_at_utc,
            "window_end_utc": observation.window.ends_at_utc,
            "cycle_id": observation.window.cycle_id,
            "used_units": observation.used_units,
            "known": observation.known,
            "evidence_digest": observation.evidence_digest,
            "included_authorization_ids": observation.included_authorization_ids,
        },
    }


def _attestation_payload(attestation: TopUpAttestation | None) -> object:
    if attestation is None:
        return None
    return {
        "attestation_id": attestation.attestation_id,
        "provider_id": attestation.provider_id,
        "provider_lane_id": attestation.provider_lane_id,
        "policy_id": attestation.policy_id,
        "policy_revision": attestation.policy_revision,
        "mode": attestation.mode,
        "source_kind": attestation.source_kind,
        "source_id": attestation.source_id,
        "evidence_digest": attestation.evidence_digest,
        "observed_at_utc": attestation.observed_at_utc,
        "expires_at_utc": attestation.expires_at_utc,
    }


@dataclass(frozen=True, slots=True)
class DispatchAuthorizationReceipt:
    created: bool
    authorization_id: str
    job_id: str
    reason: str
    reservation_id: str | None
    held_microcents: int
    quota_holds: tuple[tuple[str, int], ...]
    decision_at: datetime
    expires_at: datetime
