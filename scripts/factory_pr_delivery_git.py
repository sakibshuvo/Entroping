"""Exact revision creation and sanitized SSH push boundaries for Tier A delivery."""

from __future__ import annotations

import hashlib
import sqlite3
import stat
from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from scripts.factory_control_plane_policy import static_tier_a_doc_scope
from scripts.factory_orchestration_git_identity import operation_active, worktree_records
from scripts.factory_pr_delivery_git_io import (
    canonical_diff,
    diff_paths,
    git_bytes,
    git_ok,
    git_text,
    plan_commit,
    status_paths,
)
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_models import (
    CommitResult,
    DeliveryEnvelope,
    DeliveryGitError,
    approved_path_digest,
)
from scripts.factory_pr_delivery_ssh import (
    build_push_spec as build_push_spec,
)
from scripts.factory_pr_delivery_ssh import (
    push_exact_commit as push_exact_commit,
)
from scripts.factory_scheduler_queries import read_assignment, read_execution_for_job
from scripts.factory_scheduler_storage import readonly_connection
from scripts.factory_scheduler_storage_fs import SchedulerStateError

_COMMIT_ENV: Final = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "LANG": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def validate_scheduler_authority(
    repo_root: Path,
    envelope: DeliveryEnvelope,
) -> None:
    """Revalidate stored post-acceptance authority without requiring a live lease."""

    request = envelope.orchestration_request
    try:
        with readonly_connection(repo_root) as connection:
            connection.execute("BEGIN")
            assignment = read_assignment(connection, job_id=request.job_id)
            execution = read_execution_for_job(connection, job_id=request.job_id)
            connection.execute("COMMIT")
    except (SchedulerStateError, sqlite3.DatabaseError, ValidationError, TypeError, ValueError):
        raise DeliveryGitError("authority-mismatch") from None
    if assignment is None or execution is None:
        raise DeliveryGitError("authority-mismatch")
    stored = assignment.request
    authority = stored.delivery_authority
    if (
        assignment.state != "active"
        or assignment.assignment_id != request.assignment_id
        or stored.request_id != request.request_id
        or stored.issue_number != request.issue_number
        or stored.job_id != request.job_id
        or stored.worktree_id != request.worktree_id
        or stored.worker_class != "free-local"
        or stored.access_mode != "write"
        or authority is None
        or authority.selector_digest != request.selector_digest
        or authority.selection_digest != request.selection_digest
        or authority.autonomy_tier != request.autonomy_tier
        or authority.verification_lane != request.verification_lane
        or authority.allowed_scopes != request.allowed_scopes
        or authority.allowed_scope_digest != request.allowed_scope_digest
        or execution.assignment_id != request.assignment_id
        or execution.phase != "completed-unsettled"
        or execution.evidence_digest != request.proposal_sha256
    ):
        raise DeliveryGitError("authority-mismatch")


