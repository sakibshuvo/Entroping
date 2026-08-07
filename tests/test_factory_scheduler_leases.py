from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from factory_scheduler_test_support import (
    NOW,
    complete_free_assignment,
    dead,
    owner,
    request,
    scheduler,
)


def test_plan_only_is_deterministic_and_creates_no_state(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    candidate = request()

    first = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )
    second = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )

    assert first == second
    assert first.decision == "would-assign"
    assert first.reason == "capacity-available"
    assert first.authoritative is False
    assert first.paid_work_authorized is False
    assert not (tmp_path / ".entroping").exists()


def test_concurrent_paid_ticks_commit_exactly_one_assignment(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)

    def tick(index: int) -> str:
        return subject.tick(
            request=request(index),
            owner=owner(index),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        ).decision

    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(tick, (1, 2)))

    assert decisions.count("assigned") == 1
    assert decisions.count("blocked") == 1
    snapshot = subject.snapshot()
    assert snapshot.active_paid == 1
    assert snapshot.active_assignment_count == 1


def test_expired_lease_is_not_stolen_while_owner_is_healthy(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    first = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=5,
        plan_only=False,
        owner_health=dead,
    )
    assert first.decision == "assigned"

    blocked = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=6),
        lease_seconds=5,
        plan_only=False,
        owner_health=lambda value: value == owner(1),
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "lease-owner-healthy"
    assert blocked.lease_epoch == first.lease_epoch


def test_dead_expired_owner_is_fenced_by_a_new_epoch(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    first = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=5,
        plan_only=False,
        owner_health=dead,
    )
    assert first.lease_epoch is not None
    complete_free_assignment(
        subject,
        assignment_id=first.assignment_id,
        lease_owner=owner(1),
        epoch=first.lease_epoch,
        completed_at=NOW + timedelta(seconds=1),
    )

    second = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=6),
        lease_seconds=5,
        plan_only=False,
        owner_health=dead,
    )

    assert second.decision == "assigned"
    assert second.lease_epoch == first.lease_epoch + 1
    stale = subject.heartbeat(
        owner=owner(1),
        epoch=first.lease_epoch,
        as_of=NOW + timedelta(seconds=7),
        lease_seconds=5,
    )
    assert stale.decision == "blocked"
    assert stale.reason == "stale-lease-epoch"
