from __future__ import annotations

import os
import stat
from pathlib import Path

from scripts.factory_retention_fs import RetentionFsError

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_parent_fs import open_private_relative_directory

LEDGER_DIRECTORY = (".entroping", "factory-budget")
LEDGER_NAME = "ledger.sqlite3"
INITIALIZING_NAME = ".ledger.sqlite3.init"
LOCK_NAME = "ledger.lock"
MAX_LEDGER_BYTES = 536_870_912
SQLITE_HEADER_BYTES = 20
SQLITE_HEADER_PREFIX = b"SQLite format 3\x00"
type FileIdentity = tuple[int, int, int, int, int]


def validate_existing_entry(root: Path, name: str) -> FileIdentity:
    try:
        with open_private_relative_directory(
            root,
            LEDGER_DIRECTORY,
            create=False,
        ) as ledger_fd:
            identity = validate_regular(ledger_fd, name)
            reject_unsafe_sidecars(ledger_fd)
            return identity
    except (OSError, RetentionFsError) as exc:
        raise FactoryBudgetLedgerError("path", "ledger state path is unsafe") from exc


def validated_root(repo_root: Path) -> Path:
    root = repo_root.expanduser()
    if not root.is_absolute():
        root = root.absolute()
    if any(part == ".." for part in root.parts):
        raise FactoryBudgetLedgerError(
            "path",
            "repository root must not contain parent traversal",
        )
    if not root.is_dir() or root.is_symlink():
        raise FactoryBudgetLedgerError("path", "repository root must be a real directory")
    return root


def open_lock(directory_fd: int, name: str) -> int:
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | nofollow_flag(),
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise FactoryBudgetLedgerError("path", "ledger lock is unsafe") from exc
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise FactoryBudgetLedgerError("path", "ledger lock is unsafe")
    return descriptor


def validate_regular(directory_fd: int, name: str) -> FileIdentity:
    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    return validated_file_identity(metadata)


def validated_file_identity(metadata: os.stat_result) -> FileIdentity:
    if not _regular_metadata_safe(metadata, expected_links=1):
        raise FactoryBudgetLedgerError("path", "ledger database is unsafe or too large")
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def path_file_identity(path: Path) -> FileIdentity:
    try:
        return validated_file_identity(os.stat(path, follow_symlinks=False))
    except (OSError, FactoryBudgetLedgerError) as exc:
        raise FactoryBudgetLedgerError("path", "ledger database changed during open") from exc


def validate_delete_journal_header(path: Path, expected_identity: FileIdentity) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow_flag())
    except OSError as exc:
        raise FactoryBudgetLedgerError("path", "ledger database changed during open") from exc
    try:
        try:
            identity = validated_file_identity(os.fstat(descriptor))
        except FactoryBudgetLedgerError as exc:
            raise FactoryBudgetLedgerError(
                "path",
                "ledger database changed during open",
            ) from exc
        if identity != expected_identity:
            raise FactoryBudgetLedgerError("path", "ledger database changed during open")
        header = os.pread(descriptor, SQLITE_HEADER_BYTES, 0)
    finally:
        os.close(descriptor)
    if (
        len(header) == SQLITE_HEADER_BYTES
        and header.startswith(SQLITE_HEADER_PREFIX)
        and header[18:20] != b"\x01\x01"
    ):
        raise FactoryBudgetLedgerError("database", "DELETE journal mode is required")


def reject_unsafe_sidecars(directory_fd: int) -> None:
    for name in (f"{LEDGER_NAME}-journal", f"{LEDGER_NAME}-wal", f"{LEDGER_NAME}-shm"):
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if (
            name != f"{LEDGER_NAME}-journal"
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_LEDGER_BYTES
        ):
            raise FactoryBudgetLedgerError("path", "ledger sidecar is unsafe")


def recover_published_initialization(directory_fd: int) -> None:
    if not entry_exists(directory_fd, LEDGER_NAME) or not entry_exists(
        directory_fd,
        INITIALIZING_NAME,
    ):
        return
    ledger_metadata = os.stat(
        LEDGER_NAME,
        dir_fd=directory_fd,
        follow_symlinks=False,
    )
    initializing_metadata = os.stat(
        INITIALIZING_NAME,
        dir_fd=directory_fd,
        follow_symlinks=False,
    )
    same_inode = (
        ledger_metadata.st_dev == initializing_metadata.st_dev
        and ledger_metadata.st_ino == initializing_metadata.st_ino
    )
    if not same_inode:
        return
    if not _regular_metadata_safe(
        ledger_metadata,
        expected_links=2,
    ) or not _regular_metadata_safe(initializing_metadata, expected_links=2):
        raise FactoryBudgetLedgerError("path", "published ledger recovery is unsafe")
    os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
    os.fsync(directory_fd)


def discard_initializing_file(directory_fd: int) -> None:
    if not entry_exists(directory_fd, INITIALIZING_NAME):
        return
    _ = validate_regular(directory_fd, INITIALIZING_NAME)
    os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
    os.fsync(directory_fd)


def entry_exists(directory_fd: int, name: str) -> bool:
    try:
        _ = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def fsync_regular(directory_fd: int, name: str) -> None:
    descriptor = os.open(name, os.O_RDONLY | nofollow_flag(), dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        try:
            _ = validated_file_identity(metadata)
        except FactoryBudgetLedgerError as exc:
            raise FactoryBudgetLedgerError("path", "initializing ledger is unsafe") from exc
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def nofollow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _regular_metadata_safe(
    metadata: os.stat_result,
    *,
    expected_links: int,
) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_uid == os.geteuid()
        and metadata.st_nlink == expected_links
        and metadata.st_size <= MAX_LEDGER_BYTES
    )
