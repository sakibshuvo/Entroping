from __future__ import annotations

import sqlite3
from typing import cast

from .factory_budget_ledger_models import (
    SIGNED_64_BIT_MAX,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
    LedgerEntryReceipt,
)
from .factory_budget_ledger_periods import period_summary_at

type EntrySignature = tuple[int, str, str, int, str, str, str, str, str | None]
type OriginalCharge = tuple[int, str, int, str, str]


def entry_signature(
    connection: sqlite3.Connection,
    digest: str,
) -> EntrySignature | None:
    return cast(
        EntrySignature | None,
        connection.execute(
            """
            SELECT e.id, e.kind, e.direction, e.amount_microcents,
                   e.occurred_at_utc, e.currency, e.source_id,
                   p.period_start_utc, reference.idempotency_digest
            FROM ledger_entries AS e
            JOIN budget_periods AS p ON p.id = e.period_id
            LEFT JOIN ledger_entries AS reference ON reference.id = e.reference_entry_id
            WHERE e.idempotency_digest = ?
            """,
            (digest,),
        ).fetchone(),
    )


def validate_reference(
    connection: sqlite3.Connection,
    entry: LedgerEntryInput,
    reference_digest: str | None,
) -> int | None:
    if entry.kind != "refund":
        return None
    if reference_digest is None:
        raise FactoryBudgetLedgerError("entry", "refund entries require a charge reference")
    original = cast(
        OriginalCharge | None,
        connection.execute(
            """
            SELECT id, kind, amount_microcents, currency, source_id
            FROM ledger_entries WHERE idempotency_digest = ?
            """,
            (reference_digest,),
        ).fetchone(),
    )
    if original is None or original[1] not in {
        "fixed_subscription_charge",
        "provider_charge",
    }:
        raise FactoryBudgetLedgerError("refund", "refund reference is not an existing charge")
    if original[3] != entry.currency or original[4] != entry.source_id:
        raise FactoryBudgetLedgerError("refund", "refund must match the original charge source")
    refunded_row = cast(
        tuple[int] | None,
        connection.execute(
            """
            SELECT COALESCE(SUM(amount_microcents), 0)
            FROM ledger_entries
            WHERE kind = 'refund' AND reference_entry_id = ?
            """,
            (original[0],),
        ).fetchone(),
    )
    refunded = refunded_row[0] if refunded_row is not None else 0
    if refunded > original[2] - entry.amount_microcents:
        raise FactoryBudgetLedgerError("refund", "refund exceeds the original charge")
    return original[0]


def prospective_net(
    *,
    current_net: int,
    cap: int,
    reserve: int,
    entry: LedgerEntryInput,
) -> int:
    if entry.direction == "debit":
        available = (cap - reserve) - max(current_net, 0)
        if entry.amount_microcents > available:
            raise FactoryBudgetLedgerError(
                "budget",
                "paid entry exceeds available budget",
            )
        if current_net > SIGNED_64_BIT_MAX - entry.amount_microcents:
            raise FactoryBudgetLedgerError("amount", "ledger balance exceeds integer bounds")
        return current_net + entry.amount_microcents
    minimum = -(2**63)
    if current_net < minimum + entry.amount_microcents:
        raise FactoryBudgetLedgerError("amount", "ledger balance exceeds integer bounds")
    return current_net - entry.amount_microcents


def entry_receipt(
    connection: sqlite3.Connection,
    *,
    created: bool,
    entry_id: int,
    digest: str,
    entry: LedgerEntryInput,
    period_start: str,
) -> LedgerEntryReceipt:
    return LedgerEntryReceipt(
        created=created,
        entry_id=entry_id,
        idempotency_digest=digest,
        kind=entry.kind,
        direction=entry.direction,
        amount_microcents=entry.amount_microcents,
        occurred_at_utc=entry.occurred_at_utc,
        summary=period_summary_at(connection, period_start),
    )
