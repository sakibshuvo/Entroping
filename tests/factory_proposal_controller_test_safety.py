from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from factory_proposal_controller_test_cli import recovery_request, recovery_snapshots
from factory_proposal_controller_test_quota import quota_exhausted_request
from factory_proposal_controller_test_support import ScenarioReceipt, record_receipt
from factory_scheduler_test_support import NOW, dead, owner, paid_request_with_reservation, request

from scripts.factory_budget_ledger import (
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    PriceTerm,
    SettlementReceipt,
    UsageEnvelope,
)
from scripts.factory_retry_policy import RetryPolicy
from scripts.factory_scheduler import FactoryScheduler


def authority_observations(root: Path) -> ScenarioReceipt:
    assigned = FactoryScheduler(root).tick(
        request=request(6, worker_class="free-local"),
        owner=owner(6),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    current = NOW + timedelta(seconds=2)
    observations = (
        recovery_snapshots(current, expires=0),
        (),
        recovery_snapshots(current, future=True),
    )
    for index, snapshots in enumerate(observations, start=1):
        receipt = FactoryScheduler(root).recover(
            recovery_request(
                assigned.assignment_id, assigned.lease_epoch, snapshots[:2], f"authority-{index}"
            ),
            owner=owner(7),
            as_of=current,
            lease_seconds=30,
            retry_policy=RetryPolicy(),
            plan_only=False,
            owner_health=(lambda _owner: True) if index == 3 else dead,
        )
        assert receipt.decision in {"blocked", "retry-scheduled"}
    return record_receipt(
        root,
        scenario="authority-observations",
        return_class="fail-closed",
        changed_paths=("scheduler",),
        invariants=("stale", "missing", "future", "conflicting"),
    )


def cash_and_uncertain_settlement(root: Path) -> tuple[ScenarioReceipt, ScenarioReceipt]:
    ledger, paid = paid_request_with_reservation(root)
    assert paid.reservation_id is not None
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
        BudgetPeriodConfig(
            starts_on=date(2026, 7, 1),
            cash_cap_microcents=1_000,
            emergency_reserve_microcents=20,
            currency="USD",
            policy_id="factory-policy",
            policy_revision=3,
            reserve_idempotency_key="quota-period",
        )
    )
    try:
        quota_ledger.authorize_dispatch(quota_exhausted_request())
    except FactoryBudgetLedgerError as exc:
        assert exc.code == "quota"
    else:
        raise AssertionError("quota exhaustion admitted a fake worker")
    uncertain = ledger.mark_reservation_uncertain(
        paid.reservation_id,
        idempotency_key="controller-missing",
        reason="partial_receipt",
        occurred_at=NOW + timedelta(seconds=1),
        evidence_digest="b" * 64,
    )
    assert uncertain.state == "uncertain"
    cash = record_receipt(
        root,
        scenario="cash-quota-exhaustion",
        return_class="cash-blocked",
        changed_paths=("ledger",),
        invariants=("no-worker-before-cash", "no-worker-before-quota"),
    )
    malformed = ledger.settle_reservation(_malformed_receipt(paid.reservation_id, paid.job_id))
    assert malformed.state == "uncertain"
    duplicate = ledger.mark_reservation_uncertain(
        paid.reservation_id,
        idempotency_key="controller-missing",
        reason="partial_receipt",
        occurred_at=NOW + timedelta(seconds=1),
        evidence_digest="b" * 64,
    )
    assert not duplicate.created
    mismatched = ledger.settle_reservation(_mismatched_receipt(paid.reservation_id))
    assert mismatched.state == "uncertain"
    uncertainty = record_receipt(
        root,
        scenario="uncertain-settlement",
        return_class="uncertain",
        changed_paths=("ledger",),
        invariants=("missing", "malformed", "mismatched", "duplicate"),
    )
    return cash, uncertainty


def _exhausted_request() -> CostReservationRequest:
    return CostReservationRequest(
        idempotency_key="controller-exhausted",
        job_id="controller-exhausted",
        provider_lane_id="test-paid/direct",
        provider_id="test-paid",
        model_id="test-paid/model",
        requested_model="test-paid-model",
        cost_policy_lane_id="test-paid-lane",
        policy_id="monthly-budget",
        policy_revision=1,
        occurred_at=NOW,
        usage_envelope=UsageEnvelope(requests=1),
        price_terms=(
            PriceTerm(
                snapshot_id="controller-price",
                unit="request",
                quantity=1,
                price_microcents=60,
                observed_at=NOW - timedelta(seconds=1),
                expires_at=NOW + timedelta(seconds=1),
            ),
        ),
    )


def _malformed_receipt(reservation_id: str, job_id: str) -> SettlementReceipt:
    return SettlementReceipt(
        idempotency_key="controller-malformed",
        reservation_id=reservation_id,
        job_id=job_id,
        provider_lane_id="test-paid/direct",
        provider_id="test-paid",
        model_id="test-paid/model",
        requested_model="test-paid-model",
        provider_session_digest="c" * 63,
        input_tokens=0,
        output_tokens=0,
        requests=1,
        minutes=0,
        occurred_at=NOW + timedelta(seconds=2),
    )


def _mismatched_receipt(reservation_id: str) -> SettlementReceipt:
    return SettlementReceipt(
        idempotency_key="controller-mismatched",
        reservation_id=reservation_id,
        job_id="controller-wrong-job",
        provider_lane_id="test-paid/direct",
        provider_id="test-paid",
        model_id="test-paid/model",
        requested_model="test-paid-model",
        provider_session_digest="c" * 64,
        input_tokens=0,
        output_tokens=0,
        requests=1,
        minutes=0,
        occurred_at=NOW + timedelta(seconds=2),
    )
