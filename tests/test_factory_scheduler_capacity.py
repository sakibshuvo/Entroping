from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
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


def test_limits_paid_free_review_and_writer_scope_independently(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    paid = subject.tick(
        request=request(1),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert paid.decision == "assigned"

    paid_blocked = subject.tick(
        request=request(2),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=100),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert paid_blocked.reason == "paid-capacity"

    free_review = subject.tick(
        request=request(3, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=200),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert free_review.decision == "assigned"

    free_blocked = subject.tick(
        request=request(4, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=300),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert free_blocked.reason == "free-review-capacity"

    complete_free_assignment(
        subject,
        assignment_id=free_review.assignment_id,
        lease_owner=owner(1),
        epoch=free_review.lease_epoch,
        completed_at=NOW + timedelta(milliseconds=400),
    )
    first_writer = subject.tick(
        request=request(
            5,
            worker_class="free-local",
            access_mode="write",
            worktree_id=f"wt_{'5' * 64}",
        ),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=500),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert first_writer.decision == "assigned"

    second_writer = subject.tick(
        request=request(
            6,
            worker_class="free-local",
            access_mode="write",
            worktree_id=f"wt_{'5' * 64}",
        ),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=600),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert second_writer.reason == "writer-scope-capacity"


def test_exact_replay_is_idempotent_and_changed_request_fails_closed(
    tmp_path: Path,
) -> None:
    subject = scheduler(tmp_path)
    candidate = request(1)
    first = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    replay = subject.tick(
        request=candidate,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert replay.decision == "assigned"
    assert replay.reason == "exact-replay"
    assert replay.assignment_id == first.assignment_id
    assert subject.snapshot().active_assignment_count == 1

    changed = candidate.model_copy(update={"job_id": "review-20260729-job-changed"})
    rejected = subject.tick(
        request=changed,
        owner=owner(3),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert rejected.decision == "blocked"
    assert rejected.reason == "request-id-conflict"


def test_clock_rollback_and_unknown_owner_health_fail_closed(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    first = subject.tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert first.decision == "assigned"

    rollback = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW - timedelta(seconds=1),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert rollback.reason == "clock-rollback"

    unknown = subject.tick(
        request=request(3, worker_class="free-local"),
        owner=owner(3),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        plan_only=False,
        owner_health=lambda _value: None,
    )
    assert unknown.reason == "lease-owner-health-unknown"
