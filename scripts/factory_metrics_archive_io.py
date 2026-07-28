from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from scripts.factory_metrics_archive_validation import (
    FactoryMetricsArchiveValidationError,
    validate_ledger_payload,
)
from scripts.factory_metrics_modules.storage import (
    ACTIVE_METRICS_BYTE_LIMIT,
    ACTIVE_METRICS_DEPTH_LIMIT,
    ACTIVE_METRICS_ENTRY_LIMIT,
)
from scripts.factory_retention_fs import RetentionFsError, list_names

type LedgerSpec = tuple[tuple[str, ...], int, int, int, int]


class FactoryMetricsArchiveIoError(RuntimeError):
    pass


def safe_root(path: Path, *, label: str) -> Path:
    try:
        metadata = path.lstat()
        root = path.resolve(strict=True)
    except OSError as exc:
        raise FactoryMetricsArchiveIoError(f"{label} root is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise FactoryMetricsArchiveIoError(f"{label} root must be a non-symlink directory")
    return root


@contextmanager
def open_metrics_source(worktree_root: Path) -> Generator[int | None, None, None]:
    root = safe_root(worktree_root, label="worktree")
    root_fd = open_directory(root)
    entroping_fd = -1
    metrics_fd = -1
    lock_fd = -1
    try:
        try:
            entroping_fd = open_child_directory(root_fd, ".entroping")
            metrics_fd = open_child_directory(entroping_fd, "factory-metrics")
        except FileNotFoundError:
            yield None
            return
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(".metrics-storage.lock", flags, 0o600, dir_fd=metrics_fd)
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise FactoryMetricsArchiveIoError("factory metrics source lock must be a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield metrics_fd
    except OSError as exc:
        raise FactoryMetricsArchiveIoError("factory metrics source path is unsafe") from exc
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if metrics_fd >= 0:
            os.close(metrics_fd)
        if entroping_fd >= 0:
            os.close(entroping_fd)
        os.close(root_fd)


def discover_ledgers(source_fd: int) -> tuple[LedgerSpec, ...]:
    ledgers: list[LedgerSpec] = []
    try:
        _discover_directory(
            source_fd,
            prefix=(),
            depth=0,
            seen=[0],
            total=[0],
            ledgers=ledgers,
        )
    except (OSError, RetentionFsError) as exc:
        raise FactoryMetricsArchiveIoError("factory metrics source path is unsafe") from exc
    return tuple(ledgers)


def _discover_directory(
    directory_fd: int,
    *,
    prefix: tuple[str, ...],
    depth: int,
    seen: list[int],
    total: list[int],
    ledgers: list[LedgerSpec],
) -> None:
    if depth > ACTIVE_METRICS_DEPTH_LIMIT:
        raise FactoryMetricsArchiveIoError(
            "factory metrics archive exceeds the directory depth limit"
        )
    for name in list_names(directory_fd):
        if depth == 0 and name in {"finished-issues", ".metrics-storage.lock"}:
            continue
        seen[0] += 1
        if seen[0] > ACTIVE_METRICS_ENTRY_LIMIT:
            raise FactoryMetricsArchiveIoError("factory metrics archive exceeds the entry limit")
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        parts = (*prefix, name)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = open_child_directory(directory_fd, name)
            try:
                _discover_directory(
                    child_fd,
                    prefix=parts,
                    depth=depth + 1,
                    seen=seen,
                    total=total,
                    ledgers=ledgers,
                )
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(metadata.st_mode) or not name.endswith(".jsonl"):
            continue
        if metadata.st_size < 0 or total[0] > ACTIVE_METRICS_BYTE_LIMIT - metadata.st_size:
            raise FactoryMetricsArchiveIoError(
                "factory metrics archive exceeds the aggregate byte limit"
            )
        total[0] += metadata.st_size
        ledgers.append(
            (
                parts,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_dev,
                metadata.st_ino,
            )
        )


def read_source_ledger(source_fd: int, spec: LedgerSpec) -> bytes:
    parts, expected_size, expected_mtime, expected_device, expected_inode = spec
    try:
        with open_descendant_directory(source_fd, parts[:-1], create=False) as parent_fd:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(parts[-1], flags, dir_fd=parent_fd)
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size != expected_size
                    or before.st_mtime_ns != expected_mtime
                    or before.st_dev != expected_device
                    or before.st_ino != expected_inode
                ):
                    raise FactoryMetricsArchiveIoError(
                        "factory metrics ledger changed during archival"
                    )
                payload = _read_exact(descriptor, expected_size)
                after = os.fstat(descriptor)
                if (
                    after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_dev != before.st_dev
                    or after.st_ino != before.st_ino
                ):
                    raise FactoryMetricsArchiveIoError(
                        "factory metrics ledger changed during archival"
                    )
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise FactoryMetricsArchiveIoError(
            "factory metrics ledger changed during archival"
        ) from exc
    try:
        validate_ledger_payload(payload)
    except FactoryMetricsArchiveValidationError as exc:
        raise FactoryMetricsArchiveIoError(str(exc)) from exc
    return payload


def _read_exact(descriptor: int, expected_size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(descriptor, min(65_536, remaining))
        if not chunk:
            raise FactoryMetricsArchiveIoError("factory metrics ledger changed during archival")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise FactoryMetricsArchiveIoError("factory metrics ledger changed during archival")
    return b"".join(chunks)


@contextmanager
def open_descendant_directory(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> Generator[int, None, None]:
    descriptors = [os.dup(root_fd)]
    try:
        for part in parts:
            child = (
                open_or_create_child_directory(descriptors[-1], part)
                if create
                else open_child_directory(descriptors[-1], part)
            )
            descriptors.append(child)
        yield descriptors[-1]
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def open_or_create_child_directory(parent_fd: int, name: str) -> int:
    with suppress(FileExistsError):
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    return open_child_directory(parent_fd, name)


def open_child_directory(parent_fd: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise FactoryMetricsArchiveIoError("factory metrics path must be a directory")
    return descriptor


def open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise FactoryMetricsArchiveIoError("factory metrics root must be a directory")
    return descriptor
