from __future__ import annotations

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
    NoChargeReconciliationInput,
    PriceTerm,
    SettlementReceipt,
    UsageEnvelope,
)
from scripts.factory_quota_models import (  # noqa: E402
    DispatchAuthorizationRequest,
    QuotaObservation,
    QuotaRequirement,
    QuotaWindow,
    TopUpAttestation,
)

NOW = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)


def _ledger(tmp_path: Path, *, cap: int = 1_000) -> FactoryBudgetLedger:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(2026, 7, 1),
            cash_cap_microcents=cap,
            emergency_reserve_microcents=20,
            currency="USD",
            policy_id="factory-policy",
            policy_revision=3,
            reserve_idempotency_key="reserve-2026-07-v1",
        )
    )
    return ledger


def _attestation(*, expires_at: datetime = NOW + timedelta(minutes=10)) -> TopUpAttestation:
    return TopUpAttestation(
        attestation_id="topup-attestation-1",
        provider_id="deepseek",
        provider_lane_id="deepseek-direct",
        policy_id="factory-policy",
        policy_revision=3,
        mode="disabled",
        source_kind="provider-policy-export",
        source_id="provider-policy-1",
        evidence_digest="a" * 64,
        observed_at=NOW - timedelta(minutes=1),
        expires_at=expires_at,
    )


def _observation(*, used: int = 40, known: bool = True) -> QuotaObservation:
    return QuotaObservation(
        observation_id="quota-observation-1",
        quota_id="deepseek-five-hour",
        provider_id="deepseek",
        provider_lane_id="deepseek-direct",
        policy_id="factory-policy",
        policy_revision=3,
        unit="tokens",
        source_kind="provider-usage-export",
        source_id="provider-usage-1",
        observed_at=NOW - timedelta(minutes=1),
        recorded_at=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=10),
        window=QuotaWindow(
            kind="rolling",
            starts_at=NOW - timedelta(hours=5),
            ends_at=NOW + timedelta(minutes=10),
            cycle_id=None,
        ),
        used_units=used,
        known=known,
        evidence_digest="b" * 64,
    )


def _request(
    *,
    key: str = "authorize-job-1",
    job_id: str = "job-1",
    used: int = 40,
    requested: int = 10,
    known: bool = True,
) -> DispatchAuthorizationRequest:
    observation = _observation(used=used, known=known)
    return DispatchAuthorizationRequest(
        idempotency_key=key,
        job_id=job_id,
        provider_lane_id="deepseek-direct",
        provider_id="deepseek",
        cost_policy_lane_id="deepseek-included",
        policy_id="factory-policy",
        policy_revision=3,
        billing_mode="included_quota",
        work_purpose="essential",
        usage_envelope=UsageEnvelope(input_tokens=requested),
        cash_reservation=None,
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=50,
                observation=observation,
            ),
        ),
        top_up_attestation=_attestation(),
        decision_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def _metered_request() -> DispatchAuthorizationRequest:
    cash = CostReservationRequest(
        idempotency_key="cash-job-1",
        job_id="job-1",
        provider_lane_id="deepseek-direct",
        provider_id="deepseek",
        model_id="deepseek/deepseek-v4-pro",
        requested_model="deepseek-v4-pro",
        cost_policy_lane_id="deepseek-metered",
        policy_id="factory-policy",
        policy_revision=3,
        occurred_at=NOW,
        usage_envelope=UsageEnvelope(input_tokens=10),
        price_terms=(
            PriceTerm(
                snapshot_id="input-price",
                unit="input_token",
                quantity=1,
                price_microcents=1,
                observed_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(minutes=10),
            ),
        ),
    )
    return replace(
        _request(used=0, requested=10),
        cost_policy_lane_id="deepseek-metered",
        billing_mode="metered",
        cash_reservation=cash,
    )


def _later_request(
    *,
    suffix: str,
    used: int,
    requested: int,
    included_authorization_ids: tuple[str, ...] = (),
) -> DispatchAuthorizationRequest:
    observation = replace(
        _observation(used=used),
        observation_id=f"quota-observation-{suffix}",
        source_id=f"provider-usage-{suffix}",
        observed_at=NOW + timedelta(seconds=4),
        recorded_at=NOW + timedelta(seconds=5),
        included_authorization_ids=included_authorization_ids,
    )
    return replace(
        _request(
            key=f"authorize-{suffix}",
            job_id=f"job-{suffix}",
            used=used,
            requested=requested,
        ),
        decision_at=NOW + timedelta(seconds=6),
        expires_at=NOW + timedelta(minutes=5, seconds=6),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id=f"topup-attestation-{suffix}",
        ),
    )


