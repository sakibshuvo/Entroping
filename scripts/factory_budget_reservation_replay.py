from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_models import CostReservationRequest
from .factory_budget_reservation_rows import ReservationRow
from .factory_budget_reservation_store import price_terms_for

MAX_PERIOD_RESERVATIONS = 100_000


def require_exact_reservation_replay(
    connection: sqlite3.Connection,
    row: ReservationRow,
    request: CostReservationRequest,
    public_id: str,
) -> None:
    expected = (
        public_id,
        request.job_id,
        request.provider_lane_id,
        request.provider_id,
        request.model_id,
        request.requested_model,
        request.cost_policy_lane_id,
        request.policy_id,
        request.policy_revision,
        request.pricing_digest,
        request.worst_case_microcents,
        request.usage_envelope.requests,
        request.usage_envelope.input_tokens,
        request.usage_envelope.output_tokens,
        request.usage_envelope.minutes,
        request.occurred_at_utc,
        request.period_start_utc,
    )
    actual = (*row[1:16], row[21], row[23])
    if actual != expected or price_terms_for(connection, row[0]) != tuple(
        sorted(request.price_terms, key=lambda item: item.unit)
    ):
        raise FactoryBudgetLedgerError(
            "idempotency",
            "idempotency key conflicts with an existing cost reservation",
        )


def period_reservation_limit_reached(
    connection: sqlite3.Connection,
    period_id: int,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM cost_reservations
            WHERE period_id = ? ORDER BY id LIMIT 1 OFFSET ?
            """,
            (period_id, MAX_PERIOD_RESERVATIONS - 1),
        ).fetchone()
        is not None
    )
