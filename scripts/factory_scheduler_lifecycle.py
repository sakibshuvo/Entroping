from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_retry_policy import RetryPolicy
from scripts.factory_scheduler_completion_service import complete_scheduler_assignment
from scripts.factory_scheduler_execution_models import (
    ExecutionPhase,
    ExecutionState,
    RecoveryReceipt,
    RecoveryRequest,
)
from scripts.factory_scheduler_execution_transaction import transition_execution
from scripts.factory_scheduler_lease_transaction import heartbeat_lease
from scripts.factory_scheduler_models import DecisionReceipt, LeaseOwner, StoredAssignment
from scripts.factory_scheduler_process import probe_owner
from scripts.factory_scheduler_receipts import blocked_state_receipt
from scripts.factory_scheduler_recovery_service import recover_scheduler_assignment
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState
from scripts.factory_scheduler_storage import database_exists, writable_connection
from scripts.factory_scheduler_storage_fs import SchedulerStateError, is_busy
from scripts.factory_scheduler_validation import (
    FactorySchedulerError,
    scheduler_timestamp,
    validate_lease_epoch,
    validate_lease_seconds,
    validate_phase_version,
)

type HealthCheck = Callable[[LeaseOwner], bool | None]
type SettlementAuthorityCheck = Callable[[StoredAssignment], SettlementAuthorityState]
type SettlementAuthorityGuard = Callable[
    [StoredAssignment], AbstractContextManager[SettlementAuthorityState]
]


class FactorySchedulerLifecycle:
    def __init__(
        self,
        *,
        project_root: Path,
        settlement_authority: SettlementAuthorityCheck,
        settlement_guard: SettlementAuthorityGuard,
    ) -> None:
        self.project_root: Path = project_root
        self.settlement_authority: SettlementAuthorityCheck = settlement_authority
        self.settlement_guard: SettlementAuthorityGuard = settlement_guard

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
        expected_phase_version: int,
        completed_at: datetime,
    ) -> None:
        if assignment_id is None:
            raise FactorySchedulerError("assignment id is required")
        if epoch is None:
            raise FactorySchedulerError("assignment epoch is required")
        phase_version = validate_phase_version(expected_phase_version)
        try:
            complete_scheduler_assignment(
                self.project_root,
                assignment_id=assignment_id,
                owner=owner,
                epoch=validate_lease_epoch(epoch),
                expected_phase_version=phase_version,
                completed_at=completed_at,
                settlement_guard=self.settlement_guard,
            )
        except (SchedulerStateError, sqlite3.DatabaseError, ValueError) as exc:
            raise FactorySchedulerError("assignment completion failed") from exc

    def transition_execution(
        self,
        *,
        assignment_id: str,
        owner: LeaseOwner,
        epoch: int,
        expected_phase_version: int,
        target_phase: ExecutionPhase,
        observed_at: datetime,
        evidence_digest: str,
    ) -> ExecutionState:
        phase_version = validate_phase_version(expected_phase_version)
        try:
            with writable_connection(
                self.project_root,
                initialized_at=scheduler_timestamp(observed_at),
            ) as connection:
                return transition_execution(
                    connection,
                    assignment_id=assignment_id,
                    owner=owner,
                    epoch=validate_lease_epoch(epoch),
                    expected_phase_version=phase_version,
                    target_phase=target_phase,
                    observed_at=observed_at,
                    evidence_digest=evidence_digest,
                )
        except (SchedulerStateError, sqlite3.DatabaseError, ValidationError, ValueError) as exc:
            raise FactorySchedulerError("execution transition failed") from exc

    def recover(
        self,
        request: RecoveryRequest,
        *,
        owner: LeaseOwner,
        as_of: datetime,
        lease_seconds: int,
        retry_policy: RetryPolicy,
        plan_only: bool,
        owner_health: HealthCheck | None = None,
    ) -> RecoveryReceipt:
        validate_lease_seconds(lease_seconds)
        health = owner_health or probe_owner
        try:
            if not database_exists(self.project_root):
                raise FactorySchedulerError("scheduler state is unavailable")
            return recover_scheduler_assignment(
                self.project_root,
                request=request,
                owner=owner,
                as_of=as_of,
                lease_seconds=lease_seconds,
                retry_policy=retry_policy,
                plan_only=plan_only,
                owner_health=health,
                settlement_check=self.settlement_authority,
                settlement_guard=self.settlement_guard,
            )
        except FactorySchedulerError:
            raise
        except (SchedulerStateError, sqlite3.DatabaseError, ValidationError, ValueError) as exc:
            raise FactorySchedulerError("scheduler recovery failed") from exc
