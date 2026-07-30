from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import FactoryBudgetLedgerError, UsageEnvelope  # noqa: E402
from scripts.factory_quota_models import (  # noqa: E402
    QuotaWindow,
    subscription_cycle_window,
    utc_month_window,
)
from scripts.factory_quota_windows import (  # noqa: E402
    fixed_interval_subscription_cycle_window,
    monthly_subscription_cycle_window,
    quota_units,
)


def test_usage_envelope_charges_combined_tokens_once() -> None:
    # Given separate input and output usage.
    usage = UsageEnvelope(input_tokens=40, output_tokens=60)

    # When the quota units are projected.
    projected = quota_units(usage)

    # Then the combined dimension is the overflow-safe sum, not a second charge.
    assert projected == {
        "requests": 0,
        "input_tokens": 40,
        "output_tokens": 60,
        "tokens": 100,
    }


def test_utc_month_window_is_half_open_at_exact_expiry() -> None:
    # Given an instant on the last day of a UTC month.
    observed = datetime(2028, 2, 29, 23, 59, 59, tzinfo=UTC)

    # When the calendar window is derived.
    window = utc_month_window(observed)

    # Then it uses deterministic UTC half-open boundaries.
    assert window.starts_at == datetime(2028, 2, 1, tzinfo=UTC)
    assert window.ends_at == datetime(2028, 3, 1, tzinfo=UTC)
    assert window.starts_at is not None
    assert window.ends_at is not None
    assert window.contains(window.starts_at)
    assert not window.contains(window.ends_at)


@pytest.mark.parametrize(
    ("as_of", "expected_start", "expected_end"),
    (
        (
            datetime(2028, 2, 28, tzinfo=UTC),
            datetime(2027, 2, 28, tzinfo=UTC),
            datetime(2028, 2, 29, tzinfo=UTC),
        ),
        (
            datetime(2028, 2, 29, tzinfo=UTC),
            datetime(2028, 2, 29, tzinfo=UTC),
            datetime(2029, 2, 28, tzinfo=UTC),
        ),
    ),
)
def test_annual_subscription_cycle_uses_last_day_and_leap_boundaries(
    as_of: datetime,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    # Given an annual renewal anchored to February 29 with last-day behavior.
    # When the containing subscription cycle is derived.
    window = subscription_cycle_window(
        as_of,
        renewal_month=2,
        renewal_day=29,
        cycle_id="annual-plan",
    )

    # Then the annual UTC boundary is deterministic across leap years.
    assert (window.starts_at, window.ends_at) == (expected_start, expected_end)


@pytest.mark.parametrize(
    ("as_of", "expected_start", "expected_end"),
    (
        (
            datetime(2026, 3, 30, tzinfo=UTC),
            datetime(2026, 2, 28, tzinfo=UTC),
            datetime(2026, 3, 31, tzinfo=UTC),
        ),
        (
            datetime(2026, 3, 31, tzinfo=UTC),
            datetime(2026, 3, 31, tzinfo=UTC),
            datetime(2026, 4, 30, tzinfo=UTC),
        ),
    ),
)
def test_monthly_subscription_cycle_clamps_last_day(
    as_of: datetime,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    window = monthly_subscription_cycle_window(
        as_of,
        renewal_day=31,
        cycle_id="monthly-plan",
    )
    assert (window.starts_at, window.ends_at) == (expected_start, expected_end)


def test_fixed_interval_subscription_cycle_uses_anchor_and_half_open_reset() -> None:
    window = fixed_interval_subscription_cycle_window(
        datetime(2026, 2, 1, tzinfo=UTC),
        anchor_on=date(2026, 1, 1),
        interval_days=30,
        cycle_id="fixed-plan",
    )
    assert window.starts_at == datetime(2026, 1, 31, tzinfo=UTC)
    assert window.ends_at == datetime(2026, 3, 2, tzinfo=UTC)


def test_quota_window_rejects_wall_clock_reset_without_explicit_bounds() -> None:
    # Given a rolling quota with no source-provided half-open bounds.
    # When it is parsed.
    # Then wall clock alone cannot reset its authority.
    with pytest.raises(FactoryBudgetLedgerError, match="explicit window bounds"):
        QuotaWindow(
            kind="rolling",
            starts_at=None,
            ends_at=None,
            cycle_id=None,
        ).validate()


def test_quota_units_rejects_combined_token_overflow() -> None:
    # Given usage whose combined token count exceeds SQLite's signed range.
    usage = UsageEnvelope(
        input_tokens=9_223_372_036_854_775_807,
        output_tokens=1,
    )

    # When it is projected to quota units.
    # Then overflow fails closed.
    with pytest.raises(FactoryBudgetLedgerError, match="combined token usage"):
        quota_units(usage)
