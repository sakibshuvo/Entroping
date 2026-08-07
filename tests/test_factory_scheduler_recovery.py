from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import sqlite3
from collections.abc import Callable
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from concurrent.futures import (
    TimeoutError as FuturesTimeoutError,
)
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from factory_scheduler_test_support import (
    NOW,
    dead,
    owner,
    paid_request_with_reservation,
    prepare_completion,
    request,
    scheduler,
)

from scripts import factory_scheduler_completion_service
from scripts.factory_budget_ledger import NoChargeReconciliationInput, SettlementReceipt
from scripts.factory_retry_policy import RecoverySnapshot, RetryPolicy, SnapshotSource
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import (
    ExecutionPhase,
    RecoveryReceipt,
    RecoveryRequest,
)
from scripts.factory_scheduler_models import LeaseOwner, WorkerClass
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState


@dataclass(frozen=True)
class AssignedEvidence:
    assignment_id: str
    lease_epoch: int


def _snapshots(*, expires_in: int = 60) -> tuple[RecoverySnapshot, ...]:
    sources: tuple[SnapshotSource, ...] = (
        "github",
        "provider-capability",
        "price",
        "quota",
    )
    return tuple(
        RecoverySnapshot(
            source=source,
            observed_at=NOW - timedelta(seconds=1),
            expires_at=NOW + timedelta(seconds=expires_in),
            digest=f"{index:x}" * 64,
        )
        for index, source in enumerate(sources, start=1)
    )


def _recovery(
    *,
    request_id: str = "recover-1",
    assignment_id: str,
    expected_epoch: int,
    dispatch_state: str = "not-dispatched",
    settlement_state: str = "not-required",
    failure_class: str = "transient",
    failure_code: str = "provider-unavailable",
    retry_after_seconds: int | None = None,
    snapshots: tuple[RecoverySnapshot, ...] | None = None,
) -> RecoveryRequest:
    return RecoveryRequest.model_validate(
        {
            "request_id": request_id,
            "assignment_id": assignment_id,
            "expected_epoch": expected_epoch,
            "dispatch_state": dispatch_state,
            "settlement_state": settlement_state,
            "failure_class": failure_class,
            "failure_code": failure_code,
            "retry_after_seconds": retry_after_seconds,
            "snapshots": snapshots if snapshots is not None else _snapshots(),
        },
        strict=True,
    )


def _assigned(
    tmp_path: Path,
    *,
    worker_class: WorkerClass = "paid",
) -> tuple[FactoryScheduler, AssignedEvidence]:
    subject = scheduler(tmp_path)
    receipt = subject.tick(
        request=request(1, worker_class=worker_class),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert receipt.assignment_id is not None
    assert receipt.lease_epoch is not None
    return subject, AssignedEvidence(receipt.assignment_id, receipt.lease_epoch)


def test_assignment_starts_with_durable_never_dispatched_execution_state(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path)

    execution = subject.execution_for_job_readonly(request().job_id)

    assert execution is not None
    assert execution.assignment_id == assigned.assignment_id
    assert execution.phase == "never-dispatched"
    assert execution.phase_version == 1
    assert execution.attempt_count == 1
    assert execution.lease_owner_id == owner(1).owner_id
    assert execution.lease_epoch == assigned.lease_epoch
    assert execution.retry_not_before is None
    assert execution.terminal_outcome is None


def test_recovery_schedules_then_resumes_proven_never_dispatched_work(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path)
    recovery = _recovery(
        assignment_id=str(assigned.assignment_id),
        expected_epoch=int(assigned.lease_epoch),
    )
    policy = RetryPolicy(
        base_delay_seconds=10,
        max_delay_seconds=60,
        max_attempts=3,
        max_elapsed_seconds=300,
        jitter_percent=0,
    )

    scheduled = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        retry_policy=policy,
        plan_only=False,
        owner_health=dead,
    )
    replay = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        retry_policy=policy,
        plan_only=False,
        owner_health=dead,
    )

    assert scheduled == replay
    assert scheduled.decision == "retry-scheduled"
    assert scheduled.phase == "retry-wait"
    assert scheduled.retry_not_before == NOW + timedelta(seconds=12)
    assert subject.snapshot().active_assignment_count == 1

    not_due = subject.recover(
        recovery.model_copy(update={"request_id": "recover-2", "expected_epoch": 2}),
        owner=owner(3),
        as_of=NOW + timedelta(seconds=4),
        lease_seconds=1,
        retry_policy=policy,
        plan_only=False,
        owner_health=dead,
    )
    assert not_due.decision == "blocked"
    assert not_due.reason == "retry-not-due"

    resumed = subject.recover(
        recovery.model_copy(update={"request_id": "recover-3", "expected_epoch": 2}),
        owner=owner(3),
        as_of=NOW + timedelta(seconds=12),
        lease_seconds=30,
        retry_policy=policy,
        plan_only=False,
        owner_health=dead,
    )
    execution = subject.execution_for_job_readonly(request().job_id)

    assert resumed.decision == "resumed"
    assert resumed.phase == "never-dispatched"
    assert resumed.attempt_count == 2
    assert resumed.lease_epoch == 3
    assert execution is not None
    assert execution.lease_owner_id == owner(3).owner_id
    assert execution.lease_epoch == 3


