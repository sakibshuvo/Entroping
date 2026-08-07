from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_status_database  # noqa: E402
from scripts.factory_status import collect_factory_status  # noqa: E402


def _database(path: Path, marker: str) -> None:
    """Write one private SQLite marker database for the descriptor tests."""

    connection = sqlite3.connect(path, autocommit=True)
    try:
        _ = connection.execute("CREATE TABLE marker (value TEXT NOT NULL) STRICT")
        _ = connection.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
    finally:
        connection.close()
    path.chmod(0o600)


def test_status_database_path_swap_is_original_or_fails_closed(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A path swap yields original content or unsafe with no connection."""

    path = tmp_path / "state.sqlite3"
    replacement = tmp_path / "replacement.sqlite3"
    _database(path, "original")
    _database(replacement, "replacement")
    connect = sqlite3.connect

    def swap_before_connect(
        database: str,
        *,
        uri: bool,
        autocommit: bool,
        timeout: float,
        factory: type[sqlite3.Connection],
    ) -> sqlite3.Connection:
        os.replace(replacement, path)
        return connect(database, uri=uri, autocommit=autocommit, timeout=timeout, factory=factory)

    monkeypatch.setattr("scripts.factory_status_database.sqlite3.connect", swap_before_connect)
    connection, state = factory_status_database.open_status_database(tmp_path, path, [])

    if state == "unsafe":
        assert connection is None
        return

    assert state == "available"
    assert connection is not None
    try:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("original",)
    finally:
        connection.close()


def test_status_database_rejects_hot_journal_before_immutable_read(tmp_path: Path) -> None:
    """A live journal is not a stable immutable snapshot."""

    path = tmp_path / "state.sqlite3"
    _database(path, "original")
    journal = path.with_name(f"{path.name}-journal")
    journal.write_bytes(b"hot journal")
    journal.chmod(0o600)

    connection, state = factory_status_database.open_status_database(tmp_path, path, [])

    assert connection is None
    assert state == "unsafe"


def test_status_database_rechecks_sidecars_after_transaction_start(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A sidecar appearing while the immutable transaction starts fails closed."""

    path = tmp_path / "state.sqlite3"
    _database(path, "original")
    journal = path.with_name(f"{path.name}-journal")
    descriptor_matches = factory_status_database._descriptor_matches_expected

    def create_sidecar_after_begin(
        connection: sqlite3.Connection,
        expected: tuple[int, int, int, int, int],
    ) -> bool:
        journal.write_bytes(b"late journal")
        journal.chmod(0o600)
        return descriptor_matches(connection, expected)

    monkeypatch.setattr(
        factory_status_database,
        "_descriptor_matches_expected",
        create_sidecar_after_begin,
    )

    connection, state = factory_status_database.open_status_database(tmp_path, path, [])

    assert connection is None
    assert state == "unsafe"


def test_malformed_policy_is_unsafe_not_an_unconfigured_pause(tmp_path: Path) -> None:
    """A present but invalid authority file is a security failure."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    (policy_dir / "factory-cost-policy.example.json").write_text("{", encoding="utf-8")
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.budget.status == "unsafe"
    assert "budget-policy-unsafe" in report.reason_codes


def test_symlinked_policy_authority_is_unsafe(tmp_path: Path) -> None:
    """A policy path must be a regular tracked authority document."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    target = tmp_path / "policy-target.json"
    target.write_text("{}", encoding="utf-8")
    os.symlink(target, policy_dir / "factory-cost-policy.example.json")
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert "budget-policy-unsafe" in report.reason_codes