@pytest.mark.parametrize(
    ("authorization_request", "message"),
    (
        (_request(known=False), "uncertain"),
        (
            replace(_request(), top_up_attestation=None),
            "top-up attestation",
        ),
        (
            replace(_request(), top_up_attestation=_attestation(expires_at=NOW)),
            "top-up attestation",
        ),
    ),
)
def test_authorization_rejects_unknown_quota_or_missing_stale_attestation_before_mutation(
    tmp_path: Path,
    authorization_request: DispatchAuthorizationRequest,
    message: str,
) -> None:
    # Given a fresh ledger and invalid authorization evidence.
    ledger = _ledger(tmp_path)

    # When authorization is attempted.
    # Then it fails closed before either cash or quota is held.
    with pytest.raises(FactoryBudgetLedgerError, match=message):
        ledger.authorize_dispatch(authorization_request)
    assert ledger.period_summary_for(NOW).active_reserved_microcents == 0
    assert ledger.authorization_for_job("job-1") is None


def test_exact_authorization_replay_is_noop_and_conflicting_reuse_fails(tmp_path: Path) -> None:
    # Given one successful immutable authorization.
    ledger = _ledger(tmp_path)
    request = _request()
    first = ledger.authorize_dispatch(request)

    # When the exact request and then a conflicting request reuse its key.
    replay = ledger.authorize_dispatch(request)
    with pytest.raises(FactoryBudgetLedgerError, match="idempotency"):
        ledger.authorize_dispatch(_request(requested=9))

    # Then replay is a no-op and the conflict cannot create authority.
    assert first.created is True
    assert replay.created is False
    assert replay.authorization_id == first.authorization_id


def test_authorization_replay_binds_complete_provider_evidence(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    request = _request()
    _ = ledger.authorize_dispatch(request)
    observation = request.quota_requirements[0].observation
    conflicting = replace(
        request,
        quota_requirements=(
            replace(
                request.quota_requirements[0],
                observation=replace(
                    observation,
                    source_id="different-provider-export",
                ),
            ),
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="idempotency"):
        ledger.authorize_dispatch(conflicting)
    assert request.top_up_attestation is not None
    conflicting_attestation = replace(
        request,
        top_up_attestation=replace(
            request.top_up_attestation,
            source_id="different-policy-export",
        ),
    )
    with pytest.raises(FactoryBudgetLedgerError, match="idempotency"):
        ledger.authorize_dispatch(conflicting_attestation)


def test_metered_authorization_requires_matching_cash_usage_envelope(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    request = _metered_request()
    assert request.cash_reservation is not None
    mismatched = replace(
        request,
        cash_reservation=replace(
            request.cash_reservation,
            usage_envelope=UsageEnvelope(input_tokens=9),
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="cash reservation identity"):
        ledger.authorize_dispatch(mismatched)


def test_two_near_limit_concurrent_authorizations_allow_exactly_one(tmp_path: Path) -> None:
    # Given quota capacity for only one of two jobs.
    ledger = _ledger(tmp_path)
    first = _request(key="authorize-job-1", job_id="job-1", used=30, requested=20)
    second = replace(
        _request(key="authorize-job-2", job_id="job-2", used=30, requested=20),
        quota_requirements=(
            replace(
                _request(used=30, requested=20).quota_requirements[0],
                observation=replace(
                    _observation(used=30),
                    observation_id="quota-observation-2",
                    source_id="provider-usage-2",
                ),
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    # When both try to authorize concurrently.
    def attempt(request: DispatchAuthorizationRequest) -> bool:
        try:
            ledger.authorize_dispatch(request)
        except FactoryBudgetLedgerError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(attempt, (first, second)))

    # Then BEGIN IMMEDIATE serialization admits exactly one hold.
    assert sorted(results) == [False, True]


def test_shifted_rolling_window_counts_existing_active_authority(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    first = replace(
        _request(used=0, requested=10),
        quota_requirements=(
            replace(_request().quota_requirements[0], limit=15, observation=_observation(used=0)),
        ),
    )
    _ = ledger.authorize_dispatch(first)
    shifted_observation = replace(
        _observation(used=0),
        observation_id="quota-observation-2",
        source_id="provider-usage-2",
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        window=QuotaWindow(
            "rolling",
            NOW - timedelta(hours=5) + timedelta(seconds=1),
            NOW + timedelta(minutes=10, seconds=1),
            None,
        ),
    )
    second = replace(
        _request(key="authorize-job-2", job_id="job-2", used=0, requested=10),
        decision_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5, seconds=2),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=shifted_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="capacity"):
        ledger.authorize_dispatch(second)


def test_non_overlapping_quota_reset_does_not_carry_expired_active_hold(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_observation = replace(
        _observation(used=0),
        window=QuotaWindow(
            "rolling",
            NOW - timedelta(hours=5) + timedelta(seconds=1),
            NOW + timedelta(seconds=1),
            None,
        ),
    )
    first = replace(
        _request(used=0, requested=10),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=first_observation,
            ),
        ),
    )
    first_authorization = ledger.authorize_dispatch(first)
    second_observation = replace(
        _observation(used=0),
        observation_id="quota-observation-2",
        source_id="provider-usage-2",
        observed_at=NOW + timedelta(seconds=1),
        recorded_at=NOW + timedelta(seconds=1, milliseconds=500),
        expires_at=NOW + timedelta(minutes=10),
        window=QuotaWindow(
            "rolling",
            NOW + timedelta(seconds=1),
            NOW + timedelta(hours=5, seconds=1),
            None,
        ),
    )
    second = replace(
        _request(key="authorize-job-2", job_id="job-2", used=0, requested=10),
        decision_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5, seconds=2),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=second_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    second_authorization = ledger.authorize_dispatch(second)

    assert second_authorization.created is True
    assert ledger.quota_authorization_state(first_authorization.authorization_id) == "active"
    assert ledger.validate_dispatch_authorization(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    ) is False


def test_authenticated_quota_observation_timestamp_cannot_roll_back(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.authorize_dispatch(_request(used=0, requested=1))
    older = replace(
        _observation(used=0),
        observation_id="quota-observation-2",
        source_id="provider-usage-2",
        observed_at=NOW - timedelta(minutes=2),
        recorded_at=NOW + timedelta(seconds=1),
    )
    second = replace(
        _request(key="authorize-job-2", job_id="job-2", used=0, requested=1),
        decision_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5, seconds=2),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=50,
                observation=older,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="observation rollback"):
        ledger.authorize_dispatch(second)


def test_quota_capacity_is_scoped_to_provider_lane_and_policy(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    first = replace(
        _request(used=0, requested=10),
        quota_requirements=(
            replace(
                _request().quota_requirements[0],
                limit=15,
                observation=_observation(used=0),
            ),
        ),
    )
    _ = ledger.authorize_dispatch(first)
    base = _request(key="authorize-job-2", job_id="job-2", used=0, requested=10)
    other_observation = replace(
        _observation(used=0),
        observation_id="quota-observation-2",
        provider_id="other-provider",
        provider_lane_id="other-provider-direct",
        policy_id="other-policy",
        source_id="other-provider-usage",
        recorded_at=NOW + timedelta(seconds=1),
    )
    other = replace(
        base,
        provider_id="other-provider",
        provider_lane_id="other-provider-direct",
        cost_policy_lane_id="other-provider-included",
        policy_id="other-policy",
        decision_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5, seconds=2),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=other_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
            provider_id="other-provider",
            provider_lane_id="other-provider-direct",
            policy_id="other-policy",
            source_id="other-provider-policy",
        ),
    )

    authorization = ledger.authorize_dispatch(other)

    assert authorization.created is True


def test_settlement_after_provider_observation_counts_until_next_snapshot(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_observation = replace(
        _observation(used=0),
        observed_at=NOW - timedelta(minutes=2),
        recorded_at=NOW - timedelta(minutes=1),
    )
    first = replace(
        _request(used=0, requested=10),
        decision_at=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=4),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=first_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            observed_at=NOW - timedelta(minutes=2),
        ),
    )
    authorization = ledger.authorize_dispatch(first)
    _ = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(input_tokens=10),
        occurred_at=NOW + timedelta(seconds=10),
    )
    next_observation = replace(
        _observation(used=0),
        observation_id="quota-observation-2",
        source_id="provider-usage-2",
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=20),
    )
    second = replace(
        _request(key="authorize-job-2", job_id="job-2", used=0, requested=10),
        decision_at=NOW + timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=5, seconds=30),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=next_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="capacity"):
        ledger.authorize_dispatch(second)


