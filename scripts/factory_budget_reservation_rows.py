from __future__ import annotations

import sqlite3

from pydantic import TypeAdapter, ValidationError

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_models import PriceUnit, ReservationState

type ReservationRow = tuple[
    int,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    int,
    str,
    int,
    int,
    int,
    int,
    int,
    int | None,
    ReservationState,
    str | None,
    str | None,
    int | None,
    str,
    str,
    str,
]
type ReservationPriceRow = tuple[str, PriceUnit, int, int, str, str]
type ReservationEventRow = tuple[
    int,
    int,
    str,
    ReservationState,
    str,
    str | None,
    str | None,
    str | None,
]
type ReservationPeriodAuthority = tuple[int, int, int, int, int, str, int]

RESERVATION_ROW: TypeAdapter[ReservationRow | None] = TypeAdapter(ReservationRow | None)
RESERVATION_PRICE_ROWS: TypeAdapter[list[ReservationPriceRow]] = TypeAdapter(
    list[ReservationPriceRow]
)
RESERVATION_EVENT_ROW: TypeAdapter[ReservationEventRow | None] = TypeAdapter(
    ReservationEventRow | None
)
RESERVATION_PERIOD_AUTHORITY: TypeAdapter[ReservationPeriodAuthority | None] = TypeAdapter(
    ReservationPeriodAuthority | None
)


def reservation_row(cursor: sqlite3.Cursor) -> ReservationRow | None:
    try:
        return RESERVATION_ROW.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def reservation_price_rows(cursor: sqlite3.Cursor) -> tuple[ReservationPriceRow, ...]:
    try:
        rows = RESERVATION_PRICE_ROWS.validate_python(cursor.fetchmany(5), strict=True)
    except ValidationError:
        raise _invalid_values() from None
    if len(rows) > 4:
        raise FactoryBudgetLedgerError("limit", "reservation price term limit exceeded")
    return tuple(rows)


def reservation_event_row(cursor: sqlite3.Cursor) -> ReservationEventRow | None:
    try:
        return RESERVATION_EVENT_ROW.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def reservation_period_authority(
    cursor: sqlite3.Cursor,
) -> ReservationPeriodAuthority | None:
    try:
        return RESERVATION_PERIOD_AUTHORITY.validate_python(
            cursor.fetchone(),
            strict=True,
        )
    except ValidationError:
        raise _invalid_values() from None


def _invalid_values() -> FactoryBudgetLedgerError:
    return FactoryBudgetLedgerError("database", "reservation database values are invalid")
