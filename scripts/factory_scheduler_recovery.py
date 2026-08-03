from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime

from scripts.factory_retry_policy import RetryPolicy
from scripts.factory_scheduler_execution_models import (
    ExecutionState,
    RecoveryDecision,
    RecoveryReceipt,
    RecoveryRequest,
)
from scripts.factory_scheduler_lease_transaction import lease_expiration, recovery_epoch
from scripts.factory_scheduler_models import LeaseOwner
from scripts.factory_scheduler_queries import clock
from scripts.factory_scheduler_recovery_authority import (
    recovery_authority_blocker,
    recovery_context,
)
from scripts.factory_scheduler_recovery_decision import RecoveryTransition, decide_recovery
from scripts.factory_scheduler_recovery_receipts import (
    make_recovery_receipt,
    recovery_request_digest,
    replay_recovery_receipt,
    store_recovery_receipt,
)
from scripts.factory_scheduler_recovery_state import (
    apply_recovery_transition,
    project_recovery_transition,
)
from scripts.factory_scheduler_settlement_authority import SettlementAuthorityState
from scripts.factory_scheduler_transaction_control import rollback_transaction, update_clock
from scripts.factory_scheduler_validation import aware_utc

type HealthCheck = Callable[[LeaseOwner], bool | None]


def recover_assignment(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    owner: LeaseOwner,
    as_of: datetime,
    lease_seconds: int,
    retry_policy: RetryPolicy,
    owner_health: HealthCheck,
    plan_only: bool,
    settlement_authority: SettlementAuthorityState,
) -> RecoveryReceipt:
    observed_at = aware_utc(as_of)
    if plan_only:
        return _plan_recovery(
            connection,
            request=request,
            owner=owner,
            observed_at=observed_at,
            lease_seconds=lease_seconds,
            retry_policy=retry_policy,
            owner_health=owner_health,
            settlement_authority=settlement_authority,
        )
    request_digest = recovery_request_digest(
        request,
        owner=owner,
        lease_seconds=lease_seconds,
        policy=retry_policy,
    )
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        replay = replay_recovery_receipt(
            connection,
            request_id=request.request_id,
            request_digest=request_digest,
        )
        if replay is not None:
            _ = connection.execute("COMMIT")
            return replay
        transition, execution = _evaluate(
            connection,
            request=request,
            owner=owner,
            observed_at=observed_at,
            retry_policy=retry_policy,
            owner_health=owner_health,
            settlement_authority=settlement_authority,
        )
        if transition.mutates_execution:
            execution = apply_recovery_transition(
                connection,
                request=request,
                execution=execution,
                transition=transition,
                owner=owner,
                observed_at=observed_at,
                lease_seconds=lease_seconds,
            )
        else:
            update_clock(connection, observed_at)
        return _commit_receipt(
            connection,
            request=request,
            request_digest=request_digest,
            execution=execution,
            transition=transition,
            observed_at=observed_at,
        )
    except BaseException:
        rollback_transaction(connection)
        raise


def _plan_recovery(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    owner: LeaseOwner,
    observed_at: datetime,
    lease_seconds: int,
    retry_policy: RetryPolicy,
    owner_health: HealthCheck,
    settlement_authority: SettlementAuthorityState,
) -> RecoveryReceipt:
    transition, execution = _evaluate(
        connection,
        request=request,
        owner=owner,
        observed_at=observed_at,
        retry_policy=retry_policy,
        owner_health=owner_health,
        settlement_authority=settlement_authority,
    )
    reason: str
    if transition.mutates_execution:
        _clock_at, last_epoch = clock(connection)
        epoch = recovery_epoch(connection, owner=owner, last_epoch=last_epoch)
        expires_at = lease_expiration(observed_at, lease_seconds)
        if isinstance(epoch, str) or expires_at is None:
            raise ValueError("recovery lease cannot advance")
        execution = project_recovery_transition(
            execution=execution,
            transition=transition,
            request=request,
            owner=owner,
            epoch=epoch,
            lease_expires_at=expires_at,
            observed_at=observed_at,
        )
        decision: RecoveryDecision = "would-recover"
        reason = transition.decision
    else:
        decision = transition.decision
        reason = transition.reason
    return make_recovery_receipt(
        request=request,
        execution=execution,
        decision=decision,
        reason=reason,
        authoritative=False,
        observed_at=observed_at,
    )


def _evaluate(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    owner: LeaseOwner,
    observed_at: datetime,
    retry_policy: RetryPolicy,
    owner_health: HealthCheck,
    settlement_authority: SettlementAuthorityState,
) -> tuple[RecoveryTransition, ExecutionState]:
    clock_at, _last_epoch = clock(connection)
    if observed_at < clock_at:
        raise ValueError("recovery clock rollback")
    execution, worker_class, job_id, created_at = recovery_context(
        connection,
        request.assignment_id,
    )
    if execution.phase not in {"completed", "failed"}:
        blocked = recovery_authority_blocker(
            connection,
            request=request,
            execution=execution,
            owner=owner,
            observed_at=observed_at,
            owner_health=owner_health,
            worker_class=worker_class,
            settlement_authority=settlement_authority,
        )
        if blocked is not None:
            return (
                RecoveryTransition(
                    execution.phase,
                    "blocked",
                    blocked,
                    execution.terminal_outcome,
                    execution.attempt_count,
                    execution.retry_not_before,
                    mutates_execution=False,
                ),
                execution,
            )
    return (
        decide_recovery(
            request=request,
            execution=execution,
            worker_class=worker_class,
            job_id=job_id,
            created_at=created_at,
            observed_at=observed_at,
            retry_policy=retry_policy,
        ),
        execution,
    )


def _commit_receipt(
    connection: sqlite3.Connection,
    *,
    request: RecoveryRequest,
    request_digest: str,
    execution: ExecutionState,
    transition: RecoveryTransition,
    observed_at: datetime,
) -> RecoveryReceipt:
    receipt = make_recovery_receipt(
        request=request,
        execution=execution,
        decision=transition.decision,
        reason=transition.reason,
        authoritative=True,
        observed_at=observed_at,
    )
    store_recovery_receipt(connection, request_digest=request_digest, receipt=receipt)
    _ = connection.execute("COMMIT")
    return receipt
