#!/usr/bin/env python3
"""Check GitHub issue backlog labels before or after marathons."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from script_safety import ScriptSafetyError, read_json_file, run_subprocess

MAX_ISSUE_LIMIT = 1000
MAX_REGISTERED_ISSUES = 256
MAX_WORKTREE_OUTPUT_BYTES = 262_144
_ACTIVE_STATUS_LABELS = ("status:ready", "status:in-progress")
_ISSUE_JSON_FIELDS = "number,title,url,state,labels,milestone"
_ISSUE_WORKTREE = re.compile(r"^Entroping-issue-([1-9][0-9]*)$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check open GitHub issues for type, priority, status, and milestone labels. "
            "Without --input this shells out to gh issue list."
        )
    )
    parser.add_argument("--input", type=Path, help="Read gh issue JSON from a file.")
    parser.add_argument(
        "--repo",
        default="sakibshuvo/Entroping",
        help="GitHub repository for gh issue list mode.",
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="Maximum open issues to inspect."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root whose registered issue worktrees should be checked.",
    )
    args = parser.parse_args()

    try:
        repo_root = args.repo_root
        if repo_root is None and args.input is None:
            repo_root = _git_root()
        registered = _registered_issue_numbers(repo_root) if repo_root is not None else ()
        issues = _load_issues(
            args.input,
            repo=args.repo,
            limit=args.limit,
            registered_issue_numbers=registered,
        )
    except ValueError as exc:
        print(f"Backlog health check failed: {exc}", file=sys.stderr)
        return 1

    failures = _health_failures(issues, registered_issue_numbers=registered)
    if failures:
        print("Backlog health failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("Backlog health OK")
    print(f"issues checked: {len(issues)}")
    return 0


def _load_issues(
    input_path: Path | None,
    *,
    repo: str,
    limit: int,
    registered_issue_numbers: tuple[int, ...] = (),
) -> list[dict[str, Any]]:
    if input_path is not None:
        try:
            payload = read_json_file(input_path)
        except ScriptSafetyError as exc:
            message = str(exc)
            if "not valid UTF-8" in message:
                raise ValueError(f"issue JSON file is not valid UTF-8: {input_path}") from exc
            if "invalid JSON in" in message:
                raise ValueError(f"invalid issue JSON in {input_path}: {message}") from exc
            raise ValueError(f"could not read issue JSON file {input_path}: {message}") from exc
    else:
        payload = _load_issues_from_gh(
            repo=repo,
            limit=limit,
            registered_issue_numbers=registered_issue_numbers,
        )
    if not isinstance(payload, list):
        raise ValueError("issue payload must be a list")
    issues: list[dict[str, Any]] = []
    for index, issue in enumerate(payload):
        if not isinstance(issue, dict):
            raise ValueError(f"issue payload item {index} must be an object")
        issues.append(issue)
    return issues


def _load_issues_from_gh(
    *,
    repo: str,
    limit: int,
    registered_issue_numbers: tuple[int, ...] = (),
) -> object:
    if limit <= 0:
        raise ValueError("--limit must be greater than zero")
    if limit > MAX_ISSUE_LIMIT:
        raise ValueError(f"--limit must not exceed {MAX_ISSUE_LIMIT}")
    if len(registered_issue_numbers) > MAX_REGISTERED_ISSUES:
        raise ValueError(
            f"registered issue worktrees must not exceed {MAX_REGISTERED_ISSUES}"
        )

    issue_lists = [
        _gh_issue_list(repo=repo, state="open", limit=limit),
        *(
            _gh_issue_list(
                repo=repo,
                state="closed",
                limit=MAX_ISSUE_LIMIT,
                label=label,
                require_complete=True,
            )
            for label in _ACTIVE_STATUS_LABELS
        ),
    ]
    issues = _merge_live_issues(issue_lists)
    for issue_number in registered_issue_numbers:
        if issue_number in issues:
            continue
        payload = _run_gh_json(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repo,
                "--json",
                _ISSUE_JSON_FIELDS,
            ],
            operation="gh issue view",
        )
        if not isinstance(payload, dict):
            raise ValueError("gh issue view returned invalid issue evidence")
        _merge_live_issue(issues, payload)
    return [issues[number] for number in sorted(issues)]


def _gh_issue_list(
    *,
    repo: str,
    state: str,
    limit: int,
    label: str | None = None,
    require_complete: bool = False,
) -> list[dict[str, Any]]:
    command = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        _ISSUE_JSON_FIELDS,
    ]
    if label is not None:
        command.extend(("--label", label))
    payload = _run_gh_json(command, operation="gh issue list")
    if not isinstance(payload, list) or not all(
        isinstance(issue, dict) for issue in payload
    ):
        raise ValueError("gh issue list returned invalid issue evidence")
    if require_complete and len(payload) >= limit:
        raise ValueError("closed active issue query reached its safety limit")
    return payload


def _run_gh_json(command: list[str], *, operation: str) -> object:
    try:
        completed = run_subprocess(command, check=False, timeout=30)
    except ScriptSafetyError as exc:
        message = str(exc)
        if message.startswith("command timed out after"):
            raise ValueError(f"{operation} timed out after 30 seconds") from exc
        raise ValueError(f"could not run {operation}: {message}") from exc
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise ValueError(f"{operation} failed: {details}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{operation} returned invalid JSON: {exc.msg}") from exc


def _merge_live_issues(
    payloads: list[list[dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    issues: dict[int, dict[str, Any]] = {}
    for payload in payloads:
        for issue in payload:
            _merge_live_issue(issues, issue)
    return issues


def _merge_live_issue(
    issues: dict[int, dict[str, Any]], issue: dict[str, Any]
) -> None:
    number = issue.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("GitHub issue evidence has an invalid issue number")
    existing = issues.get(number)
    if existing is not None and existing != issue:
        raise ValueError(f"GitHub issue evidence conflicts for #{number}")
    issues[number] = issue


def _git_root() -> Path:
    try:
        result = run_subprocess(
            ["git", "rev-parse", "--show-toplevel"],
            timeout=30,
            max_output_bytes=4096,
        )
    except ScriptSafetyError as exc:
        raise ValueError("could not inspect the current repository root") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("could not inspect the current repository root")
    return Path(result.stdout.strip())


def _registered_issue_numbers(repo_root: Path) -> tuple[int, ...]:
    try:
        result = run_subprocess(
            ["git", "-C", repo_root, "worktree", "list", "--porcelain"],
            timeout=30,
            max_output_bytes=MAX_WORKTREE_OUTPUT_BYTES,
        )
    except ScriptSafetyError as exc:
        raise ValueError("could not inspect registered issue worktrees") from exc
    if result.returncode != 0:
        raise ValueError("could not inspect registered issue worktrees")
    numbers: set[int] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        match = _ISSUE_WORKTREE.fullmatch(Path(line.removeprefix("worktree ").strip()).name)
        if match is not None:
            numbers.add(int(match.group(1)))
    return tuple(sorted(numbers))


def _health_failures(
    issues: list[dict[str, Any]],
    *,
    registered_issue_numbers: tuple[int, ...] = (),
) -> tuple[str, ...]:
    failures: list[str] = []
    registered = set(registered_issue_numbers)
    ordered = sorted(issues, key=lambda issue: _issue_sort_key(issue.get("number")))
    for issue in ordered:
        number = issue.get("number", "?")
        labels = _label_names(issue.get("labels"))
        if issue.get("state") == "CLOSED":
            for active in _ACTIVE_STATUS_LABELS:
                if active in labels:
                    failures.append(
                        f"#{number}: closed issue retains active status label: {active}"
                    )
            if type(number) is int and number in registered:
                failures.append(f"#{number}: closed issue retains registered issue worktree")
            continue
        for prefix in ("type:", "priority:", "status:"):
            if not any(label.startswith(prefix) for label in labels):
                failures.append(f"#{number}: missing {prefix}* label")
        if issue.get("milestone") is None:
            failures.append(f"#{number}: missing milestone")
    return tuple(failures)


def _issue_sort_key(value: object) -> tuple[int, str]:
    if type(value) is int:
        return value, ""
    return sys.maxsize, str(value)


def _label_names(raw_labels: object) -> tuple[str, ...]:
    if not isinstance(raw_labels, list):
        return ()
    labels: list[str] = []
    for label in raw_labels:
        if isinstance(label, str):
            labels.append(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            labels.append(label["name"])
    return tuple(labels)


if __name__ == "__main__":
    raise SystemExit(main())