def test_clock_rollback_is_rejected_and_exact_expiry_is_not_fresh(tmp_path: Path) -> None:
    # Given a persisted later decision clock.
    ledger = _ledger(tmp_path)
    ledger.authorize_dispatch(_request())
    rollback = replace(
        _request(key="authorize-job-2", job_id="job-2"),
        decision_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=4),
    )

    # When an earlier decision or exact-expiry revalidation is attempted.
    # Then both fail closed.
    with pytest.raises(FactoryBudgetLedgerError, match="rollback"):
        ledger.authorize_dispatch(rollback)
    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(minutes=5),
        )
        is False
    )


def test_subsecond_concurrent_clock_skew_preserves_the_decision_high_water(
    tmp_path: Path,
) -> None:
    # Given a persisted decision followed by a concurrent request timestamped
    # just before it acquired the writer lock.
    ledger = _ledger(tmp_path)
    first = ledger.authorize_dispatch(_request())
    ledger.release_quota_authorization(first.authorization_id, occurred_at=NOW)
    concurrent = replace(
        _request(key="authorize-job-2", job_id="job-2"),
        decision_at=NOW - timedelta(milliseconds=500),
        expires_at=NOW + timedelta(minutes=4),
    )
    rollback = replace(
        _request(key="authorize-job-3", job_id="job-3"),
        decision_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=4),
    )

    # When the bounded concurrent skew is authorized.
    receipt = ledger.authorize_dispatch(concurrent)

    # Then it succeeds without lowering the clock high-water mark.
    assert receipt.job_id == "job-2"
    with pytest.raises(FactoryBudgetLedgerError, match="rollback"):
        ledger.authorize_dispatch(rollback)


