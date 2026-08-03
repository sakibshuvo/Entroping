from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

from factory_proposal_controller_test_cli import candidate_arguments
from factory_proposal_controller_test_receipt_contracts import CompositionOutcome, ScenarioReceipt
from factory_proposal_controller_test_receipts import PendingReceipt
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    compose_counted_worker,
    offline_scenario,
    run_cli,
)
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation, request

from scripts.factory_budget_ledger import (
    CostReservationRequest,
    FactoryBudgetLedgerError,
    PriceTerm,
    UsageEnvelope,
)
from scripts.factory_scheduler import FactoryScheduler


@offline_scenario
def free_local_assignment(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "free-local-assignment")
    assigned = FactoryScheduler(root).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.decision == "assigned" and assigned.assignment_id is not None
    compose_counted_worker(observed, CompositionOutcome.accepted(assigned.assignment_id))
    assert FactoryScheduler(root).snapshot().active_assignment_count == 1
    return observed.receipt(return_class="assigned")


@offline_scenario
def replay_and_conflict(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "request-replay-conflict")
    first_request = request(3, worker_class="free-local")
    first = FactoryScheduler(root).tick(
        request=first_request,
        owner=owner(3),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    replay = FactoryScheduler(root).tick(
        request=first_request,
        owner=owner(4),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    ledger, paid = paid_request_with_reservation(root)
    conflict_request = CostReservationRequest(
        "controller-distinct-request",
        paid.job_id,
        "test-paid/direct",
        "test-paid",
        "test-paid/model",
        "test-paid-model",
        "test-paid-lane",
        "monthly-budget",
        1,
        NOW,
        UsageEnvelope(requests=1),
        (
            PriceTerm(
                "controller-conflict-price",
                "request",
                1,
                60,
                NOW - timedelta(seconds=1),
                NOW + timedelta(seconds=1),
            ),
        ),
    )
    try:
        ledger.reserve_for_dispatch(conflict_request)
    except FactoryBudgetLedgerError as exc:
        assert exc.code == "job" and str(exc) == "job: job already has a cost reservation"
    else:
        raise AssertionError("same job with distinct request was admitted")
    assert first.assignment_id == replay.assignment_id and replay.reason == "exact-replay"
    assert ledger.reservation_for_job(paid.job_id) is not None
    return observed.receipt(return_class="replay-conflict")


@offline_scenario
def overlapping_ticks(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "overlapping-process-ticks")
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
    return observed.receipt(return_class="one-capacity-winner")


def run_budget_and_recovery_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    from factory_proposal_controller_test_settlement import (
        overlapping_settlement_replay,
        paid_exact_settlement,
        restart_boundaries,
    )

    return (
        free_local_assignment(root / "free"),
        paid_exact_settlement(root / "paid"),
        replay_and_conflict(root / "replay"),
        restart_boundaries(root / "restart"),
        overlapping_ticks(root / "overlap"),
        overlapping_settlement_replay(root / "overlap-settlement"),
    )
