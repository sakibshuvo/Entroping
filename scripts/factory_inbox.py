#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory_inbox_core import (
    DEFAULT_ARTIFACT_ROOT,
    MARK_DECISIONS,
    list_payload,
    mark_payload,
    next_payload,
)
from factory_inbox_io import InboxError, JsonObject, repo_root, resolve_root


def main() -> int:
    try:
        args = parse_args()
        repo_root_path = repo_root()
        artifact_root = resolve_root(repo_root_path, args.artifact_root, "artifact root")
        command = command_name(args)
        if command == "list":
            payload = list_payload(
                artifact_root,
                include_completed=bool(args.include_completed),
            )
        elif command == "next":
            payload = next_payload(
                repo_root_path,
                artifact_root,
                include_completed=bool(args.include_completed),
                newest=bool(args.newest),
                claim=bool(args.claim),
            )
        elif command in MARK_DECISIONS:
            payload = mark_payload(
                artifact_root,
                args.artifact_dir,
                decision=MARK_DECISIONS[command],
            )
        else:
            msg = f"unsupported command: {command}"
            raise InboxError(msg)
    except InboxError as exc:
        print(f"factory_inbox: {exc}", file=sys.stderr)
        return 2

    print_payload(payload, json_output=bool(args.json))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find ready OpenCode/DeepSeek handoffs for Codex review."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List ready inbox handoffs.")
    add_common_options(list_parser)
    list_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Also treat legacy completed/patch-proposed artifacts as ready.",
    )

    next_parser = subparsers.add_parser("next", help="Print the next review packet.")
    add_common_options(next_parser)
    next_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Also treat legacy completed/patch-proposed artifacts as ready.",
    )
    next_parser.add_argument(
        "--newest",
        action="store_true",
        help="Pick the newest ready handoff instead of the oldest.",
    )
    next_parser.add_argument(
        "--claim",
        action="store_true",
        help="Mark the selected handoff as in_review before printing it.",
    )

    for command, decision in MARK_DECISIONS.items():
        mark_parser = subparsers.add_parser(command, help=f"Mark a handoff as {decision}.")
        add_common_options(mark_parser)
        mark_parser.add_argument("artifact_dir", type=Path, help="Artifact directory.")

    return parser.parse_args()


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Worker artifact root. Default: .entroping/ai-reviews",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")


def command_name(args: argparse.Namespace) -> str:
    value = args.command
    if not isinstance(value, str):
        msg = "missing command"
        raise InboxError(msg)
    return value


def print_payload(payload: JsonObject, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"Factory inbox: {payload['schema_version']}")
    if "ready" in payload:
        ready = payload["ready"]
        skipped = payload["skipped"]
        print(f"Ready: {len(ready) if isinstance(ready, list) else 0}")
        print(f"Skipped: {len(skipped) if isinstance(skipped, list) else 0}")
        return

    inbox = payload.get("inbox")
    if isinstance(inbox, dict):
        print(f"Selected: {inbox.get('artifact_dir')}")
        print(f"Issue: {inbox.get('issue')}")
        print(f"Status: {inbox.get('status')}")
    print("Review packet embedded under `review_packet`.")


if __name__ == "__main__":
    raise SystemExit(main())
