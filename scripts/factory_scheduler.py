from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_scheduler_completion_transaction import complete_assignment
from scripts.factory_scheduler_lease_transaction import heartbeat_lease
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
    SchedulerLimits,
    SchedulerSnapshot,
    StoredAssignment,
)
from scripts.factory_scheduler_process import probe_owner
from scripts.factory_scheduler_queries import read_assignment, read_snapshot
from scripts.factory_scheduler_receipts import blocked_state_receipt
from scripts.factory_scheduler_reservation import (
    ReservationHandoffError,
    budget_reservation_handoff,
)
from scripts.factory_scheduler_root import SchedulerRootError, resolve_scheduler_root
from scripts.factory_scheduler_storage import (
    database_exists,
    readonly_connection,
    writable_connection,
)
from scripts.factory_scheduler_storage_fs import SchedulerStateError, is_busy
from scripts.factory_scheduler_tick import immutable_request_decision, tick_state
from scripts.factory_scheduler_validation import (
    FactorySchedulerError as FactorySchedulerError,
)
from scripts.factory_scheduler_validation import (
    scheduler_timestamp,
    validate_lease_epoch,
    validate_lease_seconds,
)

type HealthCheck = Callable[[LeaseOwner], bool | None]
type ReservationGuard = Callable[
    [AssignmentRequest],
    AbstractContextManager[bool | None],
]


class FactoryScheduler:
    def __init__(
        self,
        project_root: Path,
        *,
        limits: SchedulerLimits | None = None,
        reservation_guard: ReservationGuard | None = None,
    ) -> None:
        try:
            self.project_root = resolve_scheduler_root(project_root)
        except SchedulerRootError as exc:
            raise FactorySchedulerError("scheduler root is unavailable") from exc
        self.limits = limits or SchedulerLimits()
        self.reservation_guard = reservation_guard or self._budget_reservation_guard

    def tick(
        self,
        *,
        request: AssignmentRequest | None,
        owner: LeaseOwner,
        as_of: datetime | None,
        lease_seconds: int,
        plan_only: bool,
        owner_health: HealthCheck | None = None,
    ) -> DecisionReceipt:
        validate_lease_seconds(lease_seconds)
        health = owner_health or probe_owner
        receipt_time = datetime.now(UTC) if as_of is None else as_of
        if not plan_only and request is not None and request.worker_class == "paid":
            stored_decision = immutable_request_decision(
                self.project_root,
                request,
                receipt_time,
            )
            if stored_decision is not None:
                return stored_decision
            try:
                with self.reservation_guard(request) as reservation:
                    if reservation is not True:
                        reason = (
                            "reservation-mismatch"
                            if reservation is False
                            else "reservation-unavailable"
                        )
                        return blocked_state_receipt(
                            request=request,
                            observed_at=receipt_time,
                            reason=reason,
                        )
                    return tick_state(
                        self.project_root,
                        self.limits,
                        request=request,
                        owner=owner,
                        as_of=as_of,
                        lease_seconds=lease_seconds,
                        plan_only=False,
                        health=health,
                    )
            except ReservationHandoffError as exc:
                return blocked_state_receipt(
                    request=request,
                    observed_at=receipt_time,
                    reason=(
                        "reservation-busy" if exc.code == "busy" else "reservation-unavailable"
                    ),
                )
        return tick_state(
            self.project_root,
            self.limits,
            request=request,
            owner=owner,
            as_of=as_of,
            lease_seconds=lease_seconds,
            plan_only=plan_only,
            health=health,
        )

    def heartbeat(
        self,
        *,
        owner: LeaseOwner,
        epoch: int,
        as_of: datetime,
        lease_seconds: int,
    ) -> DecisionReceipt:
        validate_lease_seconds(lease_seconds)
        validated_epoch = validate_lease_epoch(epoch)
        try:
            with writable_connection(
                self.project_root,
                initialized_at=scheduler_timestamp(as_of),
            ) as connection:
                return heartbeat_lease(
                    connection,
                    owner=owner,
                    epoch=validated_epoch,
                    as_of=as_of,
                    lease_seconds=lease_seconds,
                )
        except SchedulerStateError as exc:
            return blocked_state_receipt(
                request=None,
                observed_at=as_of,
                reason=exc.code,
            )
        except sqlite3.OperationalError as exc:
            reason = "state-busy" if is_busy(exc) else "state-invalid"
            return blocked_state_receipt(
                request=None,
                observed_at=as_of,
                reason=reason,
            )
        except (sqlite3.DatabaseError, ValidationError, ValueError, TypeError):
            return blocked_state_receipt(
                request=None,
                observed_at=as_of,
                reason="state-invalid",
            )

    def complete_assignment(
        self,
        *,
        assignment_id: str | None,
        owner: LeaseOwner,
        epoch: int | None,
        completed_at: datetime,
    ) -> None:
        if assignment_id is None:
            raise FactorySchedulerError("assignment id is required")
        if epoch is None:
            raise FactorySchedulerError("assignment epoch is required")
        validated_epoch = validate_lease_epoch(epoch)
        try:
            with writable_connection(
                self.project_root,
                initialized_at=scheduler_timestamp(completed_at),
            ) as connection:
                complete_assignment(
                    connection,
                    assignment_id=assignment_id,
                    owner=owner,
                    epoch=validated_epoch,
                    completed_at=completed_at,
                )
        except (SchedulerStateError, sqlite3.DatabaseError, ValueError) as exc:
            raise FactorySchedulerError("assignment completion failed") from exc

    def snapshot(self) -> SchedulerSnapshot:
        try:
            if not database_exists(self.project_root):
                return read_snapshot(None)
            with readonly_connection(self.project_root) as connection:
                return read_snapshot(connection)
        except (
            SchedulerStateError,
            sqlite3.DatabaseError,
            ValidationError,
            ValueError,
            TypeError,
        ) as exc:
            raise FactorySchedulerError("scheduler state is unavailable") from exc

    def assignment_for_job_readonly(self, job_id: str) -> StoredAssignment | None:
        try:
            if not database_exists(self.project_root):
                return None
            with readonly_connection(self.project_root) as connection:
                return read_assignment(connection, job_id=job_id)
        except (SchedulerStateError, sqlite3.DatabaseError, ValidationError) as exc:
            raise FactorySchedulerError("scheduler assignment is unavailable") from exc

    def _budget_reservation_guard(
        self,
        request: AssignmentRequest,
    ) -> AbstractContextManager[bool | None]:
        return budget_reservation_handoff(
            self.project_root,
            request,
        )
