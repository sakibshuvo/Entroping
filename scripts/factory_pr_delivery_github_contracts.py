"""Shared semantic contract types for the GitHub delivery port."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from scripts.factory_pr_delivery_github_models import (
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
)

REPOSITORY = "sakibshuvo/Entroping"


class GitHubDeliveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class GitHubCall:
    operation: str
    repo: str
    issue_number: int | None = None
    pr_number: int | None = None
    head_sha: str | None = None
    body_sha256: str | None = None


class GitHubDeliveryPort(Protocol):
    def observe_issue(self, repo: str, issue_number: int) -> IssueObservation: ...

    def observe_pull_requests(
        self, repo: str, issue_number: int, head_branch: str
    ) -> tuple[PullRequestObservation, ...]: ...

    def create_pull_request(
        self, repo: str, *, title: str, body: str, head_branch: str, base_ref: str
    ) -> PullRequestObservation: ...

    def update_pull_request(
        self, repo: str, *, pr_number: int, title: str, body: str
    ) -> PullRequestObservation: ...

    def observe_pull_request(self, repo: str, pr_number: int) -> PullRequestObservation: ...

    def observe_protection(
        self, repo: str, *, base_ref: str, base_sha: str
    ) -> ProtectionObservation: ...

    def observe_ci(
        self,
        repo: str,
        *,
        pr_number: int,
        head_sha: str,
        protection: ProtectionObservation,
    ) -> CiObservation: ...

    def merge_pull_request(self, repo: str, *, pr_number: int, head_sha: str) -> MergeResult: ...


def digest_body(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()
