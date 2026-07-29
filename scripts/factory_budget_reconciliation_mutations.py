from __future__ import annotations

import sqlite3

from .factory_budget_ledger_integrity import require_entry_capacity
from .factory_budget_ledger_models import FactoryBudgetLedgerError, idempotency_digest
from .factory_budget_ledger_rows import manual_adjustment_authority
from .factory_budget_reservation_rows import ReservationEventRow, ReservationRow


def insert_manual_entry(
    connection: sqlite3.Connection,
    *,
    reservation: ReservationRow,
    idempotency_key: str,
    amount: int,
    source_id: str | None,
) -> int | None:
    if amount == 0:
        return None
    if source_id is None:
        raise FactoryBudgetLedgerError("source", "manual reconciliation source is missing")
    require_entry_capacity(connection)
    cursor = connection.execute(
        """
        INSERT INTO ledger_entries(
            idempotency_digest, period_id, kind, direction,
            amount_microcents, occurred_at_utc, currency, source_id,
            reference_entry_id
        ) VALUES (?, (SELECT id FROM budget_periods WHERE period_start_utc = ?),
            'manual_adjustment', 'debit', ?, ?, 'USD', ?, NULL)
        """,
        (
            idempotency_digest(f"manual-reconcile-entry:{idempotency_key}"),
            reservation[23],
            amount,
            reservation[21],
            source_id,
        ),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "manual adjustment id is unavailable")
    return cursor.lastrowid


def insert_reconciliation_event(
    connection: sqlite3.Connection,
    *,
    reservation: ReservationRow,
    event_digest: str,
    event_type: str,
    occurred_at: str,
    reason: str,
    evidence_digest: str,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO cost_reservation_events(
            reservation_id, idempotency_digest, event_type,
            resulting_state, occurred_at_utc, reason,
            evidence_digest, receipt_digest
        ) VALUES (?, ?, ?, 'reconciled', ?, ?, ?, NULL)
        """,
        (
            reservation[0],
            event_digest,
            event_type,
            occurred_at,
            reason,
            evidence_digest,
        ),
    )


def require_reconciliation_replay(
    connection: sqlite3.Connection,
    event: ReservationEventRow,
    *,
    reservation: ReservationRow,
    occurred_at: str,
    reason: str,
    evidence_digest: str,
    amount: int,
    source_id: str | None,
) -> None:
    event_type = "reconciled_manual_debit" if amount > 0 else "reconciled_no_charge"
    if (
        event[1] != reservation[0]
        or event[2] != event_type
        or event[3] != "reconciled"
        or event[4] != occurred_at
        or event[5] != reason
        or event[6] != evidence_digest
        or event[7] is not None
        or not _reconciliation_authority_matches(
            connection,
            reservation,
            amount=amount,
            source_id=source_id,
        )
    ):
        raise FactoryBudgetLedgerError(
            "idempotency",
            "idempotency key conflicts with an existing reservation event",
        )


def _reconciliation_authority_matches(
    connection: sqlite3.Connection,
    reservation: ReservationRow,
    *,
    amount: int,
    source_id: str | None,
) -> bool:
    if reservation[16] != amount:
        return False
    entry_id = reservation[20]
    if amount == 0:
        return source_id is None and entry_id is None
    if source_id is None or entry_id is None:
        return False
    row = manual_adjustment_authority(
        connection.execute(
            """
            SELECT kind, direction, amount_microcents, source_id
            FROM ledger_entries WHERE id = ?
            """,
            (entry_id,),
        )
    )
    return row == ("manual_adjustment", "debit", amount, source_id)
