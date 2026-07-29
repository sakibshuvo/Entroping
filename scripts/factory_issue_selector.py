#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.factory_issue_selector_service import select_live  # noqa: E402


class _Arguments(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.repo: str = "sakibshuvo/Entroping"
        self.repo_root: Path = Path.cwd()
        self.ttl_seconds: int = 60
        self.refresh: bool = False
        self.autonomy_ceiling: str = "tier-a"
        self.active_state_complete: bool = False
        self.active_issue: list[int] = []
        self.active_file: list[str] = []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select one live, ready, non-overlapping issue without authorizing work."
        )
    )
    _ = parser.add_argument("--repo", default="sakibshuvo/Entroping")
    _ = parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    _ = parser.add_argument(
        "--ttl-seconds",
        type=_ttl_seconds,
        default=60,
        help="GitHub cache TTL from 1 through 300 seconds (default: 60).",
    )
    _ = parser.add_argument(
        "--refresh", action="store_true", help="Ignore a valid cache and refresh GitHub."
    )
    _ = parser.add_argument(
        "--autonomy-ceiling",
        choices=("tier-a", "tier-b", "tier-c"),
        default="tier-a",
    )
    _ = parser.add_argument(
        "--active-state-complete",
        action="store_true",
        help="Assert that the supplied external lease state is complete.",
    )
    _ = parser.add_argument(
        "--active-issue",
        action="append",
        type=_positive_issue,
        default=[],
        help="Issue number held by an external active lease; repeat as needed.",
    )
    _ = parser.add_argument(
        "--active-file",
        action="append",
        default=[],
        help="File scope held by an external active lease; repeat as needed.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv, namespace=_Arguments())
    result = select_live(
        repo_root=args.repo_root,
        repo=args.repo,
        ttl_seconds=args.ttl_seconds,
        force_refresh=args.refresh,
        autonomy_ceiling=args.autonomy_ceiling,
        lease_state_complete=args.active_state_complete,
        lease_issue_numbers=frozenset(args.active_issue),
        lease_scopes=tuple(args.active_file),
    )
    print(json.dumps(result.to_payload(), indent=2, sort_keys=True))
    return 2 if result.status == "blocked" else 0


def _positive_issue(value: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise argparse.ArgumentTypeError("issue must be a positive integer")
    return int(value)


def _ttl_seconds(value: str) -> int:
    if not value.isdigit() or not 1 <= int(value) <= 300:
        raise argparse.ArgumentTypeError("TTL must be an integer from 1 through 300")
    return int(value)


if __name__ == "__main__":
    sys.exit(main())