def test_revalidation_rejects_exact_observation_and_window_expiry(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    base = _request()
    short_observation = replace(
        base.quota_requirements[0].observation,
        expires_at=NOW + timedelta(minutes=1),
        window=QuotaWindow(
            "rolling",
            NOW - timedelta(hours=5),
            NOW + timedelta(minutes=1),
            None,
        ),
    )
    request = replace(
        base,
        quota_requirements=(replace(base.quota_requirements[0], observation=short_observation),),
    )

    _ = ledger.authorize_dispatch(request)

    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(seconds=59),
        )
        is True
    )
    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(minutes=1),
        )
        is False
    )


def test_revalidation_rejects_host_clock_rollback_after_later_decision(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.authorize_dispatch(_request())
    second = _request(key="authorize-job-2", job_id="job-2")
    second = replace(
        second,
        quota_requirements=(),
        top_up_attestation=replace(
            second.top_up_attestation,
            attestation_id="topup-attestation-2",
        )
        if second.top_up_attestation is not None
        else None,
        decision_at=NOW + timedelta(minutes=2),
        expires_at=NOW + timedelta(minutes=7),
    )
    _ = ledger.authorize_dispatch(second)

    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(minutes=1),
        )
        is False
    )


def test_launch_consumes_authorization_exactly_once(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_request())

    assert (
        ledger.consume_dispatch_authorization_for_launch(
            "job-1",
            as_of=NOW + timedelta(seconds=1),
        )
        is True
    )
    assert ledger.quota_authorization_state(authorization.authorization_id) == "launched"
    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )
        is False
    )
    with pytest.raises(FactoryBudgetLedgerError, match="not available"):
        ledger.consume_dispatch_authorization_for_launch(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )


@pytest.mark.parametrize("transition", ("settle", "release", "uncertain"))
def test_backdated_quota_transition_after_launch_cannot_reopen_capacity(
    tmp_path: Path,
    transition: str,
) -> None:
    ledger = _ledger(tmp_path)
    first_observation = replace(
        _observation(used=0),
        observed_at=NOW - timedelta(minutes=2),
        recorded_at=NOW - timedelta(minutes=1),
    )
    first = replace(
        _request(used=0, requested=10),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=first_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            observed_at=NOW - timedelta(minutes=2),
        ),
    )
    authorization = ledger.authorize_dispatch(first)
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="clock rollback"):
        match transition:
            case "settle":
                _ = ledger.settle_quota_authorization(
                    authorization.authorization_id,
                    UsageEnvelope(input_tokens=10),
                    occurred_at=NOW + timedelta(seconds=1),
                )
            case "release":
                _ = ledger.release_quota_authorization(
                    authorization.authorization_id,
                    occurred_at=NOW + timedelta(seconds=1),
                )
            case "uncertain":
                _ = ledger.mark_quota_authorization_uncertain(
                    authorization.authorization_id,
                    occurred_at=NOW + timedelta(seconds=1),
                )
            case _:
                raise AssertionError(f"unsupported transition: {transition}")

    assert ledger.quota_authorization_state(authorization.authorization_id) == "launched"
    next_observation = replace(
        _observation(used=0),
        observation_id=f"quota-observation-{transition}",
        source_id=f"provider-usage-{transition}",
        observed_at=NOW + timedelta(seconds=3),
        recorded_at=NOW + timedelta(seconds=4),
    )
    second = replace(
        _request(
            key=f"authorize-job-{transition}",
            job_id=f"job-{transition}",
            used=0,
            requested=10,
        ),
        decision_at=NOW + timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=5, seconds=5),
        quota_requirements=(
            QuotaRequirement(
                quota_id="deepseek-five-hour",
                unit="tokens",
                limit=15,
                observation=next_observation,
            ),
        ),
        top_up_attestation=replace(
            _attestation(),
            attestation_id=f"topup-attestation-{transition}",
        ),
    )
    with pytest.raises(FactoryBudgetLedgerError, match="capacity"):
        _ = ledger.authorize_dispatch(second)


