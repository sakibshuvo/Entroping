from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import (
    SIGNED_64_BIT_MAX,
    FactoryBudgetLedgerError,
)
from .factory_quota_models import DispatchAuthorizationRequest, QuotaRequirement
from .factory_quota_store import insert_observation
from .factory_quota_windows import quota_units


def record_validated_observation(
    connection: sqlite3.Connection,
    request: DispatchAuthorizationRequest,
    requirement: QuotaRequirement,
) -> int:
    observation = requirement.observation
    latest = connection.execute(
        """
        SELECT observed_at_utc FROM quota_observations
        WHERE quota_id = ? AND provider_id = ? AND provider_lane_id = ?
          AND policy_id = ? AND policy_revision = ? AND unit = ?
        ORDER BY observed_at_utc DESC, id DESC LIMIT 1
        """,
        (
            observation.quota_id,
            observation.provider_id,
            observation.provider_lane_id,
            observation.policy_id,
            observation.policy_revision,
            observation.unit,
        ),
    ).fetchone()
    if latest is not None and str(latest[0]) > observation.observed_at_utc:
        raise FactoryBudgetLedgerError("quota", "quota observation rollback rejected")
    previous = connection.execute(
        """
        SELECT MAX(used_units) FROM quota_observations
        WHERE quota_id = ? AND provider_id = ? AND provider_lane_id = ?
          AND policy_id = ? AND policy_revision = ? AND unit = ?
          AND window_start_utc = ? AND window_end_utc = ?
        """,
        (
            observation.quota_id,
            observation.provider_id,
            observation.provider_lane_id,
            observation.policy_id,
            observation.policy_revision,
            observation.unit,
            observation.window.starts_at_utc,
            observation.window.ends_at_utc,
        ),
    ).fetchone()
    if (
        previous is not None
        and previous[0] is not None
        and int(previous[0]) > observation.used_units
    ):
        raise FactoryBudgetLedgerError("quota", "quota observation regresses within its window")
    observation_id = insert_observation(connection, observation)
    projected = quota_units(request.usage_envelope)[requirement.unit]
    active, settled = connection.execute(
        """
        SELECT
          COALESCE(SUM(CASE WHEN h.state IN ('active', 'uncertain')
              THEN h.held_units ELSE 0 END), 0),
          COALESCE(SUM(CASE WHEN h.state = 'settled'
              AND a.state = 'settled'
              AND NOT EXISTS (
                  SELECT 1 FROM quota_observation_inclusions AS inclusion
                  WHERE inclusion.observation_id = ?
                    AND inclusion.authorization_id = a.id
              ) THEN h.actual_units ELSE 0 END), 0)
        FROM quota_holds AS h
        JOIN dispatch_authorizations AS a ON a.id = h.authorization_id
        JOIN quota_observations AS o ON o.id = h.observation_id
        WHERE h.quota_id = ? AND h.unit = ?
          AND a.provider_id = ? AND a.provider_lane_id = ?
          AND a.policy_id = ?
          AND o.window_start_utc < ? AND o.window_end_utc > ?
        """,
        (
            observation_id,
            requirement.quota_id,
            requirement.unit,
            observation.provider_id,
            observation.provider_lane_id,
            observation.policy_id,
            observation.window.ends_at_utc,
            observation.window.starts_at_utc,
        ),
    ).fetchone()
    prospective = observation.used_units + int(active) + int(settled) + projected
    if prospective > SIGNED_64_BIT_MAX or prospective > requirement.limit:
        raise FactoryBudgetLedgerError("quota", "quota requirement exceeds available capacity")
    return observation_id
