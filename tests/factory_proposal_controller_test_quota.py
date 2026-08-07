from __future__ import annotations

from datetime import timedelta

from factory_scheduler_test_support import NOW

from scripts.factory_budget_ledger import UsageEnvelope
from scripts.factory_quota_models import (
    DispatchAuthorizationRequest,
    QuotaObservation,
    QuotaRequirement,
    QuotaWindow,
    TopUpAttestation,
)


def quota_exhausted_request() -> DispatchAuthorizationRequest:
    observation = QuotaObservation(
        observation_id="controller-quota-observation",
        quota_id="controller-quota",
        provider_id="test-paid",
        provider_lane_id="test-paid/direct",
        policy_id="factory-policy",
        policy_revision=3,
        unit="tokens",
        source_kind="provider-usage-export",
        source_id="controller-usage",
        observed_at=NOW - timedelta(minutes=1),
        recorded_at=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=1),
        window=QuotaWindow(
            kind="rolling",
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(minutes=1),
            cycle_id=None,
        ),
        used_units=1,
        known=True,
        evidence_digest="d" * 64,
    )
    return DispatchAuthorizationRequest(
        idempotency_key="controller-quota-exhausted",
        job_id="controller-quota-job",
        provider_lane_id="test-paid/direct",
        provider_id="test-paid",
        cost_policy_lane_id="test-paid-quota",
        policy_id="factory-policy",
        policy_revision=3,
        billing_mode="included_quota",
        work_purpose="essential",
        usage_envelope=UsageEnvelope(input_tokens=1),
        cash_reservation=None,
        quota_requirements=(
            QuotaRequirement(
                quota_id="controller-quota",
                unit="tokens",
                limit=1,
                observation=observation,
            ),
        ),
        top_up_attestation=TopUpAttestation(
            attestation_id="controller-topup",
            provider_id="test-paid",
            provider_lane_id="test-paid/direct",
            policy_id="factory-policy",
            policy_revision=3,
            mode="disabled",
            source_kind="provider-policy-export",
            source_id="controller-policy",
            evidence_digest="e" * 64,
            observed_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=1),
        ),
        decision_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
