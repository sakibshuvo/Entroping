from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_scheduler_test_support import dead, owner, request, scheduler  # noqa: E402

from scripts.factory_status import collect_factory_status  # noqa: E402


def _started_scheduler(tmp_path: Path, now: datetime) -> Path:
    """Start one nonterminal free-local execution and return its state database."""

    subject = scheduler(tmp_path)
    _ = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=now,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    return tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"


def _update_scheduler(database: Path, statement: str, values: tuple[str, ...] = ()) -> None:
    """Mutate established scheduler authority to model a corrupted handoff."""

    connection = sqlite3.connect(database, autocommit=True)
    try:
        _ = connection.execute(statement, values)
    finally:
        connection.close()


def test_scheduler_execution_lease_mismatch_is_unsafe(tmp_path: Path) -> None:
    """Execution ownership that disagrees with the lease is ambiguous authority."""

    database = _started_scheduler(tmp_path, datetime.now(UTC))
    _update_scheduler(
        database, "UPDATE scheduler_execution_state SET lease_epoch = lease_epoch + 1"
    )

    report = collect_factory_status(tmp_path)

    assert report.scheduler.status == "unsafe"
    assert "scheduler-concurrency-unsafe" in report.reason_codes


def test_expired_singleton_lease_with_nonterminal_execution_is_unsafe(tmp_path: Path) -> None:
    """A nonterminal execution cannot outlive its singleton scheduler lease."""

    now = datetime.now(UTC)
    database = _started_scheduler(tmp_path, now - timedelta(seconds=5))
    _update_scheduler(
        database,
        "UPDATE scheduler_lease SET heartbeat_at_utc = ?, expires_at_utc = ? WHERE id = 1",
        ((now - timedelta(seconds=2)).isoformat(), (now - timedelta(seconds=1)).isoformat()),
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.scheduler.status == "unsafe"
    assert "scheduler-concurrency-unsafe" in report.reason_codes


@pytest.mark.parametrize(
    ("offset", "reason"),
    (
        (timedelta(minutes=1), "scheduler-retry-waiting"),
        (timedelta(minutes=-1), "scheduler-retry-stale"),
    ),
)
def test_scheduler_retry_timing_pauses_status(
    tmp_path: Path, offset: timedelta, reason: str
) -> None:
    """Future and stale retries are distinguishable paused state projections."""

    now = datetime.now(UTC)
    database = _started_scheduler(tmp_path, now)
    _update_scheduler(
        database,
        "UPDATE scheduler_execution_state SET phase = 'retry-wait', retry_not_before_utc = ?",
        ((now + offset).isoformat(),),
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"
    assert reason in report.reason_codes
