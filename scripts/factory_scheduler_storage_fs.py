from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
import time
from pathlib import Path

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError
from scripts.factory_budget_ledger_parent_fs import open_private_relative_directory
from scripts.factory_retention_fs import RetentionFsError

STATE_DIRECTORY = (".entroping", "factory-scheduler")
DATABASE_NAME = "scheduler.sqlite3"
INITIALIZING_NAME = ".scheduler.sqlite3.init"
INITIALIZATION_LOCK = "scheduler.lock"
RETENTION_LOCK = "retention.lock"
MAX_DATABASE_BYTES = 67_108_864
BUSY_TIMEOUT_MILLISECONDS = 100
LOCK_RETRY_SECONDS = 0.01
SQLITE_HEADER_BYTES = 20
SQLITE_HEADER_PREFIX = b"SQLite format 3\x00"
type FileIdentity = tuple[int, int, int, int, int]


class SchedulerStateError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validated_existing_identity(root: Path) -> FileIdentity:
    try:
        with open_private_relative_directory(
            root,
            STATE_DIRECTORY,
            create=False,
        ) as directory_fd:
            reject_unsafe_sidecars(directory_fd)
            return file_identity(directory_fd, DATABASE_NAME)
    except SchedulerStateError:
        raise
    except (FactoryBudgetLedgerError, OSError, RetentionFsError) as exc:
        raise SchedulerStateError("state-invalid") from exc


def open_lock(directory_fd: int, name: str) -> int:
    deadline = time.monotonic() + (BUSY_TIMEOUT_MILLISECONDS / 1_000)
    while True:
        try:
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | nofollow_flag(),
                0o600,
                dir_fd=directory_fd,
            )
            break
        except FileNotFoundError as exc:
            if time.monotonic() >= deadline:
                raise SchedulerStateError("state-busy") from exc
            time.sleep(LOCK_RETRY_SECONDS)
    metadata = os.fstat(descriptor)
    if not safe_regular(metadata, maximum_bytes=1_048_576):
        os.close(descriptor)
        raise SchedulerStateError("state-invalid")
    return descriptor


def acquire_lock(descriptor: int, operation: int) -> None:
    deadline = time.monotonic() + (BUSY_TIMEOUT_MILLISECONDS / 1_000)
    while True:
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            return
        except BlockingIOError as exc:
            if time.monotonic() >= deadline:
                raise SchedulerStateError("state-busy") from exc
            time.sleep(LOCK_RETRY_SECONDS)


def file_identity(directory_fd: int, name: str) -> FileIdentity:
    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if not safe_regular(metadata, maximum_bytes=MAX_DATABASE_BYTES):
        raise SchedulerStateError("state-invalid")
    return identity(metadata)


def path_identity(path: Path) -> FileIdentity:
    metadata = os.stat(path, follow_symlinks=False)
    if not safe_regular(metadata, maximum_bytes=MAX_DATABASE_BYTES):
        raise SchedulerStateError("state-invalid")
    return identity(metadata)


def validate_header(path: Path, expected_identity: FileIdentity) -> None:
    descriptor = os.open(path, os.O_RDONLY | nofollow_flag())
    try:
        metadata = os.fstat(descriptor)
        if not safe_regular(metadata, maximum_bytes=MAX_DATABASE_BYTES):
            raise SchedulerStateError("state-invalid")
        if identity(metadata) != expected_identity:
            raise SchedulerStateError("state-invalid")
        header = os.pread(descriptor, SQLITE_HEADER_BYTES, 0)
    finally:
        os.close(descriptor)
    if (
        len(header) == SQLITE_HEADER_BYTES
        and header.startswith(SQLITE_HEADER_PREFIX)
        and header[18:20] != b"\x01\x01"
    ):
        raise SchedulerStateError("state-invalid")


def reject_unsafe_sidecars(directory_fd: int) -> None:
    for name in (
        f"{DATABASE_NAME}-journal",
        f"{DATABASE_NAME}-wal",
        f"{DATABASE_NAME}-shm",
    ):
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        allowed_journal = name == f"{DATABASE_NAME}-journal" and safe_regular(
            metadata,
            maximum_bytes=MAX_DATABASE_BYTES,
        )
        if not allowed_journal:
            raise SchedulerStateError("state-invalid")


def safe_regular(metadata: os.stat_result, *, maximum_bytes: int) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_uid == os.geteuid()
        and metadata.st_nlink == 1
        and metadata.st_size <= maximum_bytes
    )


def identity(metadata: os.stat_result) -> FileIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def entry_exists(directory_fd: int, name: str) -> bool:
    try:
        _ = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def fsync_regular(directory_fd: int, name: str) -> None:
    descriptor = os.open(name, os.O_RDONLY | nofollow_flag(), dir_fd=directory_fd)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validated_root(repo_root: Path) -> Path:
    root = repo_root.expanduser()
    if not root.is_absolute():
        root = root.absolute()
    if any(part == ".." for part in root.parts) or not root.is_dir() or root.is_symlink():
        raise SchedulerStateError("state-invalid")
    return root


def is_busy(exc: sqlite3.OperationalError) -> bool:
    text = str(exc).casefold()
    return "locked" in text or "busy" in text


def nofollow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)
