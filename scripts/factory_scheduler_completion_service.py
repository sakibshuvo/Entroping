from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path

from scripts.factory_scheduler_completion_transaction import (
    complete_assignment as complete_assignment,
)
from scripts.factory_scheduler_models import LeaseOwner, StoredAssignment
from scripts.factory_scheduler_queries import read_assignment_by_id
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState
from scripts.factory_scheduler_storage import readonly_connection, writable_connection
from scripts.factory_scheduler_validation import scheduler_timestamp

type SettlementAuthorityGuard = Callable[
    [StoredAssignment], AbstractContextManager[SettlementAuthorityState]
]


def complete_scheduler_assignment(
    project_root: Path,
    *,
    assignment_id: str,
    owner: LeaseOwner,
    epoch: int,
    expected_phase_version: int,
    completed_at: datetime,
    settlement_guard: SettlementAuthorityGuard,
) -> None:
    with readonly_connection(project_root) as connection:
        assignment = read_assignment_by_id(connection, assignment_id=assignment_id)
    if assignment is None:
        raise ValueError("scheduler assignment not found")
    with settlement_guard(assignment) as authority:
        if assignment.request.worker_class == "paid" and authority != "settled":
            raise ValueError("paid assignment settlement authority is not settled")
        if assignment.request.worker_class == "free-local" and authority != "not-required":
            raise ValueError("free assignment settlement authority is invalid")
        with writable_connection(
            project_root,
            initialized_at=scheduler_timestamp(completed_at),
        ) as connection:
            complete_assignment(
                connection,
                assignment_id=assignment_id,
                owner=owner,
                epoch=epoch,
                expected_phase_version=expected_phase_version,
                completed_at=completed_at,
            )
