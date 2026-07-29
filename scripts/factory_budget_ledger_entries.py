from __future__ import annotations

import sqlite3

from .factory_budget_ledger_integrity import require_entry_capacity
from .factory_budget_ledger_models import (
    FactoryBudgetLedgerError,
    LedgerEntryInput,
    LedgerEntryReceipt,
    idempotency_digest,
    month_boundary,
)
from .factory_budget_ledger_rows import PeriodState, period_state
from .factory_budget_ledger_rules import (
    entry_receipt,
    entry_signature,
    prospective_net,
    validate_reference,
)

MAX_PERIOD_ENTRIES = 100_000


def record_entry(
    connection: sqlite3.Connection,
    entry: LedgerEntryInput,
) -> LedgerEntryReceipt:
    entry.validate()
    digest = idempotency_digest(entry.idempotency_key)
    reference_digest = (
        idempotency_digest(entry.reference_idempotency_key)
        if entry.reference_idempotency_key is not None
        else None
    )
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        period_start = month_boundary(entry.period_starts_on)
        existing = entry_signature(connection, digest)
        expected = (
            entry.kind,
            entry.direction,
            entry.amount_microcents,
            entry.occurred_at_utc,
            entry.currency,
            entry.source_id,
            period_start,
            reference_digest,
        )
        if existing is not None:
            if existing[1:] != expected:
                raise FactoryBudgetLedgerError(
                    "idempotency",
                    "idempotency key conflicts with an existing ledger entry",
                )
            receipt = entry_receipt(
                connection,
                created=False,
                entry_id=existing[0],
                digest=digest,
                entry=entry,
                period_start=period_start,
            )
            _ = connection.execute("COMMIT")
            return receipt
        period = _period_state(connection, period_start)
        if period[5] >= MAX_PERIOD_ENTRIES:
            raise FactoryBudgetLedgerError("limit", "budget period entry limit reached")
        require_entry_capacity(connection)
        reference_id = validate_reference(connection, entry, reference_digest)
        prospective = prospective_net(
            current_net=period[3],
            cap=period[1],
            reserve=period[2],
            active_reserved=period[4],
            entry=entry,
        )
        entry_id = _insert_entry(
            connection,
            digest=digest,
            period_id=period[0],
            entry=entry,
            reference_id=reference_id,
        )
        _ = connection.execute(
            """
            UPDATE budget_periods
            SET net_spent_microcents = ?, entry_count = entry_count + 1
            WHERE id = ?
            """,
            (prospective, period[0]),
        )
        receipt = entry_receipt(
            connection,
            created=True,
            entry_id=entry_id,
            digest=digest,
            entry=entry,
            period_start=period_start,
        )
        _ = connection.execute("COMMIT")
        return receipt
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.OperationalError as exc:
        _rollback(connection)
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
        raise FactoryBudgetLedgerError("database", "ledger write failed") from exc
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "ledger write failed") from exc


def _period_state(connection: sqlite3.Connection, period_start: str) -> PeriodState:
    period = period_state(
        connection.execute(
            """
            SELECT id, cash_cap_microcents, emergency_reserve_microcents,
                   net_spent_microcents, active_reserved_microcents, entry_count
            FROM budget_periods WHERE period_start_utc = ?
            """,
            (period_start,),
        )
    )
    if period is None:
        raise FactoryBudgetLedgerError("period", "budget period not found")
    return period


def _insert_entry(
    connection: sqlite3.Connection,
    *,
    digest: str,
    period_id: int,
    entry: LedgerEntryInput,
    reference_id: int | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO ledger_entries(
            idempotency_digest, period_id, kind, direction,
            amount_microcents, occurred_at_utc, currency, source_id,
            reference_entry_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            digest,
            period_id,
            entry.kind,
            entry.direction,
            entry.amount_microcents,
            entry.occurred_at_utc,
            entry.currency,
            entry.source_id,
            reference_id,
        ),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "ledger entry id is unavailable")
    return cursor.lastrowid


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
