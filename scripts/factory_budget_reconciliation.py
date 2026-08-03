from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    canonical_occurred_at,
    idempotency_digest,
)
from .factory_budget_reconciliation_mutations import (
    insert_manual_entry,
    insert_reconciliation_event,
    require_reconciliation_replay,
)
from .factory_budget_reservation_integrity import require_reservation_event_capacity
from .factory_budget_reservation_models import (
    ManualReconciliationInput,
    NoChargeReconciliationInput,
    SettlementOutcome,
)
from .factory_budget_reservation_rows import ReservationRow
from .factory_budget_reservation_store import (
    find_event,
    find_reservation_by_public_id,
    settlement_outcome,
)
from .factory_budget_reservation_validation import require_identifier, require_sha256
from .factory_quota_settlement import mark_quota_holds_uncertain, release_quota_holds


def reconcile_no_charge(
    connection: sqlite3.Connection,
    command: NoChargeReconciliationInput,
) -> SettlementOutcome:
    _validate_reconciliation(
        command.idempotency_key,
        command.reservation_id,
        command.evidence_digest,
    )
    occurred_at = canonical_occurred_at(command.occurred_at)
    return _reconcile(
        connection,
        idempotency_key=command.idempotency_key,
        reservation_id=command.reservation_id,
        evidence_digest=command.evidence_digest,
        occurred_at=occurred_at,
        reason=command.reason,
        amount=0,
        source_id=None,
    )


def reconcile_manual_debit(
    connection: sqlite3.Connection,
    command: ManualReconciliationInput,
) -> SettlementOutcome:
    _validate_reconciliation(
        command.idempotency_key,
        command.reservation_id,
        command.evidence_digest,
    )
    require_identifier(command.source_id, "manual adjustment source id")
    amount = _validated_positive_amount(command.amount_microcents)
    return _reconcile(
        connection,
        idempotency_key=command.idempotency_key,
        reservation_id=command.reservation_id,
        evidence_digest=command.evidence_digest,
        occurred_at=canonical_occurred_at(command.occurred_at),
        reason="manual_adjustment",
        amount=amount,
        source_id=command.source_id,
    )


def _reconcile(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    reservation_id: str,
    evidence_digest: str,
    occurred_at: str,
    reason: str,
    amount: int,
    source_id: str | None,
) -> SettlementOutcome:
    event_digest = idempotency_digest(idempotency_key)
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        reservation = _required_reservation(connection, reservation_id)
        replay = find_event(connection, event_digest)
        if replay is not None:
            require_reconciliation_replay(
                connection,
                replay,
                reservation=reservation,
                occurred_at=occurred_at,
                reason=reason,
                evidence_digest=evidence_digest,
                amount=amount,
                source_id=source_id,
            )
            outcome = settlement_outcome(reservation, created=False)
            _ = connection.execute("COMMIT")
            return outcome
        if reservation[17] in {"settled", "reconciled"}:
            raise FactoryBudgetLedgerError("state", "reservation is already terminal")
        require_reservation_event_capacity(connection)
        if amount > reservation[11]:
            raise FactoryBudgetLedgerError(
                "amount",
                "manual reconciliation exceeds the held amount",
            )
        entry_id = insert_manual_entry(
            connection,
            reservation=reservation,
            idempotency_key=idempotency_key,
            amount=amount,
            source_id=source_id,
        )
        _ = connection.execute(
            """
            UPDATE budget_periods
            SET net_spent_microcents = net_spent_microcents + ?,
                active_reserved_microcents = active_reserved_microcents - ?,
                entry_count = entry_count + ?
            WHERE period_start_utc = ?
            """,
            (amount, reservation[11], int(amount > 0), reservation[23]),
        )
        _ = connection.execute(
            """
            UPDATE cost_reservations
            SET actual_microcents = ?, state = 'reconciled', reason = ?,
                settlement_entry_id = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (amount, reason, entry_id, occurred_at, reservation[0]),
        )
        insert_reconciliation_event(
            connection,
            reservation=reservation,
            event_digest=event_digest,
            event_type=("reconciled_manual_debit" if amount > 0 else "reconciled_no_charge"),
            occurred_at=occurred_at,
            reason=reason,
            evidence_digest=evidence_digest,
        )
        if amount == 0:
            release_quota_holds(
                connection,
                cash_reservation_id=reservation[0],
                occurred_at=occurred_at,
            )
        else:
            mark_quota_holds_uncertain(
                connection,
                cash_reservation_id=reservation[0],
                occurred_at=occurred_at,
            )
        updated = _required_reservation(connection, reservation_id)
        outcome = settlement_outcome(updated, created=True)
        _ = connection.execute("COMMIT")
        return outcome
    except (FactoryBudgetLedgerError, sqlite3.DatabaseError) as exc:
        _rollback(connection)
        if isinstance(exc, FactoryBudgetLedgerError):
            raise
        raise FactoryBudgetLedgerError("database", "reconciliation write failed") from exc


def _validate_reconciliation(
    idempotency_key: str,
    reservation_id: str,
    evidence_digest: str,
) -> None:
    require_identifier(idempotency_key, "idempotency key")
    require_identifier(reservation_id, "reservation id")
    require_sha256(evidence_digest, "evidence digest")


def _validated_positive_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FactoryBudgetLedgerError(
            "amount",
            "manual reconciliation amount must be positive",
        )
    return value


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
