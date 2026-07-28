from __future__ import annotations

import re
from typing import Annotated, ClassVar, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .factory_retention_fs import MAX_POLICY_TOTAL_BYTES
from .factory_retention_types import (
    AI_JOB_TERMINAL_STATES,
    AI_REVIEW_TERMINAL_STATES,
    CANDIDATE_SCHEMA_VERSION,
    DELETE_REASONS,
    FACTORY_LOG_TERMINAL_STATES,
    FACTORY_METRICS_ARCHIVE_TERMINAL_STATES,
    MANAGED_CLASSES,
    MAX_AGE_DAYS,
    MAX_IDENTIFIER_LENGTH,
    MAX_INT64,
    MAX_PATH_LENGTH,
    MAX_STATE_LENGTH,
    PLANNER_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION,
    PROTECTED_REASONS,
    RETENTION_JOURNAL_TERMINAL_STATES,
    ArtifactClass,
    DecisionAction,
    ReasonCode,
    ReferenceKind,
    ReferenceState,
    SettlementState,
)
from .factory_retention_validation import (
    require_clean_text,
    require_managed_path,
    require_utc,
)

Count = Annotated[int, Field(ge=0, le=MAX_INT64)]
PositiveBytes = Annotated[int, Field(gt=0, le=MAX_INT64)]
Bytes = Annotated[int, Field(ge=0, le=MAX_INT64)]
AgeDays = Annotated[int, Field(gt=0, le=MAX_AGE_DAYS)]
Identifier = Annotated[str, Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)]
StateText = Annotated[str, Field(min_length=1, max_length=MAX_STATE_LENGTH)]


class RetentionError(ValueError):
    pass


class StrictRetentionModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class ArtifactReference(StrictRetentionModel):
    kind: ReferenceKind
    reference_id: Identifier
    state: ReferenceState

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        require_clean_text(self.reference_id)
        return self


class RetentionStatePolicy(StrictRetentionModel):
    state: StateText
    max_age_days: AgeDays

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        require_clean_text(self.state)
        return self


class RetentionClassPolicy(StrictRetentionModel):
    schema_version: Annotated[str, Field(pattern=f"^{re.escape(POLICY_SCHEMA_VERSION)}$")]
    artifact_class: ArtifactClass
    byte_ceiling: PositiveBytes
    state_policies: tuple[RetentionStatePolicy, ...]

    @model_validator(mode="after")
    def validate_states(self) -> Self:
        states = tuple(item.state for item in self.state_policies)
        expected = _terminal_states(self.artifact_class)
        if len(states) != len(set(states)) or set(states) != set(expected):
            raise RetentionError("class policy must define each terminal state exactly once")
        return self

    def max_age_days_for(self, state: str) -> int:
        for item in self.state_policies:
            if item.state == state:
                return item.max_age_days
        raise RetentionError("terminal state has no retention policy")


class RetentionPolicy(StrictRetentionModel):
    schema_version: Annotated[str, Field(pattern=f"^{re.escape(POLICY_SCHEMA_VERSION)}$")]
    class_policies: tuple[RetentionClassPolicy, ...]

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        classes = tuple(item.artifact_class for item in self.class_policies)
        if len(classes) != len(set(classes)) or set(classes) != set(MANAGED_CLASSES):
            raise RetentionError("policy must define each managed class exactly once")
        if sum(item.byte_ceiling for item in self.class_policies) > MAX_POLICY_TOTAL_BYTES:
            raise RetentionError("policy byte ceilings exceed the bounded inventory allowance")
        return self


class ArtifactCandidate(StrictRetentionModel):
    schema_version: Annotated[str, Field(pattern=f"^{re.escape(CANDIDATE_SCHEMA_VERSION)}$")]
    artifact_id: Identifier
    bundle_id: Identifier
    artifact_class: ArtifactClass
    relative_path: Annotated[str, Field(min_length=1, max_length=MAX_PATH_LENGTH)]
    byte_size: Bytes
    created_at: AwareDatetime
    state: StateText
    inbox_status: StateText | None = None
    references: tuple[ArtifactReference, ...] = ()
    reservation_id: Identifier | None = None
    settlement_state: SettlementState | None = None
    metadata_valid: bool = True

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        for value in (self.artifact_id, self.bundle_id, self.state):
            require_clean_text(value)
        if self.inbox_status is not None:
            require_clean_text(self.inbox_status)
        if self.reservation_id is not None:
            require_clean_text(self.reservation_id)
        require_utc(self.created_at)
        require_managed_path(self.artifact_class, self.relative_path)
        reference_keys = {(item.kind, item.reference_id) for item in self.references}
        if len(reference_keys) != len(self.references):
            raise RetentionError("candidate references must be unique")
        return self


