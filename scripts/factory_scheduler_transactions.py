from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from scripts.factory_delivery_admission import _DeliveryAdmission
from scripts.factory_scheduler_assignment_transaction import (
    insert_assignment,
    replay_assignment,
)
from scripts.factory_scheduler_capacity import capacity_reason
from scripts.factory_scheduler_capacity import observed_at as scheduler_observed_at
from scripts.factory_scheduler_delivery_transaction import _delivery_admission_block
from scripts.factory_scheduler_lease_transaction import (
    lease_epoch,
    lease_expiration,
    store_lease,
)
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
    SchedulerLimits,
)
from scripts.factory_scheduler_queries import clock, counts
from scripts.factory_scheduler_receipts import (
    assignment_id,
    decision_receipt,
    iso_utc,
    make_decision_id,
    request_digest,
)
from scripts.factory_scheduler_transaction_control import (
    blocked_receipt,
    finish_transaction,
    rollback_transaction,
    update_clock,
)

HealthCheck = Callable[[LeaseOwner], bool | None]


def _plan_or_assign(
    connection: sqlite3.Connection | None,
    *,
    request: AssignmentRequest | None,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    limits: SchedulerLimits,
    plan_only: bool,
    owner_health: HealthCheck,
    delivery_root: Path | None = None,
    delivery_admission: _DeliveryAdmission | None = None,
) -> DecisionReceipt:
    if request is None:
        observed_at = scheduler_observed_at(as_of)
        return decision_receipt(
            request=None,
            owner=None,
            epoch=None,
            observed_at=observed_at,
            decision="idle",
            reason="no-candidate",
            authoritative=not plan_only,
            counts=(0, 0, 0),
        )
    if connection is None:
        observed_at = scheduler_observed_at(as_of)
        return decision_receipt(
            request=request,
            owner=owner,
            epoch=1,
            observed_at=observed_at,
            decision="would-assign",
            reason="capacity-available",
            authoritative=False,
            counts=(0, 0, 0),
        )
    request_digest_value = request_digest(request)
    if not plan_only:
        _ = connection.execute("BEGIN IMMEDIATE")
    try:
        observed_at_value = scheduler_observed_at(as_of)
        clock_at, last_epoch = clock(connection)
        if observed_at_value < clock_at:
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=blocked_receipt(
                    connection,
                    request=request,
                    observed_at=observed_at_value,
                    reason="clock-rollback",
                ),
            )
        replay = replay_assignment(
            connection,
            request=request,
            request_digest_value=request_digest_value,
        )
        if replay is not None:
            return finish_transaction(connection, plan_only=plan_only, receipt=replay)
        delivery_block = _delivery_admission_block(
            connection,
            delivery_root,
            request,
            delivery_admission,
            observed_at=observed_at_value,
            plan_only=plan_only,
        )
        if delivery_block is not None:
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=delivery_block,
            )
        lease_outcome = lease_epoch(
            connection,
            owner=owner,
            as_of=observed_at_value,
            last_epoch=last_epoch,
            owner_health=owner_health,
        )
        if isinstance(lease_outcome, str):
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=blocked_receipt(
                    connection,
                    request=request,
                    observed_at=observed_at_value,
                    reason=lease_outcome,
                ),
            )
        epoch = lease_outcome
        active_counts = counts(connection, request.scope_key)
        capacity_block = capacity_reason(
            request,
            counts=active_counts,
            limits=limits,
        )
        if capacity_block is not None:
            if not plan_only:
                update_clock(connection, observed_at_value)
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=decision_receipt(
                    request=request,
                    owner=owner,
                    epoch=epoch,
                    observed_at=observed_at_value,
                    decision="blocked",
                    reason=capacity_block,
                    authoritative=not plan_only,
                    counts=active_counts,
                ),
            )
        if plan_only:
            return decision_receipt(
                request=request,
                owner=owner,
                epoch=epoch,
                observed_at=observed_at_value,
                decision="would-assign",
                reason="capacity-available",
                authoritative=False,
                counts=active_counts,
            )
        expires_at = lease_expiration(observed_at_value, lease_seconds)
        if expires_at is None:
            return finish_transaction(
                connection,
                plan_only=False,
                receipt=blocked_receipt(
                    connection,
                    request=request,
                    observed_at=observed_at_value,
                    reason="state-invalid",
                ),
            )
        store_lease(connection, owner, epoch, observed_at_value, expires_at)
        _ = connection.execute(
            "UPDATE scheduler_execution_state SET worker_heartbeat_at_utc = ?, "
            "lease_expires_at_utc = ? WHERE lease_owner_id = ? "
            "AND lease_owner_pid = ? AND lease_owner_start_token = ? "
            "AND lease_epoch = ? AND phase NOT IN ('completed', 'failed')",
            (
                iso_utc(observed_at_value),
                iso_utc(expires_at),
                owner.owner_id,
                owner.pid,
                owner.process_start_token,
                epoch,
            ),
        )
        update_clock(connection, observed_at_value, epoch=epoch)
        public_assignment_id = assignment_id(request_digest_value)
        decision_id = make_decision_id(
            request_digest_value=request_digest_value,
            epoch=epoch,
            observed_at=observed_at_value,
            decision="assigned",
            reason="capacity-reserved",
        )
        insert_assignment(
            connection,
            request=request,
            request_digest=request_digest_value,
            assignment_id=public_assignment_id,
            decision_id=decision_id,
            owner=owner,
            epoch=epoch,
            created_at=observed_at_value,
            lease_expires_at=expires_at,
        )
        receipt = decision_receipt(
            request=request,
            owner=owner,
            epoch=epoch,
            observed_at=observed_at_value,
            decision="assigned",
            reason="capacity-reserved",
            authoritative=True,
            counts=counts(connection, request.scope_key),
            assignment_id=public_assignment_id,
            decision_id=decision_id,
        )
        return finish_transaction(connection, plan_only=False, receipt=receipt)
    finally:
        rollback_transaction(connection)
