from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from scripts.factory_issue_selector_models import (
    GitHubSnapshot,
    JsonObject,
    JsonValue,
    ParsedIssue,
    SnapshotMetadata,
    UserEvidence,
)
from scripts.factory_issue_selector_parser import normalize_scope
from scripts.factory_issue_selector_snapshot_evidence import (
    CachedEvidenceError,
    validate_cached_evidence,
)

CACHE_SCHEMA_VERSION = "entroping.factory-issue-snapshot-cache.v1"
MAX_TTL_SECONDS = 300


class SnapshotCodecError(ValueError):
    pass


def encode_snapshot(snapshot: GitHubSnapshot) -> JsonObject:
    _validate_ttl(snapshot.metadata)
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "repo": snapshot.metadata.repo,
        "fetched_at": _iso(snapshot.metadata.fetched_at),
        "expires_at": _iso(snapshot.metadata.expires_at),
        "complete": snapshot.metadata.complete,
        "issues": _json_list(_encode_issue(issue) for issue in snapshot.issues),
        "open_pr_issue_numbers": _json_list(sorted(snapshot.open_pr_issue_numbers)),
        "open_pr_scopes": _json_list(snapshot.open_pr_scopes),
    }


def decode_snapshot(payload: JsonValue, *, expected_repo: str) -> GitHubSnapshot:
    root = _mapping(payload, "cache root")
    expected_keys = {
        "schema_version",
        "repo",
        "fetched_at",
        "expires_at",
        "complete",
        "issues",
        "open_pr_issue_numbers",
        "open_pr_scopes",
    }
    if set(root) != expected_keys or root["schema_version"] != CACHE_SCHEMA_VERSION:
        raise SnapshotCodecError("cache schema is invalid")
    repo = _string(root["repo"], "repo")
    if repo != expected_repo:
        raise SnapshotCodecError("cache repository mismatch")
    metadata = SnapshotMetadata(
        repo=repo,
        fetched_at=_timestamp(root["fetched_at"], "fetched_at"),
        expires_at=_timestamp(root["expires_at"], "expires_at"),
        complete=_boolean(root["complete"], "complete"),
    )
    _validate_ttl(metadata)
    issues = tuple(
        _decode_issue(value) for value in _list(root["issues"], "issues")
    )
    if len({issue.number for issue in issues}) != len(issues):
        raise SnapshotCodecError("cache contains duplicate issue numbers")
    pr_numbers = frozenset(
        _positive_int(value, "open PR issue number")
        for value in _list(root["open_pr_issue_numbers"], "open PR issue numbers")
    )
    pr_scopes = _scopes(root["open_pr_scopes"], "open PR scopes")
    return GitHubSnapshot(
        metadata=metadata,
        issues=tuple(sorted(issues, key=lambda issue: issue.number)),
        open_pr_issue_numbers=pr_numbers,
        open_pr_scopes=pr_scopes,
    )


def _encode_issue(issue: ParsedIssue) -> JsonObject:
    return {
        "number": issue.number,
        "title": issue.title,
        "url": issue.url,
        "state": issue.state,
        "milestone_present": issue.milestone_present,
        "labels": _json_list(issue.labels),
        "assignee_count": issue.assignee_count,
        "sections": _json_list(sorted(issue.sections)),
        "verification_lanes": _json_list(issue.verification_lanes),
        "autonomy_labels": _json_list(issue.autonomy_labels),
        "priority_labels": _json_list(issue.priority_labels),
        "status_labels": _json_list(issue.status_labels),
        "type_labels": _json_list(issue.type_labels),
        "dependency_numbers": _json_list(issue.dependency_numbers),
        "allowed_scopes": _json_list(issue.allowed_scopes),
        "evidence": {
            "valid": issue.evidence.valid,
            "verified": issue.evidence.verified,
            "severity": issue.evidence.severity,
            "warning": issue.evidence.warning,
        },
    }


