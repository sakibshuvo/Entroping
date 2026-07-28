from __future__ import annotations

from datetime import date
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

type Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=96),
]
type ModelIdentifier = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$",
        max_length=160,
    ),
]
type Microcents = Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
type PositiveMicrocents = Annotated[
    int,
    Field(gt=0, le=9_223_372_036_854_775_807),
]
type PositiveCount = Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
type QuotaUnit = Literal["requests", "input_tokens", "output_tokens", "tokens"]
type PriceUnit = Literal["request", "input_token", "output_token", "minute"]


class StrictPolicyModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class CashThresholds(StrictPolicyModel):
    stop_experiments_basis_points: Literal[8000]
    subscription_only_basis_points: Literal[9000]
    stop_paid_dispatch_basis_points: Literal[10000]


class CashPolicy(StrictPolicyModel):
    calendar_month_timezone: Literal["UTC"]
    calendar_month_cap_microcents: Microcents
    emergency_reserve_microcents: Microcents
    thresholds: CashThresholds

    @model_validator(mode="after")
    def validate_reserve(self) -> Self:
        if self.emergency_reserve_microcents >= self.calendar_month_cap_microcents:
            raise PydanticCustomError(
                "cash_reserve",
                "reserve must be less than the cash cap",
            )
        subscription_only_amount = (
            self.calendar_month_cap_microcents
            * self.thresholds.subscription_only_basis_points
        )
        spendable_amount = (
            self.calendar_month_cap_microcents - self.emergency_reserve_microcents
        ) * 10_000
        if subscription_only_amount > spendable_amount:
            raise PydanticCustomError(
                "cash_reserve_threshold",
                "subscription-only threshold must preserve the reserve",
            )
        return self


class CalendarMonthRenewal(StrictPolicyModel):
    kind: Literal["calendar_month"]
    timezone: Literal["UTC"]
    day: Annotated[int, Field(ge=1, le=31)]
    invalid_date_behavior: Literal["last_day"]


class AnnualRenewal(StrictPolicyModel):
    kind: Literal["annual"]
    timezone: Literal["UTC"]
    month: Annotated[int, Field(ge=1, le=12)]
    day: Annotated[int, Field(ge=1, le=31)]
    invalid_date_behavior: Literal["last_day"]


class FixedIntervalRenewal(StrictPolicyModel):
    kind: Literal["fixed_interval"]
    timezone: Literal["UTC"]
    anchor_on: date
    interval_days: Annotated[int, Field(gt=0, le=3660)]


type SubscriptionRenewal = Annotated[
    CalendarMonthRenewal | AnnualRenewal | FixedIntervalRenewal,
    Field(discriminator="kind"),
]


class SubscriptionPolicy(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    charge_microcents: PositiveMicrocents
    renewal: SubscriptionRenewal


class PriceSnapshot(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    model_id: ModelIdentifier
    unit: PriceUnit
    quantity: PositiveCount
    price_microcents: PositiveMicrocents
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_observation_window(self) -> Self:
        if self.model_id.partition("/")[0] != self.provider_id:
            raise PydanticCustomError(
                "price_model_provider",
                "price model provider does not match its provider id",
            )
        if self.observed_at >= self.expires_at:
            raise PydanticCustomError(
                "price_window",
                "price observation must precede its expiry",
            )
        return self


class RollingQuotaWindow(StrictPolicyModel):
    kind: Literal["rolling"]
    duration_seconds: Annotated[int, Field(gt=0, le=31_536_000)]


class CalendarMonthQuotaWindow(StrictPolicyModel):
    kind: Literal["calendar_month"]
    timezone: Literal["UTC"]


class SubscriptionCycleQuotaWindow(StrictPolicyModel):
    kind: Literal["subscription_cycle"]
    subscription_id: Identifier


type QuotaWindow = Annotated[
    RollingQuotaWindow | CalendarMonthQuotaWindow | SubscriptionCycleQuotaWindow,
    Field(discriminator="kind"),
]


class ProviderQuota(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    unit: QuotaUnit
    limit: PositiveCount
    window: QuotaWindow


class DisabledAutomaticTopUp(StrictPolicyModel):
    mode: Literal["disabled"]


class IncludedQuotaLane(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    billing_mode: Literal["included_quota"]
    enabled: bool
    quota_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]


class FixedSubscriptionLane(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    billing_mode: Literal["fixed_subscription"]
    enabled: bool
    subscription_id: Identifier
    quota_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()


class MeteredLane(StrictPolicyModel):
    id: Identifier
    provider_id: Identifier
    model_id: ModelIdentifier
    billing_mode: Literal["metered"]
    enabled: bool
    price_snapshot_ids: Annotated[
        tuple[Identifier, ...],
        Field(min_length=1, max_length=64),
    ]
    quota_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def validate_model_provider(self) -> Self:
        if self.model_id.partition("/")[0] != self.provider_id:
            raise PydanticCustomError(
                "lane_model_provider",
                "metered-lane model provider does not match its provider id",
            )
        return self


type AutomationLane = Annotated[
    IncludedQuotaLane | FixedSubscriptionLane | MeteredLane,
    Field(discriminator="billing_mode"),
]
