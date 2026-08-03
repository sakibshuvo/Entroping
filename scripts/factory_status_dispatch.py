from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_budget_ledger_fs import LEDGER_DIRECTORY, LEDGER_NAME
from scripts.factory_budget_ledger_schema import validate_schema as validate_ledger_schema
from scripts.factory_cost_policy_io import read_policy_document
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_cost_policy_types import AutomationLane, ProviderQuota
from scripts.factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at
from scripts.provider_capability_io import load_provider_registry
from scripts.provider_capability_types import ProviderCapabilityRegistry, ProviderRegistryError

from .factory_status_database import open_status_database
from .factory_status_filesystem import FactoryStatusError, exists_lstat, fingerprint_file
from .factory_status_models import DispatchLanesStatus, SourceState

type Fingerprints = list[tuple[str, int, int, int]]


def collect_dispatch_lanes(
    root: Path, observed_at: datetime, fingerprints: Fingerprints
) -> tuple[DispatchLanesStatus, tuple[str, ...]]:
    """Project enabled, configured routes and their current quota capacity."""

    try:
        policy = _load_policy(root, observed_at, fingerprints)
        registry = _load_registry(root, fingerprints)
    except FactoryStatusError:
        return _blank("unsafe"), ("dispatch-policy-unsafe",)
    except (FactoryCostPolicyError, ProviderRegistryError, ValidationError, OSError, ValueError):
        return _blank("unavailable"), ("dispatch-policy-unavailable",)
    active = tuple(
        lane
        for lane in registry.lanes
        if lane.lifecycle == "active" and "queue_dispatch" in lane.capabilities
    )
    enabled = tuple(lane for lane in policy.automation_lanes if lane.enabled)
    applicable = tuple(
        lane
        for lane in enabled
        if any(route.policy_provider_id == lane.provider_id for route in active)
    )
    quota_states = _quota_states(root, policy, applicable, observed_at, fingerprints)
    route_states = tuple(
        _route_state(
            tuple(lane for lane in applicable if lane.provider_id == route.policy_provider_id),
            quota_states,
        )
        for route in active
    )
    ready = sum(state == "available" for state in route_states)
    status: SourceState = (
        "unsafe" if "unsafe" in route_states else "available" if ready else "unavailable"
    )
    quota_status: SourceState = (
        "unsafe" if "unsafe" in quota_states.values() else "available" if ready else "unavailable"
    )
    reasons: tuple[str, ...] = ()
    if status == "unsafe":
        reasons = ("dispatch-quota-unsafe",)
    elif not ready:
        reasons = ("dispatch-quota-unavailable",) if applicable else ("dispatch-route-unavailable",)
    return DispatchLanesStatus(
        status=status, active_routes=len(active), ready_routes=ready, quota_status=quota_status
    ), reasons


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


def _quota_states(
    root: Path,
    policy: FactoryCostPolicy,
    lanes: tuple[AutomationLane, ...],
    observed_at: datetime,
    fingerprints: Fingerprints,
) -> dict[str, SourceState]:
    quota_ids = {quota_id for lane in lanes for quota_id in lane.quota_ids}
    if not quota_ids:
        return {lane.id: "available" for lane in lanes}
    path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
    connection, state = open_status_database(root, path, fingerprints)
    if connection is None:
        return {lane.id: "unsafe" if state == "unsafe" else "unavailable" for lane in lanes}
    try:
        validate_ledger_schema(connection)
        quotas = {quota.id: quota for quota in policy.provider_quotas}
        values = {
            lane.id: _lane_quota_state(connection, policy, lane, quotas, observed_at)
            for lane in lanes
        }
    except (sqlite3.DatabaseError, ValueError):
        values = {lane.id: "unsafe" for lane in lanes}
    finally:
        connection.close()
    return values


def _lane_quota_state(
    connection: sqlite3.Connection,
    policy: FactoryCostPolicy,
    lane: AutomationLane,
    quotas: Mapping[str, ProviderQuota],
    observed_at: datetime,
) -> SourceState:
    for quota_id in lane.quota_ids:
        quota = quotas[quota_id]
        observation = connection.execute(
            "SELECT id, used_units, known, expires_at_utc, window_start_utc, window_end_utc "
            "FROM quota_observations WHERE quota_id = ? AND provider_id = ? "
            "AND policy_id = ? AND policy_revision = ? AND unit = ? "
            "AND observed_at_utc <= ? AND recorded_at_utc <= ? "
            "ORDER BY observed_at_utc DESC, id DESC LIMIT 1",
            (
                quota.id,
                lane.provider_id,
                policy.policy_id,
                policy.policy_revision,
                quota.unit,
                observed_at.isoformat(),
                observed_at.isoformat(),
            ),
        ).fetchone()
        if observation is None:
            return "unavailable"
        observation_id, used, known, expires, starts, ends = observation
        if not int(known):
            return "unsafe"
        if (
            str(expires) <= observed_at.isoformat()
            or str(starts) > observed_at.isoformat()
            or str(ends) <= observed_at.isoformat()
        ):
            return "unavailable"
        active, uncertain, settled = connection.execute(
            "SELECT COALESCE(SUM(CASE WHEN h.state = 'active' THEN h.held_units ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN h.state = 'uncertain' THEN h.held_units ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN h.state = 'settled' AND a.state = 'settled' "
            "AND NOT EXISTS (SELECT 1 FROM quota_observation_inclusions AS i "
            "WHERE i.observation_id = ? AND i.authorization_id = a.id) "
            "THEN h.actual_units ELSE 0 END), 0) FROM quota_holds AS h "
            "JOIN dispatch_authorizations AS a ON a.id = h.authorization_id "
            "JOIN quota_observations AS source ON source.id = h.observation_id "
            "WHERE h.quota_id = ? AND h.unit = ? AND a.provider_id = ? "
            "AND a.policy_id = ? AND a.policy_revision = ? "
            "AND source.window_start_utc < ? AND source.window_end_utc > ?",
            (
                observation_id,
                quota.id,
                quota.unit,
                lane.provider_id,
                policy.policy_id,
                policy.policy_revision,
                ends,
                starts,
            ),
        ).fetchone()
        if int(uncertain):
            return "unsafe"
        consumed = int(used) + int(active) + int(settled)
        if consumed > quota.limit:
            return "unsafe"
        if consumed >= quota.limit:
            return "unavailable"
    return "available"


def _route_state(lanes: tuple[AutomationLane, ...], states: dict[str, SourceState]) -> SourceState:
    if not lanes:
        return "unavailable"
    values = tuple(states[lane.id] for lane in lanes)
    if "available" in values:
        return "available"
    return "unsafe" if "unsafe" in values else "unavailable"


def _blank(status: SourceState) -> DispatchLanesStatus:
    return DispatchLanesStatus(status=status, active_routes=0, ready_routes=0, quota_status=status)
