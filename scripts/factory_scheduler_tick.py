from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_scheduler_assignment_transaction import replay_assignment
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
    SchedulerLimits,
)
from scripts.factory_scheduler_receipts import blocked_state_receipt, request_digest
from scripts.factory_scheduler_storage import (
    database_exists,
    readonly_connection,
    writable_connection,
)
from scripts.factory_scheduler_storage_fs import SchedulerStateError, is_busy
from scripts.factory_scheduler_transactions import plan_or_assign
from scripts.factory_scheduler_validation import scheduler_timestamp

type HealthCheck = Callable[[LeaseOwner], bool | None]


def immutable_request_decision(
    project_root: Path,
    request: AssignmentRequest,
    observed_at: datetime,
) -> DecisionReceipt | None:
    try:
        if not database_exists(project_root):
            return None
        with readonly_connection(project_root) as connection:
            return replay_assignment(
                connection,
                request=request,
                request_digest_value=request_digest(request),
            )
    except SchedulerStateError as exc:
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason=exc.code,
        )
    except sqlite3.OperationalError as exc:
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason="state-busy" if is_busy(exc) else "state-invalid",
        )
    except (sqlite3.DatabaseError, ValidationError, ValueError, TypeError):
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason="state-invalid",
        )


def tick_state(
    project_root: Path,
    limits: SchedulerLimits,
    *,
    request: AssignmentRequest | None,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    plan_only: bool,
    health: HealthCheck,
) -> DecisionReceipt:
    initialization_time = datetime.now(UTC) if as_of is None else as_of
    try:
        if plan_only:
            if not database_exists(project_root):
                return plan_or_assign(
                    None,
                    request=request,
                    owner=owner,
                    as_of=as_of,
                    lease_seconds=lease_seconds,
                    limits=limits,
                    plan_only=True,
                    owner_health=health,
                )
            with readonly_connection(project_root) as connection:
                return plan_or_assign(
                    connection,
                    request=request,
                    owner=owner,
                    as_of=as_of,
                    lease_seconds=lease_seconds,
                    limits=limits,
                    plan_only=True,
                    owner_health=health,
                )
        with writable_connection(
            project_root,
            initialized_at=scheduler_timestamp(initialization_time),
        ) as connection:
            return plan_or_assign(
                connection,
                request=request,
                owner=owner,
                as_of=as_of,
                lease_seconds=lease_seconds,
                limits=limits,
                plan_only=False,
                owner_health=health,
            )
    except SchedulerStateError as exc:
        return blocked_state_receipt(
            request=request,
            observed_at=initialization_time,
            reason=exc.code,
        )
    except sqlite3.OperationalError as exc:
        return blocked_state_receipt(
            request=request,
            observed_at=initialization_time,
            reason="state-busy" if is_busy(exc) else "state-invalid",
        )
    except (sqlite3.DatabaseError, ValidationError, ValueError, TypeError):
        return blocked_state_receipt(
            request=request,
            observed_at=initialization_time,
            reason="state-invalid",
        )
