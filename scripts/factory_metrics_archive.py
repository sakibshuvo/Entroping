from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.factory_metrics_archive_destination import (
    copy_archive,
    verify_empty_source_archive,
)
from scripts.factory_metrics_archive_errors import FactoryMetricsArchiveError
from scripts.factory_metrics_archive_io import (
    FactoryMetricsArchiveIoError,
    discover_ledgers,
    open_metrics_source,
    read_source_ledger,
    safe_root,
)
from scripts.factory_retention_types import FACTORY_METRICS_ARCHIVE_SCHEMA_VERSION

__all__ = ["FactoryMetricsArchiveError", "preserve_archive"]


def preserve_archive(
    *,
    repo_root: Path,
    worktree_root: Path,
    issue: int,
    pull_request: int,
    archived_at: str,
    dry_run: bool = False,
) -> tuple[Path, tuple[str, ...]]:
    try:
        root = safe_root(repo_root, label="repository")
        payload = _archive_payload(
            issue=issue,
            pull_request=pull_request,
            archived_at=archived_at,
        )
        destination = root / ".entroping" / "factory-metrics" / "finished-issues" / f"issue-{issue}"
        with open_metrics_source(worktree_root) as source_fd:
            if source_fd is None:
                if not dry_run:
                    verify_empty_source_archive(root, issue, payload)
                return destination, ()
            ledgers = discover_ledgers(source_fd)
            paths = tuple("/".join(spec[0]) for spec in ledgers)
            if dry_run:
                return destination, paths
            if not ledgers:
                verify_empty_source_archive(root, issue, payload)
                return destination, paths
            prepared = tuple((spec, read_source_ledger(source_fd, spec)) for spec in ledgers)
            copy_archive(
                repo_root=root,
                issue=issue,
                payload=payload,
                ledgers=prepared,
            )
            return destination, paths
    except FactoryMetricsArchiveIoError as exc:
        raise FactoryMetricsArchiveError(str(exc)) from exc


def _archive_payload(*, issue: int, pull_request: int, archived_at: str) -> dict[str, object]:
    if issue <= 0 or pull_request <= 0:
        raise FactoryMetricsArchiveError("issue and pull request must be positive integers")
    return {
        "schema_version": FACTORY_METRICS_ARCHIVE_SCHEMA_VERSION,
        "issue": issue,
        "pull_request": pull_request,
        "status": "archived",
        "issue_state": "closed",
        "pr_state": "merged",
        "archived_at": _utc_timestamp(archived_at),
    }


def _utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FactoryMetricsArchiveError("archived-at must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FactoryMetricsArchiveError("archived-at must be UTC")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    from scripts.factory_metrics_archive_cli import run_cli

    return run_cli(
        argv,
        preserve_archive=preserve_archive,
        error_types=(FactoryMetricsArchiveError, OSError, ValueError),
    )


if __name__ == "__main__":
    raise SystemExit(main())
