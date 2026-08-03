from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import FactoryBudgetLedger  # noqa: E402
from scripts.factory_cost_policy_models import FactoryCostPolicy  # noqa: E402
from scripts.factory_paid_dispatch import (  # noqa: E402
    PaidDispatchError,
    prepare_paid_dispatch,
    recover_paid_dispatch,
    revalidate_or_release_paid_dispatch,
    revalidate_paid_dispatch,
    settle_paid_dispatch,
)
from scripts.factory_paid_dispatch_policy import require_policy_quota_window  # noqa: E402
from scripts.factory_quota_models import (  # noqa: E402
    QuotaObservation,
    QuotaWindow,
    TopUpAttestation,
    subscription_cycle_window,
    utc_month_window,
)


def _top_up(now: datetime) -> TopUpAttestation:
    return TopUpAttestation(
        attestation_id="deepseek-topup-disabled",
        provider_id="deepseek",
        provider_lane_id="deepseek-api/direct",
        policy_id="paid-worker-policy",
        policy_revision=3,
        mode="disabled",
        source_kind="provider-policy-export",
        source_id="deepseek-account-policy",
        evidence_digest="f" * 64,
        observed_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
    )


def _write_policy(path: Path, *, now: datetime, model_id: str) -> Path:
    policy = {
        "schema_version": "entroping.factory-cost-policy.v1",
        "policy_id": "paid-worker-policy",
        "policy_revision": 3,
        "currency": "USD",
        "monetary_unit": "microcent",
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "unknown_cost_behavior": "deny_paid_dispatch",
        "unknown_quota_behavior": "deny_affected_paid_lane",
        "cash": {
            "calendar_month_timezone": "UTC",
            "calendar_month_cap_microcents": 10_000_000,
            "emergency_reserve_microcents": 1_000_000,
            "thresholds": {
                "stop_experiments_basis_points": 8000,
                "subscription_only_basis_points": 9000,
                "stop_paid_dispatch_basis_points": 10000,
            },
        },
        "subscriptions": [],
        "price_snapshots": [
            {
                "id": "deepseek-input-price",
                "provider_id": "deepseek",
                "model_id": model_id,
                "unit": "input_token",
                "quantity": 1_000_000,
                "price_microcents": 20_000,
                "observed_at": (now - timedelta(minutes=5)).isoformat(),
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
            {
                "id": "deepseek-output-price",
                "provider_id": "deepseek",
                "model_id": model_id,
                "unit": "output_token",
                "quantity": 1_000_000,
                "price_microcents": 80_000,
                "observed_at": (now - timedelta(minutes=5)).isoformat(),
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
        ],
        "provider_quotas": [],
        "automatic_top_up": {"mode": "disabled"},
        "automation_lanes": [
            {
                "id": "deepseek-pro-metered",
                "provider_id": "deepseek",
                "model_id": model_id,
                "billing_mode": "metered",
                "enabled": True,
                "price_snapshot_ids": [
                    "deepseek-input-price",
                    "deepseek-output-price",
                ],
                "quota_ids": [],
            }
        ],
    }
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def _direct_job() -> dict[str, object]:
    return {
        "job_id": "job-paid-direct",
        "engine": "deepseek-api",
        "model": "deepseek-v4-pro",
        "timeout_seconds": 300,
    }


def _policy_with_quota(
    tmp_path: Path,
    *,
    now: datetime,
    window: dict[str, object],
    subscriptions: list[dict[str, object]] | None = None,
) -> FactoryCostPolicy:
    path = _write_policy(
        tmp_path / "policy-with-quota.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["subscriptions"] = subscriptions or []
    payload["provider_quotas"] = [
        {
            "id": "deepseek-quota",
            "provider_id": "deepseek",
            "unit": "requests",
            "limit": 100,
            "window": window,
        }
    ]
    payload["automation_lanes"][0]["quota_ids"] = ["deepseek-quota"]
    return FactoryCostPolicy.model_validate_json(json.dumps(payload), strict=True)


def _quota_observation(now: datetime, window: QuotaWindow) -> QuotaObservation:
    return QuotaObservation(
        observation_id="deepseek-quota-observation",
        quota_id="deepseek-quota",
        provider_id="deepseek",
        provider_lane_id="deepseek-api/direct",
        policy_id="paid-worker-policy",
        policy_revision=3,
        unit="requests",
        source_kind="provider-usage-export",
        source_id="deepseek-usage",
        observed_at=now - timedelta(minutes=1),
        recorded_at=now - timedelta(seconds=30),
        expires_at=now + timedelta(minutes=10),
        window=window,
        used_units=0,
        known=True,
        evidence_digest="a" * 64,
    )


def test_policy_rejects_provider_rolling_window_with_wrong_duration(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _policy_with_quota(
        tmp_path,
        now=now,
        window={"kind": "rolling", "duration_seconds": 18_000},
    )
    observation = _quota_observation(
        now,
        QuotaWindow("rolling", now - timedelta(hours=1), now + timedelta(hours=1), None),
    )

    with pytest.raises(PaidDispatchError, match="policy duration"):
        require_policy_quota_window(
            policy,
            policy.provider_quotas[0],
            observation,
            decision_at=now,
        )


def test_policy_requires_exact_utc_calendar_month_window(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _policy_with_quota(
        tmp_path,
        now=now,
        window={"kind": "calendar_month", "timezone": "UTC"},
    )
    exact = _quota_observation(now, utc_month_window(now))
    require_policy_quota_window(
        policy,
        policy.provider_quotas[0],
        exact,
        decision_at=now,
    )
    shifted = _quota_observation(
        now,
        QuotaWindow(
            "calendar_month",
            datetime(2026, 7, 2, tzinfo=UTC),
            datetime(2026, 8, 2, tzinfo=UTC),
            None,
        ),
    )
    with pytest.raises(PaidDispatchError, match="policy boundary"):
        require_policy_quota_window(
            policy,
            policy.provider_quotas[0],
            shifted,
            decision_at=now,
        )


def test_policy_requires_exact_annual_subscription_cycle_and_id(tmp_path: Path) -> None:
    now = datetime(2028, 2, 29, tzinfo=UTC)
    subscription_id = "deepseek-annual-plan"
    policy = _policy_with_quota(
        tmp_path,
        now=now,
        window={"kind": "subscription_cycle", "subscription_id": subscription_id},
        subscriptions=[
            {
                "id": subscription_id,
                "provider_id": "deepseek",
                "charge_microcents": 1,
                "renewal": {
                    "kind": "annual",
                    "timezone": "UTC",
                    "month": 2,
                    "day": 29,
                    "invalid_date_behavior": "last_day",
                },
            }
        ],
    )
    cycle_id = "deepseek-annual-plan-2028-02-29"
    exact_window = subscription_cycle_window(
        now,
        renewal_month=2,
        renewal_day=29,
        cycle_id=cycle_id,
    )
    exact = _quota_observation(now, exact_window)
    require_policy_quota_window(
        policy,
        policy.provider_quotas[0],
        exact,
        decision_at=now,
    )
    with pytest.raises(PaidDispatchError, match="cycle id"):
        require_policy_quota_window(
            policy,
            policy.provider_quotas[0],
            _quota_observation(
                now,
                QuotaWindow(
                    "subscription_cycle",
                    exact_window.starts_at,
                    exact_window.ends_at,
                    "wrong-cycle",
                ),
            ),
            decision_at=now,
        )


def test_included_quota_launch_revalidation_releases_expired_hold(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy_path = _write_policy(
        tmp_path / "included-policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    payload["provider_quotas"] = [
        {
            "id": "deepseek-five-hour-requests",
            "provider_id": "deepseek",
            "unit": "requests",
            "limit": 100,
            "window": {"kind": "rolling", "duration_seconds": 18_000},
        }
    ]
    payload["automation_lanes"] = [
        {
            "id": "deepseek-included",
            "provider_id": "deepseek",
            "billing_mode": "included_quota",
            "enabled": True,
            "quota_ids": ["deepseek-five-hour-requests"],
        }
    ]
    policy_path.write_text(json.dumps(payload), encoding="utf-8")
    job: dict[str, object] = {
        "job_id": "job-included",
        "engine": "opencode",
        "model": "opencode/deepseek-v4-flash-free",
        "timeout_seconds": 300,
    }
    top_up = TopUpAttestation(
        attestation_id="included-topup-disabled",
        provider_id="deepseek",
        provider_lane_id="opencode/native-deepseek",
        policy_id="paid-worker-policy",
        policy_revision=3,
        mode="disabled",
        source_kind="provider-policy-export",
        source_id="deepseek-account-policy",
        evidence_digest="f" * 64,
        observed_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
    )
    observation = QuotaObservation(
        observation_id="included-quota-observation",
        quota_id="deepseek-five-hour-requests",
        provider_id="deepseek",
        provider_lane_id="opencode/native-deepseek",
        policy_id="paid-worker-policy",
        policy_revision=3,
        unit="requests",
        source_kind="provider-usage-export",
        source_id="deepseek-usage",
        observed_at=now - timedelta(minutes=1),
        recorded_at=now - timedelta(seconds=30),
        expires_at=now + timedelta(seconds=1),
        window=QuotaWindow(
            "rolling",
            now - timedelta(hours=1),
            now + timedelta(hours=4),
            None,
        ),
        used_units=0,
        known=True,
        evidence_digest="a" * 64,
    )

    authorization = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy_path,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=top_up,
        quota_observations=(observation,),
    )
    assert authorization is not None
    job.update(authorization.job_projection())

    assert revalidate_or_release_paid_dispatch(
        tmp_path,
        job,
        occurred_at=now + timedelta(seconds=1),
    ) is False
    with sqlite3.connect(FactoryBudgetLedger.open_project(tmp_path).db_path) as connection:
        assert connection.execute(
            "SELECT state, actual_units FROM quota_holds"
        ).fetchone() == ("released", 0)


def test_consumed_paid_authorization_cannot_launch_or_release_twice(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    assert revalidate_or_release_paid_dispatch(
        tmp_path,
        job,
        occurred_at=now + timedelta(seconds=1),
    ) is True
    assert revalidate_or_release_paid_dispatch(
        tmp_path,
        job,
        occurred_at=now + timedelta(seconds=2),
    ) is False

    cash = FactoryBudgetLedger.reservation_for_job_readonly(
        tmp_path,
        "job-paid-direct",
    )
    assert cash is not None
    assert cash.state == "dispatching"
    with sqlite3.connect(FactoryBudgetLedger.open_project(tmp_path).db_path) as connection:
        assert connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE job_id = 'job-paid-direct'"
        ).fetchone() == ("launched",)


def test_paid_dispatch_reserves_worst_case_and_settles_provider_usage(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()

    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )

    assert reservation is not None
    assert reservation.held_microcents == 40_328
    job.update(reservation.job_projection())
    assert revalidate_paid_dispatch(
        tmp_path,
        job,
        occurred_at=now + timedelta(minutes=1),
    ).authorization_id == reservation.authorization_id
    with pytest.raises(PaidDispatchError, match="invalid or expired"):
        revalidate_paid_dispatch(
            tmp_path,
            job,
            occurred_at=now + timedelta(minutes=5),
        )
    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "accounted",
                "job_id": "job-paid-direct",
                "requested_model": "deepseek-v4-pro",
                "reported_model": "deepseek-v4-pro",
                "run_id": "run-1",
                "provider_session_digest": "a" * 64,
                "requests": 1,
                "input_tokens": 1_000,
                "output_tokens": 100,
                "total_tokens": 1_100,
            }
        },
        expected_run_id="run-1",
        occurred_at=now + timedelta(minutes=1),
    )

    assert outcome is not None
    assert outcome.state == "settled"
    assert outcome.actual_microcents == 28
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == 0
    assert summary.net_spent_microcents == 28


def test_paid_dispatch_blocks_missing_policy_before_reservation(tmp_path: Path) -> None:
    with pytest.raises(PaidDispatchError, match="cost policy is unavailable"):
        prepare_paid_dispatch(
            tmp_path,
            _direct_job(),
            policy_path=tmp_path / "missing.json",
            occurred_at=datetime(2026, 7, 29, 20, 0, tzinfo=UTC),
            worker_dry_run=False,
        )

    assert not (tmp_path / ".entroping" / "factory-budget").exists()


@pytest.mark.parametrize("timeout_seconds", (math.nan, math.inf, -math.inf, 86_401.0))
def test_paid_dispatch_rejects_non_finite_or_excessive_timeout(
    tmp_path: Path,
    timeout_seconds: float,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    job["timeout_seconds"] = timeout_seconds

    with pytest.raises(PaidDispatchError, match="job timeout is invalid"):
        prepare_paid_dispatch(
            tmp_path,
            job,
            policy_path=policy,
            occurred_at=now,
            worker_dry_run=False,
            top_up_attestation=_top_up(now),
        )

    assert not (tmp_path / ".entroping" / "factory-budget").exists()


def test_paid_dispatch_rejects_metered_opencode_without_enforceable_ceiling(
    tmp_path: Path,
) -> None:
    job: dict[str, object] = {
        "job_id": "job-paid-opencode",
        "engine": "opencode",
        "model": "deepseek/deepseek-v4-pro",
        "timeout_seconds": 300,
    }

    with pytest.raises(PaidDispatchError, match="enforceable usage ceiling"):
        prepare_paid_dispatch(
            tmp_path,
            job,
            policy_path=tmp_path / "unused.json",
            occurred_at=datetime(2026, 7, 29, 20, 0, tzinfo=UTC),
            worker_dry_run=False,
        )


def test_paid_dispatch_dry_run_bypasses_cash_reservation(tmp_path: Path) -> None:
    assert (
        prepare_paid_dispatch(
            tmp_path,
            _direct_job(),
            policy_path=tmp_path / "missing.json",
            occurred_at=datetime(2026, 7, 29, 20, 0, tzinfo=UTC),
            worker_dry_run=True,
        )
        is None
    )
    assert not (tmp_path / ".entroping").exists()


def test_paid_dispatch_recovery_finds_crash_window_hold_by_job_id(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None

    recovery = recover_paid_dispatch(
        tmp_path,
        job,
        occurred_at=now + timedelta(minutes=6),
    )

    assert recovery is not None
    assert recovery.queue_state == "failed"
    assert recovery.settlement_state == "unresolved"
    assert recovery.reservation_id == reservation.reservation_id
    stored = FactoryBudgetLedger.reservation_for_job_readonly(
        tmp_path,
        "job-paid-direct",
    )
    assert stored is not None
    assert stored.state == "uncertain"
    assert stored.reason == "worker_interrupted"


def test_paid_dispatch_recovery_terminalizes_already_settled_job(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())
    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "accounted",
                "job_id": "job-paid-direct",
                "requested_model": "deepseek-v4-pro",
                "reported_model": "deepseek-v4-pro",
                "run_id": "run-terminal",
                "provider_session_digest": "c" * 64,
                "requests": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            }
        },
        expected_run_id="run-terminal",
        occurred_at=now + timedelta(minutes=1),
    )
    assert outcome is not None
    assert outcome.state == "settled"

    recovery = recover_paid_dispatch(
        tmp_path,
        {"job_id": "job-paid-direct"},
        occurred_at=now + timedelta(minutes=6),
    )

    assert recovery is not None
    assert recovery.queue_state == "completed"
    assert recovery.settlement_state == "settled"


def test_paid_dispatch_verified_pre_network_block_releases_hold(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "unaccounted",
                "accounting_reason": "request_not_dispatched",
                "job_id": "job-paid-direct",
                "requested_model": "deepseek-v4-pro",
                "run_id": "run-pre-network-block",
            }
        },
        expected_run_id="run-pre-network-block",
        occurred_at=now + timedelta(seconds=1),
    )

    assert outcome is not None
    assert outcome.state == "reconciled"
    assert outcome.actual_microcents == 0
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == 0


