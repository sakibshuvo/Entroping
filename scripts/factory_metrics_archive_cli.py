from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Protocol, cast


class PreserveArchive(Protocol):
    def __call__(
        self,
        *,
        repo_root: Path,
        worktree_root: Path,
        issue: int,
        pull_request: int,
        archived_at: str,
        dry_run: bool = False,
    ) -> tuple[Path, tuple[str, ...]]: ...


def run_cli(
    argv: list[str] | None,
    *,
    preserve_archive: PreserveArchive,
    error_types: tuple[type[BaseException], ...],
) -> int:
    parser = argparse.ArgumentParser(
        description="Preserve bounded factory metrics with terminal provenance."
    )
    _ = parser.add_argument("--repo-root", type=Path, required=True)
    _ = parser.add_argument("--source-worktree", type=Path, required=True)
    _ = parser.add_argument("--issue", type=int, required=True)
    _ = parser.add_argument("--pull-request", type=int, required=True)
    _ = parser.add_argument("--archived-at", required=True)
    _ = parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        destination, ledgers = preserve_archive(
            repo_root=cast(Path, args.repo_root),
            worktree_root=cast(Path, args.source_worktree),
            issue=cast(int, args.issue),
            pull_request=cast(int, args.pull_request),
            archived_at=cast(str, args.archived_at),
            dry_run=cast(bool, args.dry_run),
        )
    except error_types as exc:
        print(f"factory_metrics_archive: {exc}", file=sys.stderr)
        return 2
    if not ledgers:
        return 0
    if cast(bool, args.dry_run):
        print(f"Would preserve factory metrics ledgers to {destination}:")
        for ledger in ledgers:
            print(f"  {ledger}")
    else:
        print(f"Preserved factory metrics ledgers ({len(ledgers)} files): {destination}")
    return 0
