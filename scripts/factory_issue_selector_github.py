from __future__ import annotations

import os
import pwd
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

from scripts.bounded_process import (
    BoundedProcessError,
)
from scripts.bounded_process import (
    run_bounded_process as run_subprocess,
)
from scripts.factory_issue_selector_json import JsonBoundaryError, decode_json
from scripts.factory_issue_selector_models import (
    GitHubSnapshot,
    JsonObject,
    JsonValue,
    ParsedIssue,
    SnapshotMetadata,
)
from scripts.factory_issue_selector_parser import (
    IssueParseError,
    normalize_scope,
    parse_issue,
)
from scripts.factory_issue_selector_snapshot import MAX_TTL_SECONDS
from scripts.factory_orchestration_errors import OrchestrationServiceError
from scripts.factory_orchestration_tools import trusted_executable

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_GITHUB_BYTES = 5_000_000
_ISSUE_PROJECTION = (
    '.[] | ({number,title,state,html_url,body,labels:[.labels[]|{name}],'
    "assignees:[.assignees[]|{}],"
    "milestone:(if .milestone == null then null else {} end)} + "
    '(if has("pull_request") then {pull_request:{}} else {} end))'
)


class GitHubStateError(ValueError):
    pass


def refresh_snapshot(
    *, repo: str, as_of: datetime, ttl_seconds: int
) -> GitHubSnapshot:
    _validate_request(repo=repo, as_of=as_of, ttl_seconds=ttl_seconds)
    gh, environment = _trusted_gh_contract()
    issue_items = _request_items(
        f"repos/{repo}/issues?state=all&per_page=100",
        projection=_ISSUE_PROJECTION,
        gh=gh,
        environment=environment,
    )
    pull_items = _request_pull_items(repo, gh=gh, environment=environment)

    issues_by_number: dict[int, ParsedIssue] = {}
    try:
        for item in issue_items:
            if "pull_request" in item:
                continue
            issue = parse_issue(item)
            if issue.number in issues_by_number:
                raise GitHubStateError("github-snapshot-incomplete")
            issues_by_number[issue.number] = issue
    except IssueParseError as exc:
        raise GitHubStateError("github-snapshot-incomplete") from exc

    complete = len(pull_items) < 1000
    open_pr_issue_numbers: set[int] = set()
    open_pr_scopes: set[str] = set()
    for pull in pull_items:
        references = _pull_issue_numbers(pull)
        scopes = _pull_scopes(pull)
        automated = _pull_is_bot(pull)
        if (
            references is None
            or scopes is None
            or automated is None
            or (not references and not automated)
        ):
            complete = False
            continue
        open_pr_issue_numbers.update(references)
        open_pr_scopes.update(scopes)

    known_numbers = set(issues_by_number)
    if not open_pr_issue_numbers.issubset(known_numbers):
        complete = False
    if any(
        dependency not in known_numbers
        for issue in issues_by_number.values()
        for dependency in issue.dependency_numbers
    ):
        complete = False

    return GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo=repo,
            fetched_at=as_of,
            expires_at=as_of + timedelta(seconds=ttl_seconds),
            complete=complete,
        ),
        issues=tuple(sorted(issues_by_number.values(), key=lambda issue: issue.number)),
        open_pr_issue_numbers=frozenset(open_pr_issue_numbers),
        open_pr_scopes=tuple(sorted(open_pr_scopes)),
    )


def _request_items(
    endpoint: str,
    *,
    projection: str,
    gh: Path,
    environment: Mapping[str, str],
) -> tuple[JsonObject, ...]:
    try:
        completed = run_subprocess(
            [gh, "api", "--paginate", endpoint, "--jq", projection],
            cwd=Path.cwd(),
            timeout_seconds=20,
            max_output_bytes=_MAX_GITHUB_BYTES,
            env=environment,
        )
    except BoundedProcessError as exc:
        raise GitHubStateError("github-refresh-failed") from exc
    if completed.timed_out:
        raise GitHubStateError("github-refresh-failed")
    if completed.output_limit_exceeded:
        raise GitHubStateError("github-snapshot-incomplete")
    combined = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode != 0:
        reason = (
            "github-rate-limited"
            if "rate limit" in combined
            else "github-refresh-failed"
        )
        raise GitHubStateError(reason)
    values: list[JsonValue] = []
    try:
        for line in completed.stdout.splitlines():
            if line.strip():
                value = decode_json(line)
                values.append(value)
    except (JsonBoundaryError, GitHubStateError) as exc:
        raise GitHubStateError("github-snapshot-incomplete") from exc
    return tuple(_flatten_values(values))


def _request_pull_items(
    repo: str,
    *,
    gh: Path,
    environment: Mapping[str, str],
) -> tuple[JsonObject, ...]:
    try:
        completed = run_subprocess(
            [
                gh,
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "1000",
                "--json",
                "number,author,files,closingIssuesReferences",
            ],
            cwd=Path.cwd(),
            timeout_seconds=20,
            max_output_bytes=_MAX_GITHUB_BYTES,
            env=environment,
        )
    except BoundedProcessError as exc:
        raise GitHubStateError("github-refresh-failed") from exc
    if completed.timed_out:
        raise GitHubStateError("github-refresh-failed")
    if completed.output_limit_exceeded:
        raise GitHubStateError("github-snapshot-incomplete")
    combined = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode != 0:
        reason = (
            "github-rate-limited"
            if "rate limit" in combined
            else "github-refresh-failed"
        )
        raise GitHubStateError(reason)
    try:
        value = decode_json(completed.stdout)
    except (JsonBoundaryError, GitHubStateError) as exc:
        raise GitHubStateError("github-snapshot-incomplete") from exc
    return tuple(_flatten_values([value]))


def _pull_issue_numbers(pull: JsonObject) -> frozenset[int] | None:
    value = pull.get("closingIssuesReferences")
    if not isinstance(value, list):
        return None
    numbers: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            return None
        number = item.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            return None
        numbers.add(number)
    return frozenset(numbers)


def _pull_scopes(pull: JsonObject) -> tuple[str, ...] | None:
    value = pull.get("files")
    if not isinstance(value, list):
        return None
    if not value or len(value) >= 100:
        return None
    scopes: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        if not isinstance(path, str) or (scope := normalize_scope(path)) is None:
            return None
        scopes.add(scope)
    return tuple(sorted(scopes))


def _pull_is_bot(pull: JsonObject) -> bool | None:
    value = pull.get("author")
    if not isinstance(value, dict):
        return None
    is_bot = value.get("is_bot")
    return is_bot if isinstance(is_bot, bool) else None


def _flatten_values(values: list[JsonValue]) -> list[JsonObject]:
    flattened: list[JsonObject] = []
    pending = list(values)
    while pending:
        item = pending.pop(0)
        if isinstance(item, list):
            pending[0:0] = item
            continue
        if not isinstance(item, dict):
            raise GitHubStateError("github-snapshot-incomplete")
        flattened.append(item)
    return flattened


def _validate_request(*, repo: str, as_of: datetime, ttl_seconds: int) -> None:
    if _REPO_RE.fullmatch(repo) is None:
        raise GitHubStateError("github-repository-invalid")
    if as_of.tzinfo is None:
        raise GitHubStateError("as-of-naive")
    if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise GitHubStateError("snapshot-ttl-invalid")


def _trusted_gh_contract() -> tuple[Path, Mapping[str, str]]:
    try:
        executable = trusted_executable("gh")
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve(strict=True)
    except (KeyError, OSError, OrchestrationServiceError) as exc:
        raise GitHubStateError("github-refresh-failed") from exc
    return executable, {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
    }
