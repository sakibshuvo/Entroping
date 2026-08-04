"""Bounded Git process and diff helpers for Tier A delivery."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_pr_delivery_models import DeliveryGitError

_GIT: Final = "/usr/bin/git"
_TIMEOUT: Final = 15.0
_OUTPUT_LIMIT: Final = 1_048_576
_BASE_ENV: Final = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "LANG": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def canonical_diff(worktree: Path, base: str) -> bytes:
    """Read the canonical uncommitted binary diff without external filters."""

    return git_bytes(
        worktree,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        base,
        "--",
    )


def diff_paths(worktree: Path, base: str, *, cached: bool) -> tuple[str, ...]:
    """Return sorted, NUL-delimited changed paths for one index state."""

    args = ["diff"]
    if cached:
        args.append("--cached")
    args.extend(("--name-only", "-z", "--no-renames", base, "--"))
    raw = git_bytes(worktree, *args)
    return tuple(sorted(part.decode("utf-8") for part in raw.split(b"\0") if part))


def status_paths(worktree: Path) -> tuple[str, ...]:
    """Return paths from bounded porcelain status output."""

    raw = git_bytes(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    paths: list[str] = []
    for item in raw.split(b"\0"):
        if item:
            paths.append(item[3:].decode("utf-8"))
    return tuple(paths)


def git_text(cwd: Path, *args: str) -> str:
    """Run one bounded Git command and return sanitized text."""

    return git_bytes(cwd, *args).decode().strip()


def git_ok(cwd: Path, *args: str) -> None:
    """Run one bounded Git command and discard its bounded output."""

    _ = git_bytes(cwd, *args)


def git_bytes(
    cwd: Path,
    *args: str,
    input_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
    stdout_consumer: Callable[[bytes], None] | None = None,
) -> bytes:
    """Run fixed Git with bounded output and a scrubbed environment."""

    chunks: list[bytes] = []
    consumer = chunks.append if stdout_consumer is None else stdout_consumer
    try:
        result = run_bounded_process(
            [_GIT, *args],
            cwd=cwd,
            timeout_seconds=_TIMEOUT,
            max_output_bytes=_OUTPUT_LIMIT,
            env=dict(_BASE_ENV) if env is None else dict(env),
            input_bytes=input_bytes,
            stdout_consumer=consumer,
            capture_stdout=False,
        )
    except BoundedProcessError:
        raise DeliveryGitError("git-failed") from None
    if result.returncode != 0 or result.timed_out or result.output_limit_exceeded:
        raise DeliveryGitError("git-failed")
    return b"".join(chunks)
