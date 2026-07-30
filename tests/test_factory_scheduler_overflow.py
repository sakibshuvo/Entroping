from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from factory_scheduler_test_support import NOW, dead, owner, request, scheduler

from scripts.factory_scheduler import FactorySchedulerError

EXTREME_OFFSET_TIMESTAMPS = (
    datetime.min.replace(tzinfo=timezone(timedelta(hours=14))),
    datetime.max.replace(tzinfo=timezone(-timedelta(hours=14))),
)


@pytest.mark.parametrize("as_of", EXTREME_OFFSET_TIMESTAMPS)
@pytest.mark.parametrize("plan_only", [False, True])
def test_tick_bounds_utc_normalization_overflow_without_state(
    tmp_path: Path,
    as_of: datetime,
    plan_only: bool,
) -> None:
    receipt = scheduler(tmp_path).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=as_of,
        lease_seconds=1,
        plan_only=plan_only,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"
    assert not (tmp_path / ".entroping").exists()


def test_tick_bounds_lease_expiry_datetime_overflow(tmp_path: Path) -> None:
    receipt = scheduler(tmp_path).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=datetime.max.replace(tzinfo=UTC),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"


def test_heartbeat_bounds_lease_expiry_datetime_overflow(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.lease_epoch is not None

    receipt = subject.heartbeat(
        owner=owner(1),
        epoch=assigned.lease_epoch,
        as_of=datetime.max.replace(tzinfo=UTC),
        lease_seconds=1,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"


@pytest.mark.parametrize("as_of", EXTREME_OFFSET_TIMESTAMPS)
def test_heartbeat_bounds_utc_normalization_overflow(
    tmp_path: Path,
    as_of: datetime,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.lease_epoch is not None

    receipt = subject.heartbeat(
        owner=owner(1),
        epoch=assigned.lease_epoch,
        as_of=as_of,
        lease_seconds=1,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"


@pytest.mark.parametrize("completed_at", EXTREME_OFFSET_TIMESTAMPS)
def test_completion_bounds_utc_normalization_overflow(
    tmp_path: Path,
    completed_at: datetime,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    with pytest.raises(FactorySchedulerError, match="completion failed"):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            completed_at=completed_at,
        )

    assert subject.snapshot().active_assignment_count == 1


@pytest.mark.parametrize(
    "stored_clock",
    ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"],
)
def test_tick_bounds_hostile_stored_clock_offset(
    tmp_path: Path,
    stored_clock: str,
) -> None:
    subject = scheduler(tmp_path)
    initialized = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert initialized.decision == "assigned"
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        _ = connection.execute(
            "UPDATE scheduler_clock SET last_observed_at_utc = ?",
            (stored_clock,),
        )
        connection.commit()
    finally:
        connection.close()

    receipt = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"


@pytest.mark.parametrize("invalid_epoch", [True, 1.0])
def test_mutation_boundaries_reject_non_strict_epochs(
    tmp_path: Path,
    invalid_epoch: object,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    unsafe_epoch = cast(int, invalid_epoch)

    with pytest.raises(FactorySchedulerError, match="lease epoch"):
        subject.heartbeat(
            owner=owner(1),
            epoch=unsafe_epoch,
            as_of=NOW + timedelta(seconds=1),
            lease_seconds=30,
        )
    with pytest.raises(FactorySchedulerError, match="lease epoch"):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=unsafe_epoch,
            completed_at=NOW + timedelta(seconds=1),
        )

    assert subject.snapshot().active_assignment_count == 1


@pytest.mark.parametrize("invalid_seconds", [True, 1.5])
def test_tick_rejects_non_strict_lease_seconds(
    tmp_path: Path,
    invalid_seconds: object,
) -> None:
    with pytest.raises(FactorySchedulerError, match="lease seconds"):
        scheduler(tmp_path).tick(
            request=request(1, worker_class="free-local"),
            owner=owner(1),
            as_of=NOW,
            lease_seconds=cast(int, invalid_seconds),
            plan_only=False,
            owner_health=dead,
        )

    assert not (tmp_path / ".entroping").exists()


def test_tick_bounds_epoch_overflow(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    subject.complete_assignment(
        assignment_id=assigned.assignment_id,
        owner=owner(1),
        epoch=assigned.lease_epoch,
        completed_at=NOW + timedelta(milliseconds=100),
    )
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        _ = connection.execute("UPDATE scheduler_clock SET last_epoch = 9223372036854775807")
        connection.commit()
    finally:
        connection.close()

    receipt = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-invalid"
