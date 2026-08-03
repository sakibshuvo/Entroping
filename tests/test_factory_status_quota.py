from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_status_test_support import initialize_status_period, write_status_policy  # noqa: E402

from scripts.factory_budget_ledger import FactoryBudgetLedger  # noqa: E402
from scripts.factory_budget_reservation_models import UsageEnvelope  # noqa: E402
from scripts.factory_quota_models import (  # noqa: E402
    DispatchAuthorizationReceipt,
    DispatchAuthorizationRequest,
    QuotaObservation,
    QuotaRequirement,
    QuotaWindow,
    TopUpAttestation,
)
from scripts.factory_status import collect_factory_status  # noqa: E402


def _authorize_quota(
    root: Path, now: datetime, *, decision_at: datetime | None = None
) -> tuple[FactoryBudgetLedger, DispatchAuthorizationReceipt]:
    """Create one fresh direct-provider quota authorization."""

    decided = decision_at or now
    write_status_policy(root, now, quota_backed=True)
    ledger = initialize_status_period(root, now)
    observation = QuotaObservation(
        observation_id="status-observation",
        quota_id="deepseek-five-hour",
        provider_id="deepseek",
        provider_lane_id="deepseek-api/direct",
        policy_id="status-policy",
        policy_revision=1,
        unit="requests",
        source_kind="provider-usage-export",
        source_id="status-provider-export",
        observed_at=decided - timedelta(minutes=1),
        recorded_at=decided - timedelta(seconds=30),
        expires_at=decided + timedelta(minutes=10),
        window=QuotaWindow(
            kind="rolling",
            starts_at=decided - timedelta(hours=5),
            ends_at=decided + timedelta(minutes=10),
            cycle_id=None,
        ),
        used_units=1,
        known=True,
        evidence_digest="a" * 64,
    )
    receipt = ledger.authorize_dispatch(
        DispatchAuthorizationRequest(
            idempotency_key="status-authorize",
            job_id="status-job",
            provider_lane_id="deepseek-api/direct",
            provider_id="deepseek",
            cost_policy_lane_id="deepseek-included",
            policy_id="status-policy",
            policy_revision=1,
            billing_mode="included_quota",
            work_purpose="essential",
            usage_envelope=UsageEnvelope(requests=1),
            cash_reservation=None,
            quota_requirements=(
                QuotaRequirement(
                    quota_id="deepseek-five-hour",
                    unit="requests",
                    limit=100,
                    observation=observation,
                ),
            ),
            top_up_attestation=TopUpAttestation(
                attestation_id="status-top-up",
                provider_id="deepseek",
                provider_lane_id="deepseek-api/direct",
                policy_id="status-policy",
                policy_revision=1,
                mode="disabled",
                source_kind="provider-policy-export",
                source_id="status-policy-export",
                evidence_digest="b" * 64,
                observed_at=decided - timedelta(minutes=1),
                expires_at=decided + timedelta(minutes=10),
            ),
            decision_at=decided,
            expires_at=decided + timedelta(minutes=5),
        )
    )
    return ledger, receipt


def test_quota_evidence_for_one_provider_route_never_readies_another(tmp_path: Path) -> None:
    """Quota authority is keyed by the registered provider lane, not provider alone."""

    now = datetime.now(UTC)
    _ = _authorize_quota(tmp_path, now)

    report = collect_factory_status(tmp_path)

    assert report.dispatch_lanes.ready_routes == 1
    assert tuple(row.provider_lane_id for row in report.dispatch_lanes.lanes) == (
        "deepseek-api/direct",
        "opencode/native-deepseek",
    )
    assert tuple(row.status for row in report.dispatch_lanes.lanes) == ("available", "unavailable")
    assert report.dispatch_lanes.lanes[1].quotas[0].reason_code == "quota-unavailable"


@pytest.mark.parametrize(
    ("decision_offset", "reason"),
    (
        (timedelta(minutes=-20), "quota-stale"),
        (timedelta(minutes=10), "quota-unavailable"),
    ),
)
def test_stale_or_future_quota_observation_pauses_affected_route(
    tmp_path: Path, decision_offset: timedelta, reason: str
) -> None:
    """Expired and not-yet-active quota authority cannot ready a route."""

    now = datetime.now(UTC)
    _ = _authorize_quota(tmp_path, now, decision_at=now + decision_offset)

    report = collect_factory_status(tmp_path)

    assert report.dispatch_lanes.status == "unavailable"
    assert report.dispatch_lanes.lanes[0].quotas[0].reason_code == reason


def test_uncertain_quota_hold_is_unsafe_authority(tmp_path: Path) -> None:
    """An unresolved quota hold makes the quota projection unsafe."""

    now = datetime.now(UTC)
    ledger, receipt = _authorize_quota(tmp_path, now)
    _ = ledger.mark_quota_authorization_uncertain(
        receipt.authorization_id, occurred_at=now + timedelta(seconds=1)
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.dispatch_lanes.lanes[0].quotas[0].reason_code == "quota-authority-uncertain"
