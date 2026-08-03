from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import FactoryBudgetLedgerError, idempotency_digest
from .factory_budget_reservation_integrity import (
    require_reservation_capacity,
    require_reservation_event_capacity,
)
from .factory_budget_reservation_models import (
    CostReservationReceipt,
    CostReservationRequest,
    PriceTerm,
)
from .factory_budget_reservation_replay import (
    period_reservation_limit_reached,
    require_exact_reservation_replay,
)
from .factory_budget_reservation_rows import reservation_period_authority
from .factory_budget_reservation_store import (
    find_reservation_by_digest,
    find_reservation_by_job,
    find_reservation_by_public_id,
    reservation_receipt,
)
from .factory_budget_reservation_validation import public_reservation_id


def reserve_for_dispatch(
    connection: sqlite3.Connection,
    request: CostReservationRequest,
) -> CostReservationReceipt:
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        receipt = reserve_for_dispatch_locked(connection, request)
        _ = connection.execute("COMMIT")
        return receipt
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.IntegrityError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "reservation constraint failed") from exc
    except sqlite3.OperationalError as exc:
        _rollback(connection)
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
        raise FactoryBudgetLedgerError("database", "reservation write failed") from exc
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "reservation write failed") from exc


def reserve_for_dispatch_locked(
    connection: sqlite3.Connection,
    request: CostReservationRequest,
) -> CostReservationReceipt:
    request.validate()
    digest = idempotency_digest(request.idempotency_key)
    public_id = public_reservation_id(request.idempotency_key)
    existing = find_reservation_by_digest(connection, digest)
    if existing is not None:
        require_exact_reservation_replay(connection, existing, request, public_id)
        return reservation_receipt(existing, created=False)
    if find_reservation_by_job(connection, request.job_id) is not None:
        raise FactoryBudgetLedgerError("job", "job already has a cost reservation")
    require_reservation_capacity(connection, price_count=len(request.price_terms))
    require_reservation_event_capacity(connection)
    period = _period_authority(connection, request)
    if period_reservation_limit_reached(connection, period[0]):
        raise FactoryBudgetLedgerError("limit", "budget period reservation limit reached")
    available = (period[1] - period[2]) - max(period[3], 0) - period[4]
    held = request.worst_case_microcents
    if held > available:
        raise FactoryBudgetLedgerError("budget", "reservation exceeds available budget")
    reservation_id = _insert_reservation(
        connection,
        request=request,
        digest=digest,
        public_id=public_id,
        period_id=period[0],
        held=held,
    )
    _insert_prices(connection, reservation_id, request.price_terms)
    _ = connection.execute(
        """
        INSERT INTO cost_reservation_events(
            reservation_id, idempotency_digest, event_type,
            resulting_state, occurred_at_utc, reason,
            evidence_digest, receipt_digest
        ) VALUES (?, ?, 'dispatch_reserved', 'dispatching', ?, NULL, NULL, NULL)
        """,
        (
            reservation_id,
            idempotency_digest(f"dispatch-event:{request.idempotency_key}"),
            request.occurred_at_utc,
        ),
    )
    _ = connection.execute(
        """
        UPDATE budget_periods
        SET active_reserved_microcents = active_reserved_microcents + ?
        WHERE id = ?
        """,
        (held, period[0]),
    )
    created = find_reservation_by_public_id(connection, public_id)
    if created is None:
        raise FactoryBudgetLedgerError("database", "reservation insert was not observable")
    return reservation_receipt(created, created=True)
def reservation_for_job(
    connection: sqlite3.Connection,
    job_id: str,
) -> CostReservationReceipt | None:
    row = find_reservation_by_job(connection, job_id)
    return None if row is None else reservation_receipt(row, created=False)


def _period_authority(
    connection: sqlite3.Connection,
    request: CostReservationRequest,
) -> tuple[int, int, int, int, int]:
    row = reservation_period_authority(
        connection.execute(
            """
            SELECT id, cash_cap_microcents, emergency_reserve_microcents,
                   net_spent_microcents, active_reserved_microcents,
                   policy_id, policy_revision
            FROM budget_periods WHERE period_start_utc = ?
            """,
            (request.period_start_utc,),
        )
    )
    if row is None:
        raise FactoryBudgetLedgerError("period", "budget period not found")
    if row[5] != request.policy_id or row[6] != request.policy_revision:
        raise FactoryBudgetLedgerError(
            "policy",
            "reservation policy does not match period authority",
        )
    return row[0], row[1], row[2], row[3], row[4]


def _insert_reservation(
    connection: sqlite3.Connection,
    *,
    request: CostReservationRequest,
    digest: str,
    public_id: str,
    period_id: int,
    held: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO cost_reservations(
            public_id, idempotency_digest, period_id, job_id,
            provider_lane_id, provider_id, model_id, requested_model,
            cost_policy_lane_id, policy_id, policy_revision, pricing_digest,
            held_microcents, max_requests, max_input_tokens,
            max_output_tokens, max_minutes, actual_microcents, state, reason,
            provider_session_digest, settlement_entry_id,
            created_at_utc, updated_at_utc
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            NULL, 'dispatching', NULL, NULL, NULL, ?, ?
        )
        """,
        (
            public_id,
            digest,
            period_id,
            request.job_id,
            request.provider_lane_id,
            request.provider_id,
            request.model_id,
            request.requested_model,
            request.cost_policy_lane_id,
            request.policy_id,
            request.policy_revision,
            request.pricing_digest,
            held,
            request.usage_envelope.requests,
            request.usage_envelope.input_tokens,
            request.usage_envelope.output_tokens,
            request.usage_envelope.minutes,
            request.occurred_at_utc,
            request.occurred_at_utc,
        ),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "reservation id is unavailable")
    return cursor.lastrowid


def _insert_prices(
    connection: sqlite3.Connection,
    reservation_id: int,
    terms: tuple[PriceTerm, ...],
) -> None:
    for term in terms:
        _ = connection.execute(
            """
            INSERT INTO cost_reservation_prices(
                reservation_id, snapshot_id, unit, quantity,
                price_microcents, observed_at_utc, expires_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                term.snapshot_id,
                term.unit,
                term.quantity,
                term.price_microcents,
                term.observed_at_utc,
                term.expires_at_utc,
            ),
        )


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
