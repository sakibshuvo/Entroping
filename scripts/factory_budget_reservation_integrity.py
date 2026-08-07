from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_validation import canonical_digest

MAX_COST_RESERVATIONS = 100_000
MAX_RESERVATION_EVENTS = 500_000
MAX_RESERVATION_PRICES = 400_000
VALIDATION_BATCH_SIZE = 512

type PriceValidationRow = tuple[int, str, str, str, int, int, str, str, str]
type TimestampValidationRow = tuple[str]
PRICE_VALIDATION_ROWS: TypeAdapter[list[PriceValidationRow]] = TypeAdapter(
    list[PriceValidationRow]
)
TIMESTAMP_VALIDATION_ROWS: TypeAdapter[list[TimestampValidationRow]] = TypeAdapter(
    list[TimestampValidationRow]
)


def validate_reservation_integrity(connection: sqlite3.Connection) -> None:
    if _reservation_limit_exceeded(connection):
        raise FactoryBudgetLedgerError("limit", "global reservation limit exceeded")
    if _event_limit_exceeded(connection):
        raise FactoryBudgetLedgerError("limit", "global reservation event limit exceeded")
    if _price_limit_exceeded(connection):
        raise FactoryBudgetLedgerError("limit", "global reservation price limit exceeded")
    if not _balances_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "reservation balances are invalid")
    if not _relations_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "reservation relations are invalid")
    if not _pricing_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "reservation pricing is invalid")
    if not _timestamps_valid(connection):
        raise FactoryBudgetLedgerError("integrity", "reservation timestamps are invalid")


def require_reservation_capacity(
    connection: sqlite3.Connection,
    *,
    price_count: int,
) -> None:
    if _reservation_exists_at_offset(connection, MAX_COST_RESERVATIONS - 1):
        raise FactoryBudgetLedgerError("limit", "global reservation limit reached")
    price_offset = MAX_RESERVATION_PRICES - price_count
    if price_offset < 0 or _price_exists_at_offset(connection, price_offset):
        raise FactoryBudgetLedgerError("limit", "global reservation price limit reached")


def require_reservation_event_capacity(connection: sqlite3.Connection) -> None:
    if _event_exists_at_offset(connection, MAX_RESERVATION_EVENTS - 1):
        raise FactoryBudgetLedgerError("limit", "global reservation event limit reached")


def _reservation_limit_exceeded(connection: sqlite3.Connection) -> bool:
    return _reservation_exists_at_offset(connection, MAX_COST_RESERVATIONS)


def _event_limit_exceeded(connection: sqlite3.Connection) -> bool:
    return _event_exists_at_offset(connection, MAX_RESERVATION_EVENTS)


def _price_limit_exceeded(connection: sqlite3.Connection) -> bool:
    return _price_exists_at_offset(connection, MAX_RESERVATION_PRICES)


def _reservation_exists_at_offset(
    connection: sqlite3.Connection,
    offset: int,
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM cost_reservations ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        is not None
    )


def _event_exists_at_offset(connection: sqlite3.Connection, offset: int) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM cost_reservation_events ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        is not None
    )


def _price_exists_at_offset(connection: sqlite3.Connection, offset: int) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM cost_reservation_prices ORDER BY id LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        is not None
    )


def _balances_valid(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            """
            SELECT p.id
            FROM budget_periods AS p
            LEFT JOIN cost_reservations AS r ON r.period_id = p.id
            GROUP BY p.id
            HAVING p.active_reserved_microcents != COALESCE(SUM(
                CASE WHEN r.state IN ('dispatching', 'uncertain')
                    THEN r.held_microcents ELSE 0 END
            ), 0)
                OR MAX(p.net_spent_microcents, 0) + p.active_reserved_microcents
                    > p.cash_cap_microcents - p.emergency_reserve_microcents
            LIMIT 1
            """
        ).fetchone()
        is None
    )