class RetentionDecision(StrictRetentionModel):
    action: DecisionAction
    reason_code: ReasonCode
    artifact_id: Identifier
    bundle_id: Identifier
    artifact_class: ArtifactClass
    relative_path: Annotated[str, Field(min_length=1, max_length=MAX_PATH_LENGTH)]
    byte_size: Bytes
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        for value in (self.artifact_id, self.bundle_id):
            require_clean_text(value)
        require_utc(self.created_at)
        require_managed_path(self.artifact_class, self.relative_path)
        if (self.action == "delete") != (self.reason_code in DELETE_REASONS):
            raise RetentionError("decision action and reason are inconsistent")
        return self


class ClassRetentionSummary(StrictRetentionModel):
    artifact_class: ArtifactClass
    state_max_age_days: dict[str, AgeDays]
    byte_ceiling: PositiveBytes
    candidate_count: Count
    deleted_count: Count
    retained_count: Count
    deleted_bytes: Bytes
    retained_bytes: Bytes
    protected_count: Count
    protected_bytes: Bytes
    pressure_bytes: Bytes

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if set(self.state_max_age_days) != set(_terminal_states(self.artifact_class)):
            raise RetentionError("class summary terminal-state ages are incomplete")
        if self.deleted_count + self.retained_count != self.candidate_count:
            raise RetentionError("class counts are inconsistent")
        if self.protected_count > self.retained_count or self.protected_bytes > self.retained_bytes:
            raise RetentionError("class protected totals are inconsistent")
        if self.pressure_bytes != max(0, self.retained_bytes - self.byte_ceiling):
            raise RetentionError("class pressure bytes are inconsistent")
        return self


class RetentionPlanReport(StrictRetentionModel):
    schema_version: Annotated[str, Field(pattern=f"^{re.escape(PLANNER_SCHEMA_VERSION)}$")]
    as_of: AwareDatetime
    total_candidate_count: Count
    total_retain_count: Count
    total_delete_count: Count
    total_retain_bytes: Bytes
    total_delete_bytes: Bytes
    decisions: tuple[RetentionDecision, ...]
    class_summaries: tuple[ClassRetentionSummary, ...]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        require_utc(self.as_of)
        decision_keys = {(item.artifact_id, item.relative_path) for item in self.decisions}
        if len(decision_keys) != len(self.decisions):
            raise RetentionError("report decisions must be unique")
        deleted = tuple(item for item in self.decisions if item.action == "delete")
        retained = tuple(item for item in self.decisions if item.action == "retain")
        expected = (
            len(self.decisions),
            len(retained),
            len(deleted),
            sum(item.byte_size for item in retained),
            sum(item.byte_size for item in deleted),
        )
        actual = (
            self.total_candidate_count,
            self.total_retain_count,
            self.total_delete_count,
            self.total_retain_bytes,
            self.total_delete_bytes,
        )
        if actual != expected:
            raise RetentionError("report totals are inconsistent")
        self._validate_class_summaries()
        return self

    def _validate_class_summaries(self) -> None:
        summaries = {item.artifact_class: item for item in self.class_summaries}
        if len(summaries) != len(self.class_summaries) or set(summaries) != set(MANAGED_CLASSES):
            raise RetentionError("report must summarize each managed class exactly once")
        for artifact_class, summary in summaries.items():
            decisions = tuple(
                item for item in self.decisions if item.artifact_class == artifact_class
            )
            deleted = tuple(item for item in decisions if item.action == "delete")
            retained = tuple(item for item in decisions if item.action == "retain")
            protected = tuple(item for item in retained if item.reason_code in PROTECTED_REASONS)
            observed = (
                len(decisions),
                len(deleted),
                len(retained),
                sum(item.byte_size for item in deleted),
                sum(item.byte_size for item in retained),
                len(protected),
                sum(item.byte_size for item in protected),
            )
            declared = (
                summary.candidate_count,
                summary.deleted_count,
                summary.retained_count,
                summary.deleted_bytes,
                summary.retained_bytes,
                summary.protected_count,
                summary.protected_bytes,
            )
            if observed != declared:
                raise RetentionError("class summary does not match decisions")


def _terminal_states(artifact_class: ArtifactClass) -> frozenset[str]:
    if artifact_class == "ai_job":
        return AI_JOB_TERMINAL_STATES
    if artifact_class == "ai_review":
        return AI_REVIEW_TERMINAL_STATES
    if artifact_class == "factory_log":
        return FACTORY_LOG_TERMINAL_STATES
    if artifact_class == "factory_metrics_archive":
        return FACTORY_METRICS_ARCHIVE_TERMINAL_STATES
    return RETENTION_JOURNAL_TERMINAL_STATES
