from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from .factory_retention_models import (
    ArtifactCandidate,
    ClassRetentionSummary,
    RetentionDecision,
    RetentionPlanReport,
    RetentionPolicy,
)
from .factory_retention_protection import protected_reasons
from .factory_retention_types import (
    MANAGED_CLASSES,
    PLANNER_SCHEMA_VERSION,
    PROTECTED_REASONS,
    ArtifactClass,
    DecisionAction,
    ReasonCode,
)


def plan_retention(
    policy: RetentionPolicy,
    candidates: tuple[ArtifactCandidate, ...],
    as_of: datetime,
) -> RetentionPlanReport:
    normalized_as_of = _normalize_as_of(as_of)
    _validate_candidate_uniqueness(candidates)
    policy_by_class = {item.artifact_class: item for item in policy.class_policies}
    ordered = tuple(sorted(candidates, key=_candidate_sort_key))
    groups = _candidate_groups(ordered)
    retained_reasons = protected_reasons(ordered, groups)
    deleted_reasons: dict[str, ReasonCode] = {}

    safe_groups = tuple(
        members
        for _, members in sorted(groups.items())
        if not any(item.artifact_id in retained_reasons for item in members)
    )
    for members in safe_groups:
        if all(
            item.created_at
            < _age_cutoff(
                normalized_as_of,
                policy_by_class[item.artifact_class].max_age_days_for(_retention_state(item)),
            )
            for item in members
        ):
            for item in members:
                deleted_reasons[item.artifact_id] = "delete_by_age"

    retained_bytes = _class_bytes(ordered, deleted_reasons)
    remaining_groups = tuple(
        members
        for members in safe_groups
        if not any(item.artifact_id in deleted_reasons for item in members)
    )
    for members in sorted(remaining_groups, key=_group_sort_key):
        pressured = {
            artifact_class
            for artifact_class in MANAGED_CLASSES
            if retained_bytes[artifact_class] > policy_by_class[artifact_class].byte_ceiling
        }
        if not pressured:
            break
        if not any(item.artifact_class in pressured for item in members):
            continue
        for item in members:
            deleted_reasons[item.artifact_id] = "delete_by_byte_cap"
            retained_bytes[item.artifact_class] -= item.byte_size

    decisions = tuple(
        sorted(
            (
                _decision(
                    item,
                    deleted_reasons.get(item.artifact_id),
                    retained_reasons.get(item.artifact_id),
                )
                for item in ordered
            ),
            key=_decision_sort_key,
        )
    )
    summaries = tuple(
        _class_summary(
            artifact_class,
            {
                item.state: item.max_age_days
                for item in policy_by_class[artifact_class].state_policies
            },
            policy_by_class[artifact_class].byte_ceiling,
            decisions,
        )
        for artifact_class in MANAGED_CLASSES
    )
    deleted = tuple(item for item in decisions if item.action == "delete")
    retained = tuple(item for item in decisions if item.action == "retain")
    return RetentionPlanReport(
        schema_version=PLANNER_SCHEMA_VERSION,
        as_of=normalized_as_of,
        total_candidate_count=len(decisions),
        total_retain_count=len(retained),
        total_delete_count=len(deleted),
        total_retain_bytes=sum(item.byte_size for item in retained),
        total_delete_bytes=sum(item.byte_size for item in deleted),
        decisions=decisions,
        class_summaries=summaries,
    )


def _candidate_groups(
    candidates: tuple[ArtifactCandidate, ...],
) -> dict[str, tuple[ArtifactCandidate, ...]]:
    grouped: defaultdict[str, list[ArtifactCandidate]] = defaultdict(list)
    for item in candidates:
        grouped[item.bundle_id].append(item)
    return {
        bundle_id: tuple(sorted(members, key=_candidate_sort_key))
        for bundle_id, members in grouped.items()
    }


def _class_bytes(
    candidates: tuple[ArtifactCandidate, ...],
    deleted_reasons: dict[str, ReasonCode],
) -> dict[ArtifactClass, int]:
    result: dict[ArtifactClass, int] = {artifact_class: 0 for artifact_class in MANAGED_CLASSES}
    for item in candidates:
        if item.artifact_id not in deleted_reasons:
            result[item.artifact_class] += item.byte_size
    return result


def _class_summary(
    artifact_class: ArtifactClass,
    state_max_age_days: dict[str, int],
    byte_ceiling: int,
    decisions: tuple[RetentionDecision, ...],
) -> ClassRetentionSummary:
    class_decisions = tuple(item for item in decisions if item.artifact_class == artifact_class)
    deleted = tuple(item for item in class_decisions if item.action == "delete")
    retained = tuple(item for item in class_decisions if item.action == "retain")
    protected = tuple(item for item in retained if item.reason_code in PROTECTED_REASONS)
    retained_bytes = sum(item.byte_size for item in retained)
    return ClassRetentionSummary(
        artifact_class=artifact_class,
        state_max_age_days=state_max_age_days,
        byte_ceiling=byte_ceiling,
        candidate_count=len(class_decisions),
        deleted_count=len(deleted),
        retained_count=len(retained),
        deleted_bytes=sum(item.byte_size for item in deleted),
        retained_bytes=retained_bytes,
        protected_count=len(protected),
        protected_bytes=sum(item.byte_size for item in protected),
        pressure_bytes=max(0, retained_bytes - byte_ceiling),
    )


def _decision(
    candidate: ArtifactCandidate,
    delete_reason: ReasonCode | None,
    retain_reason: ReasonCode | None,
) -> RetentionDecision:
    action: DecisionAction = "delete" if delete_reason is not None else "retain"
    reason = delete_reason or retain_reason or "age_not_reached"
    return RetentionDecision(
        action=action,
        reason_code=reason,
        artifact_id=candidate.artifact_id,
        bundle_id=candidate.bundle_id,
        artifact_class=candidate.artifact_class,
        relative_path=candidate.relative_path,
        byte_size=candidate.byte_size,
        created_at=candidate.created_at,
    )


def _validate_candidate_uniqueness(candidates: tuple[ArtifactCandidate, ...]) -> None:
    if len({item.artifact_id for item in candidates}) != len(candidates):
        raise ValueError("duplicate candidate id detected")
    if len({item.relative_path for item in candidates}) != len(candidates):
        raise ValueError("duplicate candidate path detected")


def _retention_state(candidate: ArtifactCandidate) -> str:
    if candidate.artifact_class == "ai_review":
        return candidate.inbox_status or candidate.state
    return candidate.state


def _normalize_as_of(as_of: datetime) -> datetime:
    if as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
        raise ValueError("as_of must be UTC")
    return as_of.astimezone(UTC)


def _age_cutoff(as_of: datetime, max_age_days: int) -> datetime:
    try:
        return as_of - timedelta(days=max_age_days)
    except (OverflowError, ValueError) as exc:
        raise ValueError("retention age exceeds the supported datetime range") from exc


def _candidate_sort_key(candidate: ArtifactCandidate) -> tuple[datetime, str, str]:
    return candidate.created_at, candidate.relative_path, candidate.artifact_id


def _group_sort_key(
    candidates: tuple[ArtifactCandidate, ...],
) -> tuple[datetime, str, str]:
    first = min(candidates, key=_candidate_sort_key)
    return _candidate_sort_key(first)


def _decision_sort_key(decision: RetentionDecision) -> tuple[int, datetime, str, str]:
    return (
        0 if decision.action == "delete" else 1,
        decision.created_at,
        decision.relative_path,
        decision.artifact_id,
    )
