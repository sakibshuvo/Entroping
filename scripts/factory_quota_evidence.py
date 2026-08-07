from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .factory_budget_ledger_models import FactoryBudgetLedgerError, canonical_occurred_at
from .factory_budget_reservation_validation import (
    canonical_digest,
    require_identifier,
    require_non_negative_int,
    require_positive_int,
    require_sha256,
)
from .factory_quota_windows import QuotaUnit, QuotaWindow


class DispatchEvidenceContext(Protocol):
    @property
    def provider_id(self) -> str:
        raise NotImplementedError

    @property
    def provider_lane_id(self) -> str:
        raise NotImplementedError

    @property
    def policy_id(self) -> str:
        raise NotImplementedError

    @property
    def policy_revision(self) -> int:
        raise NotImplementedError

    @property
    def decision_at(self) -> datetime:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class QuotaObservation:
    observation_id: str
    quota_id: str
    provider_id: str
    provider_lane_id: str
    policy_id: str
    policy_revision: int
    unit: QuotaUnit
    source_kind: str
    source_id: str
    observed_at: datetime
    recorded_at: datetime
    expires_at: datetime
    window: QuotaWindow
    used_units: int
    known: bool
    evidence_digest: str
    included_authorization_ids: tuple[str, ...] = ()

    def validate_for(self, request: DispatchEvidenceContext) -> None:
        for label, value in (
            ("quota observation id", self.observation_id),
            ("quota id", self.quota_id),
            ("provider id", self.provider_id),
            ("provider lane id", self.provider_lane_id),
            ("policy id", self.policy_id),
            ("quota source kind", self.source_kind),
            ("quota source id", self.source_id),
        ):
            require_identifier(value, label)
        require_positive_int(self.policy_revision, "policy revision")
        require_non_negative_int(self.used_units, "used quota units")
        require_sha256(self.evidence_digest, "quota evidence digest")
        if (
            len(self.included_authorization_ids) > 256
            or tuple(sorted(self.included_authorization_ids))
            != self.included_authorization_ids
            or len(set(self.included_authorization_ids))
            != len(self.included_authorization_ids)
        ):
            raise FactoryBudgetLedgerError(
                "quota",
                "included authorization ids must be unique and sorted",
            )
        for authorization_id in self.included_authorization_ids:
            require_identifier(authorization_id, "included authorization id")
        self.window.validate()
        observed = canonical_occurred_at(self.observed_at)
        recorded = canonical_occurred_at(self.recorded_at)
        expires = canonical_occurred_at(self.expires_at)
        decision = canonical_occurred_at(request.decision_at)
        if not observed <= recorded <= decision < expires:
            raise FactoryBudgetLedgerError("quota", "quota observation is future or stale")
        if not self.window.contains(request.decision_at):
            raise FactoryBudgetLedgerError("quota", "quota observation window is mismatched")
        if not self.known:
            raise FactoryBudgetLedgerError("quota", "quota observation is uncertain")
        if (
            self.provider_id != request.provider_id
            or self.provider_lane_id != request.provider_lane_id
            or self.policy_id != request.policy_id
            or self.policy_revision != request.policy_revision
        ):
            raise FactoryBudgetLedgerError("quota", "quota observation identity is mismatched")

    @property
    def observed_at_utc(self) -> str:
        return canonical_occurred_at(self.observed_at)

    @property
    def recorded_at_utc(self) -> str:
        return canonical_occurred_at(self.recorded_at)

    @property
    def expires_at_utc(self) -> str:
        return canonical_occurred_at(self.expires_at)

    @property
    def inclusions_digest(self) -> str:
        return canonical_digest(self.included_authorization_ids)


@dataclass(frozen=True, slots=True)
class TopUpAttestation:
    attestation_id: str
    provider_id: str
    provider_lane_id: str
    policy_id: str
    policy_revision: int
    mode: Literal["disabled"]
    source_kind: str
    source_id: str
    evidence_digest: str
    observed_at: datetime
    expires_at: datetime

    def validate_for(self, request: DispatchEvidenceContext) -> None:
        for label, value in (
            ("top-up attestation id", self.attestation_id),
            ("provider id", self.provider_id),
            ("provider lane id", self.provider_lane_id),
            ("policy id", self.policy_id),
            ("top-up source kind", self.source_kind),
            ("top-up source id", self.source_id),
        ):
            require_identifier(value, label)
        require_positive_int(self.policy_revision, "policy revision")
        require_sha256(self.evidence_digest, "top-up evidence digest")
        observed = canonical_occurred_at(self.observed_at)
        expires = canonical_occurred_at(self.expires_at)
        decision = canonical_occurred_at(request.decision_at)
        if not observed <= decision < expires:
            raise FactoryBudgetLedgerError("top_up", "top-up attestation is future or stale")
        if (
            self.provider_id != request.provider_id
            or self.provider_lane_id != request.provider_lane_id
            or self.policy_id != request.policy_id
            or self.policy_revision != request.policy_revision
        ):
            raise FactoryBudgetLedgerError("top_up", "top-up attestation identity is mismatched")

    @property
    def observed_at_utc(self) -> str:
        return canonical_occurred_at(self.observed_at)

    @property
    def expires_at_utc(self) -> str:
        return canonical_occurred_at(self.expires_at)


@dataclass(frozen=True, slots=True)
class QuotaRequirement:
    quota_id: str
    unit: QuotaUnit
    limit: int
    observation: QuotaObservation
