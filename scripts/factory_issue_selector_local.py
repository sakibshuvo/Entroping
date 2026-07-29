from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path, PurePosixPath

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_issue_selector_json import JsonBoundaryError, decode_json
from scripts.factory_issue_selector_models import (
    ActiveState,
    GitHubSnapshot,
)
from scripts.factory_issue_selector_parser import normalize_scope
from scripts.factory_retention_fs import (
    RetentionFsError,
    list_names,
    open_relative_directory,
    path_exists,
    read_bounded_regular,
)

_WORKTREE_RE = re.compile(r"^Entroping-issue-(?P<number>[1-9][0-9]*)$")
_BRANCH_ISSUE_RE = re.compile(
    r"(?:^|[/_-])issue[-_](?P<number>[1-9][0-9]*)(?:$|[/_-])"
)
_QUEUE_PARTS = ((".entroping", "ai-jobs", "queued"), (".entroping", "ai-jobs", "running"))
_MAX_JOB_BYTES = 1_048_576
_MAX_SCOPE_ENTRIES = 10_000


def collect_active_state(
    *,
    repo_root: Path,
    snapshot: GitHubSnapshot,
    lease_state_complete: bool,
    lease_issue_numbers: frozenset[int],
    lease_scopes: tuple[str, ...],
) -> ActiveState:
    complete = lease_state_complete
    worktree_numbers, worktrees_complete = _worktree_issues(repo_root)
    branch_numbers, branches_complete = _branch_issues(repo_root)
    queue_numbers, queue_scopes, queue_complete = _queue_state(repo_root)
    complete = complete and worktrees_complete and branches_complete and queue_complete

    normalized_leases = tuple(normalize_scope(scope) for scope in lease_scopes)
    if any(
        scope is None or scope_has_symlink(repo_root, scope)
        for scope in normalized_leases
    ):
        complete = False
    occupied = set(snapshot.open_pr_scopes)
    occupied.update(queue_scopes)
    occupied.update(scope for scope in normalized_leases if scope is not None)
    if any(scope_has_symlink(repo_root, scope) for scope in occupied):
        complete = False
    owned = set(snapshot.open_pr_issue_numbers)
    owned.update(worktree_numbers)
    owned.update(branch_numbers)
    owned.update(queue_numbers)
    if any(isinstance(number, bool) or number <= 0 for number in lease_issue_numbers):
        complete = False
    else:
        owned.update(lease_issue_numbers)

    issues_by_number = {issue.number: issue for issue in snapshot.issues}
    for issue_number in owned:
        issue = issues_by_number.get(issue_number)
        if issue is None or not issue.allowed_scopes:
            complete = False
            continue
        if any(scope_has_symlink(repo_root, scope) for scope in issue.allowed_scopes):
            complete = False
            continue
        occupied.update(issue.allowed_scopes)
    return ActiveState(
        complete=complete,
        owned_issue_numbers=frozenset(owned),
        occupied_scopes=tuple(sorted(occupied)),
    )


def _worktree_issues(repo_root: Path) -> tuple[frozenset[int], bool]:
    output, command_complete = _run_git(repo_root, "worktree", "list", "--porcelain")
    if not command_complete:
        return frozenset(), False
    if not output.strip():
        return frozenset(), False
    issue_numbers: set[int] = set()
    complete = True
    records = [record.splitlines() for record in output.split("\n\n") if record]
    paths = [line for line in records[0] if line.startswith("worktree ")] if records else []
    if len(paths) != 1:
        return frozenset(), False
    primary = Path(paths[0].removeprefix("worktree ")).absolute()
    for record in records:
        path_lines = [line for line in record if line.startswith("worktree ")]
        if len(path_lines) != 1:
            complete = False
            continue
        worktree = Path(path_lines[0].removeprefix("worktree ")).absolute()
        if worktree == primary:
            continue
        branch_lines = [line for line in record if line.startswith("branch ")]
        detached = "detached" in record
        if len(branch_lines) != 1 or detached:
            complete = False
        match = _WORKTREE_RE.fullmatch(worktree.name)
        if match is None:
            complete = False
        else:
            issue_numbers.add(int(match.group("number")))
    return frozenset(issue_numbers), complete


