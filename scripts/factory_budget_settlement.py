from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_occurred_at,
    idempotency_digest,
)
from .factory_budget_reservation_integrity import require_reservation_event_capacity
from .factory_budget_reservation_models import (
    SettlementOutcome,
    SettlementReceipt,
    priced_cost,
)
from .factory_budget_reservation_rows import ReservationRow
from .factory_budget_reservation_store import (
    find_event,
    find_reservation_by_public_id,
    price_terms_for,
    settlement_outcome,
)
from .factory_budget_reservation_validation import require_identifier
from .factory_budget_settlement_mutations import (
    insert_receipt_event,
    post_settlement,
    record_rejection,
)
from .factory_budget_settlement_validation import (
    receipt_digest,
    rejection_reason,
    usage_exceeds_envelope,
)


def settle_reservation(
    connection: sqlite3.Connection,
    receipt: SettlementReceipt,
) -> SettlementOutcome:
    require_identifier(receipt.idempotency_key, "idempotency key")
    require_identifier(receipt.reservation_id, "reservation id")
    occurred_at = canonical_occurred_at(receipt.occurred_at)
    event_digest = idempotency_digest(receipt.idempotency_key)
    normalized_receipt_digest = receipt_digest(receipt, occurred_at)
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        reservation = _required_reservation(connection, receipt.reservation_id)
        replay = find_event(connection, event_digest)
        if replay is not None:
            if replay[1] != reservation[0] or replay[7] != normalized_receipt_digest:
                raise FactoryBudgetLedgerError(
                    "idempotency",
                    "idempotency key conflicts with an existing reservation event",
                )
            outcome = settlement_outcome(reservation, created=False)
            _ = connection.execute("COMMIT")
            return outcome
        require_reservation_event_capacity(connection)
        if reservation[17] in {"settled", "reconciled"}:
            insert_receipt_event(
                connection,
                reservation=reservation,
                event_digest=event_digest,
                receipt_digest=normalized_receipt_digest,
                occurred_at=occurred_at,
                state=reservation[17],
                reason="reservation_already_terminal",
                evidence_digest=None,
            )
            outcome = settlement_outcome(
                reservation,
                created=True,
                reason="reservation_already_terminal",
            )
            _ = connection.execute("COMMIT")
            return outcome
        rejection = rejection_reason(connection, reservation, receipt)
        if rejection is not None:
            outcome = record_rejection(
                connection,
                reservation=reservation,
                event_digest=event_digest,
                receipt_digest=normalized_receipt_digest,
                occurred_at=occurred_at,
                reason=rejection,
            )
            _ = connection.execute("COMMIT")
            return outcome
        terms = price_terms_for(connection, reservation[0])
        actual = priced_cost(receipt.usage, terms, require_positive=False)
        if actual == 0:
            outcome = record_rejection(
                connection,
                reservation=reservation,
                event_digest=event_digest,
                receipt_digest=normalized_receipt_digest,
                occurred_at=occurred_at,
                reason="zero_usage_receipt",
            )
            _ = connection.execute("COMMIT")
            return outcome
        if actual > reservation[11] or usage_exceeds_envelope(reservation, receipt):
            outcome = record_rejection(
                connection,
                reservation=reservation,
                event_digest=event_digest,
                receipt_digest=normalized_receipt_digest,
                occurred_at=occurred_at,
                reason="actual_exceeds_reservation",
            )
            _ = connection.execute("COMMIT")
            return outcome
        entry_id = post_settlement(
            connection,
            reservation=reservation,
            receipt=receipt,
            event_digest=event_digest,
            receipt_digest=normalized_receipt_digest,
            occurred_at=occurred_at,
            actual=actual,
        )
        updated = _required_reservation(connection, receipt.reservation_id)
        outcome = settlement_outcome(updated, created=True)
        if outcome.entry_id != entry_id:
            raise FactoryBudgetLedgerError("database", "settlement entry was not observable")
        _ = connection.execute("COMMIT")
        return outcome
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.OperationalError as exc:
        _rollback(connection)
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
        raise FactoryBudgetLedgerError("database", "settlement write failed") from exc
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "settlement write failed") from exc


def _required_reservation(
    connection: sqlite3.Connection,
    public_id: str,
) -> ReservationRow:
    row = find_reservation_by_public_id(connection, public_id)
    if row is None:
        raise FactoryBudgetLedgerError("reservation", "cost reservation not found")
    return row


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
