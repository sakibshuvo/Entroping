from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.factory_budget_ledger_fs import LEDGER_DIRECTORY, LEDGER_NAME
from scripts.factory_budget_ledger_schema import validate_schema as validate_ledger_schema
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_cost_policy_types import AutomationLane, ProviderQuota
from scripts.provider_capability_types import ProviderLane

from .factory_status_database import open_status_database
from .factory_status_errors import FactoryStatusError
from .factory_status_models import QuotaReadinessStatus

type Fingerprints = list[tuple[str, int, int, int]]
type RouteKey = tuple[str, str]

MAX_QUOTA_EVALUATIONS = 4_096


def collect_quota_readiness(
    root: Path,
    policy: FactoryCostPolicy,
    routes: tuple[tuple[AutomationLane, ProviderLane], ...],
    observed_at: datetime,
    fingerprints: Fingerprints,
) -> dict[RouteKey, tuple[QuotaReadinessStatus, ...]]:
    """Read quota capacity using the policy lane and registered provider-lane identity."""

    quota_routes = tuple(pair for pair in routes if pair[0].quota_ids)
    evaluation_count = sum(len(lane.quota_ids) for lane, _route in quota_routes)
    if evaluation_count > MAX_QUOTA_EVALUATIONS:
        raise FactoryStatusError("quota evaluation limit exceeded")
    ready: dict[RouteKey, tuple[QuotaReadinessStatus, ...]] = {
        key: () for key in (_route_key(*pair) for pair in routes)
    }
    if not quota_routes:
        return ready
    connection, state = open_status_database(
        root, root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME), fingerprints
    )
    if connection is None:
        unavailable = {
            _route_key(lane, route): tuple(
                QuotaReadinessStatus(
                    quota_id=quota_id,
                    status="unsafe" if state == "unsafe" else "unavailable",
                    reason_code="quota-unsafe" if state == "unsafe" else "quota-unavailable",
                )
                for quota_id in lane.quota_ids
            )
            for lane, route in quota_routes
        }
        ready.update(unavailable)
        return ready
    try:
        validate_ledger_schema(connection)
        quotas = {quota.id: quota for quota in policy.provider_quotas}
        ready.update(
            {
                _route_key(lane, route): tuple(
                    _quota_readiness(connection, policy, lane, route, quotas[quota_id], observed_at)
                    for quota_id in lane.quota_ids
                )
                for lane, route in quota_routes
            }
        )
    except (sqlite3.DatabaseError, ValueError):
        ready.update(
            {
                _route_key(lane, route): tuple(
                    QuotaReadinessStatus(
                        quota_id=quota_id, status="unsafe", reason_code="quota-unsafe"
                    )
                    for quota_id in lane.quota_ids
                )
                for lane, route in quota_routes
            }
        )
    finally:
        connection.close()
    return ready


def _quota_readiness(
    connection: sqlite3.Connection,
    policy: FactoryCostPolicy,
    lane: AutomationLane,
    route: ProviderLane,
    quota: ProviderQuota,
    observed_at: datetime,
) -> QuotaReadinessStatus:
    observation = connection.execute(
        "SELECT id, used_units, known, expires_at_utc, window_start_utc, window_end_utc "
        "FROM quota_observations WHERE quota_id = ? AND provider_id = ? "
        "AND provider_lane_id = ? AND policy_id = ? AND policy_revision = ? AND unit = ? "
        "AND observed_at_utc <= ? AND recorded_at_utc <= ? "
        "ORDER BY observed_at_utc DESC, id DESC LIMIT 1",
        (
            quota.id,
            lane.provider_id,
            route.id,
            policy.policy_id,
            policy.policy_revision,
            quota.unit,
            observed_at.isoformat(),
            observed_at.isoformat(),
        ),
    ).fetchone()
    if observation is None:
        return QuotaReadinessStatus(
            quota_id=quota.id, status="unavailable", reason_code="quota-unavailable"
        )
    observation_id, used, known, expires, starts, ends = observation
    if not int(known):
        return QuotaReadinessStatus(
            quota_id=quota.id, status="unsafe", reason_code="quota-authority-uncertain"
        )
    if (
        str(expires) <= observed_at.isoformat()
        or str(starts) > observed_at.isoformat()
        or str(ends) <= observed_at.isoformat()
    ):
        return QuotaReadinessStatus(
            quota_id=quota.id, status="unavailable", reason_code="quota-stale"
        )
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
        "AND a.provider_lane_id = ? AND a.policy_id = ? AND a.policy_revision = ? "
        "AND source.provider_lane_id = ? AND source.window_start_utc < ? "
        "AND source.window_end_utc > ?",
        (
            observation_id,
            quota.id,
            quota.unit,
            lane.provider_id,
            route.id,
            policy.policy_id,
            policy.policy_revision,
            route.id,
            ends,
            starts,
        ),
    ).fetchone()
    if int(uncertain) or int(used) + int(active) + int(settled) > quota.limit:
        return QuotaReadinessStatus(
            quota_id=quota.id, status="unsafe", reason_code="quota-authority-uncertain"
        )
    if int(used) + int(active) + int(settled) >= quota.limit:
        return QuotaReadinessStatus(
            quota_id=quota.id, status="unavailable", reason_code="quota-exhausted"
        )
    return QuotaReadinessStatus(quota_id=quota.id, status="available")


def _route_key(lane: AutomationLane, route: ProviderLane) -> RouteKey:
    return lane.id, route.id
