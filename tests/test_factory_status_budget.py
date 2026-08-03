from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_status_test_support import initialize_status_period, write_status_policy  # noqa: E402

from scripts.factory_budget_reservation_models import (  # noqa: E402
    CostReservationRequest,
    PriceTerm,
    UsageEnvelope,
)
from scripts.factory_status import collect_factory_status  # noqa: E402
from scripts.factory_status_policy import cash_threshold_reason  # noqa: E402


@pytest.mark.parametrize(
    ("amount", "reason"),
    (
        (8_000, "budget-threshold"),
        (9_000, "budget-subscription-only"),
        (10_000, "budget-stop-paid-dispatch"),
    ),
)
def test_each_configured_cash_threshold_pauses_budget(
    tmp_path: Path, amount: int, reason: str
) -> None:
    """Every policy threshold is evaluated at its exact basis-point boundary."""

    now = datetime.now(UTC)
    write_status_policy(tmp_path, now)

    threshold = cash_threshold_reason(
        tmp_path,
        now,
        "status-policy",
        1,
        10_000,
        amount,
        0,
        [],
    )

    assert threshold == reason


def test_uncertain_cash_reservation_is_unsafe_budget_authority(tmp_path: Path) -> None:
    """A cash reservation awaiting settlement fails closed in the budget section."""

    now = datetime.now(UTC)
    write_status_policy(tmp_path, now)
    ledger = initialize_status_period(tmp_path, now)
    reservation = ledger.reserve_for_dispatch(
        CostReservationRequest(
            idempotency_key="status-uncertain-cash",
            job_id="status-uncertain-job",
            provider_lane_id="deepseek-api/direct",
            provider_id="deepseek",
            model_id="deepseek/deepseek-v4-pro",
            requested_model="deepseek-v4-pro",
            cost_policy_lane_id="deepseek-metered",
            policy_id="status-policy",
            policy_revision=1,
            occurred_at=now,
            usage_envelope=UsageEnvelope(input_tokens=1),
            price_terms=(
                PriceTerm(
                    snapshot_id="status-price",
                    unit="input_token",
                    quantity=1,
                    price_microcents=1,
                    observed_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(minutes=1),
                ),
            ),
        )
    )
    _ = ledger.mark_reservation_uncertain(
        reservation.reservation_id,
        idempotency_key="status-uncertain-cash-mark",
        reason="worker_interrupted",
        occurred_at=now + timedelta(seconds=1),
        evidence_digest="c" * 64,
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.budget.status == "unsafe"
    assert "budget-authority-uncertain" in report.reason_codes
