from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from scripts.factory_scheduler_assignment_transaction import (
    insert_assignment,
    replay_assignment,
)
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
    make_decision_id,
    request_digest,
)
from scripts.factory_scheduler_transaction_control import (
    blocked_receipt,
    finish_transaction,
    rollback_transaction,
    update_clock,
)
from scripts.factory_scheduler_validation import aware_utc

HealthCheck = Callable[[LeaseOwner], bool | None]


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
    if request is None:
        observed_at = _observed_at(as_of)
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
        observed_at = _observed_at(as_of)
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
        observed_at = _observed_at(as_of)
        clock_at, last_epoch = clock(connection)
        if observed_at < clock_at:
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=blocked_receipt(
                    connection,
                    request=request,
                    observed_at=observed_at,
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
        lease_outcome = lease_epoch(
            connection,
            owner=owner,
            as_of=observed_at,
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
                    observed_at=observed_at,
                    reason=lease_outcome,
                ),
            )
        epoch = lease_outcome
        active_counts = counts(connection, request.scope_key)
        capacity_reason = _capacity_reason(
            request,
            counts=active_counts,
            limits=limits,
        )
        if capacity_reason is not None:
            if not plan_only:
                update_clock(connection, observed_at)
            return finish_transaction(
                connection,
                plan_only=plan_only,
                receipt=decision_receipt(
                    request=request,
                    owner=owner,
                    epoch=epoch,
                    observed_at=observed_at,
                    decision="blocked",
                    reason=capacity_reason,
                    authoritative=not plan_only,
                    counts=active_counts,
                ),
            )
        if plan_only:
            return decision_receipt(
                request=request,
                owner=owner,
                epoch=epoch,
                observed_at=observed_at,
                decision="would-assign",
                reason="capacity-available",
                authoritative=False,
                counts=active_counts,
            )
        expires_at = lease_expiration(observed_at, lease_seconds)
        if expires_at is None:
            return finish_transaction(
                connection,
                plan_only=False,
                receipt=blocked_receipt(
                    connection,
                    request=request,
                    observed_at=observed_at,
                    reason="state-invalid",
                ),
            )
        store_lease(connection, owner, epoch, observed_at, expires_at)
        update_clock(connection, observed_at, epoch=epoch)
        public_assignment_id = assignment_id(request_digest_value)
        decision_id = make_decision_id(
            request_digest_value=request_digest_value,
            epoch=epoch,
            observed_at=observed_at,
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
            created_at=observed_at,
        )
        receipt = decision_receipt(
            request=request,
            owner=owner,
            epoch=epoch,
            observed_at=observed_at,
            decision="assigned",
            reason="capacity-reserved",
            authoritative=True,
            counts=counts(connection, request.scope_key),
            assignment_id=public_assignment_id,
            decision_id=decision_id,
        )
        return finish_transaction(connection, plan_only=False, receipt=receipt)
    except BaseException:
        rollback_transaction(connection)
        raise


def _capacity_reason(
    request: AssignmentRequest,
    *,
    counts: tuple[int, int, int],
    limits: SchedulerLimits,
) -> str | None:
    paid, free_reviews, writers = counts
    if request.worker_class == "paid" and paid >= limits.max_paid:
        return "paid-capacity"
    if (
        request.worker_class == "free-local"
        and request.access_mode == "read-only"
        and free_reviews >= limits.max_free_local_reviews
    ):
        return "free-review-capacity"
    if request.access_mode == "write" and writers >= limits.max_writers_per_scope:
        return "writer-scope-capacity"
    return None


def _observed_at(as_of: datetime | None) -> datetime:
    return aware_utc(datetime.now(UTC) if as_of is None else as_of)
