from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_issue_selector_cache import CacheError, read_snapshot, write_snapshot
from scripts.factory_issue_selector_core import select_issue
from scripts.factory_issue_selector_github import GitHubStateError, refresh_snapshot
from scripts.factory_issue_selector_local import collect_active_state, scope_has_symlink
from scripts.factory_issue_selector_models import (
    GitHubSnapshot,
    SelectionResult,
    SnapshotMetadata,
)
from scripts.factory_issue_selector_snapshot import MAX_TTL_SECONDS


def select_live(
    *,
    repo_root: Path,
    repo: str,
    ttl_seconds: int,
    force_refresh: bool,
    autonomy_ceiling: str,
    lease_state_complete: bool,
    lease_issue_numbers: frozenset[int],
    lease_scopes: tuple[str, ...],
) -> SelectionResult:
    as_of = _utc_now()
    snapshot, error = _load_snapshot(
        repo_root=repo_root,
        repo=repo,
        as_of=as_of,
        ttl_seconds=ttl_seconds,
        force_refresh=force_refresh,
    )
    if error is not None:
        metadata = (
            snapshot.metadata
            if snapshot is not None
            else SnapshotMetadata(
                repo=repo,
                fetched_at=as_of,
                expires_at=as_of,
                complete=False,
            )
        )
        return SelectionResult(status="blocked", snapshot=metadata, errors=(error,))
    assert snapshot is not None
    active = collect_active_state(
        repo_root=repo_root,
        snapshot=snapshot,
        lease_state_complete=lease_state_complete,
        lease_issue_numbers=lease_issue_numbers,
        lease_scopes=lease_scopes,
    )
    issues = tuple(
        replace(issue, allowed_scopes=())
        if any(scope_has_symlink(repo_root, scope) for scope in issue.allowed_scopes)
        else issue
        for issue in snapshot.issues
    )
    return select_issue(
        issues=issues,
        snapshot=snapshot.metadata,
        active=active,
        as_of=_utc_now(),
        autonomy_ceiling=autonomy_ceiling,
    )


def _load_snapshot(
    *,
    repo_root: Path,
    repo: str,
    as_of: datetime,
    ttl_seconds: int,
    force_refresh: bool,
) -> tuple[GitHubSnapshot | None, str | None]:
    if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        return None, "snapshot-ttl-invalid"
    cached: GitHubSnapshot | None = None
    if not force_refresh:
        try:
            cached = read_snapshot(repo_root, expected_repo=repo)
        except CacheError:
            pass
        else:
            freshness = cached.metadata.freshness_error(as_of)
            if freshness is None:
                return cached, None
            if freshness == "snapshot-clock-rollback":
                return cached, freshness
    try:
        refreshed = refresh_snapshot(repo=repo, as_of=as_of, ttl_seconds=ttl_seconds)
    except GitHubStateError as exc:
        return cached, str(exc)
    freshness = refreshed.metadata.freshness_error(_utc_now())
    if freshness is not None:
        return refreshed, freshness
    try:
        write_snapshot(repo_root, refreshed)
    except CacheError:
        return refreshed, "cache-write-failed"
    return refreshed, None


def _utc_now() -> datetime:
    return datetime.now(UTC)
