from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import pytest
from factory_scheduler_test_support import (
    NOW,
    complete_free_assignment,
    dead,
    owner,
    request,
    scheduler,
)

from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_storage_fs import BUSY_TIMEOUT_MILLISECONDS


def test_malformed_state_and_lock_contention_return_bounded_receipts(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / ".entroping" / "factory-scheduler"
    state_directory.mkdir(parents=True)
    (tmp_path / ".entroping").chmod(0o700)
    state_directory.chmod(0o700)
    database = state_directory / "scheduler.sqlite3"
    database.write_text("not sqlite", encoding="utf-8")
    database.chmod(0o600)
    subject = scheduler(tmp_path)

    malformed = subject.tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert malformed.decision == "blocked"
    assert malformed.reason == "state-invalid"

    database.unlink()
    initialized = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert initialized.decision == "assigned"

    connection = sqlite3.connect(database, autocommit=True)
    _ = connection.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        busy = subject.tick(
            request=request(3, worker_class="free-local"),
            owner=owner(3),
            as_of=NOW + timedelta(seconds=1),
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
    finally:
        _ = connection.execute("ROLLBACK")
        connection.close()

    assert time.monotonic() - started < (BUSY_TIMEOUT_MILLISECONDS / 1_000) + 0.5
    assert busy.decision == "blocked"
    assert busy.reason == "state-busy"


def test_malformed_state_value_returns_a_bounded_receipt(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.decision == "assigned"
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        _ = connection.execute(
            "UPDATE scheduler_clock SET last_observed_at_utc = 'not-a-timestamp'"
        )
        connection.commit()
    finally:
        connection.close()

    blocked = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "state-invalid"


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "schema"])
def test_unsafe_existing_state_fails_closed_in_plan_mode(
    tmp_path: Path,
    attack: str,
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

    if attack == "symlink":
        original = database.with_suffix(".original")
        database.rename(original)
        database.symlink_to(original.name)
    elif attack == "hardlink":
        os.link(database, database.with_suffix(".hardlink"))
    else:
        connection = sqlite3.connect(database)
        try:
            _ = connection.execute("DROP TRIGGER scheduler_assignment_identity_immutable")
            connection.commit()
        finally:
            connection.close()

    blocked = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "state-invalid"


def test_dangling_scheduler_database_symlink_fails_closed_in_plan_mode(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / ".entroping" / "factory-scheduler"
    state_directory.mkdir(parents=True)
    (tmp_path / ".entroping").chmod(0o700)
    state_directory.chmod(0o700)
    (state_directory / "scheduler.sqlite3").symlink_to("missing.sqlite3")

    blocked = scheduler(tmp_path).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "state-invalid"


def test_unsafe_empty_scheduler_directory_fails_closed_in_plan_mode(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / ".entroping" / "factory-scheduler"
    state_directory.mkdir(parents=True)
    (tmp_path / ".entroping").chmod(0o700)
    state_directory.chmod(0o755)

    blocked = scheduler(tmp_path).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "state-invalid"


def test_cancelled_takeover_rolls_back_without_partial_assignment(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    first = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    complete_free_assignment(
        subject,
        assignment_id=first.assignment_id,
        lease_owner=owner(1),
        epoch=first.lease_epoch,
        completed_at=NOW + timedelta(milliseconds=100),
    )

    def cancel(_owner: LeaseOwner) -> bool:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        subject.tick(
            request=request(2, worker_class="free-local"),
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=1,
            plan_only=False,
            owner_health=cancel,
        )

    snapshot = subject.snapshot()
    assert snapshot.active_assignment_count == 0
    assert snapshot.lease_owner_id == owner(1).owner_id
    assert snapshot.lease_epoch == first.lease_epoch
