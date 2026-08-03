from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from factory_proposal_controller_test_support import (
    ScenarioReceipt,
    assert_source_unchanged,
    offline_scenario,
    record_receipt,
    run_cli,
    source_digest,
)
from factory_scheduler_test_support import dead, owner, request

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
) -> tuple[RecoverySnapshot, ...]:
    offset = timedelta(seconds=1)
    observed = now + offset if future else now - offset
    sources: tuple[SnapshotSource, ...] = (
        "github",
        "provider-capability",
        "price",
        "quota",
    )
    return tuple(
        RecoverySnapshot(
            source=source,
            observed_at=observed,
            expires_at=now + timedelta(seconds=expires),
            digest=f"{index:x}" * 64,
        )
        for index, source in enumerate(sources, start=1)
    )


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
def run_cli_safety_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    before = source_digest()
    idle = run_cli(root, "status", "--json")
    assert idle.returncode == 1 and not (root / ".entroping").exists()
    receipts = [
        record_receipt(
            root,
            scenario="idle-cli",
            return_class="exit-1",
            changed_paths=("none",),
            invariants=("offline", "no-state"),
        )
    ]
    planned = run_cli(root, "tick", "--json", *candidate_arguments(1))
    assert planned.returncode == 0 and json.loads(planned.stdout)["decision"] == "would-assign"
    assert not (root / ".entroping").exists()
    receipts.append(
        _receipt(root, "plan-only-cli", "would-assign", ("none",), ("offline", "no-state"))
    )
    invalid = run_cli(root, "tick", "--not-a-policy")
    assert invalid.returncode == 2 and not (root / ".entroping").exists()
    receipts.append(
        _receipt(root, "invalid-cli", "input-invalid", ("none",), ("offline", "no-state"))
    )
    blocked = run_cli(root, "tick", "--apply", "--json", *candidate_arguments(2))
    assert blocked.returncode == 2
    receipts.append(
        _receipt(root, "blocked-dispatch-cli", "blocked", ("none",), ("no-worker", "offline"))
    )
    now = datetime.now(UTC)
    assigned = FactoryScheduler(root).tick(
        request=request(9, worker_class="free-local"),
        owner=owner(1),
        as_of=now - timedelta(seconds=2),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    arguments = recovery_cli_arguments(assigned.assignment_id, assigned.lease_epoch, now)
    planned_recovery = run_cli(root, "recover", "--json", *arguments)
    assert planned_recovery.returncode == 0
    assert json.loads(planned_recovery.stdout)["authoritative"] is False
    receipts.append(
        _receipt(
            root,
            "plan-first-recovery-cli",
            "would-recover",
            ("scheduler",),
            ("offline", "no-worker"),
        )
    )
    applied = run_cli(
        root, "recover", "--apply", "--json", "--owner-id", "controller-recovery", *arguments
    )
    assert applied.returncode == 0 and json.loads(applied.stdout)["authoritative"] is True
    receipts.append(
        _receipt(
            root,
            "explicit-recovery-apply-cli",
            "retry-scheduled",
            ("scheduler",),
            ("offline", "no-worker"),
        )
    )
    assert_source_unchanged(before)
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


def _receipt(
    root: Path, scenario: str, result: str, paths: tuple[str, ...], invariants: tuple[str, ...]
) -> ScenarioReceipt:
    return record_receipt(
        root, scenario=scenario, return_class=result, changed_paths=paths, invariants=invariants
    )
