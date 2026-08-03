from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_cost_policy_io import read_policy_document
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_cost_policy_types import AutomationLane
from scripts.factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at
from scripts.provider_capability_io import load_provider_registry
from scripts.provider_capability_types import (
    ProviderCapabilityRegistry,
    ProviderLane,
    ProviderRegistryError,
)

from .factory_status_filesystem import FactoryStatusError, exists_lstat, fingerprint_file
from .factory_status_models import (
    DispatchLanesStatus,
    PolicyLaneStatus,
    QuotaReadinessStatus,
    SourceState,
)
from .factory_status_quota import collect_quota_readiness

type Fingerprints = list[tuple[str, int, int, int]]


def collect_dispatch_lanes(
    root: Path, observed_at: datetime, fingerprints: Fingerprints
) -> tuple[DispatchLanesStatus, tuple[str, ...]]:
    """Project trusted policy lanes, matching routes, and quota readiness."""

    try:
        policy = _load_policy(root, observed_at, fingerprints)
        registry = _load_registry(root, fingerprints)
    except FactoryStatusError:
        return _blank("unsafe"), ("dispatch-policy-unsafe",)
    except FileNotFoundError:
        return _blank("unavailable"), ("dispatch-policy-unavailable",)
    except (FactoryCostPolicyError, ProviderRegistryError, ValidationError, OSError, ValueError):
        return _blank("unsafe"), ("dispatch-policy-unsafe",)
    routes = tuple(
        route
        for route in registry.lanes
        if route.lifecycle == "active" and "queue_dispatch" in route.capabilities
    )
    enabled = tuple(lane for lane in policy.automation_lanes if lane.enabled)
    pairs = tuple(
        (lane, route)
        for lane in enabled
        for route in routes
        if route.policy_provider_id == lane.provider_id
    )
    quota_rows = collect_quota_readiness(root, policy, pairs, observed_at, fingerprints)
    lanes = _lane_rows(policy.automation_lanes, routes, quota_rows)
    ready = sum(
        any(row.status == "available" for row in lanes if row.provider_lane_id == route.id)
        for route in routes
    )
    statuses = tuple(row.status for row in lanes)
    status: SourceState = (
        "unsafe" if "unsafe" in statuses else "available" if ready else "unavailable"
    )
    quota_status: SourceState = (
        "unsafe"
        if any(quota.status == "unsafe" for row in lanes for quota in row.quotas)
        else "available"
        if ready
        else "unavailable"
    )
    reason = "dispatch-quota-unsafe" if status == "unsafe" else "dispatch-route-unavailable"
    if status == "unavailable" and any(row.quotas for row in lanes):
        reason = "dispatch-quota-unavailable"
    return DispatchLanesStatus(
        status=status,
        active_routes=len(routes),
        ready_routes=ready,
        quota_status=quota_status,
        lanes=lanes,
    ), (() if status == "available" else (reason,))


def _lane_rows(
    policy_lanes: tuple[AutomationLane, ...],
    routes: tuple[ProviderLane, ...],
    quota_rows: dict[tuple[str, str], tuple[QuotaReadinessStatus, ...]],
) -> tuple[PolicyLaneStatus, ...]:
    rows: list[PolicyLaneStatus] = []
    for lane in sorted(policy_lanes, key=lambda item: item.id):
        matching = tuple(route for route in routes if route.policy_provider_id == lane.provider_id)
        if not lane.enabled:
            rows.append(_policy_row(lane, None, "unavailable", ("policy-lane-disabled",), ()))
        elif not matching:
            rows.append(_policy_row(lane, None, "unavailable", ("dispatch-route-unavailable",), ()))
        else:
            rows.extend(
                _route_row(lane, route, quota_rows.get((lane.id, route.id), ()))
                for route in sorted(matching, key=lambda item: item.id)
            )
    return tuple(rows)


def _route_row(
    lane: AutomationLane, route: ProviderLane, quotas: tuple[QuotaReadinessStatus, ...]
) -> PolicyLaneStatus:
    status: SourceState = (
        "unsafe"
        if any(item.status == "unsafe" for item in quotas)
        else "unavailable"
        if any(item.status == "unavailable" for item in quotas)
        else "available"
    )
    reasons = tuple(sorted(item.reason_code for item in quotas if item.reason_code is not None))
    return _policy_row(lane, route, status, reasons, quotas)


def _policy_row(
    lane: AutomationLane,
    route: ProviderLane | None,
    status: SourceState,
    reasons: tuple[str, ...],
    quotas: tuple[QuotaReadinessStatus, ...],
) -> PolicyLaneStatus:
    return PolicyLaneStatus(
        policy_lane_id=lane.id,
        provider_lane_id=None if route is None else route.id,
        status=status,
        reason_codes=reasons,
        quotas=quotas,
    )


def _load_policy(
    root: Path, observed_at: datetime, fingerprints: Fingerprints
) -> FactoryCostPolicy:
    path = root / ".entroping" / "factory-cost-policy.json"
    if not exists_lstat(path):
        path = root / "docs" / "meta" / "factory-cost-policy.example.json"
    fingerprint_file(root, path, fingerprints)
    policy = FactoryCostPolicy.model_validate_json(read_policy_document(path), strict=True)
    validate_policy_at(policy, observed_at)
    return policy


def _load_registry(root: Path, fingerprints: Fingerprints) -> ProviderCapabilityRegistry:
    path = root / "docs" / "meta" / "provider-capability-registry.json"
    fingerprint_file(root, path, fingerprints)
    return load_provider_registry(path)


def _blank(status: SourceState) -> DispatchLanesStatus:
    return DispatchLanesStatus(
        status=status, active_routes=0, ready_routes=0, quota_status=status, lanes=()
    )
