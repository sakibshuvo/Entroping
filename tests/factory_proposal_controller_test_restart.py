from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from factory_proposal_controller_test_support import run_offline_python

from scripts.factory_scheduler_execution_models import ExecutionPhase
from scripts.factory_scheduler_models import LeaseOwner

_CHILD_CODE = (
    "import sys; from factory_proposal_controller_test_restart_child import main; "
    "main(sys.argv[1:])"
)


@dataclass(frozen=True, slots=True)
class DurableControllerState:
    assignment_state: str | None
    authorization_id: str | None
    phase: str | None
    phase_version: int | None
    reservation_state: str | None
    held_microcents: int
    spent_microcents: int
    terminal_outcome: str | None


@dataclass(frozen=True, slots=True)
class SchedulerTransition:
    job_id: str
    assignment_id: str
    owner: LeaseOwner
    epoch: int
    version: int
    phase: ExecutionPhase
    observed_at: datetime
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class SchedulerCompletion:
    job_id: str
    assignment_id: str
    owner: LeaseOwner
    epoch: int
    version: int
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class LedgerTransition:
    operation: str
    job_id: str
    reservation_id: str
    key: str
    occurred_at: datetime


def child_state(root: Path, job_id: str) -> DurableControllerState:
    return _run(root, "state", job_id)


def child_transition(root: Path, transition: SchedulerTransition) -> DurableControllerState:
    return _run(
        root,
        "transition",
        transition.job_id,
        transition.assignment_id,
        transition.owner.model_dump_json(),
        str(transition.epoch),
        str(transition.version),
        transition.phase,
        transition.observed_at.isoformat(),
        transition.evidence_digest,
    )


def child_complete(root: Path, completion: SchedulerCompletion) -> DurableControllerState:
    return _run(
        root,
        "complete",
        completion.job_id,
        completion.assignment_id,
        completion.owner.model_dump_json(),
        str(completion.epoch),
        str(completion.version),
        completion.completed_at.isoformat(),
    )


def child_ledger_transition(root: Path, transition: LedgerTransition) -> DurableControllerState:
    if transition.operation not in {"uncertain", "settle"}:
        raise AssertionError("unsupported ledger child transition")
    return _run(
        root,
        transition.operation,
        transition.job_id,
        transition.reservation_id,
        transition.key,
        transition.occurred_at.isoformat(),
    )


def _run(root: Path, operation: str, job_id: str, *values: str) -> DurableControllerState:
    result = run_offline_python(root, _CHILD_CODE, operation, job_id, *values)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return DurableControllerState(**payload)