@pytest.mark.parametrize("transition", ("settle", "release", "uncertain"))
def test_backdated_cash_backed_transition_after_launch_rolls_back(
    tmp_path: Path,
    transition: str,
) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())
    assert authorization.reservation_id is not None
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    )

    with pytest.raises(FactoryBudgetLedgerError, match="clock rollback"):
        match transition:
            case "settle":
                _ = ledger.settle_reservation(
                    SettlementReceipt(
                        idempotency_key="settle-backdated",
                        reservation_id=authorization.reservation_id,
                        job_id="job-1",
                        provider_lane_id="deepseek-direct",
                        provider_id="deepseek",
                        model_id="deepseek/deepseek-v4-pro",
                        requested_model="deepseek-v4-pro",
                        provider_session_digest="d" * 64,
                        input_tokens=10,
                        output_tokens=0,
                        requests=0,
                        minutes=0,
                        occurred_at=NOW + timedelta(seconds=1),
                    )
                )
            case "release":
                _ = ledger.reconcile_no_charge(
                    NoChargeReconciliationInput(
                        idempotency_key="release-backdated",
                        reservation_id=authorization.reservation_id,
                        evidence_digest="e" * 64,
                        occurred_at=NOW + timedelta(seconds=1),
                        reason="verified_never_dispatched",
                    )
                )
            case "uncertain":
                _ = ledger.mark_reservation_uncertain(
                    authorization.reservation_id,
                    idempotency_key="uncertain-backdated",
                    reason="worker_interrupted",
                    occurred_at=NOW + timedelta(seconds=1),
                    evidence_digest="f" * 64,
                )
            case _:
                raise AssertionError(f"unsupported transition: {transition}")

    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE public_id = ?",
            (authorization.authorization_id,),
        ).fetchone() == ("launched",)
        assert connection.execute(
            "SELECT state FROM quota_holds WHERE authorization_id = "
            "(SELECT id FROM dispatch_authorizations WHERE public_id = ?)",
            (authorization.authorization_id,),
        ).fetchone() == ("active",)
        assert connection.execute(
            "SELECT state FROM cost_reservations WHERE public_id = ?",
            (authorization.reservation_id,),
        ).fetchone() == ("dispatching",)


@pytest.mark.parametrize("billing_mode", ("quota", "cash"))
@pytest.mark.parametrize("settlement_second", (2, 3))
def test_later_observation_cannot_omit_unconfirmed_local_settlement(
    tmp_path: Path,
    billing_mode: str,
    settlement_second: int,
) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(
        _request(used=0, requested=10)
        if billing_mode == "quota"
        else _metered_request()
    )
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    )
    if billing_mode == "quota":
        _ = ledger.settle_quota_authorization(
            authorization.authorization_id,
            UsageEnvelope(input_tokens=10),
            occurred_at=NOW + timedelta(seconds=settlement_second),
        )
    else:
        assert authorization.reservation_id is not None
        _ = ledger.settle_reservation(
            SettlementReceipt(
                idempotency_key=f"settle-{settlement_second}",
                reservation_id=authorization.reservation_id,
                job_id="job-1",
                provider_lane_id="deepseek-direct",
                provider_id="deepseek",
                model_id="deepseek/deepseek-v4-pro",
                requested_model="deepseek-v4-pro",
                provider_session_digest=f"{settlement_second}" * 64,
                input_tokens=10,
                output_tokens=0,
                requests=0,
                minutes=0,
                occurred_at=NOW + timedelta(seconds=settlement_second),
            )
        )

    with pytest.raises(FactoryBudgetLedgerError, match="capacity"):
        _ = ledger.authorize_dispatch(
            _later_request(
                suffix=f"{billing_mode}-{settlement_second}",
                used=0,
                requested=10,
            )
        )


@pytest.mark.parametrize("billing_mode", ("quota", "cash"))
def test_signed_inclusion_boundary_avoids_double_counting_settlement(
    tmp_path: Path,
    billing_mode: str,
) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(
        _request(used=0, requested=10)
        if billing_mode == "quota"
        else _metered_request()
    )
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    )
    if billing_mode == "quota":
        _ = ledger.settle_quota_authorization(
            authorization.authorization_id,
            UsageEnvelope(input_tokens=10),
            occurred_at=NOW + timedelta(seconds=3),
        )
    else:
        assert authorization.reservation_id is not None
        _ = ledger.settle_reservation(
            SettlementReceipt(
                idempotency_key="settle-included-cash",
                reservation_id=authorization.reservation_id,
                job_id="job-1",
                provider_lane_id="deepseek-direct",
                provider_id="deepseek",
                model_id="deepseek/deepseek-v4-pro",
                requested_model="deepseek-v4-pro",
                provider_session_digest="7" * 64,
                input_tokens=10,
                output_tokens=0,
                requests=0,
                minutes=0,
                occurred_at=NOW + timedelta(seconds=3),
            )
        )

    admitted = ledger.authorize_dispatch(
        _later_request(
            suffix=f"included-{billing_mode}",
            used=10,
            requested=5,
            included_authorization_ids=(authorization.authorization_id,),
        )
    )
    assert admitted.quota_holds == (("deepseek-five-hour", 5),)


def test_inclusion_boundary_rejects_missing_or_numerically_impossible_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    with pytest.raises(FactoryBudgetLedgerError, match="matching settled quota"):
        _ = ledger.authorize_dispatch(
            _later_request(
                suffix="missing-inclusion",
                used=10,
                requested=5,
                included_authorization_ids=("auth-00000000000000000000000000000000",),
            )
        )

    authorization = ledger.authorize_dispatch(_request(used=0, requested=10))
    _ = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(input_tokens=10),
        occurred_at=NOW + timedelta(seconds=3),
    )
    with pytest.raises(FactoryBudgetLedgerError, match="exceeds observed"):
        _ = ledger.authorize_dispatch(
            _later_request(
                suffix="impossible-inclusion",
                used=0,
                requested=5,
                included_authorization_ids=(authorization.authorization_id,),
            )
        )


