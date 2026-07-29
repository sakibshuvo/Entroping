from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import FactoryBudgetLedger  # noqa: E402
from scripts.factory_paid_dispatch import (  # noqa: E402
    PaidDispatchError,
    prepare_paid_dispatch,
    recover_paid_dispatch,
    settle_paid_dispatch,
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
    )

    assert reservation is not None
    assert reservation.held_microcents == 40_328
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
