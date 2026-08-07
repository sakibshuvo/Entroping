from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from scripts.factory_retry_policy import RetryPolicy, freshness_failure, retry_not_before
from scripts.factory_scheduler_execution_models import (
    ExecutionPhase,
    ExecutionState,
    RecoveryDecision,
    RecoveryRequest,
    TerminalOutcome,
)
from scripts.factory_scheduler_models import WorkerClass


@dataclass(frozen=True, slots=True)
class RecoveryTransition:
    phase: ExecutionPhase
    decision: RecoveryDecision
    reason: str
    terminal_outcome: TerminalOutcome | None
    attempt_count: int
    retry_not_before: datetime | None
    mutates_execution: bool = True


def decide_recovery(
    *,
    request: RecoveryRequest,
    execution: ExecutionState,
    worker_class: WorkerClass,
    job_id: str,
    created_at: datetime,
    observed_at: datetime,
    retry_policy: RetryPolicy,
) -> RecoveryTransition:
    if execution.phase in {"completed", "failed"}:
        return RecoveryTransition(
            phase=execution.phase,
            decision="completed" if execution.phase == "completed" else "failed",
            reason="terminal-replay",
            terminal_outcome=execution.terminal_outcome,
            attempt_count=execution.attempt_count,
            retry_not_before=None,
            mutates_execution=False,
        )
    if request.dispatch_state == "completed" and request.settlement_state in {
        "settled",
        "not-required",
    }:
        return RecoveryTransition(
            "completed",
            "completed",
            "settlement-confirmed",
            "completed",
            execution.attempt_count,
            None,
        )
    if request.dispatch_state == "not-dispatched" and request.settlement_state == "settled":
        return RecoveryTransition(
            "failed",
            "failed",
            "never-dispatched-settled",
            "failed",
            execution.attempt_count,
            None,
        )
    if request.dispatch_state != "not-dispatched" or execution.phase not in {
        "never-dispatched",
        "retry-wait",
    }:
        return _ambiguous_transition(
            request=request,
            execution=execution,
            worker_class=worker_class,
        )
    if request.failure_class == "none":
        return _blocked(execution, "failure-class-conflict")
    exhausted = (
        execution.attempt_count >= retry_policy.max_attempts
        or observed_at >= created_at + timedelta(seconds=retry_policy.max_elapsed_seconds)
    )
    if request.failure_class == "terminal" or exhausted:
        outcome: TerminalOutcome = "retry-exhausted" if exhausted else "failed"
        reason = "retry-exhausted" if exhausted else request.failure_code
        return RecoveryTransition(
            "failed",
            "failed",
            reason,
            outcome,
            execution.attempt_count,
            None,
        )
    freshness = freshness_failure(
        request.snapshots,
        worker_class=worker_class,
        observed_at=observed_at,
    )
    if execution.phase == "retry-wait" and freshness is None:
        return RecoveryTransition(
            "never-dispatched",
            "resumed",
            "retry-reconsideration-ready",
            None,
            execution.attempt_count + 1,
            None,
        )
    deadline = retry_not_before(
        retry_policy,
        job_id=job_id,
        attempt_count=execution.attempt_count,
        observed_at=observed_at,
        retry_after_seconds=request.retry_after_seconds,
    )
    return RecoveryTransition(
        "retry-wait",
        "retry-scheduled",
        freshness or "retry-scheduled",
        None,
        execution.attempt_count,
        deadline,
    )


def _ambiguous_transition(
    *,
    request: RecoveryRequest,
    execution: ExecutionState,
    worker_class: WorkerClass,
) -> RecoveryTransition:
    if request.settlement_state == "settled":
        return RecoveryTransition(
            "completed",
            "completed",
            "settlement-confirmed",
            "completed",
            execution.attempt_count,
            None,
        )
    if worker_class == "paid" and request.settlement_state != "uncertain":
        return _blocked(execution, "settlement-uncertain-required")
    return RecoveryTransition(
        "uncertain",
        "uncertain",
        "dispatch-outcome-uncertain",
        None,
        execution.attempt_count,
        None,
    )


def _blocked(execution: ExecutionState, reason: str) -> RecoveryTransition:
    return RecoveryTransition(
        execution.phase,
        "blocked",
        reason,
        execution.terminal_outcome,
        execution.attempt_count,
        execution.retry_not_before,
        mutates_execution=False,
    )
