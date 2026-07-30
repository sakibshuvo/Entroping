from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError
from scripts.factory_budget_ledger_parent_fs import open_private_relative_directory
from scripts.factory_retention_fs import RetentionFsError
from scripts.factory_scheduler_schema import initialize_schema, validate_schema
from scripts.factory_scheduler_storage_fs import (
    BUSY_TIMEOUT_MILLISECONDS,
    DATABASE_NAME,
    INITIALIZATION_LOCK,
    INITIALIZING_NAME,
    MAX_DATABASE_BYTES,
    RETENTION_LOCK,
    STATE_DIRECTORY,
    FileIdentity,
    SchedulerStateError,
    acquire_lock,
    entry_exists,
    file_identity,
    fsync_regular,
    is_busy,
    nofollow_flag,
    open_lock,
    path_identity,
    reject_unsafe_sidecars,
    validate_header,
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
    _prepare(root, initialized_at=initialized_at)
    with _retention_guard(root):
        identity = validated_existing_identity(root)
        connection = _connect(database_path(root), readonly=False, identity=identity)
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
        connection = _connect(database_path(root), readonly=True, identity=identity)
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


def _prepare(root: Path, *, initialized_at: str) -> None:
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
                        _prepare_locked(root, scheduler_fd, initialized_at=initialized_at)
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


def _prepare_locked(root: Path, directory_fd: int, *, initialized_at: str) -> None:
    reject_unsafe_sidecars(directory_fd)
    if entry_exists(directory_fd, DATABASE_NAME):
        _ = file_identity(directory_fd, DATABASE_NAME)
        with suppress(FileNotFoundError):
            os.unlink(INITIALIZING_NAME, dir_fd=directory_fd)
            os.fsync(directory_fd)
        return
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
        connection = _connect(temporary, readonly=False, identity=identity)
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


def _connect(path: Path, *, readonly: bool, identity: FileIdentity) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        validate_header(path, identity)
        mode = "ro" if readonly else "rw"
        uri = f"file:{quote(path.as_posix(), safe='/')}?mode={mode}"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
            autocommit=True,
        )
        if path_identity(path) != identity:
            raise SchedulerStateError("state-invalid")
        _ = connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
        _ = connection.execute("PRAGMA trusted_schema = OFF")
        _ = connection.execute("PRAGMA foreign_keys = ON")
        if readonly:
            _ = connection.execute("PRAGMA query_only = ON")
        else:
            if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise SchedulerStateError("state-invalid")
            _ = connection.execute("PRAGMA synchronous = EXTRA")
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            max_pages = MAX_DATABASE_BYTES // page_size
            _ = connection.execute(f"PRAGMA max_page_count = {max_pages}")
            _ = connection.execute("PRAGMA journal_size_limit = 8388608")
        return connection
    except SchedulerStateError:
        if connection is not None:
            connection.close()
        raise
    except sqlite3.OperationalError as exc:
        if connection is not None:
            connection.close()
        code = "state-busy" if is_busy(exc) else "state-invalid"
        raise SchedulerStateError(code) from exc
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
        if connection is not None:
            connection.close()
        raise SchedulerStateError("state-invalid") from exc
