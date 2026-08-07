from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from factory_scheduler_test_support import NOW, dead, owner, request, scheduler

from scripts.factory_retry_policy import RecoverySnapshot, RetryPolicy
from scripts.factory_scheduler_execution_models import ExecutionPhase, RecoveryRequest


def _snapshots() -> tuple[RecoverySnapshot, ...]:
    return (
        RecoverySnapshot(
            source="github",
            observed_at=NOW - timedelta(seconds=1),
            expires_at=NOW + timedelta(minutes=1),
            digest="1" * 64,
        ),
        RecoverySnapshot(
            source="provider-capability",
            observed_at=NOW - timedelta(seconds=1),
            expires_at=NOW + timedelta(minutes=1),
            digest="2" * 64,
        ),
    )


def _recovery(
    assignment_id: str,
    epoch: int,
    *,
    dispatch_state: str,
    settlement_state: str,
    failure_class: str,
) -> RecoveryRequest:
    return RecoveryRequest.model_validate(
        {
            "request_id": "phase-recovery",
            "assignment_id": assignment_id,
            "expected_epoch": epoch,
            "dispatch_state": dispatch_state,
            "settlement_state": settlement_state,
            "failure_class": failure_class,
            "failure_code": "worker-interrupted",
            "snapshots": _snapshots(),
        },
        strict=True,
    )


@pytest.mark.parametrize(
    ("boundary", "dispatch_state", "settlement_state", "failure_class", "decision"),
    (
        ("never-dispatched", "not-dispatched", "not-required", "transient", "retry-scheduled"),
        ("dispatch-intent", "unknown", "not-required", "unknown", "uncertain"),
        ("dispatched", "unknown", "not-required", "unknown", "uncertain"),
        ("completed-unsettled", "completed", "not-required", "none", "completed"),
    ),
)
def test_crash_recovery_is_deterministic_at_each_phase_boundary(
    tmp_path: Path,
    boundary: ExecutionPhase,
    dispatch_state: str,
    settlement_state: str,
    failure_class: str,
    decision: str,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    chain: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for version, phase in enumerate(chain, start=1):
        if boundary == "never-dispatched":
            break
        subject.transition_execution(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=NOW + timedelta(milliseconds=version * 100),
            evidence_digest=f"{version:x}" * 64,
        )
        if phase == boundary:
            break

    receipt = subject.recover(
        _recovery(
            assigned.assignment_id,
            assigned.lease_epoch,
            dispatch_state=dispatch_state,
            settlement_state=settlement_state,
            failure_class=failure_class,
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(jitter_percent=0),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == decision
    assert receipt.paid_work_authorized is False
    assert subject.snapshot().active_assignment_count == (0 if decision == "completed" else 1)


def test_execution_transitions_and_heartbeats_are_cas_and_epoch_fenced(
    tmp_path: Path,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None

    heartbeat = subject.heartbeat(
        owner=owner(1),
        epoch=assigned.lease_epoch,
        as_of=NOW + timedelta(milliseconds=100),
        lease_seconds=1,
    )
    execution = subject.execution_for_job_readonly(request().job_id)
    assert heartbeat.decision == "heartbeat", heartbeat.reason
    assert execution is not None
    assert execution.worker_heartbeat_at == NOW + timedelta(milliseconds=100)

    with pytest.raises(RuntimeError):
        subject.transition_execution(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=1,
            target_phase="dispatched",
            observed_at=NOW + timedelta(milliseconds=200),
            evidence_digest="a" * 64,
        )
    intent = subject.transition_execution(
        assignment_id=assigned.assignment_id,
        owner=owner(1),
        epoch=assigned.lease_epoch,
        expected_phase_version=1,
        target_phase="dispatch-intent",
        observed_at=NOW + timedelta(milliseconds=200),
        evidence_digest="a" * 64,
    )
    assert intent.phase_version == 2
    for stale_owner, stale_version in ((owner(2), 2), (owner(1), 1)):
        with pytest.raises(RuntimeError):
            subject.transition_execution(
                assignment_id=assigned.assignment_id,
                owner=stale_owner,
                epoch=assigned.lease_epoch,
                expected_phase_version=stale_version,
                target_phase="dispatched",
                observed_at=NOW + timedelta(milliseconds=300),
                evidence_digest="b" * 64,
            )

    recovered = subject.recover(
        _recovery(
            assigned.assignment_id,
            assigned.lease_epoch,
            dispatch_state="unknown",
            settlement_state="not-required",
            failure_class="unknown",
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )
    assert recovered.decision == "uncertain"
    stale_heartbeat = subject.heartbeat(
        owner=owner(1),
        epoch=assigned.lease_epoch,
        as_of=NOW + timedelta(seconds=3),
        lease_seconds=30,
    )
    assert stale_heartbeat.decision == "blocked"
    assert stale_heartbeat.reason == "stale-lease-epoch"
    with pytest.raises(RuntimeError):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=3,
            completed_at=NOW + timedelta(seconds=3),
        )


def test_terminal_phase_and_outcome_must_match_in_model_and_database(
    tmp_path: Path,
) -> None:
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    execution = subject.execution_for_job_readonly(request().job_id)
    assert execution is not None
    with pytest.raises(ValueError, match="terminal execution outcome"):
        _ = type(execution).model_validate(
            {
                **execution.model_dump(),
                "phase": "completed",
                "terminal_outcome": "failed",
            },
            strict=True,
        )

    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            _ = connection.execute(
                "UPDATE scheduler_execution_state "
                "SET phase = 'completed', terminal_outcome = 'failed' "
                "WHERE assignment_id = ?",
                (assigned.assignment_id,),
            )
    finally:
        connection.close()
