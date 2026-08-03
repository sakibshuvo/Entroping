from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError
from scripts.factory_budget_ledger_parent_fs import open_private_relative_directory
from scripts.factory_retention_fs import RetentionFsError
from scripts.factory_scheduler_schema import initialize_schema, validate_schema
from scripts.factory_scheduler_schema_migration import migrate_schema
from scripts.factory_scheduler_storage_connection import open_scheduler_connection
from scripts.factory_scheduler_storage_fs import (
    DATABASE_NAME,
    INITIALIZATION_LOCK,
    INITIALIZING_NAME,
    RETENTION_LOCK,
    STATE_DIRECTORY,
    SchedulerStateError,
    acquire_lock,
    entry_exists,
    file_identity,
    fsync_regular,
    nofollow_flag,
    open_lock,
    reject_unsafe_sidecars,
    validated_existing_identity,
    validated_root,
)


def database_path(repo_root: Path) -> Path:
    return validated_root(repo_root).joinpath(*STATE_DIRECTORY, DATABASE_NAME)


def database_exists(repo_root: Path) -> bool:
    root = validated_root(repo_root)
    try:
        _ = os.stat(root / STATE_DIRECTORY[0], follow_symlinks=False)
    except FileNotFoundError:
        return False
    try:
        with open_private_relative_directory(
            root,
            (STATE_DIRECTORY[0],),
            create=False,
        ) as state_fd:
            if not entry_exists(state_fd, STATE_DIRECTORY[1]):
                return False
        with open_private_relative_directory(
            root,
            STATE_DIRECTORY,
            create=False,
        ) as scheduler_fd:
            reject_unsafe_sidecars(scheduler_fd)
            if not entry_exists(scheduler_fd, DATABASE_NAME):
                return False
            _ = file_identity(scheduler_fd, DATABASE_NAME)
            return True
    except SchedulerStateError:
        raise
    except (
        FactoryBudgetLedgerError,
        OSError,
        RetentionFsError,
    ) as exc:
        raise SchedulerStateError("state-invalid") from exc


@contextmanager
def writable_connection(
    repo_root: Path,
    *,
    initialized_at: str,
) -> Generator[sqlite3.Connection, None, None]:
    root = validated_root(repo_root)
    _prepare(root, initialized_at=initialized_at, create_if_missing=True)
    with _retention_guard(root):
        identity = validated_existing_identity(root)
        connection = open_scheduler_connection(
            database_path(root),
            readonly=False,
            identity=identity,
        )
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


@contextmanager
def readonly_connection(repo_root: Path) -> Generator[sqlite3.Connection, None, None]:
    root = validated_root(repo_root)
    if not database_path(root).exists():
        raise SchedulerStateError("state-missing")
    with _retention_guard(root):
        identity = validated_existing_identity(root)
        connection = open_scheduler_connection(
            database_path(root),
            readonly=True,
            identity=identity,
        )
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


def migrate_existing_state(repo_root: Path, *, initialized_at: str) -> None:
    root = validated_root(repo_root)
    _prepare(root, initialized_at=initialized_at, create_if_missing=False)


def _prepare(
    root: Path,
    *,
    initialized_at: str,
    create_if_missing: bool,
) -> None:
    try:
        with open_private_relative_directory(
            root,
            (".entroping",),
            create=True,
        ) as state_fd:
            retention_fd = open_lock(state_fd, RETENTION_LOCK)
            try:
                acquire_lock(retention_fd, fcntl.LOCK_SH)
                with open_private_relative_directory(
                    root,
                    STATE_DIRECTORY,
                    create=True,
                ) as scheduler_fd:
                    lock_fd = open_lock(scheduler_fd, INITIALIZATION_LOCK)
                    try:
                        acquire_lock(lock_fd, fcntl.LOCK_EX)
                        _prepare_locked(
                            root,
                            scheduler_fd,
                            initialized_at=initialized_at,
                            create_if_missing=create_if_missing,
                        )
                    finally:
                        os.close(lock_fd)
            finally:
                os.close(retention_fd)
    except SchedulerStateError:
        raise
    except (
        FactoryBudgetLedgerError,
        OSError,
        RetentionFsError,
        sqlite3.DatabaseError,
    ) as exc:
        raise SchedulerStateError("state-invalid") from exc


def _prepare_locked(
    root: Path,
    directory_fd: int,
    *,
    initialized_at: str,
    create_if_missing: bool,
) -> None:
    reject_unsafe_sidecars(directory_fd)
    if entry_exists(directory_fd, DATABASE_NAME):
        identity = file_identity(directory_fd, DATABASE_NAME)
        connection = open_scheduler_connection(
            database_path(root),
            readonly=False,
            identity=identity,
        )
        try:
            migrated = migrate_schema(connection)
        finally:
            connection.close()
        if migrated:
            fsync_regular(directory_fd, DATABASE_NAME)
        with suppress(FileNotFoundError):
            os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
            os.fsync(directory_fd)
        return
    if not create_if_missing:
        raise SchedulerStateError("state-missing")
    with suppress(FileNotFoundError):
        os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
        os.fsync(directory_fd)
    descriptor = os.open(
        INITIALIZING_NAME,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow_flag(),
        0o600,
        dir_fd=directory_fd,
    )
    os.close(descriptor)
    temporary = root.joinpath(*STATE_DIRECTORY, INITIALIZING_NAME)
    try:
        identity = file_identity(directory_fd, INITIALIZING_NAME)
        connection = open_scheduler_connection(
            temporary,
            readonly=False,
            identity=identity,
        )
        try:
            initialize_schema(connection, initialized_at=initialized_at)
            validate_schema(connection)
        finally:
            connection.close()
        fsync_regular(directory_fd, INITIALIZING_NAME)
        os.link(
            INITIALIZING_NAME,
            DATABASE_NAME,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
            os.fsync(directory_fd)


@contextmanager
def _retention_guard(root: Path) -> Generator[None, None, None]:
    try:
        with open_private_relative_directory(
            root,
            (".entroping",),
            create=False,
        ) as state_fd:
            descriptor = open_lock(state_fd, RETENTION_LOCK)
            try:
                acquire_lock(descriptor, fcntl.LOCK_SH)
                yield
            finally:
                os.close(descriptor)
    except (FactoryBudgetLedgerError, OSError, RetentionFsError) as exc:
        raise SchedulerStateError("state-invalid") from exc
