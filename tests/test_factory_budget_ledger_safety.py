from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
)
from scripts.factory_budget_ledger_storage import writable_connection  # noqa: E402


def _config() -> BudgetPeriodConfig:
    return BudgetPeriodConfig(
        starts_on=date(2026, 7, 1),
        cash_cap_microcents=20_000_000_000,
        emergency_reserve_microcents=2_000_000_000,
        currency="USD",
        policy_id="monthly-budget",
        policy_revision=1,
        reserve_idempotency_key="reserve-2026-07-v1",
    )


def test_open_rejects_symlinked_state_directory_without_writing_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".entroping").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger state path is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert tuple(outside.iterdir()) == ()


def test_open_rejects_symlinked_database_leaf(tmp_path: Path) -> None:
    state = tmp_path / ".entroping" / "factory-budget"
    state.mkdir(parents=True)
    os.chmod(state, 0o700)
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"do-not-touch")
    (state / "ledger.sqlite3").symlink_to(outside)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger database is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert outside.read_bytes() == b"do-not-touch"


def test_open_rejects_symlinked_sqlite_sidecar(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    outside = tmp_path / "outside-journal"
    outside.write_bytes(b"do-not-touch")
    (ledger.db_path.parent / "ledger.sqlite3-journal").symlink_to(outside)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger sidecar is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert outside.read_bytes() == b"do-not-touch"


def test_open_rejects_oversized_regular_sqlite_journal(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    journal = ledger.db_path.with_name("ledger.sqlite3-journal")
    with journal.open("wb") as stream:
        stream.truncate(536_870_913)
    os.chmod(journal, 0o600)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger sidecar is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_rejects_insecure_existing_database_permissions(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    os.chmod(ledger.db_path, 0o644)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger database is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_maps_symlinked_lock_to_domain_error(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    lock = ledger.db_path.parent / "ledger.lock"
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"do-not-touch")
    lock.unlink()
    lock.symlink_to(outside)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger lock is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert outside.read_bytes() == b"do-not-touch"


def test_open_rejects_future_schema_without_mutating_database(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute("PRAGMA user_version = 2")
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema version is unsupported"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_unexpected_trigger_without_executing_it(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute(
            "CREATE TRIGGER unexpected AFTER INSERT ON budget_periods BEGIN SELECT 1; END"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema objects are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_same_name_schema_drift_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        connection.execute("DROP TRIGGER ledger_entries_no_update")
        connection.execute(
            "CREATE TRIGGER ledger_entries_no_update "
            "BEFORE UPDATE ON ledger_entries BEGIN SELECT 1; END"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema objects are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_unexpected_schema_metadata_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        _ = connection.execute(
            "INSERT INTO ledger_metadata(key, value) VALUES ('unexpected', 'value')"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="schema metadata is invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_database_enforces_immutable_ledger_entries(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())

    with sqlite3.connect(ledger.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE ledger_entries SET amount_microcents = 1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM ledger_entries")

    assert ledger.period_summary(date(2026, 7, 1)).entry_count == 1


def test_open_rejects_cached_balance_drift_without_mutating_database(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())
    with sqlite3.connect(ledger.db_path) as connection:
        _ = connection.execute("UPDATE budget_periods SET net_spent_microcents = -1")
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="ledger balances are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_refund_that_references_reserve_allocation(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())
    with sqlite3.connect(ledger.db_path) as connection:
        period_id, reserve_id = connection.execute(
            """
            SELECT p.id, e.id
            FROM budget_periods AS p
            JOIN ledger_entries AS e ON e.period_id = p.id
            WHERE e.kind = 'emergency_reserve_allocation'
            """
        ).fetchone()
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'refund', 'credit', 1, ?, 'USD', ?, ?)
            """,
            (
                "a" * 64,
                period_id,
                "2026-07-15T00:00:00.000000Z",
                "monthly-budget",
                reserve_id,
            ),
        )
        _ = connection.execute(
            "UPDATE budget_periods SET net_spent_microcents = -1, entry_count = 2"
        )
    before = hashlib.sha256(ledger.db_path.read_bytes()).hexdigest()

    with pytest.raises(FactoryBudgetLedgerError, match="ledger entries are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert hashlib.sha256(ledger.db_path.read_bytes()).hexdigest() == before


def test_open_rejects_noncanonical_entry_timestamp(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())
    with sqlite3.connect(ledger.db_path) as connection:
        period_id = connection.execute("SELECT id FROM budget_periods").fetchone()[0]
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'manual_adjustment', 'debit', 1, ?, 'USD', ?, NULL)
            """,
            ("b" * 64, period_id, "2026-07-99T99:99:99Z", "maintainer"),
        )
        _ = connection.execute(
            "UPDATE budget_periods SET net_spent_microcents = 1, entry_count = 2"
        )

    with pytest.raises(FactoryBudgetLedgerError, match="ledger timestamps are invalid"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_recomputes_page_cap_from_actual_sqlite_page_size(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    with sqlite3.connect(ledger.db_path) as connection:
        _ = connection.execute("PRAGMA page_size = 65536")
        _ = connection.execute("VACUUM")

    with writable_connection(tmp_path) as connection:
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        max_page_count = connection.execute("PRAGMA max_page_count").fetchone()[0]
    assert page_size * max_page_count <= 536_870_912


def test_writer_does_not_recreate_ledger_removed_before_retention_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())

    @contextmanager
    def remove_before_guard(_repo_root: Path) -> Iterator[None]:
        ledger.db_path.unlink()
        yield

    monkeypatch.setattr(
        "scripts.factory_budget_ledger_storage._retention_guard",
        remove_before_guard,
    )
    with pytest.raises(FactoryBudgetLedgerError):
        ledger.initialize_period(_config())

    assert not ledger.db_path.exists()


def test_interrupted_initialization_leaves_no_partial_authoritative_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(connection: sqlite3.Connection) -> None:
        _ = connection.execute("BEGIN EXCLUSIVE")
        _ = connection.execute("CREATE TABLE partial_state (id INTEGER PRIMARY KEY) STRICT")
        raise RuntimeError("injected initialization interruption")

    with monkeypatch.context() as context:
        context.setattr(
            "scripts.factory_budget_ledger_storage.initialize_schema",
            interrupt,
        )
        with pytest.raises(FactoryBudgetLedgerError, match="could not initialize ledger"):
            FactoryBudgetLedger.open_project(tmp_path)

    db_path = tmp_path / ".entroping" / "factory-budget" / "ledger.sqlite3"
    assert not db_path.exists()

    ledger = FactoryBudgetLedger.open_project(tmp_path)
    assert ledger.db_path == db_path


def test_readonly_summary_preserves_database_mtime_and_permissions(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_config())
    before = ledger.db_path.stat().st_mtime_ns

    summary = FactoryBudgetLedger.period_summary_readonly(
        tmp_path,
        date(2026, 7, 1),
    )

    assert summary.entry_count == 1
    assert ledger.db_path.stat().st_mtime_ns == before
    assert stat.S_IMODE(ledger.db_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(ledger.db_path.parent.stat().st_mode) == 0o700
    assert not any(entry.is_symlink() for entry in ledger.db_path.parent.iterdir())


def test_recovery_discards_only_reserved_non_authoritative_init_file(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    initializing = ledger.db_path.parent / ".ledger.sqlite3.init"
    initializing.write_bytes(b"partial non-authoritative initialization")
    os.chmod(initializing, 0o600)

    reopened = FactoryBudgetLedger.open_project(tmp_path)

    assert reopened.db_path == ledger.db_path
    assert not initializing.exists()
