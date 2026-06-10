#!/usr/bin/env python3
"""Validate pull request documentation-impact declarations."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SECTION_TITLE = "## Documentation Impact Declaration"


def _extract_section(body: str) -> str | None:
    marker_index = body.find(SECTION_TITLE)
    if marker_index == -1:
        return None

    section_start = marker_index + len(SECTION_TITLE)
    next_header = body.find("\n## ", section_start)
    if next_header == -1:
        return body[section_start:]
    return body[section_start:next_header]


def _checked_items(section: str) -> list[str]:
    return re.findall(r"(?im)^-\s*\[[xX]\]\s+(.+)$", section)


def validate_body(body: str) -> list[str]:
    section = _extract_section(body)
    if section is None:
        return [f"PR body must include {SECTION_TITLE}."]

    checked = _checked_items(section)
    if not checked:
        return [
            "PR body must check at least one Documentation Impact Declaration item.",
        ]

    failures: list[str] = []
    for item in checked:
        if ":" in item and not item.split(":", maxsplit=1)[1].strip():
            failures.append(f"Checked documentation declaration needs detail: {item}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PR body documentation-impact declarations.",
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Validate a plain Markdown PR body file instead of a GitHub event payload.",
    )
    parser.add_argument(
        "event_path",
        nargs="?",
        default=os.environ.get("GITHUB_EVENT_PATH"),
        help="Path to the GitHub event JSON payload. Defaults to GITHUB_EVENT_PATH.",
    )
    args = parser.parse_args(argv)

    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
        failures = validate_body(body)
        if failures:
            print("PR documentation impact declaration failed:", file=sys.stderr)
            for failure in failures:
                print(f"  {failure}", file=sys.stderr)
            return 1
        print("PR documentation impact declaration OK")
        return 0

    if not args.event_path:
        print("No GitHub event payload path provided.", file=sys.stderr)
        return 2

    event_path = Path(args.event_path)
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        print("No pull request payload; skipping PR documentation impact check.")
        return 0

    body = pull_request.get("body") or ""
    failures = validate_body(body)
    if failures:
        print("PR documentation impact declaration failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("PR documentation impact declaration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
