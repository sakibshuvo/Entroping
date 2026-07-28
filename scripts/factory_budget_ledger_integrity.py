from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast

from .factory_budget_ledger_models import FactoryBudgetLedgerError

MAX_BUDGET_PERIODS = 600
MAX_LEDGER_ENTRIES = 100_000
VALIDATION_BATCH_SIZE = 512


def validate_ledger_integrity(connection: sqlite3.Connection) -> None:
    if _global_limits_exceeded(connection):
        raise FactoryBudgetLedgerError("limit", "global ledger size limit exceeded")
    if not _balances_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "ledger balances are invalid")
    if not _entries_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "ledger entries are invalid")
    if not _timestamps_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "ledger timestamps are invalid")


def require_entry_capacity(connection: sqlite3.Connection) -> None:
    if _entry_exists_at_offset(connection, MAX_LEDGER_ENTRIES - 1):
        raise FactoryBudgetLedgerError("limit", "global ledger entry limit reached")


def require_period_capacity(connection: sqlite3.Connection) -> None:
    if _period_exists_at_offset(connection, MAX_BUDGET_PERIODS - 1):
        raise FactoryBudgetLedgerError("limit", "global budget period limit reached")


def _global_limits_exceeded(connection: sqlite3.Connection) -> bool:
    return _period_exists_at_offset(
        connection, MAX_BUDGET_PERIODS
    ) or _entry_exists_at_offset(connection, MAX_LEDGER_ENTRIES)


def _period_exists_at_offset(
    connection: sqlite3.Connection,
    offset: int,
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM budget_periods ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        is not None
    )


def _entry_exists_at_offset(
    connection: sqlite3.Connection,
    offset: int,
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM ledger_entries ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        is not None
    )


def _balances_valid(connection: sqlite3.Connection) -> bool:
    invalid = cast(
        tuple[int] | None,
        connection.execute(
            """
            SELECT p.id
            FROM budget_periods AS p
            LEFT JOIN ledger_entries AS e ON e.period_id = p.id
            GROUP BY p.id
            HAVING p.entry_count != COUNT(e.id)
                OR p.net_spent_microcents != COALESCE(SUM(
                    CASE e.direction
                        WHEN 'debit' THEN e.amount_microcents
                        WHEN 'credit' THEN -e.amount_microcents
                        ELSE 0
                    END
                ), 0)
                OR SUM(
                    CASE WHEN e.kind = 'emergency_reserve_allocation' THEN 1 ELSE 0 END
                ) != 1
                OR SUM(
                    CASE WHEN e.kind = 'emergency_reserve_allocation'
                        THEN e.amount_microcents ELSE 0 END
                ) != p.emergency_reserve_microcents
                OR SUM(
                    CASE WHEN e.kind = 'emergency_reserve_allocation'
                        AND e.occurred_at_utc = p.period_start_utc
                        AND e.currency = p.currency
                        AND e.source_id = p.policy_id
                        THEN 1 ELSE 0 END
                ) != 1
                OR SUM(
                    CASE WHEN e.occurred_at_utc < p.period_start_utc
                        OR e.occurred_at_utc >= p.period_end_utc
                        THEN 1 ELSE 0 END
                ) != 0
            LIMIT 1
            """
        ).fetchone(),
    )
    return invalid is None


def _entries_valid(connection: sqlite3.Connection) -> bool:
    invalid_period = cast(
        tuple[int] | None,
        connection.execute(
            """
            SELECT id
            FROM budget_periods
            WHERE entry_count > 100000
                OR net_spent_microcents
                    > cash_cap_microcents - emergency_reserve_microcents
            LIMIT 1
            """
        ).fetchone(),
    )
    invalid_refund = cast(
        tuple[int] | None,
        connection.execute(
            """
            SELECT refund.id
            FROM ledger_entries AS refund
            LEFT JOIN ledger_entries AS charge
                ON charge.id = refund.reference_entry_id
            WHERE refund.kind = 'refund'
                AND (
                    charge.id IS NULL
                    OR charge.kind NOT IN (
                        'fixed_subscription_charge',
                        'provider_charge'
                    )
                    OR refund.currency != charge.currency
                    OR refund.source_id != charge.source_id
                )
            LIMIT 1
            """
        ).fetchone(),
    )
    excessive_refund = cast(
        tuple[int] | None,
        connection.execute(
            """
            SELECT charge.id
            FROM ledger_entries AS charge
            JOIN ledger_entries AS refund
                ON refund.reference_entry_id = charge.id
                AND refund.kind = 'refund'
            GROUP BY charge.id, charge.amount_microcents
            HAVING SUM(refund.amount_microcents) > charge.amount_microcents
            LIMIT 1
            """
        ).fetchone(),
    )
    return invalid_period is None and invalid_refund is None and excessive_refund is None


def _timestamps_valid(connection: sqlite3.Connection) -> bool:
    period_cursor = connection.execute(
        "SELECT id, period_start_utc, period_end_utc FROM budget_periods"
    )
    periods: dict[int, tuple[datetime, datetime]] = {}
    while period_rows := cast(
        list[tuple[int, str, str]],
        period_cursor.fetchmany(VALIDATION_BATCH_SIZE),
    ):
        for period_id, raw_start, raw_end in period_rows:
            start = _parse_month_boundary(raw_start)
            end = _parse_month_boundary(raw_end)
            if start is None or end is None or start.day != 1:
                return False
            try:
                expected_end = (
                    datetime(start.year + 1, 1, 1, tzinfo=UTC)
                    if start.month == 12
                    else datetime(start.year, start.month + 1, 1, tzinfo=UTC)
                )
            except ValueError:
                return False
            if end != expected_end:
                return False
            periods[period_id] = (start, end)
    entry_cursor = connection.execute(
        "SELECT period_id, kind, occurred_at_utc FROM ledger_entries"
    )
    while entry_rows := cast(
        list[tuple[int, str, str]],
        entry_cursor.fetchmany(VALIDATION_BATCH_SIZE),
    ):
        for period_id, kind, raw_occurred_at in entry_rows:
            occurred_at = (
                _parse_month_boundary(raw_occurred_at)
                if kind == "emergency_reserve_allocation"
                else _parse_entry_timestamp(raw_occurred_at)
            )
            bounds = periods.get(period_id)
            if occurred_at is None or bounds is None:
                return False
            if occurred_at < bounds[0] or occurred_at >= bounds[1]:
                return False
    return True


def _parse_month_boundary(value: str) -> datetime | None:
    if len(value) != 20:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value else None


def _parse_entry_timestamp(value: str) -> datetime | None:
    if len(value) != 27:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") == value else None
