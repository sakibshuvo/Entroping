from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from factory_proposal_controller_test_receipts import PendingReceipt
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    compose_counted_worker,
    offline_scenario,
    run_cli,
)
from factory_scheduler_test_support import NOW, dead, owner, request

from scripts.factory_retry_policy import RecoverySnapshot, SnapshotSource
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import RecoveryRequest


def candidate_arguments(index: int) -> tuple[str, ...]:
    return (
        "--request-id",
        f"controller-request-{index}",
        "--job-id",
        f"controller-job-{index}",
        "--issue",
        "1575",
        "--worktree-id",
        f"wt_{index:064x}",
        "--worker-class",
        "free-local",
        "--access-mode",
        "read-only",
    )


def recovery_snapshots(
    now: datetime,
    *,
    expires: int = 60,
    future: bool = False,
    duplicate: bool = False,
) -> tuple[RecoverySnapshot, ...]:
    observed = now + timedelta(seconds=1) if future else now - timedelta(seconds=1)
    sources: tuple[SnapshotSource, ...] = ("github", "provider-capability", "price", "quota")
    snapshots = tuple(
        RecoverySnapshot(
            source=source,
            observed_at=observed,
            expires_at=now + timedelta(seconds=expires),
            digest=f"{index:x}" * 64,
        )
        for index, source in enumerate(sources, start=1)
    )
    return (*snapshots, snapshots[0]) if duplicate else snapshots


def recovery_request(
    assignment_id: str,
    epoch: int,
    snapshots: tuple[RecoverySnapshot, ...],
    request_id: str,
) -> RecoveryRequest:
    return RecoveryRequest.model_validate(
        {
            "request_id": request_id,
            "assignment_id": assignment_id,
            "expected_epoch": epoch,
            "dispatch_state": "not-dispatched",
            "settlement_state": "not-required",
            "failure_class": "transient",
            "failure_code": "offline",
            "snapshots": snapshots,
        },
        strict=True,
    )


@offline_scenario
def run_cli_safety_sequence(root: Path) -> tuple[PendingReceipt, ...]:
    idle = ScenarioObservation.begin(root, "idle-cli")
    result = run_cli(root, "status", "--json")
    assert result.returncode == 1 and not (root / ".entroping").exists()
    receipts = [idle.receipt(return_class="exit-1")]

    plan = ScenarioObservation.begin(root, "plan-only-cli")
    result = run_cli(root, "tick", "--json", *candidate_arguments(1))
    assert result.returncode == 0 and json.loads(result.stdout)["decision"] == "would-assign"
    assert not (root / ".entroping").exists()
    receipts.append(plan.receipt(return_class="would-assign"))

    invalid = ScenarioObservation.begin(root, "invalid-cli")
    result = run_cli(root, "tick", "--not-a-policy")
    assert result.returncode == 2 and not (root / ".entroping").exists()
    receipts.append(invalid.receipt(return_class="input-invalid"))

    admitted = run_cli(
        root,
        "tick",
        "--apply",
        "--json",
        "--owner-id",
        "controller-admitted",
        *candidate_arguments(2),
    )
    blocked = ScenarioObservation.begin(root, "blocked-dispatch-cli")
    result = run_cli(
        root,
        "tick",
        "--apply",
        "--json",
        "--owner-id",
        "controller-blocked",
        *candidate_arguments(3),
    )
    assert admitted.returncode == 0 and result.returncode == 1
    decision = json.loads(result.stdout)
    assert decision["decision"] == "blocked" and decision["reason"] in {
        "capacity-full",
        "lease-held",
    }
    compose_counted_worker(blocked, decision["decision"], decision.get("assignment_id"))
    receipts.append(blocked.receipt(return_class="blocked"))

    recovery_root = root / "recovery"
    recovery_root.mkdir()
    now = NOW
    assigned = FactoryScheduler(recovery_root).tick(
        request=request(9, worker_class="free-local"),
        owner=owner(1),
        as_of=now - timedelta(seconds=2),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    arguments = recovery_cli_arguments(assigned.assignment_id, assigned.lease_epoch, now)
    planned = ScenarioObservation.begin(recovery_root, "plan-first-recovery-cli")
    result = run_cli(recovery_root, "recover", "--json", *arguments)
    assert result.returncode == 0 and json.loads(result.stdout)["authoritative"] is False
    receipts.append(planned.receipt(return_class="would-recover"))

    applied = ScenarioObservation.begin(recovery_root, "explicit-recovery-apply-cli")
    result = run_cli(
        recovery_root,
        "recover",
        "--apply",
        "--json",
        "--owner-id",
        "controller-recovery",
        *arguments,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["authoritative"] is True
    receipts.append(applied.receipt(return_class="retry-scheduled"))
    return tuple(receipts)


def recovery_cli_arguments(assignment_id: str, epoch: int, now: datetime) -> tuple[str, ...]:
    snapshots = tuple(
        f"{item.source},{item.observed_at.isoformat()},{item.expires_at.isoformat()},{item.digest}"
        for item in recovery_snapshots(now)
    )
    flags = (
        "--request-id",
        "controller-recover",
        "--assignment-id",
        assignment_id,
        "--expected-epoch",
        str(epoch),
        "--dispatch-state",
        "not-dispatched",
        "--settlement-state",
        "not-required",
        "--failure-class",
        "transient",
        "--failure-code",
        "offline",
    )
    return (*flags, *(value for item in snapshots for value in ("--snapshot", item)))
