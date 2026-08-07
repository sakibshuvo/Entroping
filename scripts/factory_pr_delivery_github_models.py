"""Typed, value-bounded observations for revision-bound GitHub delivery."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Repo = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")]
Context = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Ref = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
RepoPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1024, pattern=r"^[^\x00-\x1f]+$"),
]

type IssueState = Literal["open", "closed"]
type PullRequestState = Literal["open", "closed", "merged"]
type Mergeable = Literal["MERGEABLE", "CONFLICTING", "UNKNOWN"]
type MergeStateStatus = Literal[
    "CLEAN", "BLOCKED", "UNSTABLE", "DIRTY", "BEHIND", "UNKNOWN"
]
type CheckStatus = Literal[
    "pending",
    "success",
    "failure",
    "cancelled",
    "timed-out",
    "stale",
    "superseded",
    "neutral",
    "skipped",
    "unknown",
]
type DeliveryMergeState = Literal["merged", "already-merged", "rejected", "uncertain"]


class GitHubModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class RequiredCheck(GitHubModel):
    context: Context
    app_id: int | None = Field(default=None, ge=1, le=2_147_483_647)


class IssueObservation(GitHubModel):
    repo: Repo
    number: int = Field(ge=1, le=2_147_483_647)
    state: IssueState
    title: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    labels: tuple[Context, ...]
    body_sha256: Digest
    is_pull_request: bool = False

    @model_validator(mode="after")
    def validate_labels(self) -> Self:
        if tuple(sorted(set(self.labels))) != self.labels:
            raise ValueError("issue labels must be unique and sorted")
        return self


class PullRequestObservation(GitHubModel):
    repo: Repo
    number: int = Field(ge=1, le=2_147_483_647)
    title: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    body_sha256: Digest
    state: PullRequestState
    draft: bool
    head_branch: Ref
    head_sha: Commit
    base_ref: Ref
    base_sha: Commit
    mergeable: Mergeable
    merge_state_status: MergeStateStatus
    changed_files: tuple[RepoPath, ...]
    closing_issue_numbers: tuple[int, ...]
    merged_head: Commit | None = None

    @model_validator(mode="after")
    def validate_collections(self) -> Self:
        if tuple(sorted(set(self.changed_files))) != self.changed_files:
            raise ValueError("PR files must be unique and sorted")
        if tuple(sorted(set(self.closing_issue_numbers))) != self.closing_issue_numbers:
            raise ValueError("PR issue references must be unique and sorted")
        if self.state == "merged" and self.merged_head is None:
            raise ValueError("merged PR must expose its merge head")
        if self.state != "merged" and self.merged_head is not None:
            raise ValueError("unmerged PR must not expose a merge head")
        return self


class CheckObservation(GitHubModel):
    context: Context
    app_id: int | None = Field(default=None, ge=1, le=2_147_483_647)
    status: CheckStatus
    head_sha: Commit
    visible: bool = True


class ProtectionObservation(GitHubModel):
    repo: Repo
    base_ref: Ref
    base_sha: Commit
    required_checks: tuple[RequiredCheck, ...]
    complete: bool
    ruleset_count: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_checks(self) -> Self:
        keys = [(check.context, check.app_id) for check in self.required_checks]
        if tuple(sorted(set(keys))) != tuple(keys):
            raise ValueError("required checks must be unique and sorted")
        if not self.complete or not self.required_checks:
            raise ValueError("protection observation must be complete and nonempty")
        return self

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class CiObservation(GitHubModel):
    repo: Repo
    base_ref: Ref
    base_sha: Commit
    head_sha: Commit
    protection_digest: Digest
    checks: tuple[CheckObservation, ...]
    mergeable: Mergeable
    merge_state_status: MergeStateStatus
    complete: bool


class MergeResult(GitHubModel):
    repo: Repo
    pr_number: int = Field(ge=1, le=2_147_483_647)
    requested_head: Commit
    state: DeliveryMergeState
    merged_head: Commit | None = None

    @model_validator(mode="after")
    def validate_merge(self) -> Self:
        if self.state in {"merged", "already-merged"} and self.merged_head != self.requested_head:
            raise ValueError("successful merge must retain the requested head")
        if self.state in {"rejected", "uncertain"} and self.merged_head is not None:
            raise ValueError("failed merge must not expose a merge head")
        return self


def evaluate_ci(
    protection: ProtectionObservation,
    ci: CiObservation,
) -> tuple[bool, str]:
    """Classify a complete exact-head observation without trusting rollups."""

    if (
        protection.repo != ci.repo
        or protection.base_ref != ci.base_ref
        or protection.base_sha != ci.base_sha
        or protection.digest != ci.protection_digest
        or not ci.complete
    ):
        return False, "observation-drift"
    seen: set[tuple[str, int | None]] = set()
    by_key: dict[tuple[str, int | None], CheckObservation] = {}
    for check in ci.checks:
        key = (check.context, check.app_id)
        if key in seen:
            return False, "duplicate-check"
        seen.add(key)
        by_key[key] = check
        if check.head_sha != ci.head_sha:
            return False, "stale-check"
        if check.visible and check.status not in {"success", "neutral", "skipped"}:
            return False, "visible-check-not-terminal"
    for required in protection.required_checks:
        observed_check = by_key.get((required.context, required.app_id))
        if observed_check is None:
            return False, "required-check-absent"
        if observed_check.status != "success":
            return False, "required-check-not-green"
    if ci.mergeable != "MERGEABLE" or ci.merge_state_status != "CLEAN":
        return False, "merge-not-eligible"
    return True, "ready"
