from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

type StatusState = Literal["healthy", "paused", "unsafe"]
type SourceState = Literal["available", "unavailable", "uninitialized", "unsafe"]


class StatusModel(BaseModel):
    """Immutable, strict public factory-status projection model."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class StateCounts(StatusModel):
    active: int = Field(ge=0)
    uncertain: int = Field(ge=0)
    settled: int = Field(ge=0)
    released: int = Field(ge=0)


class BudgetStatus(StatusModel):
    status: SourceState
    cash_cap_microcents: int | None = Field(default=None, ge=0)
    reserve_microcents: int | None = Field(default=None, ge=0)
    net_available_microcents: int | None = None
    subscription_charge_microcents: int | None = Field(default=None, ge=0)
    reservations: StateCounts
    authorizations: StateCounts


class DispatchLanesStatus(StatusModel):
    status: SourceState
    active_routes: int = Field(ge=0)
    ready_routes: int = Field(ge=0)
    quota_status: SourceState


class SchedulerStatus(StatusModel):
    status: SourceState
    lease_state: Literal["uninitialized", "idle", "active", "expired", "unsafe"]
    active_paid: int = Field(ge=0)
    active_free_reviews: int = Field(ge=0)
    active_writers: int = Field(ge=0)
    executing: int = Field(ge=0)
    retry_waiting: int = Field(ge=0)
    uncertain: int = Field(ge=0)


class QueueStatus(StatusModel):
    status: SourceState
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    invalid: int = Field(ge=0)


class RetentionClassStatus(StatusModel):
    artifact_class: Literal[
        "ai_job",
        "ai_review",
        "factory_log",
        "factory_metrics_archive",
        "retention_journal",
    ]
    count: int = Field(ge=0)
    bytes: int = Field(ge=0)
    byte_ceiling: int | None = Field(default=None, ge=0)
    pressure: Literal["unavailable", "normal", "high", "exceeded", "unsafe"]


class RetentionStatus(StatusModel):
    status: SourceState
    classes: tuple[RetentionClassStatus, ...]


class FactoryStatusReport(StatusModel):
    schema_version: Literal["entroping.factory-status.v1"] = "entroping.factory-status.v1"
    observed_at_utc: datetime
    state: StatusState
    snapshot_consistency: Literal["stable", "changed", "unavailable"]
    reason_codes: tuple[str, ...]
    budget: BudgetStatus
    dispatch_lanes: DispatchLanesStatus
    scheduler: SchedulerStatus
    queue: QueueStatus
    retention: RetentionStatus
