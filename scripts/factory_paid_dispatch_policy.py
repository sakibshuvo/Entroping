from __future__ import annotations

from datetime import datetime, timedelta
from typing import assert_never

from .factory_budget_ledger import CostReservationRequest, PriceTerm, UsageEnvelope
from .factory_cost_policy_models import FactoryCostPolicy
from .factory_cost_policy_types import (
    AnnualRenewal,
    CalendarMonthQuotaWindow,
    CalendarMonthRenewal,
    FixedIntervalRenewal,
    FixedSubscriptionLane,
    IncludedQuotaLane,
    MeteredLane,
    PriceSnapshot,
    ProviderQuota,
    RollingQuotaWindow,
    SubscriptionCycleQuotaWindow,
)
from .factory_paid_dispatch_models import PaidDispatchError
from .factory_quota_models import QuotaObservation, QuotaWindow
from .factory_quota_windows import (
    canonical_subscription_cycle_id,
    fixed_interval_subscription_cycle_window,
    monthly_subscription_cycle_window,
    subscription_cycle_window,
    utc_month_window,
)

type PolicyLane = MeteredLane | IncludedQuotaLane | FixedSubscriptionLane


def require_policy_quota_window(
    policy: FactoryCostPolicy,
    quota: ProviderQuota,
    observation: QuotaObservation,
    *,
    decision_at: datetime,
) -> None:
    expected: QuotaWindow | None = None
    match quota.window:
        case RollingQuotaWindow():
            duration_seconds = quota.window.duration_seconds
            if (
                observation.window.kind != "rolling"
                or observation.window.starts_at is None
                or observation.window.ends_at is None
                or observation.window.ends_at - observation.window.starts_at
                != timedelta(seconds=duration_seconds)
            ):
                raise PaidDispatchError(
                    "quota_window",
                    "rolling quota evidence does not match the policy duration",
                )
            return
        case CalendarMonthQuotaWindow():
            expected = utc_month_window(decision_at)
        case SubscriptionCycleQuotaWindow(subscription_id=subscription_id):
            subscriptions = {item.id: item for item in policy.subscriptions}
            subscription = subscriptions[subscription_id]
            cycle_id = _cycle_id(subscription_id, observation)
            match subscription.renewal:
                case AnnualRenewal(month=month, day=day):
                    expected = subscription_cycle_window(
                        decision_at,
                        renewal_month=month,
                        renewal_day=day,
                        cycle_id=cycle_id,
                    )
                case CalendarMonthRenewal(day=day):
                    expected = monthly_subscription_cycle_window(
                        decision_at,
                        renewal_day=day,
                        cycle_id=cycle_id,
                    )
                case FixedIntervalRenewal(anchor_on=anchor_on, interval_days=interval_days):
                    expected = fixed_interval_subscription_cycle_window(
                        decision_at,
                        anchor_on=anchor_on,
                        interval_days=interval_days,
                        cycle_id=cycle_id,
                    )
                case unreachable:
                    assert_never(unreachable)
        case unreachable:
            assert_never(unreachable)
    if expected is None:
        raise PaidDispatchError("quota_window", "quota policy window is unsupported")
    if not _same_window(observation.window, expected):
        raise PaidDispatchError(
            "quota_window",
            "quota evidence window does not match the policy boundary",
        )


def _cycle_id(subscription_id: str, observation: QuotaObservation) -> str:
    start = observation.window.starts_at
    if start is None:
        raise PaidDispatchError("quota_window", "subscription quota window is incomplete")
    expected = canonical_subscription_cycle_id(subscription_id, start)
    if observation.window.cycle_id != expected:
        raise PaidDispatchError(
            "quota_window",
            "subscription quota cycle id does not match the policy boundary",
        )
    return expected


def _same_window(actual: QuotaWindow, expected: QuotaWindow) -> bool:
    return (
        actual.kind == expected.kind
        and actual.starts_at_utc == expected.starts_at_utc
        and actual.ends_at_utc == expected.ends_at_utc
        and actual.cycle_id == expected.cycle_id
    )


def policy_lane(
    policy: FactoryCostPolicy,
    provider_id: str,
    model_id: str | None,
    billing_kind: str,
) -> PolicyLane:
    matches = tuple(
        lane
        for lane in policy.automation_lanes
        if lane.enabled
        and lane.provider_id == provider_id
        and (
            (
                billing_kind == "metered"
                and isinstance(lane, MeteredLane)
                and lane.model_id == model_id
            )
            or (billing_kind == "included_quota" and isinstance(lane, IncludedQuotaLane))
            or (billing_kind == "subscription" and isinstance(lane, FixedSubscriptionLane))
        )
    )
    if len(matches) != 1:
        raise PaidDispatchError(
            "cost_policy",
            "cost policy must enable exactly one matching automation lane",
        )
    return matches[0]


def cash_request(
    lane: PolicyLane,
    *,
    job_id: str,
    requested_model: str,
    provider_lane_id: str,
    policy: FactoryCostPolicy,
    occurred_at: datetime,
    usage: UsageEnvelope,
    model_id: str | None,
) -> CostReservationRequest | None:
    match lane:
        case IncludedQuotaLane() | FixedSubscriptionLane():
            return None
        case MeteredLane():
            if model_id is None:
                raise PaidDispatchError("route", "metered route lacks a model identity")
            by_id = {snapshot.id: snapshot for snapshot in policy.price_snapshots}
            snapshots = tuple(by_id[snapshot_id] for snapshot_id in lane.price_snapshot_ids)
        case unreachable:
            assert_never(unreachable)
    terms = tuple(_price_term(snapshot) for snapshot in snapshots)
    units = {term.unit for term in terms}
    if not {"input_token", "output_token"}.issubset(units) or "minute" in units:
        raise PaidDispatchError(
            "price_contract",
            "direct paid dispatch requires input/output token prices and no minute price",
        )
    return CostReservationRequest(
        idempotency_key=f"dispatch:{job_id}",
        job_id=job_id,
        provider_lane_id=provider_lane_id,
        provider_id=lane.provider_id,
        model_id=model_id,
        requested_model=requested_model,
        cost_policy_lane_id=lane.id,
        policy_id=policy.policy_id,
        policy_revision=policy.policy_revision,
        occurred_at=occurred_at,
        usage_envelope=usage,
        price_terms=terms,
    )


def _price_term(snapshot: PriceSnapshot) -> PriceTerm:
    return PriceTerm(
        snapshot_id=snapshot.id,
        unit=snapshot.unit,
        quantity=snapshot.quantity,
        price_microcents=snapshot.price_microcents,
        observed_at=snapshot.observed_at,
        expires_at=snapshot.expires_at,
    )
