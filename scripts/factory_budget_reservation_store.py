from __future__ import annotations

import sqlite3
from datetime import datetime

from .factory_budget_reservation_models import (
    CostReservationReceipt,
    PriceTerm,
    SettlementOutcome,
)
from .factory_budget_reservation_rows import (
    ReservationEventRow,
    ReservationRow,
    reservation_event_row,
    reservation_price_rows,
    reservation_row,
)

RESERVATION_SELECT = """
    SELECT r.id, r.public_id, r.job_id, r.provider_lane_id, r.provider_id,
           r.model_id, r.requested_model, r.cost_policy_lane_id, r.policy_id,
           r.policy_revision, r.pricing_digest, r.held_microcents,
           r.max_requests, r.max_input_tokens, r.max_output_tokens,
           r.max_minutes, r.actual_microcents, r.state, r.reason,
           r.provider_session_digest, r.settlement_entry_id,
           r.created_at_utc, r.updated_at_utc, p.period_start_utc
    FROM cost_reservations AS r
    JOIN budget_periods AS p ON p.id = r.period_id
"""


def find_reservation_by_digest(
    connection: sqlite3.Connection,
    digest: str,
) -> ReservationRow | None:
    return reservation_row(
        connection.execute(
            RESERVATION_SELECT + " WHERE r.idempotency_digest = ?",
            (digest,),
        )
    )


def find_reservation_by_public_id(
    connection: sqlite3.Connection,
    public_id: str,
) -> ReservationRow | None:
    return reservation_row(
        connection.execute(
            RESERVATION_SELECT + " WHERE r.public_id = ?",
            (public_id,),
        )
    )


def find_reservation_by_job(
    connection: sqlite3.Connection,
    job_id: str,
) -> ReservationRow | None:
    return reservation_row(
        connection.execute(
            RESERVATION_SELECT + " WHERE r.job_id = ?",
            (job_id,),
        )
    )


def price_terms_for(
    connection: sqlite3.Connection,
    reservation_id: int,
) -> tuple[PriceTerm, ...]:
    rows = reservation_price_rows(
        connection.execute(
            """
            SELECT snapshot_id, unit, quantity, price_microcents,
                   observed_at_utc, expires_at_utc
            FROM cost_reservation_prices
            WHERE reservation_id = ?
            ORDER BY unit
            """,
            (reservation_id,),
        )
    )
    return tuple(
        PriceTerm(
            snapshot_id=row[0],
            unit=row[1],
            quantity=row[2],
            price_microcents=row[3],
            observed_at=_parse_utc(row[4]),
            expires_at=_parse_utc(row[5]),
        )
        for row in rows
    )


def find_event(
    connection: sqlite3.Connection,
    digest: str,
) -> ReservationEventRow | None:
    return reservation_event_row(
        connection.execute(
            """
            SELECT id, reservation_id, event_type, resulting_state,
                   occurred_at_utc, reason, evidence_digest, receipt_digest
            FROM cost_reservation_events
            WHERE idempotency_digest = ?
            """,
            (digest,),
        )
    )


def reservation_receipt(
    row: ReservationRow,
    *,
    created: bool,
) -> CostReservationReceipt:
    return CostReservationReceipt(
        created=created,
        reservation_id=row[1],
        state=row[17],
        held_microcents=row[11],
        actual_microcents=row[16],
        reason=row[18],
        period_start_utc=row[23],
        pricing_digest=row[10],
    )


def settlement_outcome(
    row: ReservationRow,
    *,
    created: bool,
    reason: str | None = None,
) -> SettlementOutcome:
    return SettlementOutcome(
        created=created,
        reservation_id=row[1],
        state=row[17],
        held_microcents=row[11],
        actual_microcents=row[16],
        reason=reason if reason is not None else row[18],
        entry_id=row[20],
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
