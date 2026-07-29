from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .factory_budget_ledger import FactoryBudgetLedger, FactoryBudgetLedgerError
from .factory_budget_reservation_validation import canonical_digest
from .factory_paid_dispatch_reservation import PaidDispatchError


@dataclass(frozen=True, slots=True)
class PaidDispatchRecovery:
    reservation_id: str
    queue_state: Literal["completed", "failed"]
    settlement_state: Literal["settled", "unresolved"]
    actual_microcents: int | None

    def job_projection(self) -> dict[str, object]:
        projection: dict[str, object] = {
            "reservation_id": self.reservation_id,
            "settlement_state": self.settlement_state,
        }
        if self.actual_microcents is not None:
            projection["actual_microcents"] = self.actual_microcents
        return projection


def recover_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    occurred_at: datetime,
) -> PaidDispatchRecovery | None:
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return None
    try:
        reservation = FactoryBudgetLedger.reservation_for_job_readonly(
            project_root,
            job_id,
        )
    except FactoryBudgetLedgerError as exc:
        if exc.code == "missing":
            return None
        raise PaidDispatchError("ledger", exc.detail) from exc
    if reservation is None:
        return None
    if reservation.state in {"settled", "reconciled"}:
        return PaidDispatchRecovery(
            reservation_id=reservation.reservation_id,
            queue_state="completed",
            settlement_state="settled",
            actual_microcents=reservation.actual_microcents,
        )
    if reservation.state == "dispatching":
        evidence = canonical_digest(
            {
                "job_id": job_id,
                "started_at": job.get("started_at"),
                "updated_at": job.get("updated_at"),
            }
        )
        try:
            uncertain = FactoryBudgetLedger.open_project(
                project_root
            ).mark_reservation_uncertain(
                reservation.reservation_id,
                idempotency_key=f"recovery:{job_id}:{evidence[:16]}",
                reason="worker_interrupted",
                occurred_at=occurred_at,
                evidence_digest=evidence,
            )
        except FactoryBudgetLedgerError as exc:
            raise PaidDispatchError("ledger", exc.detail) from exc
        return PaidDispatchRecovery(
            reservation_id=uncertain.reservation_id,
            queue_state="failed",
            settlement_state="unresolved",
            actual_microcents=uncertain.actual_microcents,
        )
    return PaidDispatchRecovery(
        reservation_id=reservation.reservation_id,
        queue_state="failed",
        settlement_state="unresolved",
        actual_microcents=reservation.actual_microcents,
    )
