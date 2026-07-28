from __future__ import annotations

import fcntl
import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path

from scripts.factory_retention_fs import RetentionFsError, list_names, open_relative_directory

from .errors import FactoryMetricsError

ACTIVE_METRICS_BYTE_LIMIT = 67_108_864
ACTIVE_METRICS_ENTRY_LIMIT = 10_000
ACTIVE_METRICS_DEPTH_LIMIT = 32
_LOCK_NAME = ".metrics-storage.lock"


def append_bounded(path: Path, payload: bytes) -> None:
    root, parts = _active_target(path)
    try:
        with open_relative_directory(
            root.parent.parent,
            (".entroping", "factory-metrics"),
            create=True,
        ) as root_fd:
            lock_fd = _open_lock(root_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                with open_relative_directory(root, parts[:-1], create=True) as parent_fd:
                    existing_size = _existing_regular_size(parent_fd, parts[-1])
                    total = _active_total(root_fd)
                    _require_capacity(total + len(payload))
                    descriptor = _open_regular(parent_fd, parts[-1], append=True)
                    try:
                        if os.fstat(descriptor).st_size != existing_size:
                            raise FactoryMetricsError(
                                "factory metrics target changed during bounded append"
                            )
                        _write_all(descriptor, payload)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    os.fsync(parent_fd)
            finally:
                os.close(lock_fd)
    except RetentionFsError as exc:
        raise FactoryMetricsError("factory metrics storage path is unsafe") from exc


def replace_bounded(path: Path, payload: bytes) -> None:
    root, parts = _active_target(path)
    try:
        with open_relative_directory(
            root.parent.parent,
            (".entroping", "factory-metrics"),
            create=True,
        ) as root_fd:
            lock_fd = _open_lock(root_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                with open_relative_directory(root, parts[:-1], create=True) as parent_fd:
                    existing_size = _existing_regular_size(parent_fd, parts[-1])
                    total = _active_total(root_fd)
                    _require_capacity(total - existing_size + len(payload))
                    _atomic_replace(parent_fd, parts[-1], payload)
            finally:
                os.close(lock_fd)
    except RetentionFsError as exc:
        raise FactoryMetricsError("factory metrics storage path is unsafe") from exc


def _active_target(path: Path) -> tuple[Path, tuple[str, ...]]:
    if not path.is_absolute():
        raise FactoryMetricsError("factory metrics target must be absolute")
    root = next(
        (
            parent
            for parent in (path, *path.parents)
            if parent.name == "factory-metrics" and parent.parent.name == ".entroping"
        ),
        None,
    )
    if root is None:
        raise FactoryMetricsError("factory metrics target is outside its managed root")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise FactoryMetricsError("factory metrics target is outside its managed root") from exc
    parts = relative.parts
    if (
        not parts
        or parts[0] == "finished-issues"
        or any(
            not part
            or Path(part).name != part
            or any(ord(character) < 32 or ord(character) == 127 for character in part)
            for part in parts
        )
    ):
        raise FactoryMetricsError("factory metrics target is not an active canonical path")
    return root, parts


def _open_lock(root_fd: int) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(_LOCK_NAME, flags, 0o600, dir_fd=root_fd)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise FactoryMetricsError("factory metrics storage lock is unsafe")
    return descriptor


def _active_total(root_fd: int) -> int:
    seen = [0]
    return _directory_total(root_fd, depth=0, seen=seen)


def _directory_total(directory_fd: int, *, depth: int, seen: list[int]) -> int:
    if depth > ACTIVE_METRICS_DEPTH_LIMIT:
        raise FactoryMetricsError("active factory metrics exceed the directory depth limit")
    total = 0
    for name in list_names(directory_fd):
        if depth == 0 and name in {"finished-issues", _LOCK_NAME}:
            continue
        seen[0] += 1
        if seen[0] > ACTIVE_METRICS_ENTRY_LIMIT:
            raise FactoryMetricsError("active factory metrics exceed the entry limit")
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            total += metadata.st_size
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            raise FactoryMetricsError("active factory metrics contain an unsafe entry")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        child_fd = os.open(name, flags, dir_fd=directory_fd)
        try:
            total += _directory_total(child_fd, depth=depth + 1, seen=seen)
        finally:
            os.close(child_fd)
    return total


def _existing_regular_size(directory_fd: int, name: str) -> int:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return 0
    if not stat.S_ISREG(metadata.st_mode):
        raise FactoryMetricsError("factory metrics target must be a regular file")
    return metadata.st_size


def _open_regular(directory_fd: int, name: str, *, append: bool) -> int:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    if append:
        flags |= os.O_APPEND
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise FactoryMetricsError("factory metrics target must be a regular file")
    return descriptor


def _atomic_replace(directory_fd: int, name: str, payload: bytes) -> None:
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])


def _require_capacity(prospective_bytes: int) -> None:
    if prospective_bytes > ACTIVE_METRICS_BYTE_LIMIT:
        raise FactoryMetricsError(
            "active factory metrics exceed the 67108864-byte aggregate limit"
        )
