from __future__ import annotations

import sys
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    PriceTerm,
    UsageEnvelope,
)
from scripts.factory_scheduler import FactoryScheduler  # noqa: E402
from scripts.factory_scheduler_execution_models import ExecutionPhase  # noqa: E402
from scripts.factory_scheduler_models import (  # noqa: E402
    AssignmentRequest,
    LeaseOwner,
)

NOW = datetime(2026, 7, 29, 22, 30, tzinfo=UTC)


def process_token(index: int) -> str:
    return f"proc_{index:064x}"


def owner(index: int) -> LeaseOwner:
    return LeaseOwner(
        owner_id=f"tick-owner-{index}",
        pid=10_000 + index,
        process_start_token=process_token(index),
    )


def request(
    index: int = 1,
    *,
    worker_class: str = "paid",
    access_mode: str = "read-only",
    issue_number: int = 1569,
    worktree_id: str = f"wt_{'1' * 64}",
) -> AssignmentRequest:
    return AssignmentRequest.model_validate(
        {
            "request_id": f"request-{index}",
            "job_id": f"review-20260729-job-{index}",
            "issue_number": issue_number,
            "worktree_id": worktree_id,
            "worker_class": worker_class,
            "access_mode": access_mode,
            "reservation_id": f"res-{index:032x}" if worker_class == "paid" else None,
        },
        strict=True,
    )


def dead(_owner: LeaseOwner) -> bool:
    return False


def prepare_completion(
    subject: FactoryScheduler,
    *,
    assignment_id: str | None,
    lease_owner: LeaseOwner,
    epoch: int | None,
    completed_at: datetime,
) -> int:
    if assignment_id is None or epoch is None:
        raise AssertionError("assignment evidence is incomplete")
    interval = timedelta(microseconds=1)
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
            assignment_id=assignment_id,
            owner=lease_owner,
            epoch=epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=completed_at - (interval * (4 - version)),
            evidence_digest=f"{version:x}" * 64,
        )
    return 4


def complete_free_assignment(
    subject: FactoryScheduler,
    *,
    assignment_id: str | None,
    lease_owner: LeaseOwner,
    epoch: int | None,
    completed_at: datetime,
) -> None:
    phase_version = prepare_completion(
        subject,
        assignment_id=assignment_id,
        lease_owner=lease_owner,
        epoch=epoch,
        completed_at=completed_at,
    )
    subject.complete_assignment(
        assignment_id=assignment_id,
        owner=lease_owner,
        epoch=epoch,
        expected_phase_version=phase_version,
        completed_at=completed_at,
    )


def scheduler(tmp_path: Path) -> FactoryScheduler:
    return FactoryScheduler(
        tmp_path,
        reservation_guard=lambda _request: nullcontext(True),
        settlement_authority=lambda assignment: (
            "not-required" if assignment.request.worker_class == "free-local" else "dispatching"
        ),
    )


def paid_request_with_reservation(
    tmp_path: Path,
) -> tuple[FactoryBudgetLedger, AssignmentRequest]:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    _ = ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(2026, 7, 1),
            cash_cap_microcents=100,
            emergency_reserve_microcents=20,
            currency="USD",
            policy_id="monthly-budget",
            policy_revision=1,
            reserve_idempotency_key="period-reserve-2026-07",
        )
    )
    reservation = ledger.reserve_for_dispatch(
        CostReservationRequest(
            idempotency_key="reserve-scheduler-job-1",
            job_id=request().job_id,
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
                    snapshot_id="test-price-v1",
                    unit="request",
                    quantity=1,
                    price_microcents=60,
                    observed_at=NOW - timedelta(minutes=1),
                    expires_at=NOW + timedelta(minutes=1),
                ),
            ),
        )
    )
    scheduler_request = AssignmentRequest.model_validate(
        {
            **request().model_dump(mode="json"),
            "reservation_id": reservation.reservation_id,
        },
        strict=True,
    )
    return ledger, scheduler_request
