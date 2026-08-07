"""Run the fixed remote source-branch observation/deletion authority."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from scripts.factory_pr_delivery_models import DeliveryGitError
from scripts.factory_pr_delivery_ssh import (
    delete_remote_branch,
    observe_remote_branch,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or delete one exact remote branch.")
    parser.add_argument("action", choices=("observe", "delete"))
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--expected-head", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "observe":
            remote_head = observe_remote_branch(
                args.worktree,
                branch=args.branch,
                expected_head=args.expected_head,
            )
            print("absent" if remote_head is None else f"present:{remote_head}")
        else:
            result = delete_remote_branch(
                args.worktree,
                branch=args.branch,
                expected_head=args.expected_head,
            )
            print(result.state)
    except (DeliveryGitError, OSError, ValueError):
        print("remote branch evidence is invalid or uncertain", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