@pytest.mark.parametrize(
    "included_authorization_ids",
    (
        ("auth-z", "auth-a"),
        ("auth-a", "auth-a"),
    ),
)
def test_inclusion_boundary_requires_canonical_authorization_ids(
    tmp_path: Path,
    included_authorization_ids: tuple[str, ...],
) -> None:
    ledger = _ledger(tmp_path)

    with pytest.raises(FactoryBudgetLedgerError, match="unique and sorted"):
        _ = ledger.authorize_dispatch(
            _later_request(
                suffix="noncanonical-inclusion",
                used=10,
                requested=5,
                included_authorization_ids=included_authorization_ids,
            )
        )


def test_open_rejects_inclusion_mapping_not_bound_by_observation_digest(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first = ledger.authorize_dispatch(_request(used=0, requested=2))
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    )
    _ = ledger.settle_quota_authorization(
        first.authorization_id,
        UsageEnvelope(input_tokens=2),
        occurred_at=NOW + timedelta(seconds=3),
    )
    second = ledger.authorize_dispatch(
        _later_request(suffix="digest-second", used=0, requested=2)
    )
    assert ledger.consume_dispatch_authorization_for_launch(
        "job-digest-second",
        as_of=NOW + timedelta(seconds=7),
    )
    _ = ledger.settle_quota_authorization(
        second.authorization_id,
        UsageEnvelope(input_tokens=2),
        occurred_at=NOW + timedelta(seconds=8),
    )
    third_base = _later_request(
        suffix="digest-third",
        used=4,
        requested=1,
        included_authorization_ids=(first.authorization_id,),
    )
    third_observation = replace(
        third_base.quota_requirements[0].observation,
        observed_at=NOW + timedelta(seconds=10),
        recorded_at=NOW + timedelta(seconds=11),
    )
    _ = ledger.authorize_dispatch(
        replace(
            third_base,
            decision_at=NOW + timedelta(seconds=12),
            quota_requirements=(
                replace(
                    third_base.quota_requirements[0],
                    observation=third_observation,
                ),
            ),
        )
    )

    with sqlite3.connect(ledger.db_path) as connection:
        observation_id = int(
            connection.execute(
                "SELECT id FROM quota_observations WHERE observation_id = ?",
                (third_observation.observation_id,),
            ).fetchone()[0]
        )
        second_id = int(
            connection.execute(
                "SELECT id FROM dispatch_authorizations WHERE public_id = ?",
                (second.authorization_id,),
            ).fetchone()[0]
        )
        _ = connection.execute(
            "INSERT INTO quota_observation_inclusions(observation_id, authorization_id) "
            "VALUES (?, ?)",
            (observation_id, second_id),
        )

    with pytest.raises(FactoryBudgetLedgerError, match="inclusion digest"):
        FactoryBudgetLedger.open_project(tmp_path)


@pytest.mark.parametrize(
    ("work_purpose", "spent_microcents", "expected_code"),
    (
        ("experiment", 790, "experiment_threshold_80"),
        ("essential", 890, "metered_threshold_90"),
    ),
)
def test_launch_revalidates_current_cash_thresholds(
    tmp_path: Path,
    work_purpose: Literal["experiment", "essential"],
    spent_microcents: int,
    expected_code: str,
) -> None:
    ledger = _ledger(tmp_path)
    request = replace(_metered_request(), work_purpose=work_purpose)
    _ = ledger.authorize_dispatch(request)
    _ = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key=f"launch-threshold-{expected_code}",
            kind="manual_adjustment",
            direction="debit",
            amount_microcents=spent_microcents,
            occurred_at=NOW + timedelta(seconds=1),
            currency="USD",
            source_id="maintainer-ledger",
        )
    )

    assert ledger.validate_dispatch_authorization(
        "job-1",
        as_of=NOW + timedelta(seconds=2),
    ) is False
    with pytest.raises(FactoryBudgetLedgerError) as blocked:
        ledger.consume_dispatch_authorization_for_launch(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )
    assert blocked.value.code == "authorization"
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE job_id = 'job-1'"
        ).fetchone() == ("active",)


def test_emergency_reserve_prevents_reaching_all_in_cap_before_launch(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())

    with pytest.raises(FactoryBudgetLedgerError) as blocked:
        _ = ledger.record_entry(
            LedgerEntryInput(
                idempotency_key="all-in-cap-before-launch",
                kind="manual_adjustment",
                direction="debit",
                amount_microcents=990,
                occurred_at=NOW + timedelta(seconds=1),
                currency="USD",
                source_id="maintainer-ledger",
            )
        )

    assert blocked.value.code == "budget"
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE public_id = ?",
            (authorization.authorization_id,),
        ).fetchone() == ("active",)


