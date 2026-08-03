from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

from factory_proposal_controller_test_receipt_contracts import (
    MAX_RECEIPT_BYTES,
    MAX_SUMMARIZED_BYTES,
    MAX_SUMMARIZED_FILE_BYTES,
    MAX_SUMMARIZED_FILES,
    MAX_SUMMARIZED_PATHS,
    StateSummary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def receipt_path(root: Path, scenario: str) -> Path:
    configured = os.environ.get("ENTROPING_PROPOSAL_RECEIPTS_DIR")
    candidate = Path(configured or root / "receipts")
    absolute = candidate.absolute()
    allowed = (REPO_ROOT / ".omo" / "evidence").absolute()
    if ".." in absolute.parts or not (
        _within(absolute, allowed) or _within(absolute, root.absolute())
    ):
        raise AssertionError("receipt destination escapes the approved fixture or evidence root")
    descriptor = open_directory(absolute, create=True)
    aggregate = configured is not None and _within(absolute, allowed)
    suffix = (
        f"-{hashlib.sha256(str(root.absolute()).encode()).hexdigest()[:12]}" if aggregate else ""
    )
    leaf = f"{scenario}{suffix}.json"
    try:
        try:
            os.stat(leaf, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return absolute / leaf
        raise AssertionError("receipt destination is reused or unsafe")
    finally:
        os.close(descriptor)


def write_new_receipt(path: Path, encoded: str) -> None:
    parent = open_directory(path.parent.absolute(), create=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path.name, flags, 0o600, dir_fd=parent)
    committed = False
    try:
        metadata = os.fstat(descriptor)
        data = encoded.encode()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise AssertionError("receipt destination is not an exclusive regular file")
        if len(data) > MAX_RECEIPT_BYTES or os.write(descriptor, data) != len(data):
            raise AssertionError("receipt write was incomplete or exceeded its bound")
        committed = True
    finally:
        os.close(descriptor)
        if not committed:
            with suppress(FileNotFoundError):
                os.unlink(path.name, dir_fd=parent)
        os.close(parent)


def open_directory(path: Path, *, create: bool) -> int:
    """Open every absolute ancestor without following links."""

    if not path.is_absolute():
        raise AssertionError("receipt directory must be absolute")
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:]:
            flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
            try:
                child = os.open(name, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise AssertionError("receipt directory is missing") from None
                os.mkdir(name, 0o700, dir_fd=current)
                child = os.open(name, flags, dir_fd=current)
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise AssertionError("receipt ancestor is not a directory")
            os.close(current)
            current = child
        return current
    except (OSError, AssertionError) as exc:
        os.close(current)
        if isinstance(exc, AssertionError):
            raise
        raise AssertionError("receipt ancestor traversal failed") from exc


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
