from __future__ import annotations

import sqlite3
from datetime import datetime

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_occurred_at,
    idempotency_digest,
)
from .factory_budget_reservation_integrity import require_reservation_event_capacity
from .factory_budget_reservation_models import (
    SettlementOutcome,
    UncertaintyReason,
)
from .factory_budget_reservation_store import (
    find_event,
    find_reservation_by_public_id,
    settlement_outcome,
)
from .factory_budget_reservation_validation import require_identifier, require_sha256

UNCERTAINTY_REASONS = frozenset(
    {
        "actual_exceeds_reservation",
        "job_mismatch",
        "malformed_receipt",
        "model_mismatch",
        "partial_receipt",
        "provider_mismatch",
        "provider_session_conflict",
        "run_mismatch",
        "worker_interrupted",
        "zero_usage_receipt",
    }
)


def mark_reservation_uncertain(
    connection: sqlite3.Connection,
    reservation_id: str,
    *,
    idempotency_key: str,
    reason: UncertaintyReason,
    occurred_at: datetime,
    evidence_digest: str,
) -> SettlementOutcome:
    require_identifier(idempotency_key, "idempotency key")
    require_identifier(reservation_id, "reservation id")
    if reason not in UNCERTAINTY_REASONS:
        raise FactoryBudgetLedgerError("reason", "uncertainty reason is unsupported")
    require_sha256(evidence_digest, "evidence digest")
    normalized_time = canonical_occurred_at(occurred_at)
    event_digest = idempotency_digest(idempotency_key)
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        reservation = find_reservation_by_public_id(connection, reservation_id)
        if reservation is None:
            raise FactoryBudgetLedgerError("reservation", "cost reservation not found")
        replay = find_event(connection, event_digest)
        if replay is not None:
            if (
                replay[1] != reservation[0]
                or replay[4] != normalized_time
                or replay[5] != reason
                or replay[6] != evidence_digest
                or replay[7] is not None
            ):
                raise FactoryBudgetLedgerError(
                    "idempotency",
                    "idempotency key conflicts with an existing reservation event",
                )
            outcome = settlement_outcome(reservation, created=False)
            _ = connection.execute("COMMIT")
            return outcome
        if reservation[17] in {"settled", "reconciled"}:
            outcome = settlement_outcome(
                reservation,
                created=False,
                reason="reservation_already_terminal",
            )
            _ = connection.execute("COMMIT")
            return outcome
        require_reservation_event_capacity(connection)
        _ = connection.execute(
            """
            UPDATE cost_reservations
            SET state = 'uncertain', reason = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (reason, normalized_time, reservation[0]),
        )
        _ = connection.execute(
            """
            INSERT INTO cost_reservation_events(
                reservation_id, idempotency_digest, event_type,
                resulting_state, occurred_at_utc, reason,
                evidence_digest, receipt_digest
            ) VALUES (?, ?, 'receipt_rejected', 'uncertain', ?, ?, ?, NULL)
            """,
            (
                reservation[0],
                event_digest,
                normalized_time,
                reason,
                evidence_digest,
            ),
        )
        updated = find_reservation_by_public_id(connection, reservation_id)
        if updated is None:
            raise FactoryBudgetLedgerError("database", "reservation update was not observable")
        outcome = settlement_outcome(updated, created=True)
        _ = connection.execute("COMMIT")
        return outcome
    except (FactoryBudgetLedgerError, sqlite3.DatabaseError) as exc:
        if connection.in_transaction:
            _ = connection.execute("ROLLBACK")
        if isinstance(exc, FactoryBudgetLedgerError):
            raise
        raise FactoryBudgetLedgerError("database", "uncertainty write failed") from exc
