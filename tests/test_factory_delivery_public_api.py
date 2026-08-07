from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from factory_orchestration_test_support import admission_repository, selection_snapshot
from factory_scheduler_test_support import dead, owner

from scripts import factory_delivery_admission as admission_module
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_assignment import plan_or_assign
from scripts.factory_scheduler_delivery import tick_selected_delivery
from scripts.factory_scheduler_models import AssignmentRequest, SchedulerLimits
from scripts.factory_scheduler_tick import tick_state


def _fabricated_request() -> AssignmentRequest:
    return AssignmentRequest.model_validate(
        {
            "request_id": "fabricated-request-9999",
            "job_id": "fabricated-job-9999",
            "issue_number": 9999,
            "worktree_id": f"wt_{'9' * 64}",
            "worker_class": "free-local",
            "access_mode": "write",
        },
        strict=True,
    )


def test_public_scheduler_apis_expose_no_snapshot_or_admission_mint_seam(
    tmp_path: Path,
) -> None:
    root = admission_repository(tmp_path)
    fabricated = replace(
        selection_snapshot(),
        issues=(replace(selection_snapshot().issues[0], number=9999),),
    )

    assert fabricated.issues[0].number == 9999
    assert "prepare_delivery_admission" not in vars(admission_module)
    assert not hasattr(FactoryScheduler, "tick_selected")
    assert "delivery_admission" not in inspect.signature(tick_state).parameters
    assert "delivery_admission" not in inspect.signature(plan_or_assign).parameters
    selected_parameters = inspect.signature(tick_selected_delivery).parameters
    assert "snapshot" not in selected_parameters
    assert "delivery_admission" not in selected_parameters

    receipt = tick_state(
        root,
        FactoryScheduler(root).limits,
        request=_fabricated_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-required"
    assert receipt.authoritative is True
    assert FactoryScheduler(root).assignment_for_job_readonly("fabricated-job-9999") is None


@pytest.mark.parametrize("plan_only", (True, False))
def test_public_empty_state_rejects_free_local_write_without_selection(
    plan_only: bool,
) -> None:
    receipt = plan_or_assign(
        None,
        request=_fabricated_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        limits=SchedulerLimits(),
        plan_only=plan_only,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-required"
    assert receipt.authoritative is False
    assert receipt.assignment_id is None
    assert receipt.lease_epoch is None
