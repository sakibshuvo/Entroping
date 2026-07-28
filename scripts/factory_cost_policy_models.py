from __future__ import annotations

from typing import Annotated, Literal, Self, TypedDict

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from .factory_cost_policy_types import (
    AutomationLane,
    CashPolicy,
    DisabledAutomaticTopUp,
    FixedSubscriptionLane,
    Identifier,
    IncludedQuotaLane,
    MeteredLane,
    PriceSnapshot,
    ProviderQuota,
    StrictPolicyModel,
    SubscriptionCycleQuotaWindow,
    SubscriptionPolicy,
)


class FactoryCostPolicy(StrictPolicyModel):
    schema_version: Literal["entroping.factory-cost-policy.v1"]
    policy_id: Identifier
    policy_revision: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
    currency: Literal["USD"]
    monetary_unit: Literal["microcent"]
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    unknown_cost_behavior: Literal["deny_paid_dispatch"]
    unknown_quota_behavior: Literal["deny_affected_paid_lane"]
    cash: CashPolicy
    subscriptions: Annotated[tuple[SubscriptionPolicy, ...], Field(max_length=128)]
    price_snapshots: Annotated[tuple[PriceSnapshot, ...], Field(max_length=512)]
    provider_quotas: Annotated[tuple[ProviderQuota, ...], Field(max_length=256)]
    automatic_top_up: DisabledAutomaticTopUp
    automation_lanes: Annotated[tuple[AutomationLane, ...], Field(max_length=128)]

    @model_validator(mode="after")
    def validate_policy_window(self) -> Self:
        if self.valid_from >= self.expires_at:
            raise PydanticCustomError(
                "policy_window",
                "policy validity start must precede its expiry",
            )
        return self

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        collections = (
            ("subscription", tuple(item.id for item in self.subscriptions)),
            ("price snapshot", tuple(item.id for item in self.price_snapshots)),
            ("provider quota", tuple(item.id for item in self.provider_quotas)),
            ("automation lane", tuple(item.id for item in self.automation_lanes)),
        )
        for label, identifiers in collections:
            duplicate = _duplicate_identifier(identifiers)
            if duplicate is not None:
                raise PydanticCustomError(
                    "duplicate_identifier",
                    "duplicate {label} id",
                    {"label": label},
                )
        return self

    @model_validator(mode="after")
    def validate_lane_references(self) -> Self:
        subscriptions = {item.id: item for item in self.subscriptions}
        prices = {item.id: item for item in self.price_snapshots}
        quotas = {item.id: item for item in self.provider_quotas}
        for quota in self.provider_quotas:
            if not isinstance(quota.window, SubscriptionCycleQuotaWindow):
                continue
            subscription = subscriptions.get(quota.window.subscription_id)
            if subscription is None:
                raise PydanticCustomError(
                    "quota_subscription_reference",
                    "subscription-cycle quota references an unknown subscription",
                )
            if subscription.provider_id != quota.provider_id:
                raise PydanticCustomError(
                    "quota_subscription_provider",
                    "subscription-cycle quota provider does not match its subscription",
                )
        for lane in self.automation_lanes:
            match lane:
                case IncludedQuotaLane(provider_id=provider_id, quota_ids=quota_ids):
                    _require_unique_references("quota", quota_ids)
                    _require_quota_references(provider_id, quota_ids, quotas)
                case FixedSubscriptionLane(
                    provider_id=provider_id,
                    subscription_id=subscription_id,
                    quota_ids=quota_ids,
                ):
                    _require_unique_references("quota", quota_ids)
                    subscription = subscriptions.get(subscription_id)
                    if subscription is None:
                        raise PydanticCustomError(
                            "subscription_reference",
                            "fixed-subscription lane references an unknown subscription",
                        )
                    if subscription.provider_id != provider_id:
                        raise PydanticCustomError(
                            "subscription_provider",
                            "subscription provider does not match its automation lane",
                        )
                    _require_quota_references(provider_id, quota_ids, quotas)
                case MeteredLane(
                    provider_id=provider_id,
                    model_id=model_id,
                    price_snapshot_ids=price_snapshot_ids,
                    quota_ids=quota_ids,
                ):
                    _require_unique_references("price snapshot", price_snapshot_ids)
                    _require_unique_references("quota", quota_ids)
                    price_units: set[str] = set()
                    for snapshot_id in price_snapshot_ids:
                        snapshot = prices.get(snapshot_id)
                        if snapshot is None:
                            raise PydanticCustomError(
                                "price_reference",
                                "metered lane references an unknown price snapshot",
                            )
                        if snapshot.provider_id != provider_id:
                            raise PydanticCustomError(
                                "price_provider",
                                "price provider does not match its automation lane",
                            )
                        if snapshot.model_id != model_id:
                            raise PydanticCustomError(
                                "price_model",
                                "price model does not match its automation lane",
                            )
                        if snapshot.unit in price_units:
                            raise PydanticCustomError(
                                "ambiguous_price_unit",
                                "metered lane contains an ambiguous price snapshot unit",
                            )
                        price_units.add(snapshot.unit)
                    _require_quota_references(provider_id, quota_ids, quotas)
        return self


class PolicySummary(TypedDict):
    schema_version: str
    policy_id: str
    currency: str
    calendar_month_cap_microcents: int
    emergency_reserve_microcents: int
    subscription_count: int
    price_snapshot_count: int
    provider_quota_count: int
    automation_lane_count: int


def summarize_policy(policy: FactoryCostPolicy) -> PolicySummary:
    return {
        "schema_version": policy.schema_version,
        "policy_id": policy.policy_id,
        "currency": policy.currency,
        "calendar_month_cap_microcents": policy.cash.calendar_month_cap_microcents,
        "emergency_reserve_microcents": policy.cash.emergency_reserve_microcents,
        "subscription_count": len(policy.subscriptions),
        "price_snapshot_count": len(policy.price_snapshots),
        "provider_quota_count": len(policy.provider_quotas),
        "automation_lane_count": len(policy.automation_lanes),
    }


def _duplicate_identifier(identifiers: tuple[str, ...]) -> str | None:
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            return identifier
        seen.add(identifier)
    return None


def _require_quota_references(
    provider_id: str,
    quota_ids: tuple[str, ...],
    quotas: dict[str, ProviderQuota],
) -> None:
    for quota_id in quota_ids:
        quota = quotas.get(quota_id)
        if quota is None:
            raise PydanticCustomError(
                "quota_reference",
                "automation lane references an unknown provider quota",
            )
        if quota.provider_id != provider_id:
            raise PydanticCustomError(
                "quota_provider",
                "quota provider does not match its automation lane",
            )


def _require_unique_references(label: str, identifiers: tuple[str, ...]) -> None:
    if _duplicate_identifier(identifiers) is not None:
        raise PydanticCustomError(
            "duplicate_reference",
            "automation lane contains a duplicate {label} reference",
            {"label": label},
        )
