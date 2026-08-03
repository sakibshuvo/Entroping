from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from factory_proposal_controller_test_cli import recovery_request, recovery_snapshots
from factory_proposal_controller_test_quota import quota_exhausted_request
from factory_proposal_controller_test_receipts import InvariantClass
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    ScenarioReceipt,
    offline_scenario,
    reopen_in_fresh_child,
)
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation, request

from scripts.factory_budget_ledger import (
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    PriceTerm,
    SettlementOutcome,
    SettlementReceipt,
    UsageEnvelope,
)
from scripts.factory_retry_policy import RecoverySnapshot, RetryPolicy
from scripts.factory_scheduler import FactoryScheduler


@offline_scenario
def authority_observations(root: Path) -> tuple[ScenarioReceipt, ...]:
    cases = (
        ("authority-control", recovery_snapshots(NOW), "retry-scheduled", "retry-scheduled"),
        (
            "authority-stale",
            recovery_snapshots(NOW, expires=0),
            "retry-scheduled",
            "github-snapshot-stale",
        ),
        ("authority-missing", (), "retry-scheduled", "github-snapshot-missing"),
        (
            "authority-future",
            recovery_snapshots(NOW, future=True),
            "retry-scheduled",
            "github-snapshot-future",
        ),
        (
            "authority-conflict",
            _conflicting_snapshots(),
            "retry-scheduled",
            "snapshot-source-duplicate",
        ),
    )
    receipts = []
    for index, (scenario, snapshots, decision, reason) in enumerate(cases, start=1):
        case_root = root / scenario
        observed = ScenarioObservation.begin(case_root, scenario)
        assigned = FactoryScheduler(case_root).tick(
            request=request(index, worker_class="free-local"),
            owner=owner(index),
            as_of=NOW - timedelta(seconds=2),
            lease_seconds=1,
            plan_only=False,
            owner_health=dead,
        )
        assert assigned.assignment_id is not None and assigned.lease_epoch is not None
        recovered = FactoryScheduler(case_root).recover(
            recovery_request(assigned.assignment_id, assigned.lease_epoch, snapshots, scenario),
            owner=owner(20 + index),
            as_of=NOW,
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=dead,
        )
        assert recovered.decision == decision and recovered.reason == reason, (
            scenario,
            recovered.decision,
            recovered.reason,
        )
        checks: dict[InvariantClass, bool] = (
            {"durable-reopen": recovered.decision == "retry-scheduled"}
            if reason == "retry-scheduled"
            else {"authority-fail-closed": recovered.decision == "retry-scheduled"}
        )
        receipts.append(
            observed.receipt(
                return_class="retry-scheduled" if decision == "retry-scheduled" else "blocked",
                checks={**checks, "offline": True, "no-source-mutation": True},
            )
        )
    return tuple(receipts)


def _conflicting_snapshots() -> tuple[RecoverySnapshot, ...]:
    snapshots = recovery_snapshots(NOW)
    return (snapshots[0], snapshots[0], snapshots[2], snapshots[3])


@offline_scenario
def cash_and_quota_exhaustion(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "cash-quota-exhaustion")
    ledger, _ = paid_request_with_reservation(root)
    try:
        ledger.reserve_for_dispatch(_exhausted_request())
    except FactoryBudgetLedgerError as exc:
        assert exc.code == "budget"
    else:
        raise AssertionError("cash exhaustion admitted a fake worker")
    quota_root = root / "quota"
    quota_root.mkdir()
    quota_ledger = FactoryBudgetLedger.open_project(quota_root)
    quota_ledger.initialize_period(
        BudgetPeriodConfig(date(2026, 7, 1), 1_000, 20, "USD", "factory-policy", 3, "quota-period")
    )
    try:
        quota_ledger.authorize_dispatch(quota_exhausted_request())
    except FactoryBudgetLedgerError as exc:
        assert exc.code == "quota"
    else:
        raise AssertionError("quota exhaustion admitted a fake worker")
    assert observed.worker.call_count == 0
    return observed.receipt(
        return_class="blocked",
        checks={
            "no-worker": observed.worker.call_count == 0,
            "offline": True,
            "no-source-mutation": True,
        },
    )


