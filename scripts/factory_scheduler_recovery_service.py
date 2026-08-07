from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path

from scripts.factory_retry_policy import RetryPolicy
from scripts.factory_scheduler_execution_models import RecoveryReceipt, RecoveryRequest
from scripts.factory_scheduler_models import LeaseOwner, StoredAssignment
from scripts.factory_scheduler_queries import read_assignment_by_id
from scripts.factory_scheduler_recovery import HealthCheck, recover_assignment
from scripts.factory_scheduler_recovery_receipts import (
    recovery_request_digest,
    replay_recovery_receipt,
)
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState
from scripts.factory_scheduler_storage import (
    migrate_existing_state,
    readonly_connection,
    writable_connection,
)
from scripts.factory_scheduler_validation import scheduler_timestamp

type SettlementAuthorityCheck = Callable[[StoredAssignment], SettlementAuthorityState]
type SettlementAuthorityGuard = Callable[
    [StoredAssignment], AbstractContextManager[SettlementAuthorityState]
]


def recover_scheduler_assignment(
    project_root: Path,
    *,
    request: RecoveryRequest,
    owner: LeaseOwner,
    as_of: datetime,
    lease_seconds: int,
    retry_policy: RetryPolicy,
    plan_only: bool,
    owner_health: HealthCheck,
    settlement_check: SettlementAuthorityCheck,
    settlement_guard: SettlementAuthorityGuard,
) -> RecoveryReceipt:
    if plan_only:
        with readonly_connection(project_root) as connection:
            assignment = _required_assignment(connection, request.assignment_id)
            authority = settlement_check(assignment)
            return recover_assignment(
                connection,
                request=request,
                owner=owner,
                as_of=as_of,
                lease_seconds=lease_seconds,
                retry_policy=retry_policy,
                owner_health=owner_health,
                plan_only=True,
                settlement_authority=authority,
            )
    migrate_existing_state(project_root, initialized_at=scheduler_timestamp(as_of))
    with readonly_connection(project_root) as connection:
        replay = replay_recovery_receipt(
            connection,
            request_id=request.request_id,
            request_digest=recovery_request_digest(
                request,
                owner=owner,
                lease_seconds=lease_seconds,
                policy=retry_policy,
            ),
        )
        if replay is not None:
            return replay
        assignment = _required_assignment(connection, request.assignment_id)
    with (
        settlement_guard(assignment) as authority,
        writable_connection(
            project_root,
            initialized_at=scheduler_timestamp(as_of),
        ) as connection,
    ):
        return recover_assignment(
            connection,
            request=request,
            owner=owner,
            as_of=as_of,
            lease_seconds=lease_seconds,
            retry_policy=retry_policy,
            owner_health=owner_health,
            plan_only=False,
            settlement_authority=authority,
        )


def _required_assignment(
    connection: sqlite3.Connection,
    assignment_id: str,
) -> StoredAssignment:
    assignment = read_assignment_by_id(connection, assignment_id=assignment_id)
    if assignment is None:
        raise ValueError("scheduler assignment not found")
    return assignment
