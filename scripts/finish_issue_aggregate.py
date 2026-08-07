"""Verify live GitHub and Git truth for aggregate-PR finish cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from finish_issue_aggregate_models import (
    AggregateManifest,
    JsonValue,
    parse_manifest,
    reject_constant,
    unique_pairs,
)
from finish_issue_aggregate_support import (
    MAX_GIT_OUTPUT_BYTES,
    AggregateEvidenceError,
    git,
    git_ok,
    patch_id,
    read_tracked_manifest,
    repository_slug,
    run,
)
from finish_issue_replay_evidence import (
    ReplayEvidenceError,
    ReplayIdentity,
    read_replay_evidence,
)


def _json_payload(command: list[str]) -> dict[str, JsonValue]:
    try:
        result = run(command, MAX_GIT_OUTPUT_BYTES)
    except AggregateEvidenceError as exc:
        raise AggregateEvidenceError("GitHub evidence lookup failed") from exc
    if result.returncode != 0:
        raise AggregateEvidenceError("GitHub evidence lookup failed")
    try:
        payload = json.loads(
            result.stdout, object_pairs_hook=unique_pairs, parse_constant=reject_constant
        )
    except (AggregateEvidenceError, json.JSONDecodeError, RecursionError) as exc:
        raise AggregateEvidenceError("GitHub evidence is invalid") from exc
    if not isinstance(payload, dict):
        raise AggregateEvidenceError("GitHub evidence is invalid")
    return payload


def _string(payload: dict[str, JsonValue], key: str, maximum: int = 4096) -> str:
    value = payload.get(key)
    if type(value) is not str or not value or len(value.encode()) > maximum:
        raise AggregateEvidenceError("GitHub evidence is invalid")
    return value


def _check_rollup(payload: dict[str, JsonValue]) -> int:
    raw = payload.get("statusCheckRollup")
    if not isinstance(raw, list) or not raw:
        raise AggregateEvidenceError("aggregate PR CI evidence is incomplete")
    for item in raw:
        if not isinstance(item, dict):
            raise AggregateEvidenceError("aggregate PR CI evidence is invalid")
        kind = item.get("__typename")
        if kind == "CheckRun":
            valid = item.get("status") == "COMPLETED" and item.get("conclusion") in {
                "SUCCESS",
                "SKIPPED",
                "NEUTRAL",
            }
        elif kind == "StatusContext":
            valid = item.get("state") == "SUCCESS"
        else:
            raise AggregateEvidenceError("aggregate PR CI evidence is invalid")
        if not valid:
            raise AggregateEvidenceError("aggregate PR CI evidence is not passing")
    return len(raw)


def _canonical_timestamp(value: str) -> bool:
    if not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return False
    return parsed.isoformat().replace("+00:00", "Z") == value


def _verify_source_or_replay(
    root: Path,
    worktree: Path,
    manifest: AggregateManifest,
    issue: int,
    merged_at: str,
) -> None:
    if worktree.exists():
        try:
            resolved = worktree.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise AggregateEvidenceError("worktree evidence is invalid") from exc
        entry = next(entry for entry in manifest.entries if entry.issue_number == issue)
        if (
            resolved != worktree.absolute()
            or git(worktree, "branch", "--show-current") != entry.source_branch
            or git(worktree, "rev-parse", "HEAD") != entry.source_commit
            or git(worktree, "status", "--porcelain")
        ):
            raise AggregateEvidenceError("source worktree is not the mapped clean commit")
        return
    if worktree.is_symlink():
        raise AggregateEvidenceError("worktree evidence is invalid")
    entry = next(entry for entry in manifest.entries if entry.issue_number == issue)
    identity = ReplayIdentity(
        issue=issue,
        pull_request=manifest.aggregate_pr_number,
        expected_head=entry.source_commit,
        expected_branch=entry.source_branch,
        merged_at=merged_at,
        worktree_path=str(worktree.absolute()),
    )
    try:
        stage = read_replay_evidence(root, identity)
    except (ReplayEvidenceError, OSError) as exc:
        raise AggregateEvidenceError("aggregate replay evidence is invalid") from exc
    if stage == "none":
        raise AggregateEvidenceError("source worktree is not the mapped clean commit")


def _verify_live(
    root: Path,
    repo: str,
    worktree: Path,
    issue: int,
    manifest_path: str,
) -> dict[str, object]:
    if git(root, "status", "--porcelain"):
        raise AggregateEvidenceError("aggregate repository is not clean")
    manifest = parse_manifest(read_tracked_manifest(root, manifest_path))
    if manifest.repository != repo or repository_slug(root) != repo:
        raise AggregateEvidenceError("repository identity does not match manifest")
    entries = tuple(entry for entry in manifest.entries if entry.issue_number == issue)
    if len(entries) != 1:
        raise AggregateEvidenceError("issue is not mapped exactly once")
    entry = entries[0]
    issue_json = _json_payload(
        [
            "gh",
            "issue",
            "view",
            str(issue),
            "--repo",
            repo,
            "--json",
            "title,url,state,closedByPullRequestsReferences",
        ]
    )
    if issue_json.get("state") != "CLOSED":
        raise AggregateEvidenceError("issue is not closed")
    references = issue_json.get("closedByPullRequestsReferences")
    if not isinstance(references, list) or not any(
        isinstance(item, dict) and item.get("number") == manifest.aggregate_pr_number
        for item in references
    ):
        raise AggregateEvidenceError("aggregate PR does not close the issue")
    pr_json = _json_payload(
        [
            "gh",
            "pr",
            "view",
            str(manifest.aggregate_pr_number),
            "--repo",
            repo,
            "--json",
            "number,url,state,headRefName,headRefOid,mergedAt,mergeCommit,commits,statusCheckRollup",
        ]
    )
    _verify_pr(manifest, entry.integrated_commit, pr_json)
    _verify_commits(root, manifest, entry.source_commit, entry.integrated_commit)
    check_count = _check_rollup(pr_json)
    merged_at = _string(pr_json, "mergedAt", 256)
    if not _canonical_timestamp(merged_at):
        raise AggregateEvidenceError("aggregate PR timestamp is invalid")
    _verify_source_or_replay(root, worktree, manifest, issue, merged_at)
    return {
        "issue_title": _string(issue_json, "title"),
        "issue_url": _string(issue_json, "url"),
        "aggregate_pr_number": manifest.aggregate_pr_number,
        "aggregate_pr_url": _string(pr_json, "url"),
        "aggregate_merge_commit": manifest.aggregate_merge_commit,
        "source_branch": entry.source_branch,
        "source_commit": entry.source_commit,
        "integrated_commit": entry.integrated_commit,
        "patch_id": entry.patch_id,
        "merged_at": merged_at,
        "check_count": check_count,
    }


def _verify_pr(
    manifest: AggregateManifest, integrated_commit: str, payload: dict[str, JsonValue]
) -> None:
    if payload.get("number") != manifest.aggregate_pr_number or payload.get("state") != "MERGED":
        raise AggregateEvidenceError("aggregate PR identity is invalid")
    merge = payload.get("mergeCommit")
    merge_oid = merge.get("oid") if isinstance(merge, dict) else None
    commits = payload.get("commits")
    if (
        merge_oid != manifest.aggregate_merge_commit
        or not isinstance(commits, list)
        or not any(
            isinstance(item, dict) and item.get("oid") == integrated_commit for item in commits
        )
    ):
        raise AggregateEvidenceError("aggregate PR commit evidence is invalid")


def _verify_commits(
    root: Path, manifest: AggregateManifest, source_commit: str, integrated_commit: str
) -> None:
    if not git_ok(root, "cat-file", "-e", f"{integrated_commit}^{{commit}}") or not git_ok(
        root, "cat-file", "-e", f"{manifest.aggregate_merge_commit}^{{commit}}"
    ):
        raise AggregateEvidenceError("aggregate commit object is missing")
    if not git_ok(
        root, "merge-base", "--is-ancestor", integrated_commit, manifest.aggregate_merge_commit
    ):
        raise AggregateEvidenceError("integrated commit is not reachable from aggregate merge")
    if not git_ok(
        root, "merge-base", "--is-ancestor", manifest.aggregate_merge_commit, "refs/heads/main"
    ):
        raise AggregateEvidenceError("aggregate merge is not reachable from current main")
    source_patch = patch_id(root, source_commit)
    integrated_patch = patch_id(root, integrated_commit)
    if source_patch != integrated_patch or source_patch != next(
        entry.patch_id for entry in manifest.entries if entry.source_commit == source_commit
    ):
        raise AggregateEvidenceError("stable patch equivalence does not match manifest")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify aggregate-PR finish evidence.")
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        result = _verify_live(args.repo_root, args.repo, args.worktree, args.issue, args.manifest)
    except (AggregateEvidenceError, OSError, ValueError):
        print("aggregate evidence is invalid or unsafe", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
