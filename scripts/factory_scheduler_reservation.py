from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from scripts.factory_budget_ledger import (
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
)
from scripts.factory_scheduler_models import AssignmentRequest


class ReservationHandoffError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@contextmanager
def budget_reservation_handoff(
    project_root: Path,
    request: AssignmentRequest,
) -> Generator[bool | None, None, None]:
    try:
        with FactoryBudgetLedger.reservation_for_scheduler_handoff(
            project_root,
            request.job_id,
        ) as reservation:
            if reservation is None:
                yield False
                return
            yield (
                reservation.reservation_id == request.reservation_id
                and reservation.state == "dispatching"
            )
    except FactoryBudgetLedgerError as exc:
        raise ReservationHandoffError(exc.code) from exc