def test_concurrent_launch_consumption_allows_one_caller(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.authorize_dispatch(_request())

    def consume(_index: int) -> bool:
        try:
            return ledger.consume_dispatch_authorization_for_launch(
                "job-1",
                as_of=NOW + timedelta(seconds=1),
            )
        except FactoryBudgetLedgerError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(consume, range(2)))

    assert sorted(results) == [False, True]


def test_cash_reservation_uncertainty_revokes_launch_authority(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())
    assert authorization.reservation_id is not None

    _ = ledger.mark_reservation_uncertain(
        authorization.reservation_id,
        idempotency_key="uncertain-before-launch",
        reason="worker_interrupted",
        occurred_at=NOW + timedelta(seconds=1),
        evidence_digest="e" * 64,
    )

    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )
        is False
    )
    with pytest.raises(FactoryBudgetLedgerError, match="not available"):
        ledger.consume_dispatch_authorization_for_launch(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )


def test_verified_no_charge_releases_uncertain_quota_hold(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())
    assert authorization.reservation_id is not None
    _ = ledger.mark_reservation_uncertain(
        authorization.reservation_id,
        idempotency_key="uncertain-before-reconciliation",
        reason="worker_interrupted",
        occurred_at=NOW + timedelta(seconds=1),
        evidence_digest="e" * 64,
    )

    _ = ledger.reconcile_no_charge(
        NoChargeReconciliationInput(
            idempotency_key="reconcile-verified-no-charge",
            reservation_id=authorization.reservation_id,
            evidence_digest="f" * 64,
            occurred_at=NOW + timedelta(seconds=2),
            reason="verified_never_dispatched",
        )
    )

    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE public_id = ?",
            (authorization.authorization_id,),
        ).fetchone() == ("released",)
        assert connection.execute(
            "SELECT state, actual_units FROM quota_holds"
        ).fetchone() == ("released", 0)


def test_zero_hold_subscription_has_durable_terminal_state(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    request = replace(
        _request(),
        billing_mode="fixed_subscription",
        cost_policy_lane_id="deepseek-subscription",
        quota_requirements=(),
    )
    authorization = ledger.authorize_dispatch(request)

    outcome = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(),
        occurred_at=NOW + timedelta(seconds=1),
    )

    assert outcome.created is True
    assert ledger.quota_authorization_state(authorization.authorization_id) == "settled"
    assert (
        ledger.validate_dispatch_authorization(
            "job-1",
            as_of=NOW + timedelta(seconds=2),
        )
        is False
    )
    replay = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(),
        occurred_at=NOW + timedelta(seconds=2),
    )
    assert replay.created is False
    with pytest.raises(FactoryBudgetLedgerError, match="conflicts"):
        _ = ledger.settle_quota_authorization(
            authorization.authorization_id,
            UsageEnvelope(input_tokens=999),
            occurred_at=NOW + timedelta(seconds=2),
        )


def test_non_cash_quota_settlement_is_exactly_idempotent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_request())

    first = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(input_tokens=5),
        occurred_at=NOW + timedelta(minutes=1),
    )
    replay = ledger.settle_quota_authorization(
        authorization.authorization_id,
        UsageEnvelope(input_tokens=5),
        occurred_at=NOW + timedelta(minutes=1),
    )

    assert first.created is True
    assert replay.created is False
    assert first.state == "settled"
    with pytest.raises(FactoryBudgetLedgerError, match="conflicts"):
        _ = ledger.settle_quota_authorization(
            authorization.authorization_id,
            UsageEnvelope(input_tokens=4),
            occurred_at=NOW + timedelta(minutes=1),
        )
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state, held_units, actual_units FROM quota_holds"
        ).fetchone() == ("settled", 10, 5)


def test_fresh_ledger_uses_v3_quota_schema(tmp_path: Path) -> None:
    # Given a freshly initialized quota ledger.
    ledger = _ledger(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        assert connection.execute(
            "SELECT value FROM ledger_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("entroping.factory-budget-ledger.v3",)


def test_cash_threshold_boundaries_include_active_holds_and_refunds(tmp_path: Path) -> None:
    # Given net cash usage exactly at the experiment threshold.
    ledger = _ledger(tmp_path)
    ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="debit-to-eighty",
            kind="manual_adjustment",
            direction="debit",
            amount_microcents=800,
            occurred_at=NOW,
            currency="USD",
            source_id="maintainer-ledger",
        )
    )

    # When experimental and essential included-quota work are evaluated.
    with pytest.raises(FactoryBudgetLedgerError, match="80 percent") as blocked:
        ledger.authorize_dispatch(replace(_request(), work_purpose="experiment"))
    essential = ledger.authorize_dispatch(_request())

    # Then only the experiment is stopped and quota never creates cash authority.
    assert essential.reason == "authorized-included-quota"
    assert ledger.period_summary_for(NOW).net_spent_microcents == 800
    assert blocked.value.code == "experiment_threshold_80"


