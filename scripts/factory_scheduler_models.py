from __future__ import annotations

from datetime import datetime
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from entroping.models.secrets import contains_secret_like_value


def _reject_secret_shaped_identifier(value: str) -> str:
    if contains_secret_like_value(value):
        raise ValueError("scheduler identifiers must not contain secret-like values")
    return value


Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
    AfterValidator(_reject_secret_shaped_identifier),
]
WorktreeId = Annotated[
    str,
    StringConstraints(pattern=r"^wt_[a-f0-9]{64}$"),
]
ReservationId = Annotated[
    str,
    StringConstraints(pattern=r"^res-[a-f0-9]{32}$"),
]
AuthorizationId = Annotated[
    str,
    StringConstraints(pattern=r"^auth-[a-f0-9]{32}$"),
]
AssignmentId = Annotated[
    str,
    StringConstraints(pattern=r"^assign_[a-f0-9]{64}$"),
]
DecisionId = Annotated[
    str,
    StringConstraints(pattern=r"^decision_[a-f0-9]{64}$"),
]
ProcessToken = Annotated[
    str,
    StringConstraints(pattern=r"^proc_[a-f0-9]{64}$"),
]
PositiveEpoch = Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]
Count = Annotated[int, Field(ge=0, le=100_000)]

type WorkerClass = Literal["paid", "free-local"]
type AccessMode = Literal["read-only", "write"]
type Decision = Literal["idle", "would-assign", "assigned", "heartbeat", "blocked"]


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )


class LeaseOwner(StrictModel):
    owner_id: Identifier
    pid: Annotated[int, Field(ge=1, le=2_147_483_647)]
    process_start_token: ProcessToken


class SchedulerLimits(StrictModel):
    max_paid: Annotated[int, Field(ge=0, le=1)] = 1
    max_free_local_reviews: Annotated[int, Field(ge=0, le=1)] = 1
    max_writers_per_scope: Annotated[int, Field(ge=0, le=1)] = 1


class AssignmentRequest(StrictModel):
    request_id: Identifier
    job_id: Identifier
    issue_number: Annotated[int, Field(ge=1, le=2_147_483_647)]
    worktree_id: WorktreeId
    worker_class: WorkerClass
    access_mode: AccessMode
    reservation_id: ReservationId | None = None
    authorization_id: AuthorizationId | None = None

    @model_validator(mode="after")
    def require_paid_reservation(self) -> Self:
        if (
            self.worker_class == "paid"
            and self.reservation_id is None
            and self.authorization_id is None
        ):
            raise ValueError("paid assignments require a dispatch authorization")
        if self.worker_class == "free-local" and (
            self.reservation_id is not None or self.authorization_id is not None
        ):
            raise ValueError("free/local assignments must not carry dispatch authority")
        return self

    @property
    def scope_key(self) -> str:
        return f"{self.issue_number}:{self.worktree_id.casefold()}"


class DecisionReceipt(StrictModel):
    schema_version: Literal["entroping.factory-scheduler-decision.v1"] = (
        "entroping.factory-scheduler-decision.v1"
    )
    decision_id: DecisionId
    decision: Decision
    reason: Identifier
    authoritative: bool
    paid_work_authorized: Literal[False] = False
    request_id: Identifier | None
    job_id: Identifier | None
    issue_number: Annotated[int, Field(ge=1, le=2_147_483_647)] | None
    worktree_id: Identifier | None
    assignment_id: AssignmentId | None
    lease_owner_id: Identifier | None
    lease_epoch: PositiveEpoch | None
    observed_at: datetime
    active_paid: Count
    active_free_reviews: Count
    active_writers_in_scope: Count

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> Self:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return self


class SchedulerSnapshot(StrictModel):
    schema_version: Literal["entroping.factory-scheduler-snapshot.v1"] = (
        "entroping.factory-scheduler-snapshot.v1"
    )
    active_assignment_count: Count
    active_paid: Count
    active_free_reviews: Count
    active_writer_count: Count
    lease_owner_id: Identifier | None
    lease_epoch: PositiveEpoch | None
    lease_expires_at: datetime | None


class StoredLease(StrictModel):
    owner: LeaseOwner
    epoch: PositiveEpoch
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


class StoredAssignment(StrictModel):
    request: AssignmentRequest
    request_digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    assignment_id: AssignmentId
    decision_id: DecisionId
    lease_owner_id: Identifier
    lease_owner_pid: Annotated[int, Field(ge=1, le=2_147_483_647)]
    lease_owner_start_token: ProcessToken
    lease_epoch: PositiveEpoch
    created_at: datetime
    state: Literal["active", "completed"]
    completed_at: datetime | None = None
