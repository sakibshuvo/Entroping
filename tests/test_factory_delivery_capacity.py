from __future__ import annotations

from pathlib import Path

import pytest
from factory_orchestration_test_support import admission_repository, selection_snapshot
from factory_scheduler_test_support import dead, owner

from scripts import factory_scheduler_delivery as scheduler_delivery
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_models import AssignmentRequest, SchedulerLimits


def test_specialized_live_admission_enforces_writer_scope_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    monkeypatch.setattr(
        scheduler_delivery,
        "refresh_snapshot",
        lambda **_kwargs: selection_snapshot(),
    )
    request = AssignmentRequest.model_validate(
        {
            "request_id": "writer-capacity-request",
            "job_id": "writer-capacity-job",
            "issue_number": 1574,
            "worktree_id": f"wt_{'8' * 64}",
            "worker_class": "free-local",
            "access_mode": "write",
        },
        strict=True,
    )
    subject = FactoryScheduler(
        root,
        limits=SchedulerLimits(max_writers_per_scope=0),
    )

    receipt = subject._tick_selected(
        request=request,
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "writer-scope-capacity"
    assert receipt.authoritative is True
    assert subject.snapshot().active_assignment_count == 0
    assert subject.snapshot().lease_owner_id is None
