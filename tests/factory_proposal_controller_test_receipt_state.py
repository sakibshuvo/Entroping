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

    file_total = 0
    byte_total = 0
    path_total = 0
    categories: list[tuple[str, str]] = []
    durable = (
        (root / ".entroping", ".entroping"),
        (root / "fake-worker-events.json", "fake-worker"),
        (root / "provider-model-events.json", "provider-model"),
    )
    for durable_root, category in durable:
        if not durable_root.exists() and not durable_root.is_symlink():
            continue
        category_sum = 0
        for path in _walk(durable_root, MAX_SUMMARIZED_PATHS - path_total):
            path_total += 1
            metadata = path.stat(follow_symlinks=False)
            relative = path.relative_to(root).as_posix().encode()
            record = hashlib.sha256()
            record.update(relative)
            record.update(str(metadata.st_mode).encode())
            record.update(str(metadata.st_size).encode())
            if path.is_symlink():
                record.update(b"symlink")
            elif path.is_file():
                file_total += 1
                if file_total > MAX_SUMMARIZED_FILES:
                    raise AssertionError("scenario durable file count exceeds summary bound")
                if metadata.st_size > MAX_SUMMARIZED_FILE_BYTES:
                    raise AssertionError("scenario durable file exceeds per-file summary bound")
                byte_total += metadata.st_size
                if byte_total > MAX_SUMMARIZED_BYTES:
                    raise AssertionError("scenario durable bytes exceed aggregate summary bound")
                record.update(_file_digest(path))
            category_sum = (category_sum + int.from_bytes(record.digest())) % (1 << 256)
        categories.append((category, f"{category_sum:064x}"))
    ordered = tuple(sorted(categories))
    digest = hashlib.sha256()
    for category, category_digest in ordered:
        digest.update(category.encode())
        digest.update(category_digest.encode())
    return StateSummary(digest.hexdigest(), file_total, byte_total, ordered)


def _walk(root: Path, limit: int = MAX_SUMMARIZED_PATHS) -> Iterator[Path]:
    if limit < 1:
        raise AssertionError("scenario durable path count exceeds summary bound")
    yield root
    if not root.is_dir() or root.is_symlink():
        return
    discovered = 1
    stack = [os.scandir(root)]
    try:
        while stack:
            iterator = stack[-1]
            try:
                entry = next(iterator)
            except StopIteration:
                iterator.close()
                stack.pop()
                continue
            discovered += 1
            if discovered > limit:
                raise AssertionError("scenario durable path count exceeds summary bound")
            path = Path(entry.path)
            yield path
            if entry.is_dir(follow_symlinks=False):
                stack.append(os.scandir(path))
    finally:
        for iterator in stack:
            iterator.close()


def _file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.digest()
