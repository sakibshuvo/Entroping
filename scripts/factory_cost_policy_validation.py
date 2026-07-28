from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import override

from .factory_cost_policy_models import FactoryCostPolicy
from .factory_cost_policy_types import (
    FixedSubscriptionLane,
    IncludedQuotaLane,
    MeteredLane,
)


@dataclass(frozen=True, slots=True)
class FactoryCostPolicyError(Exception):
    code: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def validate_policy_at(policy: FactoryCostPolicy, as_of: datetime) -> None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise FactoryCostPolicyError(
            code="as_of",
            detail="as-of timestamp must include a UTC offset",
        )
    if not policy.valid_from <= as_of < policy.expires_at:
        raise FactoryCostPolicyError(
            code="policy_freshness",
            detail="policy is stale or not yet effective",
        )
    price_snapshots = {item.id: item for item in policy.price_snapshots}
    for lane in policy.automation_lanes:
        match lane:
            case MeteredLane(enabled=True, price_snapshot_ids=price_snapshot_ids):
                for snapshot_id in price_snapshot_ids:
                    snapshot = price_snapshots.get(snapshot_id)
                    if snapshot is None:
                        raise FactoryCostPolicyError(
                            code="price_reference",
                            detail="metered lane references an unknown price snapshot",
                        )
                    if not snapshot.observed_at <= as_of < snapshot.expires_at:
                        raise FactoryCostPolicyError(
                            code="price_freshness",
                            detail="price snapshot is stale or not yet observed",
                        )
            case MeteredLane() | IncludedQuotaLane() | FixedSubscriptionLane():
                continue
