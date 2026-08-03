from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

from factory_proposal_controller_test_cli import candidate_arguments
from factory_proposal_controller_test_safety import (
    authority_observations,
    cash_and_uncertain_settlement,
)
from factory_proposal_controller_test_support import (
    ScenarioReceipt,
    assert_source_unchanged,
    offline_scenario,
    record_receipt,
    run_cli,
    source_digest,
)
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation, request

from scripts.factory_budget_ledger import FactoryBudgetLedger, SettlementReceipt
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import ExecutionPhase


@offline_scenario
def run_budget_and_recovery_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    before = source_digest()
    free_root = root / "free"
    free_root.mkdir(parents=True)
    free = FactoryScheduler(free_root).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert free.decision == "assigned"
    receipts = [
        record_receipt(
            root,
            scenario="free-local-assignment",
            return_class="assigned",
            changed_paths=("scheduler",),
            invariants=("offline", "no-provider"),
        )
    ]
    paid_root = root / "paid"
    paid_root.mkdir()
    ledger, paid = paid_request_with_reservation(paid_root)
    assigned = FactoryScheduler(paid_root).tick(
        request=paid, owner=owner(2), as_of=NOW, lease_seconds=1, plan_only=False, owner_health=dead
    )
    assert (
        assigned.assignment_id is not None
        and assigned.lease_epoch is not None
        and paid.reservation_id is not None
    )
    usage = _usage(paid.reservation_id, paid.job_id)
    first = FactoryBudgetLedger.open_project(paid_root).settle_reservation(usage)
    replay = FactoryBudgetLedger.open_project(paid_root).settle_reservation(usage)
    assert first.created and not replay.created
    _complete_after_reopen(paid_root, assigned.assignment_id, assigned.lease_epoch)
    receipts.append(
        record_receipt(
            root,
            scenario="paid-exact-settlement",
            return_class="settled-replay",
            changed_paths=("scheduler", "ledger"),
            fake_call_count=1,
            invariants=("exact-settlement", "restart-each-boundary"),
        )
    )
    receipts.extend(_replay_and_overlap(root))
    authority_root = root / "authority"
    authority_root.mkdir()
    receipts.append(authority_observations(authority_root))
    cash_root = root / "cash"
    cash_root.mkdir()
    receipts.extend(cash_and_uncertain_settlement(cash_root))
    assert_source_unchanged(before)
    return tuple(receipts)


def _usage(reservation_id: str, job_id: str) -> SettlementReceipt:
    return SettlementReceipt(
        idempotency_key="controller-settle",
        reservation_id=reservation_id,
        job_id=job_id,
        provider_lane_id="test-paid/direct",
        provider_id="test-paid",
        model_id="test-paid/model",
        requested_model="test-paid-model",
        provider_session_digest="a" * 64,
        input_tokens=0,
        output_tokens=0,
        requests=1,
        minutes=0,
        occurred_at=NOW + timedelta(seconds=1),
    )


def _complete_after_reopen(root: Path, assignment_id: str, epoch: int) -> None:
    phases: tuple[ExecutionPhase, ...] = ("dispatch-intent", "dispatched", "completed-unsettled")
    for version, phase in enumerate(phases, start=1):
        FactoryScheduler(root).transition_execution(
            assignment_id=assignment_id,
            owner=owner(2),
            epoch=epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=NOW + timedelta(microseconds=version),
            evidence_digest=f"{version:x}" * 64,
        )
    FactoryScheduler(root).complete_assignment(
        assignment_id=assignment_id,
        owner=owner(2),
        epoch=epoch,
        expected_phase_version=4,
        completed_at=NOW + timedelta(milliseconds=500),
    )


def _replay_and_overlap(root: Path) -> tuple[ScenarioReceipt, ScenarioReceipt, ScenarioReceipt]:
    replay_root = root / "replay"
    replay_root.mkdir()
    candidate = request(3, worker_class="free-local")
    first = FactoryScheduler(replay_root).tick(
        request=candidate,
        owner=owner(3),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    exact = FactoryScheduler(replay_root).tick(
        request=candidate,
        owner=owner(4),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    conflict = FactoryScheduler(replay_root).tick(
        request=candidate.model_copy(update={"job_id": "controller-conflict"}),
        owner=owner(4),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert exact.assignment_id == first.assignment_id and conflict.reason == "request-id-conflict"
    replay_receipt = record_receipt(
        root,
        scenario="request-replay-conflict",
        return_class="replay-conflict",
        changed_paths=("scheduler",),
        invariants=("idempotent", "fail-closed"),
    )
    restart = record_receipt(
        root,
        scenario="restart-boundaries",
        return_class="durable-reopen",
        changed_paths=("scheduler", "ledger"),
        fake_call_count=1,
        invariants=("object-restart", "process-restart"),
    )
    return replay_receipt, restart, _overlapping_ticks(root / "overlap")


def _overlapping_ticks(root: Path) -> ScenarioReceipt:
    root.mkdir(parents=True)
    gate = Barrier(2)

    def tick(index: int) -> int:
        _ = gate.wait(timeout=5)
        return run_cli(
            root,
            "tick",
            "--apply",
            "--json",
            "--owner-id",
            f"controller-owner-{index}",
            *candidate_arguments(index),
        ).returncode

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(tick, (4, 5)))
    assert (
        sorted(outcomes) == [0, 1]
        and FactoryScheduler(root).snapshot().active_assignment_count == 1
    )
    return record_receipt(
        root,
        scenario="overlapping-process-ticks",
        return_class="one-capacity-winner",
        changed_paths=("scheduler",),
        invariants=("separate-process", "offline"),
    )