def _branch_issues(repo_root: Path) -> tuple[frozenset[int], bool]:
    output, complete = _run_git(
        repo_root,
        "branch",
        "--no-merged",
        "main",
        "--format=%(refname:short)%09%(worktreepath)",
    )
    issue_numbers: set[int] = set()
    for line in output.splitlines():
        parts = line.split("\t", maxsplit=1)
        if len(parts) != 2 or not parts[0]:
            complete = False
            continue
        branch, worktree_text = parts
        if worktree_text:
            worktree = Path(worktree_text).absolute()
            match = _WORKTREE_RE.fullmatch(worktree.name)
        else:
            match = _BRANCH_ISSUE_RE.search(branch)
        if match is None:
            complete = False
        else:
            issue_numbers.add(int(match.group("number")))
    return frozenset(issue_numbers), complete


def _queue_state(repo_root: Path) -> tuple[frozenset[int], tuple[str, ...], bool]:
    issue_numbers: set[int] = set()
    scopes: set[str] = set()
    complete = True
    for parts in _QUEUE_PARTS:
        if not path_exists(repo_root, parts):
            continue
        try:
            with open_relative_directory(repo_root, parts) as directory_fd:
                for name in list_names(directory_fd):
                    if not name.endswith(".json"):
                        complete = False
                        continue
                    raw = read_bounded_regular(directory_fd, name, limit=_MAX_JOB_BYTES)
                    issue, files = _job_state(raw)
                    issue_numbers.add(issue)
                    scopes.update(files)
        except (OSError, RetentionFsError, ValueError):
            complete = False
    return frozenset(issue_numbers), tuple(sorted(scopes)), complete


def _job_state(raw: bytes) -> tuple[int, tuple[str, ...]]:
    try:
        value = decode_json(raw)
    except JsonBoundaryError as exc:
        raise ValueError("queue job JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("queue job must be an object")
    issue = value.get("issue")
    if isinstance(issue, bool):
        raise ValueError("queue issue must be numeric")
    text = str(issue).strip() if issue is not None else ""
    if not text.isdigit() or int(text) <= 0:
        raise ValueError("queue issue must be numeric")
    raw_files = value.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("queue files must be a list")
    normalized = tuple(
        normalize_scope(item) if isinstance(item, str) else None
        for item in raw_files
    )
    if not normalized or any(item is None for item in normalized):
        raise ValueError("queue files must contain safe scopes")
    return int(text), tuple(sorted(set(item for item in normalized if item is not None)))


def scope_has_symlink(repo_root: Path, scope: str) -> bool:
    if repo_root.is_symlink():
        return True
    normalized = normalize_scope(scope)
    if normalized is None:
        return True
    candidate = repo_root
    wildcard: str | None = None
    for component in PurePosixPath(normalized).parts:
        if "*" in component:
            wildcard = component
            break
        candidate /= component
        if candidate.is_symlink():
            return True
    if wildcard is None:
        return False
    if wildcard == "**":
        return _tree_has_symlink(candidate)
    try:
        with os.scandir(candidate) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > _MAX_SCOPE_ENTRIES:
                    return True
                if fnmatch.fnmatchcase(
                    entry.name.casefold(), wildcard.casefold()
                ) and entry.is_symlink():
                    return True
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return False


def _tree_has_symlink(root: Path) -> bool:
    pending = [root]
    seen = 0
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    seen += 1
                    if seen > _MAX_SCOPE_ENTRIES or entry.is_symlink():
                        return True
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
        except FileNotFoundError:
            continue
        except OSError:
            return True
    return False


def _run_git(repo_root: Path, *arguments: str) -> tuple[str, bool]:
    try:
        completed = run_bounded_process(
            ["git", "-C", repo_root, *arguments],
            cwd=repo_root,
            timeout_seconds=15,
            max_output_bytes=1_048_576,
        )
    except BoundedProcessError:
        return "", False
    complete = (
        completed.returncode == 0
        and not completed.timed_out
        and not completed.output_limit_exceeded
    )
    return completed.stdout, complete