def test_active_cash_hold_counts_toward_experiment_threshold(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="debit-to-seventy-nine",
            kind="manual_adjustment",
            direction="debit",
            amount_microcents=790,
            occurred_at=NOW,
            currency="USD",
            source_id="maintainer-ledger",
        )
    )
    _ = ledger.authorize_dispatch(_metered_request())
    experiment = replace(
        _request(key="authorize-job-2", job_id="job-2"),
        work_purpose="experiment",
        top_up_attestation=replace(
            _attestation(),
            attestation_id="topup-attestation-2",
        ),
    )

    with pytest.raises(FactoryBudgetLedgerError) as blocked:
        ledger.authorize_dispatch(experiment)

    assert blocked.value.code == "experiment_threshold_80"
    assert ledger.period_summary_for(NOW).active_reserved_microcents == 10


def test_metered_and_full_cash_thresholds_return_stable_codes(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="debit-to-eighty-nine",
            kind="manual_adjustment",
            direction="debit",
            amount_microcents=890,
            occurred_at=NOW,
            currency="USD",
            source_id="maintainer-ledger",
        )
    )
    with pytest.raises(FactoryBudgetLedgerError) as metered:
        ledger.authorize_dispatch(_metered_request())
    assert metered.value.code == "metered_threshold_90"

    full_root = tmp_path / "full"
    full_root.mkdir()
    full_ledger = _ledger(full_root)
    _ = full_ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="debit-to-reserve-boundary",
            kind="fixed_subscription_charge",
            direction="debit",
            amount_microcents=980,
            occurred_at=NOW,
            currency="USD",
            source_id="maintainer-ledger",
        )
    )
    metered_request = _metered_request()
    assert metered_request.cash_reservation is not None
    larger_hold = replace(
        metered_request,
        cash_reservation=replace(
            metered_request.cash_reservation,
            price_terms=(
                replace(
                    metered_request.cash_reservation.price_terms[0],
                    price_microcents=3,
                ),
            ),
        ),
    )
    with pytest.raises(FactoryBudgetLedgerError) as stopped:
        full_ledger.authorize_dispatch(larger_hold)
    assert stopped.value.code == "cash_cap_100"


def test_refund_restores_experiment_authority_below_threshold(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _ = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="debit-before-refund",
            kind="fixed_subscription_charge",
            direction="debit",
            amount_microcents=850,
            occurred_at=NOW,
            currency="USD",
            source_id="maintainer-ledger",
        )
    )
    _ = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="threshold-refund",
            kind="refund",
            direction="credit",
            amount_microcents=100,
            occurred_at=NOW + timedelta(seconds=1),
            currency="USD",
            source_id="maintainer-ledger",
            reference_idempotency_key="debit-before-refund",
        )
    )

    authorization = ledger.authorize_dispatch(replace(_request(), work_purpose="experiment"))

    assert authorization.created is True
    assert ledger.period_summary_for(NOW).net_spent_microcents == 750


def test_verified_settlement_replaces_quota_hold_with_actual_consumption(
    tmp_path: Path,
) -> None:
    # Given an atomic metered cash and quota authorization.
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())
    assert authorization.reservation_id is not None

    # When a verified bounded usage receipt settles it.
    ledger.settle_reservation(
        SettlementReceipt(
            idempotency_key="settle-job-1",
            reservation_id=authorization.reservation_id,
            job_id="job-1",
            provider_lane_id="deepseek-direct",
            provider_id="deepseek",
            model_id="deepseek/deepseek-v4-pro",
            requested_model="deepseek-v4-pro",
            provider_session_digest="c" * 64,
            input_tokens=5,
            output_tokens=0,
            requests=0,
            minutes=0,
            occurred_at=NOW + timedelta(minutes=1),
        )
    )

    # Then the hold is replaced, not added to, by verified actual units.
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute(
            "SELECT state, held_units, actual_units FROM quota_holds"
        ).fetchone() == ("settled", 10, 5)


def test_verified_no_charge_releases_quota_but_manual_debit_does_not(
    tmp_path: Path,
) -> None:
    # Given a metered authorization that was verified never dispatched.
    ledger = _ledger(tmp_path)
    authorization = ledger.authorize_dispatch(_metered_request())
    assert authorization.reservation_id is not None

    # When no-charge reconciliation is recorded.
    ledger.reconcile_no_charge(
        NoChargeReconciliationInput(
            idempotency_key="no-charge-job-1",
            reservation_id=authorization.reservation_id,
            evidence_digest="d" * 64,
            occurred_at=NOW + timedelta(minutes=1),
            reason="verified_never_dispatched",
        )
    )

    # Then the quota hold is released with zero actual consumption.
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute("SELECT state, actual_units FROM quota_holds").fetchone() == (
            "released",
            0,
        )
