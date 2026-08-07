"""Deterministic semantic fake for the GitHub delivery port."""

from __future__ import annotations

from scripts.factory_pr_delivery_github_contracts import (
    GitHubCall,
    GitHubDeliveryError,
    digest_body,
)
from scripts.factory_pr_delivery_github_models import (
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
)


class ScriptedGitHubDeliveryPort:
    """Call records contain digests and identifiers, never PR body text."""

    def __init__(
        self,
        *,
        issue: IssueObservation,
        pull_requests: tuple[PullRequestObservation, ...] = (),
        created: PullRequestObservation | None = None,
        updated: PullRequestObservation | None = None,
        protection: ProtectionObservation,
        ci: CiObservation,
        merge: MergeResult,
    ) -> None:
        self.issue = issue
        self.pull_requests = pull_requests
        self.created = created
        self.updated = updated
        self.protection = protection
        self.ci = ci
        self.merge = merge
        self.calls: list[GitHubCall] = []

    def observe_issue(self, repo: str, issue_number: int) -> IssueObservation:
        self.calls.append(GitHubCall("observe-issue", repo, issue_number=issue_number))
        return self.issue

    def observe_pull_requests(
        self, repo: str, issue_number: int, head_branch: str
    ) -> tuple[PullRequestObservation, ...]:
        self.calls.append(GitHubCall("observe-prs", repo, issue_number=issue_number))
        return tuple(
            pull
            for pull in self.pull_requests
            if issue_number in pull.closing_issue_numbers and pull.head_branch == head_branch
        )

    def create_pull_request(
        self, repo: str, *, title: str, body: str, head_branch: str, base_ref: str
    ) -> PullRequestObservation:
        self.calls.append(GitHubCall("create-pr", repo, body_sha256=digest_body(body)))
        if self.created is None:
            raise GitHubDeliveryError("create-rejected")
        return self.created

    def update_pull_request(
        self, repo: str, *, pr_number: int, title: str, body: str
    ) -> PullRequestObservation:
        self.calls.append(
            GitHubCall("update-pr", repo, pr_number=pr_number, body_sha256=digest_body(body))
        )
        if self.updated is None:
            raise GitHubDeliveryError("update-rejected")
        return self.updated

    def observe_pull_request(self, repo: str, pr_number: int) -> PullRequestObservation:
        self.calls.append(GitHubCall("observe-pr", repo, pr_number=pr_number))
        for pull in (*self.pull_requests, self.created, self.updated):
            if pull is not None and pull.number == pr_number:
                return pull
        raise GitHubDeliveryError("pr-not-found")

    def observe_protection(
        self, repo: str, *, base_ref: str, base_sha: str
    ) -> ProtectionObservation:
        self.calls.append(GitHubCall("observe-protection", repo, head_sha=base_sha))
        return self.protection

    def observe_ci(
        self,
        repo: str,
        *,
        pr_number: int,
        head_sha: str,
        protection: ProtectionObservation,
    ) -> CiObservation:
        self.calls.append(GitHubCall("observe-ci", repo, pr_number=pr_number, head_sha=head_sha))
        return self.ci

    def merge_pull_request(self, repo: str, *, pr_number: int, head_sha: str) -> MergeResult:
        self.calls.append(GitHubCall("merge-pr", repo, pr_number=pr_number, head_sha=head_sha))
        return self.merge
