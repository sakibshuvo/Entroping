"""Public and selected scheduler assignment entry boundaries."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_delivery_admission import _DeliveryAdmission
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
    SchedulerLimits,
)
from scripts.factory_scheduler_receipts import blocked_state_receipt
from scripts.factory_scheduler_transactions import HealthCheck, _plan_or_assign


def plan_or_assign(
    connection: sqlite3.Connection | None,
    *,
    request: AssignmentRequest | None,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    limits: SchedulerLimits,
    plan_only: bool,
    owner_health: HealthCheck,
) -> DecisionReceipt:
    if (
        request is not None
        and request.worker_class == "free-local"
        and request.access_mode == "write"
    ):
        observed_at = datetime.now(UTC) if as_of is None else as_of
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason="selection-required",
            authoritative=connection is not None and not plan_only,
        )
    return _plan_or_assign(
        connection,
        request=request,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        limits=limits,
        plan_only=plan_only,
        owner_health=owner_health,
    )


def _plan_or_assign_selected(
    connection: sqlite3.Connection | None,
    *,
    request: AssignmentRequest,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    limits: SchedulerLimits,
    plan_only: bool,
    owner_health: HealthCheck,
    delivery_root: Path,
    delivery_admission: _DeliveryAdmission,
) -> DecisionReceipt:
    return _plan_or_assign(
        connection,
        request=request,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        limits=limits,
        plan_only=plan_only,
        owner_health=owner_health,
        delivery_root=delivery_root,
        delivery_admission=delivery_admission,
    )
