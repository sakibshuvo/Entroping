from __future__ import annotations

import sqlite3
import sys
import traceback
from pathlib import Path
from typing import override

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_budget_ledger_schema as ledger_schema  # noqa: E402
from scripts.factory_budget_ledger import FactoryBudgetLedger  # noqa: E402


class InjectedInitializationError(RuntimeError):
    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return self.detail


def test_unexpected_initialization_error_preserves_identity_and_cleans_partial_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(connection: sqlite3.Connection) -> None:
        _ = connection.execute("BEGIN EXCLUSIVE")
        _ = connection.execute("CREATE TABLE partial_state (id INTEGER PRIMARY KEY) STRICT")
        raise InjectedInitializationError("injected initialization interruption")

    with monkeypatch.context() as context:
        context.setattr(
            "scripts.factory_budget_ledger_storage.initialize_schema",
            interrupt,
        )
        with pytest.raises(
            InjectedInitializationError,
            match="injected initialization interruption",
        ):
            _ = FactoryBudgetLedger.open_project(tmp_path)

    db_path = tmp_path / ".entroping" / "factory-budget" / "ledger.sqlite3"
    assert not db_path.exists()

    ledger = FactoryBudgetLedger.open_project(tmp_path)
    assert ledger.db_path == db_path


def test_schema_cleanup_preserves_original_error_after_transaction_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ledger_schema,
        "SCHEMA_STATEMENTS",
        ("ROLLBACK", "NOT VALID SQL"),
    )

    with (
        sqlite3.connect(":memory:", autocommit=True) as connection,
        pytest.raises(sqlite3.OperationalError, match='near "NOT"'),
    ):
        ledger_schema.initialize_schema(connection)


def test_schema_cleanup_preserves_original_error_when_rollback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_rollback(
        action_code: int,
        argument_one: str | None,
        _argument_two: str | None,
        _database_name: str | None,
        _trigger_name: str | None,
    ) -> int:
        if action_code == sqlite3.SQLITE_TRANSACTION and argument_one == "ROLLBACK":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    monkeypatch.setattr(
        ledger_schema,
        "SCHEMA_STATEMENTS",
        ("CREATE TABLE partial_state (id INTEGER PRIMARY KEY) STRICT", "NOT VALID SQL"),
    )

    with sqlite3.connect(":memory:", autocommit=True) as connection:
        connection.set_authorizer(deny_rollback)
        with pytest.raises(
            sqlite3.OperationalError,
            match='near "NOT"',
        ) as captured:
            ledger_schema.initialize_schema(connection)
        assert connection.in_transaction
        assert "not authorized" not in "".join(
            traceback.format_exception(captured.value)
        )