def commit_exact_diff(
    repo_root: Path,
    envelope: DeliveryEnvelope,
    *,
    committed_at: datetime,
    journal: DeliveryJournal | None = None,
) -> CommitResult:
    """Create one exact commit from accepted diff evidence using Git plumbing."""

    if committed_at.tzinfo is None or committed_at.utcoffset() is None:
        raise DeliveryGitError("authority-mismatch")
    request = envelope.orchestration_request
    receipt = envelope.orchestration_receipt
    worktree = envelope.worktree_path
    _validate_authority(repo_root, envelope)
    delivery_journal = journal if journal is not None else DeliveryJournal(repo_root)
    subject = f"docs(factory): deliver issue #{request.issue_number}"
    identity_env = {
        **_COMMIT_ENV,
        "HOME": "/dev/null",
        "XDG_CONFIG_HOME": "/dev/null",
        "GIT_AUTHOR_NAME": "Entroping Factory Controller",
        "GIT_AUTHOR_EMAIL": "factory-controller@entroping.invalid",
        "GIT_COMMITTER_NAME": "Entroping Factory Controller",
        "GIT_COMMITTER_EMAIL": "factory-controller@entroping.invalid",
        "GIT_AUTHOR_DATE": committed_at.isoformat(),
        "GIT_COMMITTER_DATE": committed_at.isoformat(),
    }
    accepted_diff_sha256 = receipt.diff_sha256
    accepted_manifest_sha256 = receipt.result_manifest_sha256
    if accepted_diff_sha256 is None or accepted_manifest_sha256 is None:
        raise DeliveryGitError("authority-mismatch")
    accepted_diff = canonical_diff(worktree, request.base_commit)
    accepted_paths = diff_paths(worktree, request.base_commit, cached=False)
    if (
        hashlib.sha256(accepted_diff).hexdigest() != accepted_diff_sha256
        or hashlib.sha256(request.base_commit.encode() + b"\0" + accepted_diff).hexdigest()
        != accepted_manifest_sha256
        or accepted_paths != receipt.approved_paths
    ):
        raise DeliveryGitError("authority-mismatch")
    planned_head, planned_tree = plan_commit(
        worktree,
        base=request.base_commit,
        paths=receipt.approved_paths,
        subject=subject,
        commit_env=identity_env,
    )
    _ = delivery_journal.prepare(envelope)
    _ = delivery_journal.commit_intent(
        envelope,
        committed_head=planned_head,
        commit_parent=request.base_commit,
        commit_tree=planned_tree,
    )
    for relative in receipt.approved_paths:
        candidate = worktree / relative
        if candidate.exists() or candidate.is_symlink():
            metadata = candidate.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or candidate.is_symlink()
                or stat.S_IMODE(metadata.st_mode) & 0o111
            ):
                raise DeliveryGitError("scope-denied")
            blob = (
                git_bytes(
                    worktree,
                    "hash-object",
                    "-w",
                    "--no-filters",
                    "--stdin",
                    input_bytes=candidate.read_bytes(),
                )
                .decode()
                .strip()
            )
            git_ok(worktree, "update-index", "--add", "--cacheinfo", f"100644,{blob},{relative}")
        else:
            git_ok(worktree, "update-index", "--force-remove", "--", relative)
    cached_diff = git_bytes(
        worktree,
        "diff",
        "--cached",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        request.base_commit,
        "--",
    )
    cached_paths = diff_paths(worktree, request.base_commit, cached=True)
    if cached_diff != accepted_diff or cached_paths != receipt.approved_paths:
        raise DeliveryGitError("authority-mismatch")
    tree = git_text(worktree, "write-tree")
    if tree != planned_tree:
        raise DeliveryGitError("uncertain")
    committed_head = (
        git_bytes(
            worktree,
            "commit-tree",
            tree,
            "-p",
            request.base_commit,
            input_bytes=f"{subject}\n".encode(),
            env=identity_env,
        )
        .decode()
        .strip()
    )
    if len(committed_head) != 40:
        raise DeliveryGitError("commit-failed")
    if committed_head != planned_head:
        raise DeliveryGitError("uncertain")
    git_ok(
        worktree,
        "update-ref",
        f"refs/heads/{request.branch}",
        committed_head,
        request.base_commit,
    )
    committed_diff = git_bytes(
        worktree,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        request.base_commit,
        committed_head,
        "--",
    )
    status = git_bytes(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if committed_diff != accepted_diff or status:
        raise DeliveryGitError("uncertain")
    _ = delivery_journal.committed(envelope)
    diff_sha = hashlib.sha256(committed_diff).hexdigest()
    manifest_sha = hashlib.sha256(request.base_commit.encode() + b"\0" + committed_diff).hexdigest()
    return CommitResult(
        accepted_local_head=request.base_commit,
        committed_head=committed_head,
        commit_parent=request.base_commit,
        commit_tree=tree,
        accepted_diff_sha256=accepted_diff_sha256,
        committed_diff_sha256=diff_sha,
        accepted_manifest_sha256=accepted_manifest_sha256,
        committed_manifest_sha256=manifest_sha,
        approved_path_sha256=approved_path_digest(receipt.approved_paths),
    )


def _validate_authority(repo_root: Path, envelope: DeliveryEnvelope) -> None:
    validate_scheduler_authority(repo_root, envelope)
    request = envelope.orchestration_request
    receipt = envelope.orchestration_receipt
    if repo_root.resolve() != envelope.main_root or envelope.main_root != repo_root.resolve():
        raise DeliveryGitError("authority-mismatch")
    if request.autonomy_tier != "tier-a" or request.verification_lane not in {
        "tiny-docs",
        "docs-guardrail",
    }:
        raise DeliveryGitError("scope-denied")
    if any(
        not static_tier_a_doc_scope(path, repo_root=envelope.worktree_path)
        or not path.endswith(".md")
        for path in receipt.approved_paths
    ):
        raise DeliveryGitError("scope-denied")
    if git_text(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD") != "main":
        raise DeliveryGitError("authority-mismatch")
    if git_text(repo_root, "rev-parse", "HEAD") != request.base_commit:
        raise DeliveryGitError("authority-mismatch")
    if git_bytes(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise DeliveryGitError("authority-mismatch")
    matches = [
        record for record in worktree_records(repo_root) if record[0] == envelope.worktree_path
    ]
    if len(matches) != 1 or matches[0][1:] != (request.base_commit, request.branch):
        raise DeliveryGitError("authority-mismatch")
    worktree = envelope.worktree_path
    if operation_active(worktree):
        raise DeliveryGitError("authority-mismatch")
    if git_text(worktree, "symbolic-ref", "--quiet", "--short", "HEAD") != request.branch:
        raise DeliveryGitError("authority-mismatch")
    if git_text(worktree, "rev-parse", "HEAD") != request.base_commit:
        raise DeliveryGitError("authority-mismatch")
    if git_bytes(worktree, "diff", "--cached", request.base_commit, "--"):
        raise DeliveryGitError("authority-mismatch")
    changed_paths = status_paths(worktree)
    if any(path not in receipt.approved_paths for path in changed_paths):
        raise DeliveryGitError("authority-mismatch")
