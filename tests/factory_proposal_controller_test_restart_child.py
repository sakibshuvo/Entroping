from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from pydantic import TypeAdapter

from scripts.factory_budget_ledger import FactoryBudgetLedger, SettlementReceipt
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import ExecutionPhase
from scripts.factory_scheduler_models import LeaseOwner


def state(root: Path, job_id: str) -> dict[str, object]:
    scheduler = FactoryScheduler(root)
    assignment = scheduler.assignment_for_job_readonly(job_id)
    execution = scheduler.execution_for_job_readonly(job_id)
    ledger = FactoryBudgetLedger.open_project(root)
    reservation = ledger.reservation_for_job(job_id)
    balance = ledger.period_summary(date(2026, 7, 1))
    return {
        "assignment_state": None if assignment is None else assignment.state,
        "authorization_id": None if assignment is None else assignment.request.authorization_id,
        "phase": None if execution is None else execution.phase,
        "phase_version": None if execution is None else execution.phase_version,
        "reservation_state": None if reservation is None else reservation.state,
        "held_microcents": balance.active_reserved_microcents,
        "spent_microcents": balance.net_spent_microcents,
        "terminal_outcome": None if execution is None else execution.terminal_outcome,
    }


def main(arguments: list[str]) -> None:
    operation, job_id, *values = arguments
    root = Path.cwd()
    scheduler = FactoryScheduler(root)
    if operation == "transition":
        assignment_id, owner_json, epoch, version, phase, observed_at, evidence = values
        scheduler.transition_execution(
            assignment_id=assignment_id,
            owner=LeaseOwner.model_validate_json(owner_json, strict=True),
            epoch=int(epoch),
            expected_phase_version=int(version),
            target_phase=TypeAdapter(ExecutionPhase).validate_python(phase, strict=True),
            observed_at=datetime.fromisoformat(observed_at),
            evidence_digest=evidence,
        )
    elif operation == "complete":
        assignment_id, owner_json, epoch, version, completed_at = values
        scheduler.complete_assignment(
            assignment_id=assignment_id,
            owner=LeaseOwner.model_validate_json(owner_json, strict=True),
            epoch=int(epoch),
            expected_phase_version=int(version),
            completed_at=datetime.fromisoformat(completed_at),
        )
    elif operation == "uncertain":
        reservation_id, key, occurred_at = values
        FactoryBudgetLedger.open_project(root).mark_reservation_uncertain(
            reservation_id,
            idempotency_key=key,
            reason="partial_receipt",
            occurred_at=datetime.fromisoformat(occurred_at),
            evidence_digest="b" * 64,
        )
    elif operation == "settle":
        reservation_id, key, occurred_at = values
        FactoryBudgetLedger.open_project(root).settle_reservation(
            SettlementReceipt(
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
                datetime.fromisoformat(occurred_at),
            )
        )
    elif operation != "state":
        raise AssertionError("unsupported child operation")
    print(json.dumps(state(root, job_id), sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
