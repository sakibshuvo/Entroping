"""Protection, CI, and merge operations shared by GitHub delivery adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from scripts.factory_issue_selector_models import JsonObject, JsonValue
from scripts.factory_pr_delivery_github_contracts import GitHubDeliveryError
from scripts.factory_pr_delivery_github_io import int_field, list_field, require_object
from scripts.factory_pr_delivery_github_models import (
    CiObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
)
from scripts.factory_pr_delivery_github_parsers import (
    parse_branch_checks,
    parse_check,
    parse_pull_request,
    parse_ruleset_checks,
)


class _Transport(Protocol):
    _cwd: Path

    def _json(self, args: tuple[str, ...]) -> JsonValue: ...

    def _text(self, args: tuple[str, ...]) -> str: ...

    @staticmethod
    def _require_repo(repo: str) -> None: ...

    def observe_pull_request(self, repo: str, pr_number: int) -> PullRequestObservation: ...

    def _reconcile_merge(
        self,
        repo: str,
        pr_number: int,
        head_sha: str,
        *,
        accepted: bool = False,
    ) -> MergeResult: ...


class GitHubDeliveryOperations:
    def observe_protection(
        self: _Transport,
        repo: str,
        *,
        base_ref: str,
        base_sha: str,
    ) -> ProtectionObservation:
        self._require_repo(repo)
        branch = require_object(
            self._json(("api", f"repos/{repo}/branches/{base_ref}/protection"))
        )
        summaries = self._json(("api", f"repos/{repo}/rulesets?per_page=100"))
        if not isinstance(summaries, list) or len(summaries) >= 100:
            raise GitHubDeliveryError("protection-incomplete")
        details: list[JsonObject] = []
        for summary in summaries:
            ruleset_id = int_field(require_object(summary), "id")
            details.append(
                require_object(self._json(("api", f"repos/{repo}/rulesets/{ruleset_id}")))
            )
        required = parse_branch_checks(branch) + parse_ruleset_checks(details)
        if not required:
            raise GitHubDeliveryError("protection-incomplete")
        keys = [(check.context, check.app_id) for check in required]
        if len(set(keys)) != len(keys):
            raise GitHubDeliveryError("protection-duplicate-check")
        ordered = tuple(sorted(required, key=lambda check: (check.context, check.app_id or 0)))
        return ProtectionObservation(
            repo=repo,
            base_ref=base_ref,
            base_sha=base_sha,
            required_checks=ordered,
            complete=True,
            ruleset_count=len(summaries),
        )

    def observe_ci(
        self: _Transport,
        repo: str,
        *,
        pr_number: int,
        head_sha: str,
        protection: ProtectionObservation,
    ) -> CiObservation:
        self._require_repo(repo)
        pull = self.observe_pull_request(repo, pr_number)
        if pull.head_sha != head_sha:
            raise GitHubDeliveryError("pr-head-drift")
        payload = require_object(
            self._json(("api", f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100"))
        )
        total = int_field(payload, "total_count", minimum=0)
        raw_checks = list_field(payload, "check_runs")
        if total != len(raw_checks) or total >= 100:
            raise GitHubDeliveryError("ci-incomplete")
        checks_list = []
        for item in raw_checks:
            if not isinstance(item, dict):
                raise GitHubDeliveryError("github-response-invalid")
            checks_list.append(parse_check(item, head_sha))
        return CiObservation(
            repo=repo,
            base_ref=pull.base_ref,
            base_sha=pull.base_sha,
            head_sha=head_sha,
            protection_digest=protection.digest,
            checks=tuple(checks_list),
            mergeable=pull.mergeable,
            merge_state_status=pull.merge_state_status,
            complete=True,
        )

    def merge_pull_request(
        self: _Transport,
        repo: str,
        *,
        pr_number: int,
        head_sha: str,
    ) -> MergeResult:
        self._require_repo(repo)
        try:
            self._text(
                (
                    "pr",
                    "merge",
                    str(pr_number),
                    "--repo",
                    repo,
                    "--merge",
                    "--match-head-commit",
                    head_sha,
                )
            )
        except GitHubDeliveryError:
            return self._reconcile_merge(repo, pr_number, head_sha)
        return self._reconcile_merge(repo, pr_number, head_sha, accepted=True)

    def _reconcile_merge(
        self: _Transport,
        repo: str,
        pr_number: int,
        head_sha: str,
        *,
        accepted: bool = False,
    ) -> MergeResult:
        try:
            observed = self.observe_pull_request(repo, pr_number)
        except GitHubDeliveryError:
            return MergeResult(
                repo=repo,
                pr_number=pr_number,
                requested_head=head_sha,
                state="uncertain",
            )
        if observed.state == "merged" and observed.merged_head == head_sha:
            return MergeResult(
                repo=repo,
                pr_number=pr_number,
                requested_head=head_sha,
                state="merged" if accepted else "already-merged",
                merged_head=head_sha,
            )
        return MergeResult(
            repo=repo,
            pr_number=pr_number,
            requested_head=head_sha,
            state="rejected",
        )

    def _list_open_pull_requests(
        self: _Transport,
        repo: str,
        head_branch: str,
        fields: str,
    ) -> tuple[PullRequestObservation, ...]:
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
                fields,
            )
        )
        if not isinstance(value, list) or len(value) >= 100:
            raise GitHubDeliveryError("pr-list-incomplete")
        pulls = tuple(parse_pull_request(repo, item) for item in value)
        return tuple(pull for pull in pulls if pull.head_branch == head_branch)
