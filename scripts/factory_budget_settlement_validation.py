from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_models import (
    SettlementReceipt,
    UncertaintyReason,
)
from .factory_budget_reservation_rows import ReservationRow
from .factory_budget_reservation_validation import canonical_digest, require_sha256


def rejection_reason(
    connection: sqlite3.Connection,
    reservation: ReservationRow,
    receipt: SettlementReceipt,
) -> UncertaintyReason | None:
    if receipt.job_id != reservation[2]:
        return "job_mismatch"
    if receipt.provider_lane_id != reservation[3] or receipt.provider_id != reservation[4]:
        return "provider_mismatch"
    if receipt.model_id != reservation[5] or receipt.requested_model != reservation[6]:
        return "model_mismatch"
    try:
        require_sha256(receipt.provider_session_digest, "provider session digest")
        receipt.usage.validate()
    except FactoryBudgetLedgerError:
        return "malformed_receipt"
    duplicate_session = (
        connection.execute(
            """
            SELECT 1 FROM cost_reservations
            WHERE provider_session_digest = ? AND id != ?
            """,
            (receipt.provider_session_digest, reservation[0]),
        ).fetchone()
        is not None
    )
    return "provider_session_conflict" if duplicate_session else None


def usage_exceeds_envelope(
    reservation: ReservationRow,
    receipt: SettlementReceipt,
) -> bool:
    return any(
        actual > maximum
        for actual, maximum in (
            (receipt.requests, reservation[12]),
            (receipt.input_tokens, reservation[13]),
            (receipt.output_tokens, reservation[14]),
            (receipt.minutes, reservation[15]),
        )
    )


def receipt_digest(receipt: SettlementReceipt, occurred_at: str) -> str:
    return canonical_digest(
        {
            "input_tokens": receipt.input_tokens,
            "job_id": receipt.job_id,
            "minutes": receipt.minutes,
            "model_id": receipt.model_id,
            "occurred_at_utc": occurred_at,
            "output_tokens": receipt.output_tokens,
            "provider_id": receipt.provider_id,
            "provider_lane_id": receipt.provider_lane_id,
            "provider_session_digest": receipt.provider_session_digest,
            "requested_model": receipt.requested_model,
            "reservation_id": receipt.reservation_id,
            "requests": receipt.requests,
        }
    )
