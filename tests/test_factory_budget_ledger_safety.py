from __future__ import annotations

import os
import shutil
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

from scripts import factory_budget_ledger_fs as ledger_fs  # noqa: E402
from scripts import factory_budget_ledger_storage as ledger_storage  # noqa: E402
from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
)
from scripts.factory_budget_ledger_storage import writable_connection  # noqa: E402


def _period(
    *,
    starts_on: date = date(2026, 7, 1),
    cash_cap_microcents: int = 20_000_000_000,
    emergency_reserve_microcents: int = 2_000_000_000,
    currency: str = "USD",
    policy_id: str = "monthly-budget",
    policy_revision: int = 1,
    reserve_idempotency_key: str = "reserve-2026-07-v1",
) -> BudgetPeriodConfig:
    return BudgetPeriodConfig(
        starts_on=starts_on,
        cash_cap_microcents=cash_cap_microcents,
        emergency_reserve_microcents=emergency_reserve_microcents,
        currency=currency,
        policy_id=policy_id,
        policy_revision=policy_revision,
        reserve_idempotency_key=reserve_idempotency_key,
    )


def test_open_rejects_symlinked_database_leaf(tmp_path: Path) -> None:
    state = tmp_path / ".entroping" / "factory-budget"
    state.mkdir(parents=True)
    os.chmod(state.parent, 0o700)
    os.chmod(state, 0o700)
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"do-not-touch")
    (state / "ledger.sqlite3").symlink_to(outside)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger database is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert outside.read_bytes() == b"do-not-touch"


def test_open_rejects_hardlinked_database_leaf(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    alias = ledger.db_path.with_name("ledger.alias")
    os.link(ledger.db_path, alias)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger database is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_rejects_database_leaf_replaced_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim_root = tmp_path / "victim"
    victim_root.mkdir()
    victim = FactoryBudgetLedger.open_project(victim_root)
    victim.initialize_period(_period())
    substitute_root = tmp_path / "substitute"
    substitute_root.mkdir()
    substitute = FactoryBudgetLedger.open_project(substitute_root)
    substitute.initialize_period(
        _period(
            starts_on=date(2026, 7, 1),
            cash_cap_microcents=1_000_000_000_000,
            reserve_idempotency_key="substitute-reserve-2026-07-v1",
        )
    )
    original_validate = ledger_fs.validate_existing_entry

    def swap_after_validation(root: Path, name: str) -> ledger_fs.FileIdentity:
        identity = original_validate(root, name)
        if root == victim_root:
            victim.db_path.rename(victim.db_path.with_suffix(".saved"))
            victim.db_path.symlink_to(substitute.db_path)
        return identity

    monkeypatch.setattr(ledger_storage, "validate_existing_entry", swap_after_validation)

    with pytest.raises(FactoryBudgetLedgerError, match="changed during open"):
        victim.balance_summary(date(2026, 7, 1))


def test_open_rejects_regular_database_replacement_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim_root = tmp_path / "victim"
    victim_root.mkdir()
    victim = FactoryBudgetLedger.open_project(victim_root)
    victim.initialize_period(_period())
    substitute_root = tmp_path / "substitute"
    substitute_root.mkdir()
    substitute = FactoryBudgetLedger.open_project(substitute_root)
    substitute.initialize_period(_period(cash_cap_microcents=1_000_000_000_000))
    original_validate = ledger_fs.validate_existing_entry

    def swap_after_validation(root: Path, name: str) -> ledger_fs.FileIdentity:
        identity = original_validate(root, name)
        if root == victim_root:
            victim.db_path.rename(victim.db_path.with_suffix(".saved"))
            shutil.copy2(substitute.db_path, victim.db_path)
        return identity

    monkeypatch.setattr(ledger_storage, "validate_existing_entry", swap_after_validation)

    with pytest.raises(FactoryBudgetLedgerError, match="changed during open"):
        victim.balance_summary(date(2026, 7, 1))


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
    ledger.initialize_period(_period())

    @contextmanager
    def remove_before_guard(_repo_root: Path) -> Iterator[None]:
        ledger.db_path.unlink()
        yield

    monkeypatch.setattr(
        "scripts.factory_budget_ledger_storage._retention_guard",
        remove_before_guard,
    )
    with pytest.raises(FactoryBudgetLedgerError):
        ledger.initialize_period(_period())

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


def test_recovery_completes_published_initialization_hard_link(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    initializing = ledger.db_path.parent / ".ledger.sqlite3.init"
    os.link(ledger.db_path, initializing)
    assert ledger.db_path.stat().st_nlink == 2

    reopened = FactoryBudgetLedger.open_project(tmp_path)

    assert reopened.db_path == ledger.db_path
    assert reopened.db_path.stat().st_nlink == 1
    assert not initializing.exists()


def test_recovery_rejects_published_inode_with_an_extra_hard_link(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    initializing = ledger.db_path.parent / ".ledger.sqlite3.init"
    alias = ledger.db_path.parent / "ledger.alias"
    os.link(ledger.db_path, initializing)
    os.link(ledger.db_path, alias)

    with pytest.raises(FactoryBudgetLedgerError, match="published ledger recovery is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert (ledger.db_path.stat().st_nlink, initializing.exists()) == (3, True)


def test_readonly_summary_preserves_database_mtime_and_permissions(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
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


def test_readonly_summary_rejects_wal_mode_without_creating_sidecars(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
    before = tuple(sorted(entry.name for entry in ledger.db_path.parent.iterdir()))
    assert "ledger.sqlite3-wal" not in before
    assert "ledger.sqlite3-shm" not in before

    with pytest.raises(FactoryBudgetLedgerError, match="DELETE journal mode"):
        FactoryBudgetLedger.period_summary_readonly(tmp_path, date(2026, 7, 1))

    assert tuple(sorted(entry.name for entry in ledger.db_path.parent.iterdir())) == before


def test_recovery_discards_only_reserved_non_authoritative_init_file(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    initializing = ledger.db_path.parent / ".ledger.sqlite3.init"
    initializing.write_bytes(b"partial non-authoritative initialization")
    os.chmod(initializing, 0o600)

    reopened = FactoryBudgetLedger.open_project(tmp_path)

    assert reopened.db_path == ledger.db_path
    assert not initializing.exists()
