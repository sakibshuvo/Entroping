from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import sqlite3
from pathlib import Path

from factory_scheduler_test_support import NOW, dead, owner, request

from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_receipts import iso_utc
from scripts.factory_scheduler_schema import SCHEMA_ID, SCHEMA_VERSION
from scripts.factory_scheduler_schema_migration import (
    initialize_legacy_schema,
    initialize_previous_schema,
    migrate_schema,
)


def _database(tmp_path: Path) -> Path:
    root = tmp_path / ".entroping"
    state = root / "factory-scheduler"
    state.mkdir(parents=True)
    root.chmod(0o700)
    state.chmod(0o700)
    return state / "scheduler.sqlite3"


def test_v2_migration_preserves_terminal_work_and_quarantines_active_work(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        initialize_previous_schema(connection, initialized_at=iso_utc(NOW))
        _insert_v2_assignment(connection, index=1, state="active")
        _insert_v2_assignment(connection, index=2, state="completed")

        assert migrate_schema(connection) is True

        assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert connection.execute(
            "SELECT value FROM scheduler_metadata WHERE key = 'schema_version'"
        ).fetchone() == (SCHEMA_ID,)
        assert connection.execute(
            "SELECT phase, failure_code, terminal_outcome "
            "FROM scheduler_execution_state ORDER BY assignment_id"
        ).fetchall() == [
            ("uncertain", "legacy-active-assignment", None),
            ("completed", None, "completed"),
        ]
        assert migrate_schema(connection) is False
    finally:
        connection.close()


def test_v1_migrates_directly_to_v3_before_new_assignment(tmp_path: Path) -> None:
    database = _database(tmp_path)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        initialize_legacy_schema(connection, initialized_at=iso_utc(NOW))
    finally:
        connection.close()
    database.chmod(0o600)

    receipt = FactoryScheduler(tmp_path).tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "assigned"
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert connection.execute("SELECT phase FROM scheduler_execution_state").fetchone() == (
            "never-dispatched",
        )
    finally:
        connection.close()


def _insert_v2_assignment(
    connection: sqlite3.Connection,
    *,
    index: int,
    state: str,
) -> None:
    completed_at = iso_utc(NOW) if state == "completed" else None
    _ = connection.execute(
        "INSERT INTO scheduler_assignments("
        "request_id, request_digest, assignment_id, decision_id, job_id, issue_number, "
        "worktree_id, scope_key, worker_class, access_mode, reservation_id, "
        "authorization_id, lease_owner_id, lease_owner_pid, lease_owner_start_token, "
        "lease_epoch, created_at_utc, state, completed_at_utc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'free-local', 'read-only', NULL, NULL, "
        "?, ?, ?, ?, ?, ?, ?)",
        (
            f"legacy-request-{index}",
            f"{index:x}" * 64,
            f"assign_{index:x}" + "0" * 63,
            f"decision_{index:x}" + "0" * 63,
            f"legacy-job-{index}",
            1571,
            f"wt_{index:x}" + "0" * 63,
            f"1571:wt_{index:x}" + "0" * 63,
            f"legacy-owner-{index}",
            10_000 + index,
            f"proc_{index:x}" + "0" * 63,
            index,
            iso_utc(NOW),
            state,
            completed_at,
        ),
    )
