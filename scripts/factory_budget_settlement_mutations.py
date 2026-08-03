from __future__ import annotations

import sqlite3

from .factory_budget_ledger_integrity import require_entry_capacity
from .factory_budget_ledger_models import FactoryBudgetLedgerError, idempotency_digest
from .factory_budget_reservation_models import (
    SettlementOutcome,
    SettlementReceipt,
    UncertaintyReason,
)
from .factory_budget_reservation_rows import ReservationRow
from .factory_budget_reservation_store import (
    find_reservation_by_public_id,
    settlement_outcome,
)
from .factory_quota_settlement import mark_quota_holds_uncertain, settle_quota_holds


def post_settlement(
    connection: sqlite3.Connection,
    *,
    reservation: ReservationRow,
    receipt: SettlementReceipt,
    event_digest: str,
    receipt_digest: str,
    occurred_at: str,
    actual: int,
) -> int | None:
    if actual <= 0:
        raise FactoryBudgetLedgerError("amount", "settlement cost must be positive")
    require_entry_capacity(connection)
    cursor = connection.execute(
        """
        INSERT INTO ledger_entries(
            idempotency_digest, period_id, kind, direction,
            amount_microcents, occurred_at_utc, currency, source_id,
            reference_entry_id
        ) VALUES (?, (SELECT id FROM budget_periods WHERE period_start_utc = ?),
            'provider_charge', 'debit', ?, ?, 'USD', ?, NULL)
        """,
        (
            idempotency_digest(f"settlement-entry:{receipt.idempotency_key}"),
            reservation[23],
            actual,
            reservation[21],
            reservation[4],
        ),
    )
    entry_id = cursor.lastrowid
    if entry_id is None:
        raise FactoryBudgetLedgerError("database", "settlement entry id is unavailable")
    _ = connection.execute(
        """
        UPDATE budget_periods
        SET net_spent_microcents = net_spent_microcents + ?,
            active_reserved_microcents = active_reserved_microcents - ?,
            entry_count = entry_count + ?
        WHERE period_start_utc = ?
        """,
        (actual, reservation[11], 1, reservation[23]),
    )
    _ = connection.execute(
        """
        UPDATE cost_reservations
        SET actual_microcents = ?, state = ?, reason = ?,
            provider_session_digest = ?, settlement_entry_id = ?,
            updated_at_utc = ?
        WHERE id = ?
        """,
        (
            actual,
            "settled",
            "complete",
            receipt.provider_session_digest,
            entry_id,
            occurred_at,
            reservation[0],
        ),
    )
    insert_receipt_event(
        connection,
        reservation=reservation,
        event_digest=event_digest,
        receipt_digest=receipt_digest,
        occurred_at=occurred_at,
        state="settled",
        reason="complete",
        evidence_digest=receipt.provider_session_digest,
    )
    settle_quota_holds(
        connection,
        cash_reservation_id=reservation[0],
        usage=receipt.usage,
        occurred_at=occurred_at,
    )
    return entry_id


def record_rejection(
    connection: sqlite3.Connection,
    *,
    reservation: ReservationRow,
    event_digest: str,
    receipt_digest: str,
    occurred_at: str,
    reason: UncertaintyReason,
) -> SettlementOutcome:
    _ = connection.execute(
        """
        UPDATE cost_reservations
        SET state = 'uncertain', reason = ?, updated_at_utc = ?
        WHERE id = ?
        """,
        (reason, occurred_at, reservation[0]),
    )
    mark_quota_holds_uncertain(
        connection,
        cash_reservation_id=reservation[0],
        occurred_at=occurred_at,
    )
    insert_receipt_event(
        connection,
        reservation=reservation,
        event_digest=event_digest,
        receipt_digest=receipt_digest,
        occurred_at=occurred_at,
        state="uncertain",
        reason=reason,
        evidence_digest=None,
    )
    updated = find_reservation_by_public_id(connection, reservation[1])
    if updated is None:
        raise FactoryBudgetLedgerError("database", "reservation update was not observable")
    return settlement_outcome(updated, created=True)


def insert_receipt_event(
    connection: sqlite3.Connection,
    *,
    reservation: ReservationRow,
    event_digest: str,
    receipt_digest: str,
    occurred_at: str,
    state: str,
    reason: str,
    evidence_digest: str | None,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO cost_reservation_events(
            reservation_id, idempotency_digest, event_type,
            resulting_state, occurred_at_utc, reason,
            evidence_digest, receipt_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reservation[0],
            event_digest,
            "settled" if state == "settled" else "receipt_rejected",
            state,
            occurred_at,
            reason,
            evidence_digest,
            receipt_digest,
        ),
    )
