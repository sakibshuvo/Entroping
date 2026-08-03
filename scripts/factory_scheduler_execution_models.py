from __future__ import annotations

from datetime import datetime
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scripts.factory_retry_policy import RecoverySnapshot
from scripts.factory_scheduler_models import (
    AssignmentId,
    Identifier,
    PositiveEpoch,
    ProcessToken,
)

type ExecutionPhase = Literal[
    "never-dispatched",
    "dispatch-intent",
    "dispatched",
    "completed-unsettled",
    "retry-wait",
    "uncertain",
    "completed",
    "failed",
]
type TerminalOutcome = Literal["completed", "failed", "retry-exhausted"]
type DispatchState = Literal["not-dispatched", "dispatched", "completed", "unknown"]
type SettlementState = Literal["not-required", "settled", "uncertain", "unknown"]
type FailureClass = Literal["none", "transient", "rate-limited", "terminal", "unknown"]
type RecoveryDecision = Literal[
    "would-recover",
    "retry-scheduled",
    "resumed",
    "uncertain",
    "completed",
    "failed",
    "blocked",
]

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PhaseVersion = Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]
AttemptCount = Annotated[int, Field(ge=1, le=20)]


class _StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )


class ExecutionState(_StrictModel):
    assignment_id: AssignmentId
    phase: ExecutionPhase
    phase_version: PhaseVersion
    attempt_count: AttemptCount
    lease_owner_id: Identifier
    lease_owner_pid: Annotated[int, Field(ge=1, le=2_147_483_647)]
    lease_owner_start_token: ProcessToken
    lease_epoch: PositiveEpoch
    lease_expires_at: datetime
    phase_changed_at: datetime
    worker_heartbeat_at: datetime
    retry_not_before: datetime | None
    failure_code: Identifier | None
    terminal_outcome: TerminalOutcome | None
    evidence_digest: Digest | None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        _aware(self.phase_changed_at)
        _aware(self.worker_heartbeat_at)
        _aware(self.lease_expires_at)
        if self.worker_heartbeat_at >= self.lease_expires_at:
            raise ValueError("execution lease must expire after its heartbeat")
        if self.retry_not_before is not None:
            _aware(self.retry_not_before)
        if self.phase == "retry-wait" and self.retry_not_before is None:
            raise ValueError("retry-wait execution requires a retry deadline")
        if self.phase != "retry-wait" and self.retry_not_before is not None:
            raise ValueError("only retry-wait execution may carry a retry deadline")
        valid_outcome = (
            (self.phase == "completed" and self.terminal_outcome == "completed")
            or (self.phase == "failed" and self.terminal_outcome in {"failed", "retry-exhausted"})
            or (self.phase not in {"completed", "failed"} and self.terminal_outcome is None)
        )
        if not valid_outcome:
            raise ValueError("terminal execution outcome does not match phase")
        return self


class RecoveryRequest(_StrictModel):
    request_id: Identifier
    assignment_id: AssignmentId
    expected_epoch: PositiveEpoch
    dispatch_state: DispatchState
    settlement_state: SettlementState
    failure_class: FailureClass
    failure_code: Identifier
    retry_after_seconds: Annotated[int, Field(ge=0, le=86_400)] | None = None
    snapshots: Annotated[tuple[RecoverySnapshot, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> Self:
        if self.dispatch_state == "not-dispatched" and self.settlement_state not in {
            "not-required",
            "settled",
        }:
            raise ValueError("never-dispatched recovery has conflicting settlement state")
        if self.dispatch_state == "completed" and self.failure_class not in {
            "none",
            "unknown",
        }:
            raise ValueError("completed recovery has conflicting failure classification")
        if self.failure_class == "rate-limited" and self.retry_after_seconds is None:
            raise ValueError("rate-limited recovery requires a bounded retry hint")
        return self


class RecoveryReceipt(_StrictModel):
    schema_version: Literal["entroping.factory-scheduler-recovery.v1"] = (
        "entroping.factory-scheduler-recovery.v1"
    )
    receipt_id: Annotated[
        str,
        StringConstraints(pattern=r"^recovery_[a-f0-9]{64}$"),
    ]
    request_id: Identifier
    assignment_id: AssignmentId
    decision: RecoveryDecision
    reason: Identifier
    authoritative: bool
    paid_work_authorized: Literal[False] = False
    phase: ExecutionPhase
    phase_version: PhaseVersion
    attempt_count: AttemptCount
    retry_not_before: datetime | None
    terminal_outcome: TerminalOutcome | None
    lease_owner_id: Identifier
    lease_epoch: PositiveEpoch
    observed_at: datetime

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        _aware(self.observed_at)
        if self.retry_not_before is not None:
            _aware(self.retry_not_before)
        return self


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("execution timestamp must be timezone-aware")