def _decode_issue(value: JsonValue) -> ParsedIssue:
    item = _mapping(value, "issue")
    expected = {
        "number",
        "title",
        "url",
        "state",
        "milestone_present",
        "labels",
        "assignee_count",
        "sections",
        "verification_lanes",
        "autonomy_labels",
        "priority_labels",
        "status_labels",
        "type_labels",
        "dependency_numbers",
        "allowed_scopes",
        "evidence",
    }
    if set(item) != expected:
        raise SnapshotCodecError("cached issue shape is invalid")
    evidence = _mapping(item["evidence"], "evidence")
    if set(evidence) != {"valid", "verified", "severity", "warning"}:
        raise SnapshotCodecError("cached evidence shape is invalid")
    allowed_scopes = _scopes(item["allowed_scopes"], "allowed scopes")
    labels = _strings(item["labels"], "labels")
    autonomy_labels = _strings(item["autonomy_labels"], "autonomy labels")
    priority_labels = _strings(item["priority_labels"], "priority labels")
    status_labels = _strings(item["status_labels"], "status labels")
    type_labels = _strings(item["type_labels"], "type labels")
    derived_labels = (
        (autonomy_labels, "autonomy:"),
        (priority_labels, "priority:"),
        (status_labels, "status:"),
        (type_labels, "type:"),
    )
    if tuple(sorted(set(labels))) != labels or any(
        values != tuple(label for label in labels if label.startswith(prefix))
        for values, prefix in derived_labels
    ):
        raise SnapshotCodecError("cached issue labels are inconsistent")
    try:
        cached_evidence = validate_cached_evidence(
            UserEvidence(
                valid=_boolean(evidence["valid"], "evidence valid"),
                verified=_boolean(evidence["verified"], "evidence verified"),
                severity=_severity(evidence["severity"]),
                warning=_optional_string(evidence["warning"], "evidence warning"),
            ),
            labels=labels,
        )
    except CachedEvidenceError as exc:
        raise SnapshotCodecError(str(exc)) from exc
    return ParsedIssue(
        number=_positive_int(item["number"], "issue number"),
        title=_string(item["title"], "title"),
        url=_string(item["url"], "url"),
        state=_string(item["state"], "state"),
        milestone_present=_boolean(item["milestone_present"], "milestone"),
        labels=labels,
        assignee_count=_nonnegative_int(item["assignee_count"], "assignee count"),
        sections=frozenset(_strings(item["sections"], "sections")),
        verification_lanes=_strings(item["verification_lanes"], "verification lanes"),
        autonomy_labels=autonomy_labels,
        priority_labels=priority_labels,
        status_labels=status_labels,
        type_labels=type_labels,
        dependency_numbers=tuple(
            _positive_int(number, "dependency number")
            for number in _list(item["dependency_numbers"], "dependencies")
        ),
        allowed_scopes=allowed_scopes,
        evidence=cached_evidence,
    )
def _validate_ttl(metadata: SnapshotMetadata) -> None:
    seconds = (metadata.expires_at - metadata.fetched_at).total_seconds()
    if seconds <= 0 or seconds > MAX_TTL_SECONDS:
        raise SnapshotCodecError("cache TTL must be between 1 and 300 seconds")


def _mapping(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise SnapshotCodecError(f"{label} must be an object")
    return value


def _list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise SnapshotCodecError(f"{label} must be a list")
    return value


def _strings(value: JsonValue, label: str) -> tuple[str, ...]:
    values = _list(value, label)
    if any(not isinstance(item, str) for item in values):
        raise SnapshotCodecError(f"{label} must contain strings")
    return tuple(item for item in values if isinstance(item, str))


def _scopes(value: JsonValue, label: str) -> tuple[str, ...]:
    scopes = _strings(value, label)
    if tuple(sorted(set(scopes))) != scopes or any(
        normalize_scope(scope) != scope for scope in scopes
    ):
        raise SnapshotCodecError(f"{label} are invalid")
    return scopes


def _string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotCodecError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: JsonValue, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _boolean(value: JsonValue, label: str) -> bool:
    if not isinstance(value, bool):
        raise SnapshotCodecError(f"{label} must be a boolean")
    return value


def _positive_int(value: JsonValue, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise SnapshotCodecError(f"{label} must be positive")
    return result


def _nonnegative_int(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SnapshotCodecError(f"{label} must be a non-negative integer")
    return value


def _severity(value: JsonValue) -> Literal["blocker", "major", "minor"] | None:
    if value is None:
        return None
    if value == "blocker":
        return "blocker"
    if value == "major":
        return "major"
    if value == "minor":
        return "minor"
    raise SnapshotCodecError("evidence severity is invalid")


def _timestamp(value: JsonValue, label: str) -> datetime:
    text = _string(value, label)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotCodecError(f"{label} is invalid") from exc
    if result.tzinfo is None:
        raise SnapshotCodecError(f"{label} must be timezone-aware")
    return result


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise SnapshotCodecError("cache timestamps must be timezone-aware")
    return value.isoformat().replace("+00:00", "Z")


def _json_list(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)
