from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .factory_cost_policy_types import Identifier, PositiveCount, QuotaUnit
from .factory_quota_evidence import QuotaObservation, TopUpAttestation
from .factory_quota_windows import QuotaWindow

type Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
type EvidenceIdentifier = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$"),
]


class FactoryProviderEvidenceError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class StrictEvidenceModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class QuotaWindowEvidence(StrictEvidenceModel):
    kind: Literal["rolling", "calendar_month", "subscription_cycle"]
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    cycle_id: EvidenceIdentifier | None

    def to_domain(self) -> QuotaWindow:
        return QuotaWindow(self.kind, self.starts_at, self.ends_at, self.cycle_id)


class QuotaObservationEvidence(StrictEvidenceModel):
    observation_id: Identifier
    quota_id: Identifier
    provider_id: Identifier
    provider_lane_id: EvidenceIdentifier
    policy_id: Identifier
    policy_revision: PositiveCount
    unit: QuotaUnit
    source_kind: Identifier
    source_id: Identifier
    observed_at: AwareDatetime
    recorded_at: AwareDatetime
    expires_at: AwareDatetime
    window: QuotaWindowEvidence
    used_units: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    known: bool
    included_authorization_ids: Annotated[tuple[Identifier, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def validate_inclusion_boundary(self) -> Self:
        if (
            tuple(sorted(self.included_authorization_ids))
            != self.included_authorization_ids
            or len(set(self.included_authorization_ids))
            != len(self.included_authorization_ids)
        ):
            raise ValueError("included authorization ids must be unique and sorted")
        return self

    def to_domain(self, *, evidence_digest: str) -> QuotaObservation:
        return QuotaObservation(
            observation_id=self.observation_id,
            quota_id=self.quota_id,
            provider_id=self.provider_id,
            provider_lane_id=self.provider_lane_id,
            policy_id=self.policy_id,
            policy_revision=self.policy_revision,
            unit=self.unit,
            source_kind=self.source_kind,
            source_id=self.source_id,
            observed_at=self.observed_at,
            recorded_at=self.recorded_at,
            expires_at=self.expires_at,
            window=self.window.to_domain(),
            used_units=self.used_units,
            known=self.known,
            evidence_digest=evidence_digest,
            included_authorization_ids=self.included_authorization_ids,
        )


class TopUpAttestationEvidence(StrictEvidenceModel):
    attestation_id: Identifier
    provider_id: Identifier
    provider_lane_id: EvidenceIdentifier
    policy_id: Identifier
    policy_revision: PositiveCount
    mode: Literal["disabled"]
    source_kind: Identifier
    source_id: Identifier
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    def to_domain(self, *, evidence_digest: str) -> TopUpAttestation:
        return TopUpAttestation(
            attestation_id=self.attestation_id,
            provider_id=self.provider_id,
            provider_lane_id=self.provider_lane_id,
            policy_id=self.policy_id,
            policy_revision=self.policy_revision,
            mode=self.mode,
            source_kind=self.source_kind,
            source_id=self.source_id,
            evidence_digest=evidence_digest,
            observed_at=self.observed_at,
            expires_at=self.expires_at,
        )


class EvidenceAuthentication(StrictEvidenceModel):
    scheme: Literal["hmac-sha256"]
    key_id: Literal["maintainer-local-v1"]
    signature: Sha256Digest


class FactoryProviderEvidence(StrictEvidenceModel):
    schema_version: Literal["entroping.factory-provider-evidence.v1"]
    evidence_id: EvidenceIdentifier
    top_up_attestations: Annotated[tuple[TopUpAttestationEvidence, ...], Field(max_length=128)]
    quota_observations: Annotated[tuple[QuotaObservationEvidence, ...], Field(max_length=512)]
    authentication: EvidenceAuthentication

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> Self:
        _require_unique(
            tuple(item.attestation_id for item in self.top_up_attestations),
            "top-up attestation",
        )
        _require_unique(
            tuple(item.observation_id for item in self.quota_observations),
            "quota observation",
        )
        return self

    def matching_evidence(
        self,
        *,
        provider_id: str,
        provider_lane_id: str,
        policy_id: str,
        policy_revision: int,
    ) -> tuple[TopUpAttestationEvidence | None, tuple[QuotaObservationEvidence, ...]]:
        identity = (provider_id, provider_lane_id, policy_id, policy_revision)
        attestations = tuple(
            item
            for item in self.top_up_attestations
            if (
                item.provider_id,
                item.provider_lane_id,
                item.policy_id,
                item.policy_revision,
            )
            == identity
        )
        if len(attestations) > 1:
            raise FactoryProviderEvidenceError(
                "evidence_identity",
                "matching top-up evidence is ambiguous",
            )
        observations = tuple(
            item
            for item in self.quota_observations
            if (
                item.provider_id,
                item.provider_lane_id,
                item.policy_id,
                item.policy_revision,
            )
            == identity
        )
        if len({item.quota_id for item in observations}) != len(observations):
            raise FactoryProviderEvidenceError(
                "evidence_identity",
                "matching quota evidence is ambiguous",
            )
        return (attestations[0] if attestations else None), observations


@dataclass(frozen=True, slots=True)
class AuthenticatedFactoryProviderEvidence:
    document: FactoryProviderEvidence
    envelope_digest: str

    def for_dispatch(
        self,
        *,
        provider_id: str,
        provider_lane_id: str,
        policy_id: str,
        policy_revision: int,
    ) -> tuple[TopUpAttestation | None, tuple[QuotaObservation, ...]]:
        attestation, observations = self.document.matching_evidence(
            provider_id=provider_id,
            provider_lane_id=provider_lane_id,
            policy_id=policy_id,
            policy_revision=policy_revision,
        )
        return (
            None
            if attestation is None
            else attestation.to_domain(evidence_digest=self.envelope_digest),
            tuple(item.to_domain(evidence_digest=self.envelope_digest) for item in observations),
        )


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {label} id")
