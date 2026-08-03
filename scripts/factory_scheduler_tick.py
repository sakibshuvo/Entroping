from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_delivery_admission import _DeliveryAdmission
from scripts.factory_scheduler_assignment import _plan_or_assign_selected, plan_or_assign
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
    if (
        request is not None
        and request.worker_class == "free-local"
        and request.access_mode == "write"
    ):
        return blocked_state_receipt(
            request=request,
            observed_at=initialization_time,
            reason="selection-required",
            authoritative=not plan_only,
        )
    return _tick_state(
        project_root,
        limits,
        request=request,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        plan_only=plan_only,
        health=health,
        delivery_admission=None,
    )


def _tick_selected_state(
    project_root: Path,
    limits: SchedulerLimits,
    *,
    request: AssignmentRequest,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    plan_only: bool,
    health: HealthCheck,
    delivery_admission: _DeliveryAdmission,
) -> DecisionReceipt:
    return _tick_state(
        project_root,
        limits,
        request=request,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        plan_only=plan_only,
        health=health,
        delivery_admission=delivery_admission,
    )


def _tick_state(
    project_root: Path,
    limits: SchedulerLimits,
    *,
    request: AssignmentRequest | None,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    plan_only: bool,
    health: HealthCheck,
    delivery_admission: _DeliveryAdmission | None,
) -> DecisionReceipt:
    initialization_time = datetime.now(UTC) if as_of is None else as_of
    try:
        if plan_only:
            if not database_exists(project_root):
                return _assign(
                    None,
                    project_root=project_root,
                    request=request,
                    owner=owner,
                    as_of=as_of,
                    lease_seconds=lease_seconds,
                    limits=limits,
                    plan_only=True,
                    owner_health=health,
                    delivery_admission=delivery_admission,
                )
            with readonly_connection(project_root) as connection:
                return _assign(
                    connection,
                    project_root=project_root,
                    request=request,
                    owner=owner,
                    as_of=as_of,
                    lease_seconds=lease_seconds,
                    limits=limits,
                    plan_only=True,
                    owner_health=health,
                    delivery_admission=delivery_admission,
                )
        with writable_connection(
            project_root,
            initialized_at=scheduler_timestamp(initialization_time),
        ) as connection:
            return _assign(
                connection,
                project_root=project_root,
                request=request,
                owner=owner,
                as_of=as_of,
                lease_seconds=lease_seconds,
                limits=limits,
                plan_only=False,
                owner_health=health,
                delivery_admission=delivery_admission,
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


def _assign(
    connection: sqlite3.Connection | None,
    *,
    project_root: Path,
    request: AssignmentRequest | None,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    limits: SchedulerLimits,
    plan_only: bool,
    owner_health: HealthCheck,
    delivery_admission: _DeliveryAdmission | None,
) -> DecisionReceipt:
    if delivery_admission is not None and request is not None:
        return _plan_or_assign_selected(
            connection,
            request=request,
            owner=owner,
            as_of=as_of,
            lease_seconds=lease_seconds,
            limits=limits,
            plan_only=plan_only,
            owner_health=owner_health,
            delivery_root=project_root,
            delivery_admission=delivery_admission,
        )
    return plan_or_assign(
        connection,
        request=request,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        limits=limits,
        plan_only=plan_only,
        owner_health=owner_health,
    )
