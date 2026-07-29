from __future__ import annotations

from datetime import datetime
from typing import Final

from scripts.factory_issue_selector_models import (
    ActiveState,
    AutonomyTier,
    ParsedIssue,
    Priority,
    Rejection,
    SelectedIssue,
    SelectionBucket,
    SelectionResult,
    SnapshotMetadata,
    VerificationLane,
)
from scripts.factory_issue_selector_parser import (
    INVALID_DEPENDENCIES_SECTION,
    scopes_overlap,
)

_REQUIRED_SECTIONS: Final = frozenset(
    {"outcome", "scope", "non-goals", "acceptance criteria", "verification", "autonomy"}
)
_REASON_ORDER: Final = (
    "issue-not-open",
    "missing-milestone",
    "invalid-type-label",
    "invalid-priority-label",
    "invalid-status-label",
    "invalid-autonomy-label",
    "autonomy-ceiling-exceeded",
    "missing-required-section",
    "invalid-dependencies",
    "invalid-verification-lane",
    "assignee-owned",
    "active-ownership",
    "ambiguous-file-scope",
    "overlapping-file-scope",
    "unresolved-dependency",
)
_REASON_RANK: Final = {reason: index for index, reason in enumerate(_REASON_ORDER)}
_TIER_RANK: Final = {"tier-a": 0, "tier-b": 1, "tier-c": 2}
_PRIORITY_RANK: Final = {
    "priority:p0": 0,
    "priority:p1": 1,
    "priority:p2": 2,
    "priority:p3": 3,
}
_TYPE_LABELS: Final = frozenset(
    {
        "type:architecture",
        "type:bug",
        "type:docs",
        "type:feature",
        "type:regression",
        "type:security",
        "type:tests",
    }
)


def select_issue(
    *,
    issues: tuple[ParsedIssue, ...],
    snapshot: SnapshotMetadata,
    active: ActiveState,
    as_of: datetime,
    autonomy_ceiling: str,
) -> SelectionResult:
    freshness_error = snapshot.freshness_error(as_of)
    if freshness_error is not None:
        return _blocked(snapshot, freshness_error)
    if not active.complete:
        return _blocked(snapshot, "active-state-incomplete")
    ceiling = _autonomy_tier(autonomy_ceiling)
    if ceiling is None:
        return _blocked(snapshot, "autonomy-ceiling-invalid")

    states = {issue.number: issue.state for issue in issues}
    rejections: list[Rejection] = []
    candidates: list[SelectedIssue] = []
    warnings: list[str] = []
    for issue in sorted(issues, key=lambda item: item.number):
        reasons = _reasons(issue, states=states, active=active, ceiling=ceiling)
        rejections.extend(Rejection(issue.number, reason) for reason in reasons)
        if issue.evidence.warning is not None:
            warnings.append(f"issue-{issue.number}:{issue.evidence.warning}")
        if reasons:
            continue
        selected = _candidate(issue)
        if selected is not None:
            candidates.append(selected)

    candidates.sort(key=_selection_key)
    rejections.sort(key=lambda item: (item.issue_number, _REASON_RANK[item.reason]))
    selected = candidates[0] if candidates else None
    return SelectionResult(
        status="selected" if selected is not None else "none",
        snapshot=snapshot,
        selected=selected,
        rejections=tuple(rejections),
        warnings=tuple(warnings),
    )


