from __future__ import annotations

import sqlite3
import sys
import traceback
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError  # noqa: E402
from scripts.factory_budget_ledger_rows import (  # noqa: E402
    metadata_rows,
    period_summary_row,
    period_validation_rows,
    schema_objects,
)
from scripts.factory_budget_ledger_schema import (  # noqa: E402
    initialize_schema,
    validate_schema,
)


def test_malformed_row_error_omits_coercible_value_from_exception_chain() -> None:
    sentinel = "SENSITIVE_SENTINEL_1565"
    with sqlite3.connect(":memory:") as connection:
        cursor = connection.execute(
            "SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?",
            ("2026-07-01", "2026-08-01", "USD", sentinel, 1, 1, 1, "policy", 1),
        )

        with pytest.raises(
            FactoryBudgetLedgerError,
            match="ledger database values are invalid",
        ) as captured:
            _ = period_summary_row(cursor)

    rendered = "".join(traceback.format_exception(captured.value))
    assert captured.value.__cause__ is None
    assert sentinel not in str(captured.value)
    assert sentinel not in rendered


def test_metadata_reader_stops_after_exact_cardinality_can_be_rejected() -> None:
    observed = 0

    def observe(value: int) -> str:
        nonlocal observed
        observed += 1
        return str(value)

    with sqlite3.connect(":memory:") as connection:
        connection.create_function("observe", 1, observe)
        cursor = connection.execute(
            " ".join(
                (
                    "WITH RECURSIVE n(x) AS (",
                    "VALUES(1) UNION ALL SELECT x + 1 FROM n WHERE x < 1000",
                    ") SELECT 'key-' || x, observe(x) FROM n",
                )
            )
        )

        with pytest.raises(
            FactoryBudgetLedgerError,
            match="ledger schema metadata is invalid",
        ):
            _ = metadata_rows(cursor)

    assert observed <= 3


def test_schema_object_reader_stops_after_maximum_plus_one_row() -> None:
    observed = 0

    def observe(value: int) -> str:
        nonlocal observed
        observed += 1
        return str(value)

    with sqlite3.connect(":memory:") as connection:
        connection.create_function("observe", 1, observe)
        cursor = connection.execute(
            " ".join(
                (
                    "WITH RECURSIVE n(x) AS (",
                    "VALUES(1) UNION ALL SELECT x + 1 FROM n WHERE x < 1000",
                    ") SELECT 'table', 'name-' || x, observe(x) FROM n",
                )
            )
        )

        with pytest.raises(
            FactoryBudgetLedgerError,
            match="ledger schema objects are invalid",
        ):
            _ = schema_objects(cursor, maximum_rows=3)

    assert observed <= 5


def test_schema_validation_does_not_sort_an_unbounded_schema_before_rejection() -> None:
    steps = 0

    def count_step() -> int:
        nonlocal steps
        steps += 1
        return 0

    with sqlite3.connect(":memory:", autocommit=True) as connection:
        initialize_schema(connection)
        for index in range(1000):
            _ = connection.execute(f"CREATE TABLE extra_{index} (id INTEGER)")
        connection.set_progress_handler(count_step, 1)
        try:
            with pytest.raises(
                FactoryBudgetLedgerError,
                match="ledger schema objects are invalid",
            ):
                validate_schema(connection)
        finally:
            connection.set_progress_handler(None, 0)

    assert steps < 1000


def test_schema_validation_does_not_sort_unbounded_metadata_before_rejection() -> None:
    steps = 0

    def count_step() -> int:
        nonlocal steps
        steps += 1
        return 0

    with sqlite3.connect(":memory:", autocommit=True) as connection:
        _ = connection.execute(
            "CREATE TABLE ledger_metadata (key TEXT, value TEXT) STRICT"
        )
        _ = connection.execute("PRAGMA user_version = 1")
        _ = connection.executemany(
            "INSERT INTO ledger_metadata(key, value) VALUES (?, ?)",
            [(f"key-{index}", "value") for index in range(1000)],
        )
        connection.set_progress_handler(count_step, 1)
        try:
            with pytest.raises(
                FactoryBudgetLedgerError,
                match="ledger schema metadata is invalid",
            ):
                validate_schema(connection)
        finally:
            connection.set_progress_handler(None, 0)

    assert steps < 1000


def test_period_validation_rows_are_strict_and_streamed_in_fixed_batches() -> None:
    with sqlite3.connect(":memory:") as connection:
        invalid = connection.execute("SELECT '1', 'start', 'end'")
        with pytest.raises(
            FactoryBudgetLedgerError,
            match="ledger database values are invalid",
        ):
            _ = period_validation_rows(invalid, 2)

        valid = connection.execute(
            " ".join(
                (
                    "SELECT 1, 'start-1', 'end-1' UNION ALL",
                    "SELECT 2, 'start-2', 'end-2' UNION ALL",
                    "SELECT 3, 'start-3', 'end-3'",
                )
            )
        )
        batch_sizes = (
            len(period_validation_rows(valid, 2)),
            len(period_validation_rows(valid, 2)),
            len(period_validation_rows(valid, 2)),
        )

    assert batch_sizes == (2, 1, 0)
