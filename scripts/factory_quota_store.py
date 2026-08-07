from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from typing import Literal

from .factory_budget_ledger_models import FactoryBudgetLedgerError, idempotency_digest
from .factory_quota_inclusions import store_observation_inclusions, stored_inclusion_ids
from .factory_quota_models import (
    DispatchAuthorizationReceipt,
    DispatchAuthorizationRequest,
    QuotaObservation,
    TopUpAttestation,
)
from .factory_quota_thresholds import require_launch_cash_threshold

type QuotaAuthorizationState = Literal[
    "active",
    "launched",
    "settled",
    "released",
    "uncertain",
]


def public_authorization_id(idempotency_key: str) -> str:
    return f"auth-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}"


def authorization_by_job(
    connection: sqlite3.Connection,
    job_id: str,
    *,
    created: bool = False,
) -> DispatchAuthorizationReceipt | None:
    row = connection.execute(
        """
        SELECT a.public_id, a.job_id, a.reason, r.public_id,
               COALESCE(r.held_microcents, 0), a.decision_at_utc, a.expires_at_utc,
               a.id
        FROM dispatch_authorizations AS a
        LEFT JOIN cost_reservations AS r ON r.id = a.cash_reservation_id
        WHERE a.job_id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    holds = tuple(
        (str(item[0]), int(item[1]))
        for item in connection.execute(
            "SELECT quota_id, held_units FROM quota_holds "
            "WHERE authorization_id = ? ORDER BY quota_id",
            (row[7],),
        ).fetchall()
    )
    return DispatchAuthorizationReceipt(
        created=created,
        authorization_id=str(row[0]),
        job_id=str(row[1]),
        reason=str(row[2]),
        reservation_id=None if row[3] is None else str(row[3]),
        held_microcents=int(row[4]),
        quota_holds=holds,
        decision_at=_parse_utc(str(row[5])),
        expires_at=_parse_utc(str(row[6])),
    )


def authorization_replay(
    connection: sqlite3.Connection,
    request: DispatchAuthorizationRequest,
) -> DispatchAuthorizationReceipt | None:
    row = connection.execute(
        "SELECT job_id, request_digest FROM dispatch_authorizations WHERE idempotency_digest = ?",
        (idempotency_digest(request.idempotency_key),),
    ).fetchone()
    if row is None:
        return None
    if row != (request.job_id, request.request_digest):
        raise FactoryBudgetLedgerError("idempotency", "authorization idempotency key conflicts")
    receipt = authorization_by_job(connection, request.job_id)
    if receipt is None:
        raise FactoryBudgetLedgerError("database", "authorization replay is invalid")
    return receipt


def quota_authorization_state(
    connection: sqlite3.Connection,
    authorization_id: str,
) -> QuotaAuthorizationState | None:
    row = connection.execute(
        "SELECT state, cash_reservation_id FROM dispatch_authorizations WHERE public_id = ?",
        (authorization_id,),
    ).fetchone()
    if row is None:
        return None
    if row[1] is not None:
        raise FactoryBudgetLedgerError(
            "authorization",
            "cash-backed authorization does not have quota-only state",
        )
    state = row[0]
    if state == "active":
        return "active"
    if state == "launched":
        return "launched"
    if state == "settled":
        return "settled"
    if state == "released":
        return "released"
    if state == "uncertain":
        return "uncertain"
    raise FactoryBudgetLedgerError("integrity", "quota authorization state is invalid")


def validate_authorization(
    connection: sqlite3.Connection,
    job_id: str,
    *,
    as_of: str,
) -> bool:
    row = connection.execute(
        """
        SELECT a.decision_at_utc, a.expires_at_utc, t.expires_at_utc,
               a.state, a.cash_reservation_id, r.state
        FROM dispatch_authorizations AS a
        JOIN top_up_attestations AS t ON t.id = a.top_up_attestation_id
        LEFT JOIN cost_reservations AS r ON r.id = a.cash_reservation_id
        WHERE a.job_id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return False
    if row[3] != "active":
        return False
    if row[4] is not None and row[5] != "dispatching":
        return False
    try:
        require_launch_cash_threshold(connection, job_id, as_of=as_of)
    except FactoryBudgetLedgerError:
        return False
    clock = connection.execute(
        "SELECT decided_at_utc FROM dispatch_decision_clock WHERE singleton = 1"
    ).fetchone()
    if clock is not None and as_of < str(clock[0]):
        return False
    if not (str(row[0]) <= as_of < str(row[1]) and as_of < str(row[2])):
        return False
    invalid_hold = connection.execute(
        """
        SELECT 1
        FROM dispatch_authorizations AS a
        JOIN quota_holds AS h ON h.authorization_id = a.id
        JOIN quota_observations AS o ON o.id = h.observation_id
        WHERE a.job_id = ? AND (
            h.state != 'active' OR o.known != 1 OR o.expires_at_utc <= ?
            OR o.window_start_utc > ? OR o.window_end_utc <= ?
        )
        LIMIT 1
        """,
        (job_id, as_of, as_of, as_of),
    ).fetchone()
    return invalid_hold is None


def insert_attestation(
    connection: sqlite3.Connection,
    attestation: TopUpAttestation,
) -> int:
    expected = (
        attestation.provider_id,
        attestation.provider_lane_id,
        attestation.policy_id,
        attestation.policy_revision,
        attestation.mode,
        attestation.source_kind,
        attestation.source_id,
        attestation.evidence_digest,
        attestation.observed_at_utc,
        attestation.expires_at_utc,
    )
    row = connection.execute(
        """
        SELECT id, provider_id, provider_lane_id, policy_id, policy_revision,
               mode, source_kind, source_id, evidence_digest,
               observed_at_utc, expires_at_utc
        FROM top_up_attestations WHERE attestation_id = ?
        """,
        (attestation.attestation_id,),
    ).fetchone()
    if row is not None:
        if row[1:] != expected:
            raise FactoryBudgetLedgerError("evidence", "top-up attestation id conflicts")
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO top_up_attestations(
            attestation_id, provider_id, provider_lane_id, policy_id,
            policy_revision, mode, source_kind, source_id, evidence_digest,
            observed_at_utc, expires_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (attestation.attestation_id, *expected),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "top-up attestation id is unavailable")
    return cursor.lastrowid


def insert_observation(
    connection: sqlite3.Connection,
    observation: QuotaObservation,
) -> int:
    expected = observation_storage_values(observation)
    row = connection.execute(
        """
        SELECT id, provider_id, provider_lane_id, policy_id, policy_revision,
               unit, source_kind, source_id, observed_at_utc, recorded_at_utc,
               expires_at_utc, window_kind, window_start_utc, window_end_utc,
               cycle_id, used_units, known, evidence_digest, inclusions_digest
        FROM quota_observations WHERE observation_id = ?
        """,
        (observation.observation_id,),
    ).fetchone()
    if row is not None:
        if row[1:] != expected:
            raise FactoryBudgetLedgerError("evidence", "quota observation id conflicts")
        observation_row_id = int(row[0])
        if stored_inclusion_ids(connection, observation_row_id) != (
            observation.included_authorization_ids
        ):
            raise FactoryBudgetLedgerError("evidence", "quota observation inclusion conflicts")
        return observation_row_id
    cursor = connection.execute(
        """
        INSERT INTO quota_observations(
            observation_id, quota_id, provider_id, provider_lane_id, policy_id,
            policy_revision, unit, source_kind, source_id, observed_at_utc,
            recorded_at_utc, expires_at_utc, window_kind, window_start_utc,
            window_end_utc, cycle_id, used_units, known, evidence_digest,
            inclusions_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (observation.observation_id, observation.quota_id, *expected),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "quota observation id is unavailable")
    observation_row_id = cursor.lastrowid
    store_observation_inclusions(connection, observation_row_id, observation)
    return observation_row_id


def observation_storage_values(observation: QuotaObservation) -> tuple[str | int | None, ...]:
    return (
        observation.provider_id,
        observation.provider_lane_id,
        observation.policy_id,
        observation.policy_revision,
        observation.unit,
        observation.source_kind,
        observation.source_id,
        observation.observed_at_utc,
        observation.recorded_at_utc,
        observation.expires_at_utc,
        observation.window.kind,
        observation.window.starts_at_utc,
        observation.window.ends_at_utc,
        observation.window.cycle_id,
        observation.used_units,
        int(observation.known),
        observation.evidence_digest,
        observation.inclusions_digest,
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