def _reasons(
    issue: ParsedIssue,
    *,
    states: dict[int, str],
    active: ActiveState,
    ceiling: AutonomyTier,
) -> tuple[str, ...]:
    reasons: list[str] = []
    _append_if(reasons, issue.state != "OPEN", "issue-not-open")
    _append_if(reasons, not issue.milestone_present, "missing-milestone")
    _append_if(
        reasons,
        len(issue.type_labels) != 1 or issue.type_labels[0] not in _TYPE_LABELS,
        "invalid-type-label",
    )
    _append_if(reasons, _priority(issue) is None, "invalid-priority-label")
    _append_if(
        reasons,
        issue.status_labels != ("status:ready",),
        "invalid-status-label",
    )
    tier = _issue_tier(issue)
    _append_if(reasons, tier is None, "invalid-autonomy-label")
    _append_if(
        reasons,
        tier is not None and _TIER_RANK[tier] > _TIER_RANK[ceiling],
        "autonomy-ceiling-exceeded",
    )
    _append_if(
        reasons,
        not _REQUIRED_SECTIONS.issubset(issue.sections),
        "missing-required-section",
    )
    _append_if(
        reasons,
        INVALID_DEPENDENCIES_SECTION in issue.sections,
        "invalid-dependencies",
    )
    _append_if(reasons, _verification_lane(issue) is None, "invalid-verification-lane")
    _append_if(reasons, issue.assignee_count > 0, "assignee-owned")
    _append_if(
        reasons,
        issue.number in active.owned_issue_numbers,
        "active-ownership",
    )
    _append_if(reasons, not issue.allowed_scopes, "ambiguous-file-scope")
    _append_if(
        reasons,
        any(
            scopes_overlap(scope, occupied)
            for scope in issue.allowed_scopes
            for occupied in active.occupied_scopes
        ),
        "overlapping-file-scope",
    )
    _append_if(
        reasons,
        any(states.get(number) != "CLOSED" for number in issue.dependency_numbers),
        "unresolved-dependency",
    )
    return tuple(reasons)


def _candidate(issue: ParsedIssue) -> SelectedIssue | None:
    priority = _priority(issue)
    tier = _issue_tier(issue)
    lane = _verification_lane(issue)
    if priority is None or tier is None or lane is None:
        return None
    return SelectedIssue(
        issue_number=issue.number,
        title=issue.title,
        url=issue.url,
        priority=priority,
        autonomy_tier=tier,
        verification_lane=lane,
        bucket=_bucket(issue, priority),
        allowed_scopes=issue.allowed_scopes,
    )


def _bucket(issue: ParsedIssue, priority: Priority) -> SelectionBucket:
    if priority == "priority:p0":
        return "priority-p0"
    if (
        issue.evidence.valid
        and issue.evidence.verified
        and issue.evidence.severity == "blocker"
    ):
        return "verified-blocker"
    if issue.evidence.valid and issue.evidence.verified and priority == "priority:p1":
        return "verified-p1"
    return "ordinary"


def _selection_key(issue: SelectedIssue) -> tuple[int, int, int]:
    buckets = {
        "priority-p0": 0,
        "verified-blocker": 1,
        "verified-p1": 2,
        "ordinary": 3,
    }
    return buckets[issue.bucket], _PRIORITY_RANK[issue.priority], issue.issue_number


def _priority(issue: ParsedIssue) -> Priority | None:
    if len(issue.priority_labels) != 1:
        return None
    value = issue.priority_labels[0]
    if value == "priority:p0":
        return "priority:p0"
    if value == "priority:p1":
        return "priority:p1"
    if value == "priority:p2":
        return "priority:p2"
    if value == "priority:p3":
        return "priority:p3"
    return None


def _issue_tier(issue: ParsedIssue) -> AutonomyTier | None:
    if len(issue.autonomy_labels) != 1:
        return None
    return _autonomy_tier(issue.autonomy_labels[0].removeprefix("autonomy:"))


def _autonomy_tier(value: str) -> AutonomyTier | None:
    if value == "tier-a":
        return "tier-a"
    if value == "tier-b":
        return "tier-b"
    if value == "tier-c":
        return "tier-c"
    return None


def _verification_lane(issue: ParsedIssue) -> VerificationLane | None:
    if len(issue.verification_lanes) != 1:
        return None
    value = issue.verification_lanes[0]
    if value == "tiny-docs":
        return "tiny-docs"
    if value == "docs-guardrail":
        return "docs-guardrail"
    if value == "tests-only":
        return "tests-only"
    if value == "normal-code":
        return "normal-code"
    if value == "security-runtime":
        return "security-runtime"
    if value == "release-ci-architecture":
        return "release-ci-architecture"
    return None


def _append_if(reasons: list[str], condition: bool, reason: str) -> None:
    if condition:
        reasons.append(reason)


def _blocked(snapshot: SnapshotMetadata, error: str) -> SelectionResult:
    return SelectionResult(status="blocked", snapshot=snapshot, errors=(error,))
