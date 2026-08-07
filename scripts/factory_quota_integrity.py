from __future__ import annotations

import sqlite3
from datetime import datetime

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_quota_inclusions import validate_observation_inclusion_integrity

MAX_QUOTA_ROWS = 500_000


def require_monotonic_authorization_transition(
    occurred_at: str,
    current_state_changed_at: object,
) -> None:
    if not isinstance(current_state_changed_at, str):
        raise FactoryBudgetLedgerError("database", "authorization timestamp is invalid")
    if occurred_at < current_state_changed_at:
        raise FactoryBudgetLedgerError(
            "clock",
            "authorization transition clock rollback rejected",
        )


def validate_quota_integrity(connection: sqlite3.Connection) -> None:
    for table in (
        "quota_observations",
        "top_up_attestations",
        "dispatch_authorizations",
        "quota_holds",
        "quota_observation_inclusions",
    ):
        if (
            connection.execute(
                f"SELECT 1 FROM {table} ORDER BY id LIMIT 1 OFFSET ?",
                (MAX_QUOTA_ROWS,),
            ).fetchone()
            is not None
        ):
            raise FactoryBudgetLedgerError("limit", "global quota authority limit exceeded")
    if (
        connection.execute(
            """
        SELECT a.id FROM dispatch_authorizations AS a
        JOIN top_up_attestations AS t ON t.id = a.top_up_attestation_id
        WHERE a.provider_id != t.provider_id
           OR a.provider_lane_id != t.provider_lane_id
           OR a.policy_id != t.policy_id
           OR a.policy_revision != t.policy_revision
        LIMIT 1
        """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "authorization attestation identity is invalid")
    if (
        connection.execute(
            """
        SELECT h.id FROM quota_holds AS h
        JOIN dispatch_authorizations AS a ON a.id = h.authorization_id
        JOIN quota_observations AS o ON o.id = h.observation_id
        WHERE h.quota_id != o.quota_id OR h.unit != o.unit
           OR a.provider_id != o.provider_id
           OR a.provider_lane_id != o.provider_lane_id
           OR a.policy_id != o.policy_id
           OR a.policy_revision != o.policy_revision
           OR (h.actual_units IS NOT NULL AND h.actual_units > h.held_units)
        LIMIT 1
        """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "quota hold identity or balance is invalid")
    if (
        connection.execute(
            """
        SELECT h.id FROM quota_holds AS h
        JOIN dispatch_authorizations AS a ON a.id = h.authorization_id
        WHERE (a.state IN ('active', 'launched') AND h.state != 'active')
           OR (a.state = 'settled' AND h.state != 'settled')
           OR (a.state = 'released' AND h.state != 'released')
           OR (a.state = 'uncertain' AND h.state != 'uncertain')
        LIMIT 1
        """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "authorization lifecycle is invalid")
    if (
        connection.execute(
            """
        SELECT a.id FROM dispatch_authorizations AS a
        JOIN cost_reservations AS r ON r.id = a.cash_reservation_id
        WHERE (a.state IN ('active', 'launched') AND r.state != 'dispatching')
           OR (a.state = 'settled' AND r.state != 'settled')
           OR (a.state = 'released' AND r.state != 'reconciled')
           OR (a.state = 'uncertain' AND r.state NOT IN ('uncertain', 'reconciled'))
        LIMIT 1
        """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "cash authorization lifecycle is invalid")
    cursor = connection.execute(
        """
        SELECT observed_at_utc FROM quota_observations
        UNION ALL SELECT recorded_at_utc FROM quota_observations
        UNION ALL SELECT expires_at_utc FROM quota_observations
        UNION ALL SELECT window_start_utc FROM quota_observations
        UNION ALL SELECT window_end_utc FROM quota_observations
        UNION ALL SELECT observed_at_utc FROM top_up_attestations
        UNION ALL SELECT expires_at_utc FROM top_up_attestations
        UNION ALL SELECT decided_at_utc FROM dispatch_decision_clock
        UNION ALL SELECT decision_at_utc FROM dispatch_authorizations
        UNION ALL SELECT expires_at_utc FROM dispatch_authorizations
        UNION ALL SELECT state_changed_at_utc FROM dispatch_authorizations
        """
    )
    while rows := cursor.fetchmany(512):
        for row in rows:
            try:
                value = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            except ValueError:
                raise FactoryBudgetLedgerError("integrity", "quota timestamp is invalid") from None
            if value.tzinfo is None or value.utcoffset() is None:
                raise FactoryBudgetLedgerError("integrity", "quota timestamp is invalid")
    validate_observation_inclusion_integrity(connection)