def _relations_valid(connection: sqlite3.Connection) -> bool:
    invalid_prices = (
        connection.execute(
            """
            SELECT r.id
            FROM cost_reservations AS r
            LEFT JOIN cost_reservation_prices AS p ON p.reservation_id = r.id
            GROUP BY r.id
            HAVING COUNT(p.id) < 1 OR COUNT(p.id) > 4
            LIMIT 1
            """
        ).fetchone()
        is not None
    )
    invalid_events = (
        connection.execute(
            """
            SELECT r.id
            FROM cost_reservations AS r
            LEFT JOIN cost_reservation_events AS e ON e.reservation_id = r.id
            GROUP BY r.id
            HAVING SUM(
                CASE WHEN e.event_type = 'dispatch_reserved' THEN 1 ELSE 0 END
            ) != 1
                OR (SELECT resulting_state FROM cost_reservation_events
                    WHERE reservation_id = r.id ORDER BY id DESC LIMIT 1) != r.state
            LIMIT 1
            """
        ).fetchone()
        is not None
    )
    invalid_entries = (
        connection.execute(
            """
            SELECT r.id
            FROM cost_reservations AS r
            LEFT JOIN ledger_entries AS e ON e.id = r.settlement_entry_id
            WHERE (r.state = 'settled' AND (
                    e.kind != 'provider_charge'
                    OR e.direction != 'debit'
                    OR e.amount_microcents != r.actual_microcents
                    OR e.period_id != r.period_id
                    OR e.source_id != r.provider_id
                ))
                OR (r.state = 'reconciled' AND r.actual_microcents > 0 AND (
                    e.kind != 'manual_adjustment'
                    OR e.direction != 'debit'
                    OR e.amount_microcents != r.actual_microcents
                    OR e.period_id != r.period_id
                ))
            LIMIT 1
            """
        ).fetchone()
        is not None
    )
    return not invalid_prices and not invalid_events and not invalid_entries


def _pricing_valid(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        """
        SELECT r.id, r.pricing_digest, p.snapshot_id, p.unit,
               p.quantity, p.price_microcents, p.observed_at_utc,
               p.expires_at_utc, r.created_at_utc
        FROM cost_reservations AS r
        JOIN cost_reservation_prices AS p ON p.reservation_id = r.id
        ORDER BY r.id, p.unit
        """
    )
    current_id: int | None = None
    expected_digest = ""
    payload: list[dict[str, str | int]] = []
    while rows := _price_rows(cursor):
        for row in rows:
            if current_id is not None and row[0] != current_id:
                if canonical_digest(payload) != expected_digest:
                    return False
                payload = []
            current_id = row[0]
            expected_digest = row[1]
            observed = _parse_timestamp(row[6])
            expires = _parse_timestamp(row[7])
            created = _parse_timestamp(row[8])
            if observed is None or expires is None or created is None:
                return False
            if not observed <= created < expires:
                return False
            payload.append(
                {
                    "expires_at_utc": row[7],
                    "observed_at_utc": row[6],
                    "price_microcents": row[5],
                    "quantity": row[4],
                    "snapshot_id": row[2],
                    "unit": row[3],
                }
            )
    return current_id is None or canonical_digest(payload) == expected_digest


def _timestamps_valid(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        """
        SELECT created_at_utc FROM cost_reservations
        UNION ALL SELECT updated_at_utc FROM cost_reservations
        UNION ALL SELECT occurred_at_utc FROM cost_reservation_events
        """
    )
    while rows := _timestamp_rows(cursor):
        if any(_parse_timestamp(row[0]) is None for row in rows):
            return False
    return True


def _price_rows(cursor: sqlite3.Cursor) -> tuple[PriceValidationRow, ...]:
    try:
        return tuple(
            PRICE_VALIDATION_ROWS.validate_python(
                cursor.fetchmany(VALIDATION_BATCH_SIZE),
                strict=True,
            )
        )
    except ValidationError:
        raise FactoryBudgetLedgerError("database", "reservation values are invalid") from None


def _timestamp_rows(cursor: sqlite3.Cursor) -> tuple[TimestampValidationRow, ...]:
    try:
        return tuple(
            TIMESTAMP_VALIDATION_ROWS.validate_python(
                cursor.fetchmany(VALIDATION_BATCH_SIZE),
                strict=True,
            )
        )
    except ValidationError:
        raise FactoryBudgetLedgerError("database", "reservation values are invalid") from None


def _parse_timestamp(value: str) -> datetime | None:
    if len(value) != 27:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") == value else None
