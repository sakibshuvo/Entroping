from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier

from factory_proposal_controller_test_cli import candidate_arguments
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    ScenarioReceipt,
    offline_scenario,
    reopen_in_fresh_child,
    run_cli,
)
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation, request

from scripts.factory_budget_ledger import (
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    PriceTerm,
    SettlementReceipt,
    UsageEnvelope,
)
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import ExecutionPhase


def _usage(reservation_id: str, job_id: str, key: str = "controller-settle") -> SettlementReceipt:
    return SettlementReceipt(
        key,
        reservation_id,
        job_id,
        "test-paid/direct",
        "test-paid",
        "test-paid/model",
        "test-paid-model",
        "a" * 64,
        0,
        0,
        1,
        0,
        NOW + timedelta(milliseconds=500),
    )


@offline_scenario
def free_local_assignment(root: Path) -> ScenarioReceipt:
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
    observed.worker.dispatch(assigned.assignment_id)
    assert FactoryScheduler(root).snapshot().active_assignment_count == 1
    return observed.receipt(
        return_class="assigned",
        checks={"offline": True, "no-provider": True, "no-source-mutation": True},
    )


@offline_scenario
def paid_exact_settlement(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "paid-exact-settlement")
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    reopen_in_fresh_child(root, "ledger")
    assigned = FactoryScheduler(root).tick(
        request=paid,
        owner=owner(2),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.decision == "assigned" and assigned.assignment_id is not None
    observed.worker.dispatch(assigned.assignment_id)
    first = FactoryBudgetLedger.open_project(root).settle_reservation(
        _usage(paid.reservation_id, paid.job_id)
    )
    replay = FactoryBudgetLedger.open_project(root).settle_reservation(
        _usage(paid.reservation_id, paid.job_id)
    )
    reopened = FactoryBudgetLedger.open_project(root)
    balance = reopened.period_summary(date(2026, 7, 1))
    reservation = reopened.reservation_for_job(paid.job_id)
    assert first.created and not replay.created and first.actual_microcents == 60
    assert (
        reservation is not None
        and reservation.state == "settled"
        and reservation.actual_microcents == 60
    )
    assert (
        balance.net_spent_microcents == 60
        and balance.active_reserved_microcents == 0
        and _terminal_events(reopened, paid.reservation_id) == 1
    )
    reopen_in_fresh_child(root, "ledger")
    return observed.receipt(
        return_class="settled-replay",
        checks={
            "exact-settlement": True,
            "replay-safe": True,
            "offline": True,
            "no-source-mutation": True,
        },
    )


@offline_scenario
def restart_boundaries(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "restart-boundaries")
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    reopen_in_fresh_child(root, "ledger")
    assigned = FactoryScheduler(root).tick(
        request=paid,
        owner=owner(8),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    observed.worker.dispatch(assigned.assignment_id)
    reopen_in_fresh_child(root, "scheduler")
    phases: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for version, phase in enumerate(phases, start=1):
        FactoryScheduler(root).transition_execution(
            assignment_id=assigned.assignment_id,
            owner=owner(8),
            epoch=assigned.lease_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=NOW + timedelta(microseconds=version),
            evidence_digest=f"{version:x}" * 64,
        )
        reopen_in_fresh_child(root, "scheduler")
    uncertain = FactoryBudgetLedger.open_project(root).mark_reservation_uncertain(
        paid.reservation_id,
        idempotency_key="restart-uncertain",
        reason="partial_receipt",
        occurred_at=NOW + timedelta(seconds=1),
        evidence_digest="b" * 64,
    )
    assert uncertain.state == "uncertain"
    reopen_in_fresh_child(root, "ledger")
    settled = FactoryBudgetLedger.open_project(root).settle_reservation(
        _usage(paid.reservation_id, paid.job_id, "restart-settle")
    )
    assert settled.state == "settled"
    reopen_in_fresh_child(root, "ledger")
    FactoryScheduler(root).complete_assignment(
        assignment_id=assigned.assignment_id,
        owner=owner(8),
        epoch=assigned.lease_epoch,
        expected_phase_version=4,
        completed_at=NOW + timedelta(milliseconds=500),
    )
    reopen_in_fresh_child(root, "scheduler")
    return observed.receipt(
        return_class="settled-replay",
        checks={
            "restart-each-boundary": True,
            "durable-reopen": True,
            "offline": True,
            "no-source-mutation": True,
        },
    )


@offline_scenario
def replay_and_conflict(root: Path) -> ScenarioReceipt:
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
    return observed.receipt(
        return_class="replay-conflict",
        checks={
            "replay-safe": True,
            "fail-closed": True,
            "offline": True,
            "no-source-mutation": True,
        },
    )


@offline_scenario
def overlapping_ticks(root: Path) -> ScenarioReceipt:
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
    return observed.receipt(
        return_class="one-capacity-winner",
        checks={"one-capacity-winner": True, "offline": True, "no-source-mutation": True},
    )


@offline_scenario
def overlapping_settlement_replay(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "paid-overlapping-settlement")
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    reservation_id = paid.reservation_id
    gate = Barrier(2)

    def settle(index: int) -> bool:
        _ = gate.wait(timeout=5)
        return (
            FactoryBudgetLedger.open_project(root)
            .settle_reservation(_usage(reservation_id, paid.job_id))
            .created
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(settle, (1, 2)))
    balance = ledger.period_summary(date(2026, 7, 1))
    assert (
        sorted(outcomes) == [False, True]
        and balance.net_spent_microcents == 60
        and balance.active_reserved_microcents == 0
    )
    return observed.receipt(
        return_class="settled-replay",
        checks={
            "exact-settlement": True,
            "replay-safe": True,
            "offline": True,
            "no-source-mutation": True,
        },
    )


def _terminal_events(ledger: FactoryBudgetLedger, reservation_id: str) -> int:
    with sqlite3.connect(ledger.db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM cost_reservation_events "
            "WHERE reservation_id = (SELECT id FROM cost_reservations "
            "WHERE public_id = ?) "
            "AND resulting_state IN ('settled', 'reconciled')",
            (reservation_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def run_budget_and_recovery_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    return (
        free_local_assignment(root / "free"),
        paid_exact_settlement(root / "paid"),
        replay_and_conflict(root / "replay"),
        restart_boundaries(root / "restart"),
        overlapping_ticks(root / "overlap"),
        overlapping_settlement_replay(root / "overlap-settlement"),
    )
