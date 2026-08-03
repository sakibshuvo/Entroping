from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from datetime import timedelta
from pathlib import Path

import pytest
from factory_scheduler_test_support import (
    NOW,
    dead,
    owner,
    prepare_completion,
    request,
    scheduler,
)


def test_dead_expired_owner_with_active_assignment_requires_recovery(
    tmp_path: Path,
) -> None:
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

    blocked = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )

    assert blocked.decision == "blocked"
    assert blocked.reason == "recovery-required"


def test_completion_is_fenced_by_assignment_owner_and_epoch(tmp_path: Path) -> None:
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
    phase_version = prepare_completion(
        subject,
        assignment_id=assigned.assignment_id,
        lease_owner=owner(1),
        epoch=assigned.lease_epoch,
        completed_at=NOW + timedelta(seconds=1),
    )

    for stale_owner, stale_epoch in (
        (owner(2), assigned.lease_epoch),
        (owner(1).model_copy(update={"pid": owner(1).pid + 1}), assigned.lease_epoch),
        (
            owner(1).model_copy(update={"process_start_token": f"proc_{99:064x}"}),
            assigned.lease_epoch,
        ),
        (owner(1), assigned.lease_epoch + 1),
    ):
        with pytest.raises(RuntimeError):
            subject.complete_assignment(
                assignment_id=assigned.assignment_id,
                owner=stale_owner,
                epoch=stale_epoch,
                expected_phase_version=phase_version,
                completed_at=NOW + timedelta(seconds=1),
            )
    assert subject.snapshot().active_assignment_count == 1


def test_assignment_evidence_is_read_only_and_identity_bound(tmp_path: Path) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    evidence = subject.assignment_for_job_readonly(request().job_id)

    assert evidence is not None
    assert evidence.assignment_id == assigned.assignment_id
    assert evidence.request == request()
    assert evidence.lease_owner_id == owner(1).owner_id
    assert evidence.lease_owner_pid == owner(1).pid
    assert evidence.lease_owner_start_token == owner(1).process_start_token
