from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier

from factory_proposal_controller_test_receipts import PendingReceipt
from factory_proposal_controller_test_restart import (
    DurableControllerState,
    LedgerTransition,
    SchedulerCompletion,
    SchedulerTransition,
    child_complete,
    child_ledger_transition,
    child_state,
    child_transition,
)
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    compose_counted_worker,
    offline_scenario,
)
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation

from scripts.factory_budget_ledger import FactoryBudgetLedger, SettlementReceipt
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
def paid_exact_settlement(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "paid-exact-settlement")
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    _assert_state(child_state(root, paid.job_id), None, None, "dispatching", 60, 0, None, None)
    assigned = FactoryScheduler(root).tick(
        request=paid,
        owner=owner(2),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.decision == "assigned" and assigned.assignment_id is not None
    compose_counted_worker(observed, assigned.decision, assigned.assignment_id)
    first = FactoryBudgetLedger.open_project(root).settle_reservation(
        _usage(paid.reservation_id, paid.job_id)
    )
    replay = FactoryBudgetLedger.open_project(root).settle_reservation(
        _usage(paid.reservation_id, paid.job_id)
    )
    reopened = FactoryBudgetLedger.open_project(root)
    reservation = reopened.reservation_for_job(paid.job_id)
    assert first.created and not replay.created and first.actual_microcents == 60
    assert reservation is not None and reservation.actual_microcents == 60
    assert _terminal_events(reopened, paid.reservation_id) == 1
    _assert_state(
        child_state(root, paid.job_id), "never-dispatched", 1, "settled", 0, 60, None, "active"
    )
    return observed.receipt(return_class="settled-replay")


@offline_scenario
def restart_boundaries(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "restart-boundaries")
    _, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    _assert_state(child_state(root, paid.job_id), None, None, "dispatching", 60, 0, None, None)
    scheduler_owner = owner(8)
    assigned = FactoryScheduler(root).tick(
        request=paid,
        owner=scheduler_owner,
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    compose_counted_worker(observed, assigned.decision, assigned.assignment_id)
    _assert_state(
        child_state(root, paid.job_id), "never-dispatched", 1, "dispatching", 60, 0, None, "active"
    )
    phases: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for expected, phase in enumerate(phases, start=1):
        reconstructed = child_transition(
            root,
            SchedulerTransition(
                paid.job_id,
                assigned.assignment_id,
                scheduler_owner,
                assigned.lease_epoch,
                expected,
                phase,
                NOW + timedelta(microseconds=expected),
                f"{expected:x}" * 64,
            ),
        )
        _assert_state(reconstructed, phase, expected + 1, "dispatching", 60, 0, None, "active")
    uncertain = child_ledger_transition(
        root,
        LedgerTransition(
            "uncertain",
            paid.job_id,
            paid.reservation_id,
            "restart-uncertain",
            NOW + timedelta(seconds=1),
        ),
    )
    _assert_state(uncertain, "completed-unsettled", 4, "uncertain", 60, 0, None, "active")
    settled = child_ledger_transition(
        root,
        LedgerTransition(
            "settle",
            paid.job_id,
            paid.reservation_id,
            "restart-settle",
            NOW + timedelta(milliseconds=500),
        ),
    )
    _assert_state(settled, "completed-unsettled", 4, "settled", 0, 60, None, "active")
    completed = child_complete(
        root,
        SchedulerCompletion(
            paid.job_id,
            assigned.assignment_id,
            scheduler_owner,
            assigned.lease_epoch,
            4,
            NOW + timedelta(milliseconds=500),
        ),
    )
    _assert_state(completed, "completed", 5, "settled", 0, 60, "completed", "completed")
    return observed.receipt(return_class="settled-replay")


@offline_scenario
def overlapping_settlement_replay(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "paid-overlapping-settlement")
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
    reservation_id = paid.reservation_id
    gate = Barrier(2)

    def settle(_: int) -> bool:
        _ = gate.wait(timeout=5)
        return (
            FactoryBudgetLedger.open_project(root)
            .settle_reservation(_usage(reservation_id, paid.job_id))
            .created
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(settle, (1, 2)))
    balance = ledger.period_summary(date(2026, 7, 1))
    assert sorted(outcomes) == [False, True]
    assert balance.net_spent_microcents == 60 and balance.active_reserved_microcents == 0
    return observed.receipt(return_class="settled-replay")


def _assert_state(
    state: DurableControllerState,
    phase: str | None,
    version: int | None,
    reservation: str,
    held: int,
    spent: int,
    terminal: str | None,
    assignment: str | None,
) -> None:
    assert state == DurableControllerState(
        assignment,
        None,
        phase,
        version,
        reservation,
        held,
        spent,
        terminal,
    )


def _terminal_events(ledger: FactoryBudgetLedger, reservation_id: str) -> int:
    with sqlite3.connect(ledger.db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM cost_reservation_events "
            "WHERE reservation_id = (SELECT id FROM cost_reservations WHERE public_id = ?) "
            "AND resulting_state IN ('settled', 'reconciled')",
            (reservation_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])