@offline_scenario
def uncertain_settlement_cases(root: Path) -> tuple[ScenarioReceipt, ...]:
    outcomes = []
    for index, kind in enumerate(
        ("missing", "malformed", "mismatched", "duplicate", "ambiguous"), start=1
    ):
        case_root = root / kind
        observed = ScenarioObservation.begin(case_root, f"uncertain-{kind}")
        ledger, paid = paid_request_with_reservation(case_root)
        assert paid.reservation_id is not None
        outcome = _make_uncertain(ledger, paid.reservation_id, paid.job_id, kind, index)
        reopen_in_fresh_child(case_root, "ledger")
        reopened = FactoryBudgetLedger.open_project(case_root)
        held = reopened.period_summary(date(2026, 7, 1))
        reservation = reopened.reservation_for_job(paid.job_id)
        try:
            reopened.reserve_for_dispatch(_exhausted_request())
        except FactoryBudgetLedgerError as exc:
            assert exc.code == "budget"
        else:
            raise AssertionError("uncertain reservation reopened paid capacity")
        assert (
            outcome.state == "uncertain"
            and reservation is not None
            and reservation.state == "uncertain"
        )
        assert held.active_reserved_microcents == 60 and held.net_spent_microcents == 0
        outcomes.append(
            observed.receipt(
                return_class="uncertain",
                checks={
                    "settlement-hold-retained": True,
                    "offline": True,
                    "no-source-mutation": True,
                },
            )
        )
    return tuple(outcomes)


def _make_uncertain(
    ledger: FactoryBudgetLedger,
    reservation_id: str,
    job_id: str,
    kind: str,
    index: int,
) -> SettlementOutcome:
    if kind == "missing":
        return ledger.mark_reservation_uncertain(
            reservation_id,
            idempotency_key=f"missing-{index}",
            reason="partial_receipt",
            occurred_at=NOW + timedelta(seconds=1),
            evidence_digest="b" * 64,
        )
    if kind == "duplicate":
        first = ledger.mark_reservation_uncertain(
            reservation_id,
            idempotency_key=f"duplicate-{index}",
            reason="partial_receipt",
            occurred_at=NOW + timedelta(seconds=1),
            evidence_digest="b" * 64,
        )
        replay = ledger.mark_reservation_uncertain(
            reservation_id,
            idempotency_key=f"duplicate-{index}",
            reason="partial_receipt",
            occurred_at=NOW + timedelta(seconds=1),
            evidence_digest="b" * 64,
        )
        assert first.created and not replay.created
        return replay
    receipt = SettlementReceipt(
        f"uncertain-{kind}-{index}",
        reservation_id,
        job_id if kind != "mismatched" else "wrong-job",
        "test-paid/direct",
        "test-paid",
        "test-paid/model",
        "test-paid-model",
        "c" * (63 if kind == "malformed" else 64),
        0,
        0,
        2 if kind == "ambiguous" else 1,
        0,
        NOW + timedelta(seconds=2),
    )
    return ledger.settle_reservation(receipt)


def _exhausted_request() -> CostReservationRequest:
    return CostReservationRequest(
        "controller-exhausted",
        "controller-exhausted",
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
                "controller-price",
                "request",
                1,
                60,
                NOW - timedelta(seconds=1),
                NOW + timedelta(seconds=1),
            ),
        ),
    )


def cash_and_uncertain_settlement(root: Path) -> tuple[ScenarioReceipt, ...]:
    return (
        cash_and_quota_exhaustion(root / "cash"),
        *uncertain_settlement_cases(root / "uncertain"),
    )
