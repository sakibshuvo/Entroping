#!/usr/bin/env python3
"""Check GitHub issue backlog labels before or after marathons."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


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
            issue_json = input_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"issue JSON file is not valid UTF-8: {input_path}") from exc
        except OSError as exc:
            raise ValueError(f"could not read issue JSON file {input_path}: {exc}") from exc
        try:
            payload = json.loads(issue_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid issue JSON in {input_path}: {exc.msg}") from exc
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
        completed = subprocess.run(  # nosec B603
            command,
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"gh issue list timed out after {exc.timeout:g} seconds") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("gh issue list returned output that was not valid text") from exc
    except OSError as exc:
        raise ValueError(f"could not run gh issue list: {exc}") from exc
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
