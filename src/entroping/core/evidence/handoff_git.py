"""Bounded, sanitized Git metadata for handoff evidence."""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Final

from entroping.core.evidence_common import safe_evidence_text

GIT_TIMEOUT_SECONDS: Final = 2.0
_GIT_COMMIT_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_GIT_SUBPROCESS_SYSTEM_PATHS: Final = ("/usr/bin", "/bin")


def read_git_metadata(root: Path) -> tuple[str | None, str | None]:
    """Return sanitized branch text and a validated full commit identifier."""
    branch = _git_output(root, "branch", "--show-current")
    commit = _git_output(root, "rev-parse", "HEAD")
    safe_branch = safe_evidence_text(branch) if branch is not None else ""
    safe_commit = (
        commit
        if commit is not None and _GIT_COMMIT_PATTERN.fullmatch(commit) is not None
        else None
    )
    return safe_branch or None, safe_commit


def _git_output(root: Path, *args: str) -> str | None:
    git_binary = shutil.which("git")
    if git_binary is None:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [git_binary, "-C", str(root), *args],
            check=False,
            capture_output=True,
            env=_minimal_git_subprocess_env(git_binary),
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _minimal_git_subprocess_env(git_binary: str) -> dict[str, str]:
    path_entries = [
        str(Path(git_binary).resolve().parent),
        *_GIT_SUBPROCESS_SYSTEM_PATHS,
    ]
    return {"PATH": ":".join(dict.fromkeys(path_entries))}
