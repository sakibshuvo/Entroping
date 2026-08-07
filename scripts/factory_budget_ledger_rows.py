from __future__ import annotations

import sqlite3

from pydantic import TypeAdapter, ValidationError

from .factory_budget_ledger_models import FactoryBudgetLedgerError

type ReserveSignature = tuple[str, str, int, str, str, str, None, str, int, int]
type PeriodSummaryRow = tuple[str, str, str, int, int, int, int, int, str, int]
type PeriodState = tuple[int, int, int, int, int, int]
type EntrySignature = tuple[int, str, str, int, str, str, str, str, str | None]
type OriginalCharge = tuple[int, str, int, str, str]
type SchemaObject = tuple[str, str, str]
type PeriodValidationRow = tuple[int, str, str]
type EntryValidationRow = tuple[int, str, str]
type ManualAdjustmentAuthority = tuple[str, str, int, str]

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
MANUAL_ADJUSTMENT_AUTHORITY: TypeAdapter[ManualAdjustmentAuthority | None] = TypeAdapter(
    ManualAdjustmentAuthority | None
)


def reserve_signature(cursor: sqlite3.Cursor) -> ReserveSignature | None:
    try:
        return RESERVE_SIGNATURE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def period_summary_row(cursor: sqlite3.Cursor) -> PeriodSummaryRow | None:
    try:
        return PERIOD_SUMMARY_ROW.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def period_state(cursor: sqlite3.Cursor) -> PeriodState | None:
    try:
        return PERIOD_STATE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def entry_signature(cursor: sqlite3.Cursor) -> EntrySignature | None:
    try:
        return ENTRY_SIGNATURE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def original_charge(cursor: sqlite3.Cursor) -> OriginalCharge | None:
    try:
        return ORIGINAL_CHARGE.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def manual_adjustment_authority(cursor: sqlite3.Cursor) -> ManualAdjustmentAuthority | None:
    try:
        return MANUAL_ADJUSTMENT_AUTHORITY.validate_python(cursor.fetchone(), strict=True)
    except ValidationError:
        raise _invalid_values() from None


def integer_row(cursor: sqlite3.Cursor, *, detail: str) -> int:
    try:
        return INTEGER_ROW.validate_python(cursor.fetchone(), strict=True)[0]
    except ValidationError:
        raise FactoryBudgetLedgerError("database", detail) from None


def metadata_rows(cursor: sqlite3.Cursor) -> list[tuple[str, str]]:
    try:
        rows = METADATA_ROWS.validate_python(cursor.fetchmany(2), strict=True)
    except ValidationError:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema metadata is invalid",
        ) from None
    if len(rows) != 1:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema metadata is invalid",
        )
    return rows


def schema_objects(
    cursor: sqlite3.Cursor,
    *,
    maximum_rows: int,
) -> frozenset[SchemaObject]:
    try:
        rows = SCHEMA_OBJECTS.validate_python(
            cursor.fetchmany(maximum_rows + 1),
            strict=True,
        )
    except ValidationError:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema objects are invalid",
        ) from None
    if len(rows) > maximum_rows:
        raise FactoryBudgetLedgerError(
            "schema",
            "ledger schema objects are invalid",
        )
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
    except ValidationError:
        raise _invalid_values() from None
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
    except ValidationError:
        raise _invalid_values() from None
    return tuple(rows)


def _invalid_values() -> FactoryBudgetLedgerError:
    return FactoryBudgetLedgerError("database", "ledger database values are invalid")
