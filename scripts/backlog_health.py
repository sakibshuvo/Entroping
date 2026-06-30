#!/usr/bin/env python3
"""Check GitHub issue backlog labels before or after marathons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from script_safety import ScriptSafetyError, read_json_file, run_subprocess


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
    parser.add_argument("--limit", type=int, default=200, help="Maximum open issues to inspect.")
    args = parser.parse_args()

    try:
        issues = _load_issues(args.input, repo=args.repo, limit=args.limit)
    except ValueError as exc:
        print(f"Backlog health check failed: {exc}", file=sys.stderr)
        return 1

    failures = _health_failures(issues)
    if failures:
        print("Backlog health failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("Backlog health OK")
    print(f"issues checked: {len(issues)}")
    return 0


def _load_issues(input_path: Path | None, *, repo: str, limit: int) -> list[dict[str, Any]]:
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
        payload = _load_issues_from_gh(repo=repo, limit=limit)
    if not isinstance(payload, list):
        raise ValueError("issue payload must be a list")
    issues: list[dict[str, Any]] = []
    for index, issue in enumerate(payload):
        if not isinstance(issue, dict):
            raise ValueError(f"issue payload item {index} must be an object")
        issues.append(issue)
    return issues


def _load_issues_from_gh(*, repo: str, limit: int) -> object:
    if limit <= 0:
        raise ValueError("--limit must be greater than zero")
    command = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,title,url,labels,milestone",
    ]
    try:
        completed = run_subprocess(command, check=False, timeout=30)
    except ScriptSafetyError as exc:
        message = str(exc)
        if message.startswith("command timed out after"):
            raise ValueError("gh issue list timed out after 30 seconds") from exc
        raise ValueError(f"could not run gh issue list: {message}") from exc
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise ValueError(f"gh issue list failed: {details}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"gh issue list returned invalid JSON: {exc.msg}") from exc


def _health_failures(issues: list[dict[str, Any]]) -> tuple[str, ...]:
    failures: list[str] = []
    for issue in issues:
        number = issue.get("number", "?")
        labels = _label_names(issue.get("labels"))
        for prefix in ("type:", "priority:", "status:"):
            if not any(label.startswith(prefix) for label in labels):
                failures.append(f"#{number}: missing {prefix}* label")
        if issue.get("milestone") is None:
            failures.append(f"#{number}: missing milestone")
    return tuple(failures)


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
