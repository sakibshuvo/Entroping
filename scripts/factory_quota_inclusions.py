from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_validation import canonical_digest
from .factory_quota_evidence import QuotaObservation


def store_observation_inclusions(
    connection: sqlite3.Connection,
    observation_id: int,
    observation: QuotaObservation,
) -> None:
    included_units = 0
    for public_id in observation.included_authorization_ids:
        row = connection.execute(
            """
            SELECT a.id, a.provider_id, a.provider_lane_id, a.policy_id,
                   a.policy_revision, a.state, a.state_changed_at_utc,
                   h.actual_units, source.window_start_utc, source.window_end_utc
            FROM dispatch_authorizations AS a
            JOIN quota_holds AS h ON h.authorization_id = a.id
            JOIN quota_observations AS source ON source.id = h.observation_id
            WHERE a.public_id = ? AND h.quota_id = ? AND h.unit = ?
            """,
            (public_id, observation.quota_id, observation.unit),
        ).fetchone()
        if row is None:
            raise FactoryBudgetLedgerError(
                "quota",
                "included authorization does not have matching settled quota",
            )
        identity = (row[1], row[2], row[3], row[4])
        if identity != (
            observation.provider_id,
            observation.provider_lane_id,
            observation.policy_id,
            observation.policy_revision,
        ):
            raise FactoryBudgetLedgerError(
                "quota",
                "included authorization identity is mismatched",
            )
        if (
            row[5] != "settled"
            or row[7] is None
            or str(row[6]) > observation.observed_at_utc
            or str(row[8]) >= observation.window.ends_at_utc
            or str(row[9]) <= observation.window.starts_at_utc
        ):
            raise FactoryBudgetLedgerError(
                "quota",
                "included authorization is not covered by the observation",
            )
        included_units += int(row[7])
        if included_units > observation.used_units:
            raise FactoryBudgetLedgerError(
                "quota",
                "included authorization usage exceeds observed provider usage",
            )
        _ = connection.execute(
            "INSERT INTO quota_observation_inclusions(observation_id, authorization_id) "
            "VALUES (?, ?)",
            (observation_id, int(row[0])),
        )


def stored_inclusion_ids(
    connection: sqlite3.Connection,
    observation_id: int,
) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT a.public_id
            FROM quota_observation_inclusions AS inclusion
            JOIN dispatch_authorizations AS a ON a.id = inclusion.authorization_id
            WHERE inclusion.observation_id = ?
            ORDER BY a.public_id
            """,
            (observation_id,),
        ).fetchall()
    )


def validate_observation_inclusion_integrity(connection: sqlite3.Connection) -> None:
    if (
        connection.execute(
            """
            SELECT inclusion.observation_id
            FROM quota_observation_inclusions AS inclusion
            JOIN quota_observations AS observation ON observation.id = inclusion.observation_id
            JOIN dispatch_authorizations AS authorization
              ON authorization.id = inclusion.authorization_id
            LEFT JOIN quota_holds AS hold
              ON hold.authorization_id = authorization.id
             AND hold.quota_id = observation.quota_id
             AND hold.unit = observation.unit
            LEFT JOIN quota_observations AS source ON source.id = hold.observation_id
            WHERE hold.id IS NULL
               OR authorization.provider_id != observation.provider_id
               OR authorization.provider_lane_id != observation.provider_lane_id
               OR authorization.policy_id != observation.policy_id
               OR authorization.policy_revision != observation.policy_revision
               OR authorization.state != 'settled'
               OR authorization.state_changed_at_utc > observation.observed_at_utc
               OR hold.state != 'settled'
               OR hold.actual_units IS NULL
               OR source.window_start_utc >= observation.window_end_utc
               OR source.window_end_utc <= observation.window_start_utc
            LIMIT 1
            """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "quota observation inclusion is invalid")
    if (
        connection.execute(
            """
            SELECT observation.id
            FROM quota_observations AS observation
            JOIN quota_observation_inclusions AS inclusion
              ON inclusion.observation_id = observation.id
            JOIN quota_holds AS hold ON hold.authorization_id = inclusion.authorization_id
              AND hold.quota_id = observation.quota_id AND hold.unit = observation.unit
            GROUP BY observation.id
            HAVING COUNT(*) > 256 OR SUM(hold.actual_units) > observation.used_units
            LIMIT 1
            """
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError("integrity", "quota observation inclusion is unbounded")
    _validate_inclusion_digests(connection)


def _validate_inclusion_digests(connection: sqlite3.Connection) -> None:
    current_id: int | None = None
    current_digest = ""
    included_ids: list[str] = []
    cursor = connection.execute(
        """
        SELECT observation.id, observation.inclusions_digest, authorization.public_id
        FROM quota_observations AS observation
        LEFT JOIN quota_observation_inclusions AS inclusion
          ON inclusion.observation_id = observation.id
        LEFT JOIN dispatch_authorizations AS authorization
          ON authorization.id = inclusion.authorization_id
        ORDER BY observation.id, authorization.public_id
        """
    )
    while rows := cursor.fetchmany(512):
        for raw_id, raw_digest, raw_public_id in rows:
            observation_id = int(raw_id)
            if current_id is not None and observation_id != current_id:
                _require_inclusion_digest(current_digest, included_ids)
                included_ids = []
            current_id = observation_id
            current_digest = str(raw_digest)
            if raw_public_id is not None:
                included_ids.append(str(raw_public_id))
    if current_id is not None:
        _require_inclusion_digest(current_digest, included_ids)


def _require_inclusion_digest(expected: str, included_ids: list[str]) -> None:
    if canonical_digest(tuple(included_ids)) != expected:
        raise FactoryBudgetLedgerError("integrity", "quota inclusion digest is invalid")
