from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

SCHEMA_VERSION = "entroping.factory-issue-selection.v1"

type AutonomyTier = Literal["tier-a", "tier-b", "tier-c"]
type VerificationLane = Literal[
    "tiny-docs",
    "docs-guardrail",
    "tests-only",
    "normal-code",
    "security-runtime",
    "release-ci-architecture",
]
type Priority = Literal["priority:p0", "priority:p1", "priority:p2", "priority:p3"]
type SelectionBucket = Literal[
    "priority-p0", "verified-blocker", "verified-p1", "ordinary"
]
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class UserEvidence:
    valid: bool = False
    verified: bool = False
    severity: Literal["blocker", "major", "minor"] | None = None
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedIssue:
    number: int
    title: str
    url: str
    state: str
    milestone_present: bool
    labels: tuple[str, ...]
    assignee_count: int
    sections: frozenset[str]
    verification_lanes: tuple[str, ...]
    autonomy_labels: tuple[str, ...]
    priority_labels: tuple[str, ...]
    status_labels: tuple[str, ...]
    type_labels: tuple[str, ...]
    dependency_numbers: tuple[int, ...]
    allowed_scopes: tuple[str, ...]
    evidence: UserEvidence


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    repo: str
    fetched_at: datetime
    expires_at: datetime
    complete: bool

    def freshness_error(self, as_of: datetime) -> str | None:
        if as_of.tzinfo is None:
            return "as-of-naive"
        if self.fetched_at.tzinfo is None or self.expires_at.tzinfo is None:
            return "snapshot-time-naive"
        if not self.complete:
            return "snapshot-incomplete"
        if self.expires_at <= self.fetched_at:
            return "snapshot-window-invalid"
        if as_of < self.fetched_at:
            return "snapshot-clock-rollback"
        if as_of >= self.expires_at:
            return "snapshot-stale"
        return None

    def to_payload(self) -> JsonObject:
        return {
            "repo": self.repo,
            "fetched_at": _iso_utc(self.fetched_at),
            "expires_at": _iso_utc(self.expires_at),
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class ActiveState:
    complete: bool
    owned_issue_numbers: frozenset[int]
    occupied_scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GitHubSnapshot:
    metadata: SnapshotMetadata
    issues: tuple[ParsedIssue, ...]
    open_pr_issue_numbers: frozenset[int]
    open_pr_scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Rejection:
    issue_number: int
    reason: str

    def to_payload(self) -> JsonObject:
        return {"issue_number": self.issue_number, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class SelectedIssue:
    issue_number: int
    title: str
    url: str
    priority: Priority
    autonomy_tier: AutonomyTier
    verification_lane: VerificationLane
    bucket: SelectionBucket
    allowed_scopes: tuple[str, ...]

    def to_payload(self) -> JsonObject:
        return {
            "issue_number": self.issue_number,
            "title": self.title,
            "url": self.url,
            "priority": self.priority,
            "autonomy_tier": self.autonomy_tier,
            "verification_lane": self.verification_lane,
            "bucket": self.bucket,
            "allowed_scopes": list(self.allowed_scopes),
        }


@dataclass(frozen=True, slots=True)
class SelectionResult:
    status: Literal["selected", "none", "blocked"]
    snapshot: SnapshotMetadata
    selected: SelectedIssue | None = None
    rejections: tuple[Rejection, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def paid_work_authorized(self) -> Literal[False]:
        return False

    def to_payload(self) -> JsonObject:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "paid_work_authorized": False,
            "snapshot": self.snapshot.to_payload(),
            "selected": None if self.selected is None else self.selected.to_payload(),
            "rejections": [item.to_payload() for item in self.rejections],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
