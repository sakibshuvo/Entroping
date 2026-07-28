from __future__ import annotations

from typing import Final, Literal

POLICY_SCHEMA_VERSION: Final = "entroping.factory-retention-policy.v1"
CANDIDATE_SCHEMA_VERSION: Final = "entroping.factory-retention-candidate.v1"
PLANNER_SCHEMA_VERSION: Final = "entroping.factory-retention-plan.v1"
FACTORY_METRICS_ARCHIVE_SCHEMA_VERSION: Final = "entroping.factory-metrics-archive.v1"

type ArtifactClass = Literal[
    "ai_job",
    "ai_review",
    "factory_log",
    "factory_metrics_archive",
    "retention_journal",
]
type DecisionAction = Literal["delete", "retain"]
type ReferenceKind = Literal["issue", "pull_request"]
type ReferenceState = Literal["open", "closed", "merged", "unknown"]
type SettlementState = Literal["settled", "unresolved", "unknown"]
type ReasonCode = Literal[
    "delete_by_age",
    "delete_by_byte_cap",
    "age_not_reached",
    "protected_active_state",
    "protected_bundle",
    "protected_malformed_metadata",
    "protected_missing_settlement",
    "protected_open_reference",
    "protected_review_state",
    "protected_unknown_reference",
    "protected_unknown_settlement",
    "protected_unresolved_settlement",
    "protected_unknown_state",
]

MANAGED_CLASSES: Final[tuple[ArtifactClass, ...]] = (
    "ai_job",
    "ai_review",
    "factory_log",
    "factory_metrics_archive",
    "retention_journal",
)
DELETE_REASONS: Final[frozenset[ReasonCode]] = frozenset(
    {"delete_by_age", "delete_by_byte_cap"}
)
PROTECTED_REASONS: Final[frozenset[ReasonCode]] = frozenset(
    {
        "protected_active_state",
        "protected_bundle",
        "protected_malformed_metadata",
        "protected_missing_settlement",
        "protected_open_reference",
        "protected_review_state",
        "protected_unknown_reference",
        "protected_unknown_settlement",
        "protected_unresolved_settlement",
        "protected_unknown_state",
    }
)

AI_JOB_TERMINAL_STATES: Final = frozenset({"completed", "failed"})
AI_JOB_ACTIVE_STATES: Final = frozenset({"queued", "running"})
AI_REVIEW_TERMINAL_STATES: Final = frozenset({"accepted", "rejected"})
AI_REVIEW_HELD_STATES: Final = frozenset(
    {"ready", "ready_for_codex", "ready-for-codex", "in_review", "reviewed", "needs_review"}
)
FACTORY_LOG_TERMINAL_STATES: Final = frozenset({"rotated"})
FACTORY_LOG_ACTIVE_STATES: Final = frozenset({"active"})
FACTORY_METRICS_ARCHIVE_TERMINAL_STATES: Final = frozenset({"archived"})
RETENTION_JOURNAL_TERMINAL_STATES: Final = frozenset({"completed", "rolled_back"})

MAX_INT64: Final = 9_223_372_036_854_775_807
MAX_AGE_DAYS: Final = 3_652_058
MAX_IDENTIFIER_LENGTH: Final = 256
MAX_PATH_LENGTH: Final = 4_096
MAX_STATE_LENGTH: Final = 64
