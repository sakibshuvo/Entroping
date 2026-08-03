from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_RUN_SUBPROCESS = subprocess.run


@dataclass(frozen=True, slots=True)
class SourceManifest:
    digest: str


def source_manifest() -> SourceManifest:
    """Digest tracked source and read-only Git identity, refs, index, and status."""

    digest = hashlib.sha256()
    tracked = _RUN_SUBPROCESS(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, check=True, capture_output=True
    ).stdout
    for raw_path in tracked.split(b"\0"):
        if raw_path:
            digest.update(raw_path)
            digest.update((REPO_ROOT / raw_path.decode("utf-8")).read_bytes())
    for command in (("rev-parse", "HEAD"), ("for-each-ref",), ("status", "--porcelain=v1")):
        digest.update(
            _RUN_SUBPROCESS(
                ["git", *command], cwd=REPO_ROOT, check=True, capture_output=True
            ).stdout
        )
    index = (
        _RUN_SUBPROCESS(
            ["git", "rev-parse", "--git-path", "index"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )
    digest.update(hashlib.sha256((REPO_ROOT / index).read_bytes()).digest())
    return SourceManifest(digest.hexdigest())