def test_paid_dispatch_missing_worker_receipt_preserves_hold_as_uncertain(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {},
        expected_run_id="run-missing-receipt",
        occurred_at=now + timedelta(minutes=1),
    )

    assert outcome is not None
    assert outcome.state == "uncertain"
    assert outcome.reason == "partial_receipt"
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == reservation.held_microcents


def test_paid_dispatch_zero_usage_receipt_preserves_hold_as_uncertain(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "accounted",
                "job_id": "job-paid-direct",
                "requested_model": "deepseek-v4-pro",
                "reported_model": "deepseek-v4-pro",
                "run_id": "run-zero",
                "provider_session_digest": "d" * 64,
                "requests": 1,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        },
        expected_run_id="run-zero",
        occurred_at=now + timedelta(minutes=1),
    )

    assert outcome is not None
    assert outcome.state == "uncertain"
    assert outcome.reason == "zero_usage_receipt"
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == reservation.held_microcents


def test_paid_dispatch_receipt_must_match_validated_artifact_run(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "accounted",
                "job_id": "job-paid-direct",
                "requested_model": "deepseek-v4-pro",
                "reported_model": "deepseek-v4-pro",
                "run_id": "different-run",
                "provider_session_digest": "e" * 64,
                "requests": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            }
        },
        expected_run_id="validated-run",
        occurred_at=now + timedelta(minutes=1),
    )

    assert outcome is not None
    assert outcome.state == "uncertain"
    assert outcome.reason == "run_mismatch"
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == reservation.held_microcents


def test_paid_dispatch_no_charge_receipt_requires_bound_identity(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
    policy = _write_policy(
        tmp_path / "policy.json",
        now=now,
        model_id="deepseek/deepseek-v4-pro",
    )
    job = _direct_job()
    reservation = prepare_paid_dispatch(
        tmp_path,
        job,
        policy_path=policy,
        occurred_at=now,
        worker_dry_run=False,
        top_up_attestation=_top_up(now),
    )
    assert reservation is not None
    job.update(reservation.job_projection())

    outcome = settle_paid_dispatch(
        tmp_path,
        job,
        {
            "usage_receipt": {
                "accounting_status": "unaccounted",
                "accounting_reason": "request_not_dispatched",
            }
        },
        expected_run_id="validated-run",
        occurred_at=now + timedelta(minutes=1),
    )

    assert outcome is not None
    assert outcome.state == "uncertain"
    assert outcome.reason == "malformed_receipt"
    summary = FactoryBudgetLedger.open_project(tmp_path).period_summary_for(now)
    assert summary.active_reserved_microcents == reservation.held_microcents
