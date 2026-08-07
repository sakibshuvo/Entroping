"""Bounded raw-byte Git subprocess helpers for orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Final

from scripts.bounded_process import BoundedProcessError, BoundedProcessResult, run_bounded_process
from scripts.factory_orchestration_errors import OrchestrationGitError

_GIT: Final = "/usr/bin/git"
_TIMEOUT_SECONDS: Final = 10.0
_OUTPUT_BYTES: Final = 1_048_576
_ENV: Final = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}


def git_text(cwd: Path, *args: str) -> str:
    result = git_process(cwd, *args)
    if result.returncode != 0:
        raise OrchestrationGitError("worktree-mismatch")
    return result.stdout.strip()


def git_bytes(cwd: Path, *args: str) -> bytes:
    chunks: list[bytes] = []
    try:
        result = run_bounded_process(
            [_GIT, *args],
            cwd=cwd,
            timeout_seconds=_TIMEOUT_SECONDS,
            max_output_bytes=_OUTPUT_BYTES,
            env=_ENV,
            stdout_consumer=chunks.append,
            capture_stdout=False,
        )
    except BoundedProcessError as exc:
        raise OrchestrationGitError("post-apply-mismatch") from exc
    if result.returncode != 0 or result.timed_out or result.output_limit_exceeded:
        raise OrchestrationGitError("post-apply-mismatch")
    return b"".join(chunks)


def checkout_identity_sha256(worktree: Path) -> str:
    """Bind checkout HEAD, index/worktree diff, and status metadata."""

    top = git_text(worktree, "rev-parse", "--show-toplevel").encode()
    branch = git_text(worktree, "symbolic-ref", "--quiet", "--short", "HEAD").encode()
    common = git_text(worktree, "rev-parse", "--git-common-dir").encode()
    head = git_text(worktree, "rev-parse", "HEAD").encode()
    diff = git_bytes(worktree, "diff", "--binary", "--full-index", "HEAD", "--")
    status = git_bytes(
        worktree,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    return hashlib.sha256(
        b"\0".join((top, branch, common, head, diff, status))
    ).hexdigest()


def git_process(
    cwd: Path,
    *args: str,
    input_bytes: bytes | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> BoundedProcessResult:
    try:
        result = run_bounded_process(
            [_GIT, *args],
            cwd=cwd,
            timeout_seconds=_TIMEOUT_SECONDS,
            max_output_bytes=_OUTPUT_BYTES,
            env=_ENV,
            input_bytes=input_bytes,
            cancelled=cancelled,
        )
    except BoundedProcessError as exc:
        raise OrchestrationGitError("worktree-mismatch") from exc
    if result.timed_out or result.output_limit_exceeded:
        raise OrchestrationGitError("worktree-mismatch")
    return result