def test_ambiguous_dispatch_becomes_uncertain_without_reopening_capacity(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    subject.transition_execution(
        assignment_id=str(assigned.assignment_id),
        owner=owner(1),
        epoch=int(assigned.lease_epoch),
        expected_phase_version=1,
        target_phase="dispatch-intent",
        observed_at=NOW + timedelta(milliseconds=100),
        evidence_digest="a" * 64,
    )
    recovery = _recovery(
        assignment_id=str(assigned.assignment_id),
        expected_epoch=int(assigned.lease_epoch),
        dispatch_state="unknown",
        settlement_state="not-required",
        failure_class="unknown",
        failure_code="worker-interrupted",
    )

    receipt = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "uncertain"
    assert receipt.phase == "uncertain"
    assert subject.snapshot().active_assignment_count == 1
    with pytest.raises(RuntimeError):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=3,
            completed_at=NOW + timedelta(seconds=3),
        )


def test_completed_settled_recovery_is_terminal_and_frees_capacity(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    subject.transition_execution(
        assignment_id=str(assigned.assignment_id),
        owner=owner(1),
        epoch=int(assigned.lease_epoch),
        expected_phase_version=1,
        target_phase="dispatch-intent",
        observed_at=NOW + timedelta(milliseconds=100),
        evidence_digest="a" * 64,
    )
    subject.transition_execution(
        assignment_id=str(assigned.assignment_id),
        owner=owner(1),
        epoch=int(assigned.lease_epoch),
        expected_phase_version=2,
        target_phase="dispatched",
        observed_at=NOW + timedelta(milliseconds=200),
        evidence_digest="b" * 64,
    )
    subject.transition_execution(
        assignment_id=str(assigned.assignment_id),
        owner=owner(1),
        epoch=int(assigned.lease_epoch),
        expected_phase_version=3,
        target_phase="completed-unsettled",
        observed_at=NOW + timedelta(milliseconds=300),
        evidence_digest="c" * 64,
    )

    receipt = subject.recover(
        _recovery(
            assignment_id=str(assigned.assignment_id),
            expected_epoch=int(assigned.lease_epoch),
            dispatch_state="completed",
            settlement_state="not-required",
            failure_class="none",
            failure_code="worker-completed",
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "completed"
    assert receipt.phase == "completed"
    assert receipt.terminal_outcome == "completed"
    assert subject.snapshot().active_assignment_count == 0


def test_retry_exhaustion_is_terminal_and_does_not_hot_loop(tmp_path: Path) -> None:
    subject, assigned = _assigned(tmp_path)
    receipt = subject.recover(
        _recovery(
            assignment_id=str(assigned.assignment_id),
            expected_epoch=int(assigned.lease_epoch),
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(max_attempts=1),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "failed"
    assert receipt.reason == "retry-exhausted"
    assert receipt.terminal_outcome == "retry-exhausted"
    assert subject.snapshot().active_assignment_count == 0


def test_paid_retry_fails_closed_when_any_authority_snapshot_is_stale(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path)
    stale = _snapshots(expires_in=0)

    receipt = subject.recover(
        _recovery(
            assignment_id=str(assigned.assignment_id),
            expected_epoch=int(assigned.lease_epoch),
            snapshots=stale,
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "retry-scheduled"
    assert receipt.reason == "github-snapshot-stale"
    assert receipt.paid_work_authorized is False
    assert subject.snapshot().active_assignment_count == 1


def test_paid_ambiguous_recovery_requires_ledger_uncertainty_first(
    tmp_path: Path,
) -> None:
    ledger, candidate = paid_request_with_reservation(tmp_path)
    subject = FactoryScheduler(tmp_path)
    assigned = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    subject.transition_execution(
        assignment_id=assigned.assignment_id,
        owner=owner(1),
        epoch=assigned.lease_epoch,
        expected_phase_version=1,
        target_phase="dispatch-intent",
        observed_at=NOW + timedelta(milliseconds=100),
        evidence_digest="a" * 64,
    )
    recovery = _recovery(
        assignment_id=assigned.assignment_id,
        expected_epoch=assigned.lease_epoch,
        dispatch_state="unknown",
        settlement_state="uncertain",
        failure_class="unknown",
        failure_code="worker-interrupted",
    )

    premature = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert premature.decision == "blocked"
    assert premature.reason == "settlement-authority-conflict"
    assert candidate.reservation_id is not None
    uncertain = ledger.mark_reservation_uncertain(
        candidate.reservation_id,
        idempotency_key="recover-scheduler-job-1",
        reason="worker_interrupted",
        occurred_at=NOW + timedelta(seconds=2),
        evidence_digest="b" * 64,
    )
    assert uncertain.state == "uncertain"

    recovered = subject.recover(
        recovery.model_copy(update={"request_id": "recover-2"}),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert recovered.decision == "uncertain"
    assert recovered.phase == "uncertain"
    assert subject.snapshot().active_assignment_count == 1


def test_plan_only_predicts_recovery_without_changing_durable_state(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    before = hashlib.sha256(database.read_bytes()).digest()

    receipt = subject.recover(
        _recovery(
            assignment_id=str(assigned.assignment_id),
            expected_epoch=int(assigned.lease_epoch),
            snapshots=_snapshots()[:2],
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(jitter_percent=0),
        plan_only=True,
        owner_health=dead,
    )
    execution = subject.execution_for_job_readonly(request().job_id)

    assert receipt.decision == "would-recover"
    assert receipt.reason == "retry-scheduled"
    assert receipt.phase == "retry-wait"
    assert receipt.authoritative is False
    assert execution is not None
    assert execution.phase == "never-dispatched"
    assert hashlib.sha256(database.read_bytes()).digest() == before


@pytest.mark.parametrize(
    ("offset", "health", "reason"),
    (
        (0, dead, "lease-held"),
        (2, lambda _owner: True, "lease-owner-healthy"),
        (2, lambda _owner: None, "lease-owner-health-unknown"),
    ),
)
def test_recovery_fails_closed_while_prior_authority_is_not_proven_dead(
    tmp_path: Path,
    offset: int,
    health: Callable[[LeaseOwner], bool | None],
    reason: str,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")

    receipt = subject.recover(
        _recovery(
            assignment_id=str(assigned.assignment_id),
            expected_epoch=int(assigned.lease_epoch),
            snapshots=_snapshots()[:2],
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=offset),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=health,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == reason
    assert receipt.lease_epoch == assigned.lease_epoch


def test_recovery_request_id_conflict_preserves_first_receipt(tmp_path: Path) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    recovery = _recovery(
        assignment_id=str(assigned.assignment_id),
        expected_epoch=int(assigned.lease_epoch),
        snapshots=_snapshots()[:2],
    )
    first = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    with pytest.raises(RuntimeError):
        subject.recover(
            recovery.model_copy(update={"failure_code": "different-failure"}),
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=dead,
        )

    assert first == subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )


def test_concurrent_recovery_has_one_epoch_winner(tmp_path: Path) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")

    def recover(index: int) -> RecoveryReceipt:
        return subject.recover(
            _recovery(
                request_id=f"recover-{index}",
                assignment_id=str(assigned.assignment_id),
                expected_epoch=int(assigned.lease_epoch),
                snapshots=_snapshots()[:2],
            ),
            owner=owner(index),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=dead,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = tuple(pool.map(recover, (2, 3)))

    assert sorted(receipt.decision for receipt in receipts) == [
        "blocked",
        "retry-scheduled",
    ]
    assert sorted(receipt.reason for receipt in receipts) == [
        "retry-scheduled",
        "stale-lease-epoch",
    ]
    execution = subject.execution_for_job_readonly(request().job_id)
    assert execution is not None
    assert execution.lease_epoch == 2
    assert execution.phase_version == 2


def test_recovery_rejects_tampered_receipt_without_exposing_stored_content(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    recovery = _recovery(
        assignment_id=str(assigned.assignment_id),
        expected_epoch=int(assigned.lease_epoch),
        snapshots=_snapshots()[:2],
    )
    _ = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name = 'scheduler_recovery_receipts_immutable'"
        ).fetchone()
        assert trigger is not None
        _ = connection.execute("DROP TRIGGER scheduler_recovery_receipts_immutable")
        _ = connection.execute("UPDATE scheduler_recovery_receipts SET receipt_json = '{}'")
        _ = connection.execute(str(trigger[0]))
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="scheduler recovery failed"):
        subject.recover(
            recovery,
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=dead,
        )


def test_recovery_refuses_scheduler_database_symlink(tmp_path: Path) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    original = database.with_suffix(".original")
    database.rename(original)
    database.symlink_to(original.name)

    with pytest.raises(RuntimeError, match="scheduler recovery failed"):
        subject.recover(
            _recovery(
                assignment_id=str(assigned.assignment_id),
                expected_epoch=int(assigned.lease_epoch),
                snapshots=_snapshots()[:2],
            ),
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=True,
            owner_health=dead,
        )


def test_completed_uncertain_evidence_never_reopens_retryable_work(
    tmp_path: Path,
) -> None:
    authority: dict[str, SettlementAuthorityState] = {"state": "dispatching"}
    subject = FactoryScheduler(
        tmp_path,
        reservation_guard=lambda _request: nullcontext(True),
        settlement_authority=lambda _assignment: authority["state"],
    )
    assigned = subject.tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    scheduled = subject.recover(
        _recovery(
            assignment_id=assigned.assignment_id,
            expected_epoch=assigned.lease_epoch,
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=1,
        retry_policy=RetryPolicy(jitter_percent=0),
        plan_only=False,
        owner_health=dead,
    )
    assert scheduled.phase == "retry-wait"
    authority["state"] = "uncertain"

    recovered = subject.recover(
        _recovery(
            request_id="recover-completed-uncertain",
            assignment_id=assigned.assignment_id,
            expected_epoch=scheduled.lease_epoch,
            dispatch_state="completed",
            settlement_state="uncertain",
            failure_class="unknown",
        ),
        owner=owner(3),
        as_of=scheduled.retry_not_before or NOW + timedelta(seconds=60),
        lease_seconds=30,
        retry_policy=RetryPolicy(jitter_percent=0),
        plan_only=False,
        owner_health=dead,
    )

    assert recovered.decision == "uncertain"
    assert recovered.phase == "uncertain"


def test_paid_completion_requires_phase_and_settled_ledger_authority(
    tmp_path: Path,
) -> None:
    ledger, candidate = paid_request_with_reservation(tmp_path)
    subject = FactoryScheduler(tmp_path)
    assigned = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    with pytest.raises(RuntimeError, match="completion failed"):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=1,
            completed_at=NOW + timedelta(seconds=1),
        )
    phases: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for version, phase in enumerate(
        phases,
        start=1,
    ):
        subject.transition_execution(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=NOW + timedelta(milliseconds=version * 100),
            evidence_digest=f"{version:x}" * 64,
        )
    with pytest.raises(RuntimeError, match="completion failed"):
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=4,
            completed_at=NOW + timedelta(seconds=1),
        )
    assert candidate.reservation_id is not None
    settled = ledger.settle_reservation(
        SettlementReceipt(
            idempotency_key="settle-scheduler-job-1",
            reservation_id=candidate.reservation_id,
            job_id=candidate.job_id,
            provider_lane_id="test-paid/direct",
            provider_id="test-paid",
            model_id="test-paid/model",
            requested_model="test-paid-model",
            provider_session_digest="d" * 64,
            input_tokens=0,
            output_tokens=0,
            requests=1,
            minutes=0,
            occurred_at=NOW + timedelta(milliseconds=900),
        )
    )
    assert settled.state == "settled"

    subject.complete_assignment(
        assignment_id=assigned.assignment_id,
        owner=owner(1),
        epoch=assigned.lease_epoch,
        expected_phase_version=4,
        completed_at=NOW + timedelta(seconds=1),
    )

    assert subject.snapshot().active_assignment_count == 0


def test_paid_no_charge_reconciliation_can_close_never_dispatched_capacity(
    tmp_path: Path,
) -> None:
    ledger, candidate = paid_request_with_reservation(tmp_path)
    subject = FactoryScheduler(tmp_path)
    assigned = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    assert candidate.reservation_id is not None
    reconciled = ledger.reconcile_no_charge(
        NoChargeReconciliationInput(
            idempotency_key="no-charge-scheduler-job-1",
            reservation_id=candidate.reservation_id,
            evidence_digest="e" * 64,
            occurred_at=NOW + timedelta(seconds=1),
            reason="verified_never_dispatched",
        )
    )
    assert reconciled.state == "reconciled"

    receipt = subject.recover(
        _recovery(
            request_id="recover-no-charge",
            assignment_id=assigned.assignment_id,
            expected_epoch=assigned.lease_epoch,
            dispatch_state="not-dispatched",
            settlement_state="settled",
            failure_class="terminal",
            failure_code="verified-never-dispatched",
            snapshots=(),
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "failed"
    assert receipt.reason == "never-dispatched-settled"
    assert subject.snapshot().active_assignment_count == 0


def test_exact_recovery_replay_across_processes_does_not_transfer_execution_authority(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    recovery = _recovery(
        request_id="replacement-process-replay",
        assignment_id=assigned.assignment_id,
        expected_epoch=assigned.lease_epoch,
        snapshots=_snapshots()[:2],
    )
    first = subject.recover(
        recovery,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )
    replacement = owner(2).model_copy(
        update={
            "pid": owner(2).pid + 100,
            "process_start_token": f"proc_{999:064x}",
        }
    )

    replay = subject.recover(
        recovery,
        owner=replacement,
        as_of=NOW + timedelta(seconds=3),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )
    heartbeat = subject.heartbeat(
        owner=replacement,
        epoch=first.lease_epoch,
        as_of=NOW + timedelta(seconds=3),
        lease_seconds=30,
    )

    assert replay == first
    assert heartbeat.decision == "blocked"
    assert heartbeat.reason == "stale-lease-epoch"
    with pytest.raises(RuntimeError, match="execution transition failed"):
        subject.transition_execution(
            assignment_id=assigned.assignment_id,
            owner=replacement,
            epoch=first.lease_epoch,
            expected_phase_version=first.phase_version,
            target_phase="dispatch-intent",
            observed_at=NOW + timedelta(seconds=3),
            evidence_digest="f" * 64,
        )


def test_recovery_receipt_capacity_fails_before_database_becomes_invalid(
    tmp_path: Path,
) -> None:
    subject, assigned = _assigned(tmp_path, worker_class="free-local")
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executemany(
            "INSERT INTO scheduler_recovery_receipts("
            "request_id, request_digest, receipt_id, assignment_id, created_at_utc, "
            "receipt_json) VALUES (?, ?, ?, ?, ?, '{}')",
            (
                (
                    f"capacity-{index}",
                    f"{index:064x}",
                    f"recovery_{index:064x}",
                    assigned.assignment_id,
                    NOW.isoformat(),
                )
                for index in range(10_000)
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="scheduler recovery failed"):
        subject.recover(
            _recovery(
                request_id="capacity-overflow",
                assignment_id=assigned.assignment_id,
                expected_epoch=assigned.lease_epoch,
                snapshots=_snapshots()[:2],
            ),
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=dead,
        )

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM scheduler_recovery_receipts"
        ).fetchone() == (10_000,)
    finally:
        connection.close()
    assert subject.snapshot().active_assignment_count == 1


def test_paid_completion_holds_ledger_writer_guard_through_scheduler_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, candidate = paid_request_with_reservation(tmp_path)
    subject = FactoryScheduler(tmp_path)
    assigned = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    assert candidate.reservation_id is not None
    _ = ledger.settle_reservation(
        SettlementReceipt(
            idempotency_key="settle-guarded-scheduler-job",
            reservation_id=candidate.reservation_id,
            job_id=candidate.job_id,
            provider_lane_id="test-paid/direct",
            provider_id="test-paid",
            model_id="test-paid/model",
            requested_model="test-paid-model",
            provider_session_digest="a" * 64,
            input_tokens=0,
            output_tokens=0,
            requests=1,
            minutes=0,
            occurred_at=NOW + timedelta(milliseconds=800),
        )
    )
    phase_version = prepare_completion(
        subject,
        assignment_id=assigned.assignment_id,
        lease_owner=owner(1),
        epoch=assigned.lease_epoch,
        completed_at=NOW + timedelta(seconds=1),
    )
    original = factory_scheduler_completion_service.complete_assignment
    writer_started = Event()
    writer_future: list[Future[None]] = []

    def competing_writer() -> None:
        connection = sqlite3.connect(ledger.db_path, timeout=2, autocommit=True)
        try:
            writer_started.set()
            _ = connection.execute("BEGIN IMMEDIATE")
            _ = connection.execute("ROLLBACK")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:

        def assert_guarded_commit(
            connection: sqlite3.Connection,
            *,
            assignment_id: str,
            owner: LeaseOwner,
            epoch: int,
            expected_phase_version: int,
            completed_at: datetime,
        ) -> None:
            future = pool.submit(competing_writer)
            writer_future.append(future)
            assert writer_started.wait(timeout=1)
            with pytest.raises(FuturesTimeoutError):
                _ = future.result(timeout=0.05)
            original(
                connection,
                assignment_id=assignment_id,
                owner=owner,
                epoch=epoch,
                expected_phase_version=expected_phase_version,
                completed_at=completed_at,
            )

        monkeypatch.setattr(
            factory_scheduler_completion_service,
            "complete_assignment",
            assert_guarded_commit,
        )
        subject.complete_assignment(
            assignment_id=assigned.assignment_id,
            owner=owner(1),
            epoch=assigned.lease_epoch,
            expected_phase_version=phase_version,
            completed_at=NOW + timedelta(seconds=1),
        )
        assert writer_future
        _ = writer_future[0].result(timeout=2)


def test_recovering_one_expired_assignment_does_not_strand_its_sibling(
    tmp_path: Path,
) -> None:
    subject = scheduler(tmp_path)
    paid = subject.tick(
        request=request(1),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    free = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW + timedelta(milliseconds=100),
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert paid.assignment_id is not None and paid.lease_epoch is not None
    assert free.assignment_id is not None and free.lease_epoch is not None
    assert paid.lease_epoch == free.lease_epoch

    paid_recovery = subject.recover(
        _recovery(
            request_id="recover-paid-sibling",
            assignment_id=paid.assignment_id,
            expected_epoch=paid.lease_epoch,
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )
    free_recovery = subject.recover(
        _recovery(
            request_id="recover-free-sibling",
            assignment_id=free.assignment_id,
            expected_epoch=free.lease_epoch,
            snapshots=_snapshots()[:2],
        ),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=20),
        lease_seconds=30,
        retry_policy=RetryPolicy(),
        plan_only=False,
        owner_health=dead,
    )

    assert paid_recovery.decision == "retry-scheduled"
    assert free_recovery.decision == "retry-scheduled"
    assert free_recovery.reason != "state-invalid"
    assert free_recovery.lease_epoch == paid_recovery.lease_epoch
    assert subject.snapshot().active_assignment_count == 2
    paid_before_heartbeat = subject.execution_for_job_readonly(request(1).job_id)
    free_before_heartbeat = subject.execution_for_job_readonly(
        request(2, worker_class="free-local").job_id
    )
    assert paid_before_heartbeat is not None
    assert free_before_heartbeat is not None
    assert paid_before_heartbeat.lease_expires_at == NOW + timedelta(seconds=50)
    assert free_before_heartbeat.lease_expires_at == NOW + timedelta(seconds=50)

    heartbeat = subject.heartbeat(
        owner=owner(2),
        epoch=free_recovery.lease_epoch,
        as_of=NOW + timedelta(seconds=21),
        lease_seconds=30,
    )
    paid_execution = subject.execution_for_job_readonly(request(1).job_id)
    free_execution = subject.execution_for_job_readonly(
        request(2, worker_class="free-local").job_id
    )

    assert heartbeat.decision == "heartbeat"
    assert paid_execution is not None
    assert free_execution is not None
    assert paid_execution.lease_epoch == free_execution.lease_epoch
    assert paid_execution.lease_expires_at == NOW + timedelta(seconds=51)
    assert free_execution.lease_expires_at == NOW + timedelta(seconds=51)
