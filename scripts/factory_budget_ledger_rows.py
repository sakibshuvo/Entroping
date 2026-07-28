from __future__ import annotations

import sqlite3

from pydantic import TypeAdapter, ValidationError

from .factory_budget_ledger_models import FactoryBudgetLedgerError

type ReserveSignature = tuple[str, str, int, str, str, str, None, str, int, int]
type PeriodSummaryRow = tuple[str, str, str, int, int, int, int, str, int]
type PeriodState = tuple[int, int, int, int, int]
type EntrySignature = tuple[int, str, str, int, str, str, str, str, str | None]
type OriginalCharge = tuple[int, str, int, str, str]
type SchemaObject = tuple[str, str, str]
type PeriodValidationRow = tuple[int, str, str]
type EntryValidationRow = tuple[int, str, str]

RESERVE_SIGNATURE: TypeAdapter[ReserveSignature | None] = TypeAdapter(ReserveSignature | None)
PERIOD_SUMMARY_ROW: TypeAdapter[PeriodSummaryRow | None] = TypeAdapter(PeriodSummaryRow | None)
PERIOD_STATE: TypeAdapter[PeriodState | None] = TypeAdapter(PeriodState | None)
ENTRY_SIGNATURE: TypeAdapter[EntrySignature | None] = TypeAdapter(EntrySignature | None)
ORIGINAL_CHARGE: TypeAdapter[OriginalCharge | None] = TypeAdapter(OriginalCharge | None)
INTEGER_ROW: TypeAdapter[tuple[int]] = TypeAdapter(tuple[int])
METADATA_ROWS: TypeAdapter[list[tuple[str, str]]] = TypeAdapter(list[tuple[str, str]])
SCHEMA_OBJECTS: TypeAdapter[list[SchemaObject]] = TypeAdapter(list[SchemaObject])
PERIOD_VALIDATION_ROWS: TypeAdapter[list[PeriodValidationRow]] = TypeAdapter(
    list[PeriodValidationRow]
)
ENTRY_VALIDATION_ROWS: TypeAdapter[list[EntryValidationRow]] = TypeAdapter(list[EntryValidationRow])


def reserve_signature(cursor: sqlite3.Cursor) -> ReserveSignature | None:
    try:
        return RESERVE_SIGNATURE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError as exc:
        raise _invalid_values() from exc


def period_summary_row(cursor: sqlite3.Cursor) -> PeriodSummaryRow | None:
    try:
        return PERIOD_SUMMARY_ROW.validate_python(cursor.fetchone(), strict=True)
    except ValidationError as exc:
        raise _invalid_values() from exc


def period_state(cursor: sqlite3.Cursor) -> PeriodState | None:
    try:
        return PERIOD_STATE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError as exc:
        raise _invalid_values() from exc


def entry_signature(cursor: sqlite3.Cursor) -> EntrySignature | None:
    try:
        return ENTRY_SIGNATURE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError as exc:
        raise _invalid_values() from exc


def original_charge(cursor: sqlite3.Cursor) -> OriginalCharge | None:
    try:
        return ORIGINAL_CHARGE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError as exc:
        raise _invalid_values() from exc


def integer_row(cursor: sqlite3.Cursor, *, detail: str) -> int:
    try:
        return INTEGER_ROW.validate_python(cursor.fetchone(), strict=True)[0]
    except ValidationError as exc:
        raise FactoryBudgetLedgerError("database", detail) from exc


def metadata_rows(cursor: sqlite3.Cursor) -> list[tuple[str, str]]:
    try:
        return METADATA_ROWS.validate_python(cursor.fetchall(), strict=True)
    except ValidationError as exc:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema metadata is invalid",
        ) from exc


def schema_objects(cursor: sqlite3.Cursor) -> frozenset[SchemaObject]:
    try:
        rows = SCHEMA_OBJECTS.validate_python(cursor.fetchall(), strict=True)
    except ValidationError as exc:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema objects are invalid",
        ) from exc
    return frozenset(rows)


def period_validation_rows(
    cursor: sqlite3.Cursor,
    batch_size: int,
) -> tuple[PeriodValidationRow, ...]:
    try:
        rows = PERIOD_VALIDATION_ROWS.validate_python(
            cursor.fetchmany(batch_size),
            strict=True,
        )
    except ValidationError as exc:
        raise _invalid_values() from exc
    return tuple(rows)


def entry_validation_rows(
    cursor: sqlite3.Cursor,
    batch_size: int,
) -> tuple[EntryValidationRow, ...]:
    try:
        rows = ENTRY_VALIDATION_ROWS.validate_python(
            cursor.fetchmany(batch_size),
            strict=True,
        )
    except ValidationError as exc:
        raise _invalid_values() from exc
    return tuple(rows)


def _invalid_values() -> FactoryBudgetLedgerError:
    return FactoryBudgetLedgerError("database", "ledger database values are invalid")
