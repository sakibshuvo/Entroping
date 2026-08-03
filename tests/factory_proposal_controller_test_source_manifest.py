from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from factory_proposal_controller_test_receipt_contracts import (
    MAX_SUMMARIZED_BYTES,
    MAX_SUMMARIZED_FILE_BYTES,
    MAX_SUMMARIZED_FILES,
)

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
    untracked = _RUN_SUBPROCESS(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    untracked_total = 0
    byte_total = 0
    for raw_path in untracked.split(b"\0"):
        if not raw_path:
            continue
        untracked_total += 1
        if untracked_total > MAX_SUMMARIZED_FILES:
            raise AssertionError("untracked source file count exceeds manifest bound")
        path = REPO_ROOT / raw_path.decode("utf-8")
        metadata = path.lstat()
        digest.update(raw_path)
        digest.update(str(metadata.st_mode).encode())
        digest.update(str(metadata.st_size).encode())
        if stat.S_ISLNK(metadata.st_mode):
            digest.update(os.readlink(path).encode())
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise AssertionError("untracked source entry is not a regular file")
        if metadata.st_size > MAX_SUMMARIZED_FILE_BYTES:
            raise AssertionError("untracked source file exceeds manifest bound")
        byte_total += metadata.st_size
        if byte_total > MAX_SUMMARIZED_BYTES:
            raise AssertionError("untracked source bytes exceed manifest bound")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
            ):
                raise AssertionError("untracked source changed during manifest capture")
            while chunk := os.read(descriptor, 64 * 1024):
                digest.update(chunk)
        finally:
            os.close(descriptor)
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
