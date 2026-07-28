from __future__ import annotations

from .factory_retention_models import ArtifactCandidate
from .factory_retention_types import (
    AI_JOB_ACTIVE_STATES,
    AI_JOB_TERMINAL_STATES,
    AI_REVIEW_HELD_STATES,
    AI_REVIEW_TERMINAL_STATES,
    FACTORY_LOG_ACTIVE_STATES,
    FACTORY_LOG_TERMINAL_STATES,
    FACTORY_METRICS_ARCHIVE_TERMINAL_STATES,
    RETENTION_JOURNAL_TERMINAL_STATES,
    ReasonCode,
)


def protected_reasons(
    candidates: tuple[ArtifactCandidate, ...],
    groups: dict[str, tuple[ArtifactCandidate, ...]],
) -> dict[str, ReasonCode]:
    reasons: dict[str, ReasonCode] = {}
    for item in candidates:
        reason = _direct_protection(item)
        if reason is not None:
            reasons[item.artifact_id] = reason
    for members in groups.values():
        if any(item.artifact_id in reasons for item in members):
            for item in members:
                _ = reasons.setdefault(item.artifact_id, "protected_bundle")
    return reasons


def _direct_protection(candidate: ArtifactCandidate) -> ReasonCode | None:
    if not candidate.metadata_valid:
        return "protected_malformed_metadata"
    if candidate.reservation_id is not None:
        if candidate.settlement_state is None:
            return "protected_missing_settlement"
        if candidate.settlement_state == "unresolved":
            return "protected_unresolved_settlement"
        if candidate.settlement_state == "unknown":
            return "protected_unknown_settlement"
    if candidate.artifact_class == "ai_job":
        if candidate.state in AI_JOB_ACTIVE_STATES:
            return "protected_active_state"
        return None if candidate.state in AI_JOB_TERMINAL_STATES else "protected_unknown_state"
    if candidate.artifact_class == "ai_review":
        review_state = candidate.inbox_status or candidate.state
        if review_state in AI_REVIEW_HELD_STATES:
            return "protected_review_state"
        if review_state not in AI_REVIEW_TERMINAL_STATES:
            return "protected_unknown_state"
        if review_state == "accepted":
            if any(item.state == "open" for item in candidate.references):
                return "protected_open_reference"
            if any(item.state == "unknown" for item in candidate.references):
                return "protected_unknown_reference"
        return None
    if candidate.artifact_class == "factory_log":
        if candidate.state in FACTORY_LOG_ACTIVE_STATES:
            return "protected_active_state"
        terminal_states = FACTORY_LOG_TERMINAL_STATES
    elif candidate.artifact_class == "factory_metrics_archive":
        terminal_states = FACTORY_METRICS_ARCHIVE_TERMINAL_STATES
    else:
        terminal_states = RETENTION_JOURNAL_TERMINAL_STATES
    return None if candidate.state in terminal_states else "protected_unknown_state"
