from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_occurred_at,
    idempotency_digest,
)
from .factory_budget_reservation_store import find_reservation_by_public_id
from .factory_budget_reservations import reserve_for_dispatch_locked
from .factory_quota_capacity import record_validated_observation
from .factory_quota_models import DispatchAuthorizationReceipt, DispatchAuthorizationRequest
from .factory_quota_store import (
    authorization_by_job,
    authorization_replay,
    insert_attestation,
    public_authorization_id,
)
from .factory_quota_store import (
    validate_authorization as validate_authorization,
)
from .factory_quota_thresholds import require_cash_threshold
from .factory_quota_windows import quota_units

CONCURRENT_DECISION_SKEW_LIMIT = timedelta(seconds=1)


def authorize_dispatch(
    connection: sqlite3.Connection,
    request: DispatchAuthorizationRequest,
) -> DispatchAuthorizationReceipt:
    request.validate()
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        replay = authorization_replay(connection, request)
        if replay is not None:
            _ = connection.execute("COMMIT")
            return replay
        if authorization_by_job(connection, request.job_id) is not None:
            raise FactoryBudgetLedgerError("job", "job already has an authorization")
        _require_monotonic_clock(connection, request)
        require_cash_threshold(connection, request)
        attestation = request.top_up_attestation
        if attestation is None:
            raise FactoryBudgetLedgerError("top_up", "fresh top-up attestation is required")
        attestation_id = insert_attestation(connection, attestation)
        observation_ids = tuple(
            record_validated_observation(connection, request, requirement)
            for requirement in request.quota_requirements
        )
        cash_receipt = (
            None
            if request.cash_reservation is None
            else reserve_for_dispatch_locked(connection, request.cash_reservation)
        )
        cash_id = (
            _cash_reservation_id(connection, cash_receipt.reservation_id) if cash_receipt else None
        )
        authorization_id = _insert_authorization(
            connection,
            request=request,
            attestation_id=attestation_id,
            cash_reservation_id=cash_id,
        )
        projected = quota_units(request.usage_envelope)
        for requirement, observation_id in zip(
            request.quota_requirements,
            observation_ids,
            strict=True,
        ):
            _ = connection.execute(
                """
                INSERT INTO quota_holds(
                    authorization_id, observation_id, quota_id, unit,
                    quota_limit, held_units, actual_units, state
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'active')
                """,
                (
                    authorization_id,
                    observation_id,
                    requirement.quota_id,
                    requirement.unit,
                    requirement.limit,
                    projected[requirement.unit],
                ),
            )
        _ = connection.execute(
            """
            INSERT INTO dispatch_decision_clock(singleton, decided_at_utc)
            VALUES (1, ?)
            ON CONFLICT(singleton) DO UPDATE SET decided_at_utc =
                CASE
                    WHEN excluded.decided_at_utc > dispatch_decision_clock.decided_at_utc
                    THEN excluded.decided_at_utc
                    ELSE dispatch_decision_clock.decided_at_utc
                END
            """,
            (canonical_occurred_at(request.decision_at),),
        )
        receipt = authorization_by_job(connection, request.job_id, created=True)
        if receipt is None:
            raise FactoryBudgetLedgerError("database", "authorization insert was not observable")
        _ = connection.execute("COMMIT")
        return receipt
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.IntegrityError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "authorization constraint failed") from exc
    except sqlite3.OperationalError as exc:
        _rollback(connection)
        detail = str(exc).casefold()
        if "locked" in detail or "busy" in detail:
            raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
        raise FactoryBudgetLedgerError("database", "authorization write failed") from exc
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "authorization write failed") from exc


def consume_authorization_for_launch(
    connection: sqlite3.Connection,
    job_id: str,
    *,
    as_of: str,
) -> bool:
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT state FROM dispatch_authorizations WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise FactoryBudgetLedgerError("authorization", "dispatch authorization not found")
        if row[0] != "active":
            raise FactoryBudgetLedgerError(
                "authorization_state",
                "dispatch authorization is not available for launch",
            )
        if not validate_authorization(connection, job_id, as_of=as_of):
            raise FactoryBudgetLedgerError(
                "authorization",
                "dispatch authorization is invalid or stale",
            )
        cursor = connection.execute(
            "UPDATE dispatch_authorizations "
            "SET state = 'launched', state_changed_at_utc = ? "
            "WHERE job_id = ? AND state = 'active'",
            (as_of, job_id),
        )
        if cursor.rowcount != 1:
            raise FactoryBudgetLedgerError(
                "authorization_state",
                "dispatch authorization was already consumed",
            )
        _ = connection.execute("COMMIT")
        return True
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError(
            "database",
            "dispatch authorization launch could not be recorded",
        ) from exc


def _require_monotonic_clock(
    connection: sqlite3.Connection,
    request: DispatchAuthorizationRequest,
) -> None:
    row = connection.execute(
        "SELECT decided_at_utc FROM dispatch_decision_clock WHERE singleton = 1"
    ).fetchone()
    decision = datetime.fromisoformat(canonical_occurred_at(request.decision_at))
    if row is None:
        return
    previous = datetime.fromisoformat(str(row[0]))
    if previous - decision >= CONCURRENT_DECISION_SKEW_LIMIT:
        raise FactoryBudgetLedgerError("clock", "dispatch decision clock rollback rejected")


def _insert_authorization(
    connection: sqlite3.Connection,
    *,
    request: DispatchAuthorizationRequest,
    attestation_id: int,
    cash_reservation_id: int | None,
) -> int:
    reason = f"authorized-{request.billing_mode.replace('_', '-')}"
    cursor = connection.execute(
        """
        INSERT INTO dispatch_authorizations(
            public_id, idempotency_digest, request_digest, job_id,
            provider_lane_id, provider_id, cost_policy_lane_id, policy_id,
            policy_revision, billing_mode, work_purpose, cash_reservation_id,
            top_up_attestation_id, decision_at_utc, expires_at_utc,
            state, state_changed_at_utc, settlement_digest, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL, ?)
        """,
        (
            public_authorization_id(request.idempotency_key),
            idempotency_digest(request.idempotency_key),
            request.request_digest,
            request.job_id,
            request.provider_lane_id,
            request.provider_id,
            request.cost_policy_lane_id,
            request.policy_id,
            request.policy_revision,
            request.billing_mode,
            request.work_purpose,
            cash_reservation_id,
            attestation_id,
            canonical_occurred_at(request.decision_at),
            canonical_occurred_at(request.expires_at),
            canonical_occurred_at(request.decision_at),
            reason,
        ),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "authorization id is unavailable")
    return cursor.lastrowid


def _cash_reservation_id(connection: sqlite3.Connection, public_id: str) -> int:
    row = find_reservation_by_public_id(connection, public_id)
    if row is None:
        raise FactoryBudgetLedgerError("database", "cash reservation is unavailable")
    return row[0]


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
