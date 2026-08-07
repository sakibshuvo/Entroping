"""Production GitHub adapter for revision-bound delivery."""

from __future__ import annotations

from pathlib import Path

from scripts.factory_issue_selector_models import JsonValue
from scripts.factory_pr_delivery_github_contracts import (
    REPOSITORY,
    GitHubCall,
    GitHubDeliveryError,
    GitHubDeliveryPort,
    digest_body,
)
from scripts.factory_pr_delivery_github_io import (
    GitHubTransportError,
    require_object,
    run_gh_json,
    trusted_gh_contract,
    validate_argument,
)
from scripts.factory_pr_delivery_github_models import (
    CheckObservation,
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
    RequiredCheck,
)
from scripts.factory_pr_delivery_github_operations import GitHubDeliveryOperations
from scripts.factory_pr_delivery_github_parsers import parse_issue, parse_pull_request
from scripts.factory_pr_delivery_github_scripted import ScriptedGitHubDeliveryPort

__all__ = [
    "GitHubCall",
    "GitHubDeliveryError",
    "GitHubDeliveryPort",
    "REPOSITORY",
    "GhGitHubDeliveryPort",
    "ScriptedGitHubDeliveryPort",
    "CheckObservation",
    "CiObservation",
    "IssueObservation",
    "MergeResult",
    "ProtectionObservation",
    "PullRequestObservation",
    "RequiredCheck",
]

_PR_FIELDS = (
    "number,title,body,state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,"
    "mergeable,mergeStateStatus,files,closingIssuesReferences,mergeCommit"
)


class GhGitHubDeliveryPort(GitHubDeliveryOperations):
    def __init__(self, *, cwd: Path) -> None:
        try:
            self._executable, self._environment = trusted_gh_contract()
        except GitHubTransportError as exc:
            raise GitHubDeliveryError(exc.code) from None
        self._cwd = cwd

    def observe_issue(self, repo: str, issue_number: int) -> IssueObservation:
        self._require_repo(repo)
        payload = require_object(self._json(("api", f"repos/{repo}/issues/{issue_number}")))
        observation = parse_issue(repo, payload)
        if observation.number != issue_number:
            raise GitHubDeliveryError("issue-identity-mismatch")
        return observation

    def observe_pull_requests(
        self, repo: str, issue_number: int, head_branch: str
    ) -> tuple[PullRequestObservation, ...]:
        self._require_repo(repo)
        value = self._json(
            (
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "100",
                "--json",
                _PR_FIELDS,
            )
        )
        if not isinstance(value, list) or len(value) >= 100:
            raise GitHubDeliveryError("pr-list-incomplete")
        pulls = tuple(parse_pull_request(repo, item) for item in value)
        return tuple(
            pull
            for pull in pulls
            if issue_number in pull.closing_issue_numbers and pull.head_branch == head_branch
        )

    def create_pull_request(
        self, repo: str, *, title: str, body: str, head_branch: str, base_ref: str
    ) -> PullRequestObservation:
        self._require_repo(repo)
        validate_argument(title, max_bytes=1024)
        validate_argument(body, max_bytes=65_536, allow_newlines=True)
        self._text(
            (
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base_ref,
                "--head",
                head_branch,
                "--title",
                title,
                "--body",
                body,
            )
        )
        matches = tuple(
            pull
            for pull in self._list_open_pull_requests(repo, head_branch, _PR_FIELDS)
            if pull.title == title and pull.body_sha256 == digest_body(body)
        )
        if len(matches) != 1:
            raise GitHubDeliveryError("pr-create-reconciliation")
        return matches[0]

    def update_pull_request(
        self, repo: str, *, pr_number: int, title: str, body: str
    ) -> PullRequestObservation:
        self._require_repo(repo)
        validate_argument(title, max_bytes=1024)
        validate_argument(body, max_bytes=65_536, allow_newlines=True)
        self._text(
            (
                "pr",
                "edit",
                str(pr_number),
                "--repo",
                repo,
                "--title",
                title,
                "--body",
                body,
            )
        )
        return self.observe_pull_request(repo, pr_number)

    def observe_pull_request(self, repo: str, pr_number: int) -> PullRequestObservation:
        self._require_repo(repo)
        payload = require_object(
            self._json(("pr", "view", str(pr_number), "--repo", repo, "--json", _PR_FIELDS))
        )
        observation = parse_pull_request(repo, payload)
        if observation.number != pr_number:
            raise GitHubDeliveryError("pr-identity-mismatch")
        return observation

    def _json(self, args: tuple[str, ...]) -> JsonValue:
        try:
            return run_gh_json(self._executable, self._environment, args, cwd=self._cwd)
        except GitHubTransportError as exc:
            raise GitHubDeliveryError(exc.code) from None

    def _text(self, args: tuple[str, ...]) -> str:
        from scripts.factory_pr_delivery_github_io import run_gh_text

        try:
            return run_gh_text(self._executable, self._environment, args, cwd=self._cwd)
        except GitHubTransportError as exc:
            raise GitHubDeliveryError(exc.code) from None

    @staticmethod
    def _require_repo(repo: str) -> None:
        if repo != REPOSITORY:
            raise GitHubDeliveryError("repository-mismatch")
