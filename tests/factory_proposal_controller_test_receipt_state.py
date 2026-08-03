from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from factory_proposal_controller_test_receipt_contracts import (
    MAX_SUMMARIZED_BYTES,
    MAX_SUMMARIZED_FILE_BYTES,
    MAX_SUMMARIZED_FILES,
    MAX_SUMMARIZED_PATHS,
    StateSummary,
)


def state_summary(root: Path) -> StateSummary:
    """Stream declared durable state and stop before any configured bound is exceeded."""

    digest = hashlib.sha256()
    file_total = 0
    byte_total = 0
    path_total = 0
    categories: list[tuple[str, str]] = []
    durable = (
        (root / ".entroping", ".entroping"),
        (root / "fake-worker-events.json", "fake-worker"),
    )
    for durable_root, category in durable:
        if not durable_root.exists() and not durable_root.is_symlink():
            continue
        category_digest = hashlib.sha256()
        for path in _walk(durable_root):
            path_total += 1
            if path_total > MAX_SUMMARIZED_PATHS:
                raise AssertionError("scenario durable path count exceeds summary bound")
            metadata = path.stat(follow_symlinks=False)
            relative = path.relative_to(root).as_posix().encode()
            for current in (digest, category_digest):
                current.update(relative)
                current.update(str(metadata.st_mode).encode())
                current.update(str(metadata.st_size).encode())
            if path.is_symlink():
                digest.update(b"symlink")
                category_digest.update(b"symlink")
                continue
            if not path.is_file():
                continue
            file_total += 1
            if file_total > MAX_SUMMARIZED_FILES:
                raise AssertionError("scenario durable file count exceeds summary bound")
            if metadata.st_size > MAX_SUMMARIZED_FILE_BYTES:
                raise AssertionError("scenario durable file exceeds per-file summary bound")
            byte_total += metadata.st_size
            if byte_total > MAX_SUMMARIZED_BYTES:
                raise AssertionError("scenario durable bytes exceed aggregate summary bound")
            content = _file_digest(path)
            digest.update(content)
            category_digest.update(content)
        categories.append((category, category_digest.hexdigest()))
    return StateSummary(digest.hexdigest(), file_total, byte_total, tuple(sorted(categories)))


def _walk(root: Path) -> Iterator[Path]:
    yield root
    if root.is_dir() and not root.is_symlink():
        for directory, names, files in os.walk(root, followlinks=False):
            names.sort()
            files.sort()
            parent = Path(directory)
            for name in (*names, *files):
                yield parent / name


def _file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.digest()
