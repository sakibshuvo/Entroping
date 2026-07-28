from __future__ import annotations

import os
import subprocess  # nosec B404
from pathlib import Path, PurePosixPath

MAX_TRACKED_PATH_BYTES = 8_388_608


class RetentionGitError(RuntimeError):
    pass


def tracked_paths(repo_root: Path) -> frozenset[str]:
    try:
        top_level = subprocess.run(  # nosec B603
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        listing = subprocess.run(  # nosec B603
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RetentionGitError("retention requires a readable Git worktree index") from exc
    try:
        discovered = Path(os.fsdecode(top_level.stdout).strip()).resolve(strict=True)
    except OSError as exc:
        raise RetentionGitError("retention Git worktree root is unavailable") from exc
    if discovered != repo_root.resolve(strict=True):
        raise RetentionGitError("retention root must be the Git worktree root")
    if len(listing.stdout) > MAX_TRACKED_PATH_BYTES:
        raise RetentionGitError("tracked-path inventory exceeds its safety limit")
    return frozenset(
        os.fsdecode(raw)
        for raw in listing.stdout.split(b"\0")
        if raw
    )


def require_untracked_path(
    source: PurePosixPath,
    tracked: frozenset[str],
) -> None:
    value = source.as_posix()
    prefix = f"{value}/"
    if value in tracked or any(path.startswith(prefix) for path in tracked):
        raise RetentionGitError("retention refuses to mutate a Git-tracked path")


def require_untracked_control_state(tracked: frozenset[str]) -> None:
    protected = (
        ".entroping/retention-journal/",
        ".entroping/retention-trash/",
    )
    if any(path.startswith(protected) for path in tracked):
        raise RetentionGitError("retention control state contains a Git-tracked path")
