"""Fail-closed Git worktree and exact-patch mutation boundary."""

from __future__ import annotations

import fnmatch
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.factory_control_plane_policy import static_tier_a_doc_scope
from scripts.factory_orchestration_errors import OrchestrationGitError
from scripts.factory_orchestration_git_identity import operation_active, worktree_records
from scripts.factory_orchestration_git_process import (
    git_bytes,
    git_process,
    git_text,
)
from scripts.factory_orchestration_models import OrchestrationRequest
from scripts.factory_patch_inspection import (
    PatchInspectionError,
    inspect_proposal_bytes,
    proposal_control_plane_violations,
)


@dataclass(frozen=True, slots=True)
class WorktreeSnapshot:
    path: Path
    branch: str
    common_git_dir: Path
    head: str
    tree: str


@dataclass(frozen=True, slots=True)
class PatchTruth:
    head: str
    manifest_sha256: str
    diff_sha256: str
    paths: tuple[str, ...]
    status_sha256: str


def validate_main_base(repo_root: Path, request: OrchestrationRequest) -> None:
    """Require the local main authority to remain at the authorized base."""

    top = Path(git_text(repo_root, "rev-parse", "--show-toplevel")).resolve()
    common_raw = Path(git_text(repo_root, "rev-parse", "--git-common-dir"))
    common = common_raw if common_raw.is_absolute() else repo_root / common_raw
    if (
        top != repo_root.resolve()
        or common.resolve() != Path(request.common_git_dir).resolve()
        or git_text(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD") != "main"
        or git_text(repo_root, "rev-parse", "refs/heads/main") != request.base_commit
        or git_text(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    ):
        raise OrchestrationGitError("stale-base")


def validate_reusable_worktree(
    repo_root: Path,
    request: OrchestrationRequest,
) -> WorktreeSnapshot:
    """Require one exact clean registered worktree without repairing it."""

    target = Path(request.worktree_path)
    if not target.is_dir() or target != target.resolve():
        raise OrchestrationGitError("worktree-mismatch")
    records = worktree_records(repo_root)
    matching = [record for record in records if record[0] == target.resolve()]
    if len(matching) != 1:
        raise OrchestrationGitError("worktree-mismatch")
    registered_path, registered_head, registered_branch = matching[0]
    if registered_branch != request.branch:
        raise OrchestrationGitError("worktree-mismatch")
    if registered_head != request.base_commit:
        raise OrchestrationGitError("stale-base")
    return _validate_target_identity(target, request, require_clean=True)


def validate_inspected_scope(
    request: OrchestrationRequest,
    inspected: dict[str, object],
    *,
    repo_root: Path,
) -> tuple[str, ...]:
    """Apply protected-surface and selector-scope policy before mutation."""

    paths = _inspected_paths(inspected)
    if request.verification_lane not in {"tiny-docs", "docs-guardrail"} or any(
        not static_tier_a_doc_scope(path, repo_root=repo_root) for path in paths
    ):
        raise OrchestrationGitError("scope-denied")
    target = Path(request.worktree_path)
    policy_root = target if target.is_dir() else repo_root
    if proposal_control_plane_violations(inspected, repo_root=policy_root):
        raise OrchestrationGitError("scope-denied")
    if any(not _in_allowed_scope(path, request.allowed_scopes) for path in paths):
        raise OrchestrationGitError("scope-denied")
    return paths


def apply_exact_patch(
    repo_root: Path,
    request: OrchestrationRequest,
    payload: bytes,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> PatchTruth:
    """Apply exact authorized bytes and bind the post-apply full-index diff."""

    snapshot = validate_reusable_worktree(repo_root, request)
    try:
        inspected = inspect_proposal_bytes(payload)
    except PatchInspectionError as exc:
        raise OrchestrationGitError("proposal-invalid") from exc
    paths = validate_inspected_scope(request, inspected, repo_root=snapshot.path)
    if cancelled():
        raise OrchestrationGitError("cancelled")
    checked = git_process(
        snapshot.path,
        "apply",
        "--check",
        "-",
        input_bytes=payload,
        cancelled=cancelled,
    )
    if checked.cancelled:
        raise OrchestrationGitError("cancelled")
    if checked.returncode != 0:
        raise OrchestrationGitError("patch-check-failed")
    _ = validate_reusable_worktree(repo_root, request)
    if cancelled():
        raise OrchestrationGitError("cancelled")
    applied = git_process(
        snapshot.path,
        "apply",
        "-",
        input_bytes=payload,
        cancelled=cancelled,
    )
    if applied.cancelled:
        raise OrchestrationGitError("interrupted")
    if applied.returncode != 0:
        raise OrchestrationGitError("patch-apply-failed")
    new_files = tuple(_string_items(inspected.get("new_files")))
    if new_files:
        intent = git_process(
            snapshot.path,
            "add",
            "--intent-to-add",
            "--",
            *new_files,
            cancelled=cancelled,
        )
        if intent.cancelled or intent.returncode != 0:
            raise OrchestrationGitError("interrupted")
    current = _validate_target_identity(snapshot.path, request, require_clean=False)
    if current.head != request.base_commit:
        raise OrchestrationGitError("post-apply-mismatch")
    truth = _patch_truth(snapshot.path, request.base_commit)
    if truth.paths != paths:
        raise OrchestrationGitError("post-apply-mismatch")
    return truth


def applied_integrity_matches(
    request: OrchestrationRequest,
    expected: PatchTruth,
) -> bool:
    """Revalidate applied branch/base identity and exact worktree/index state."""

    try:
        _ = _validate_target_identity(Path(request.worktree_path), request, require_clean=False)
        return _patch_truth(Path(request.worktree_path), request.base_commit) == expected
    except OrchestrationGitError:
        return False


def _validate_target_identity(
    target: Path,
    request: OrchestrationRequest,
    *,
    require_clean: bool,
) -> WorktreeSnapshot:
    top = Path(git_text(target, "rev-parse", "--show-toplevel")).resolve()
    if top != target.resolve():
        raise OrchestrationGitError("worktree-mismatch")
    branch_result = git_process(target, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result.returncode != 0 or branch_result.stdout.strip() != request.branch:
        raise OrchestrationGitError("worktree-mismatch")
    common_raw = Path(git_text(target, "rev-parse", "--git-common-dir"))
    common = common_raw if common_raw.is_absolute() else target / common_raw
    if common.resolve() != Path(request.common_git_dir).resolve():
        raise OrchestrationGitError("worktree-mismatch")
    if operation_active(target):
        raise OrchestrationGitError("worktree-mismatch")
    head = git_text(target, "rev-parse", "HEAD")
    if head != request.base_commit:
        raise OrchestrationGitError("stale-base")
    status = git_text(target, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if require_clean and status:
        raise OrchestrationGitError("worktree-dirty")
    tree = git_text(target, "rev-parse", "HEAD^{tree}")
    return WorktreeSnapshot(target.resolve(), request.branch, common.resolve(), head, tree)


def _patch_truth(worktree: Path, base: str) -> PatchTruth:
    diff = git_bytes(
        worktree,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        base,
        "--",
    )
    names = git_bytes(worktree, "diff", "--name-only", "-z", "--no-renames", base, "--")
    paths = tuple(sorted(part.decode("utf-8") for part in names.split(b"\0") if part))
    summary = git_text(worktree, "diff", "--summary", "--no-renames", base, "--")
    if "mode change" in summary or "120000" in summary or "160000" in summary:
        raise OrchestrationGitError("post-apply-mismatch")
    diff_sha = hashlib.sha256(diff).hexdigest()
    manifest = hashlib.sha256(base.encode() + b"\0" + diff).hexdigest()
    status = git_bytes(
        worktree,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    return PatchTruth(
        git_text(worktree, "rev-parse", "HEAD"),
        manifest,
        diff_sha,
        paths,
        hashlib.sha256(status).hexdigest(),
    )


def _inspected_paths(inspected: dict[str, object]) -> tuple[str, ...]:
    value = inspected.get("changed_files")
    if not isinstance(value, list) or not value or not all(isinstance(path, str) for path in value):
        raise OrchestrationGitError("proposal-invalid")
    return tuple(sorted(set(value)))


def _string_items(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise OrchestrationGitError("proposal-invalid")
    return tuple(value)


def _in_allowed_scope(path: str, scopes: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, scope) for scope in scopes)
