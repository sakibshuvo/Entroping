from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import cast
from urllib.parse import quote

from scripts.factory_retention_fs import RetentionFsError, open_relative_directory

from .factory_budget_ledger_fs import (
    INITIALIZING_NAME,
    LEDGER_DIRECTORY,
    LEDGER_NAME,
    LOCK_NAME,
    MAX_LEDGER_BYTES,
    discard_initializing_file,
    entry_exists,
    fsync_regular,
    nofollow_flag,
    open_lock,
    reject_unsafe_sidecars,
    validate_existing_entry,
    validate_private_directory,
    validate_regular,
    validated_root,
)
from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_schema import initialize_schema, validate_schema

BUSY_TIMEOUT_MILLISECONDS = 5_000


def prepare_ledger(repo_root: Path) -> Path:
    root = validated_root(repo_root)
    try:
        with open_relative_directory(root, (".entroping",), create=True) as state_fd:
            retention_fd = open_lock(state_fd, "retention.lock")
            try:
                fcntl.flock(retention_fd, fcntl.LOCK_SH)
                with open_relative_directory(root, LEDGER_DIRECTORY, create=True) as ledger_fd:
                    validate_private_directory(ledger_fd)
                    init_lock_fd = open_lock(ledger_fd, LOCK_NAME)
                    try:
                        fcntl.flock(init_lock_fd, fcntl.LOCK_EX)
                        _prepare_locked(root, ledger_fd)
                    finally:
                        os.close(init_lock_fd)
            finally:
                os.close(retention_fd)
    except RetentionFsError as exc:
        raise FactoryBudgetLedgerError("path", "ledger state path is unsafe") from exc
    return root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)


@contextmanager
def writable_connection(repo_root: Path) -> Generator[sqlite3.Connection, None, None]:
    root = validated_root(repo_root)
    db_path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
    if not db_path.exists():
        db_path = prepare_ledger(root)
    with _retention_guard(root):
        if not db_path.exists():
            raise FactoryBudgetLedgerError("missing", "ledger database not found")
        validate_existing_entry(root, LEDGER_NAME)
        connection = _connect(db_path, readonly=False)
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


@contextmanager
def readonly_connection(repo_root: Path) -> Generator[sqlite3.Connection, None, None]:
    root = validated_root(repo_root)
    db_path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
    if not db_path.exists():
        raise FactoryBudgetLedgerError("missing", "ledger database not found")
    with _retention_guard(root):
        if not db_path.exists():
            raise FactoryBudgetLedgerError("missing", "ledger database not found")
        validate_existing_entry(root, LEDGER_NAME)
        connection = _connect(db_path, readonly=True)
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


def _prepare_locked(root: Path, ledger_fd: int) -> None:
    reject_unsafe_sidecars(ledger_fd)
    if entry_exists(ledger_fd, LEDGER_NAME):
        validate_regular(ledger_fd, LEDGER_NAME)
        db_path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
        connection = _connect(db_path, readonly=False)
        try:
            validate_schema(connection)
        finally:
            connection.close()
        discard_initializing_file(ledger_fd)
        return
    discard_initializing_file(ledger_fd)
    descriptor = os.open(
        INITIALIZING_NAME,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow_flag(),
        0o600,
        dir_fd=ledger_fd,
    )
    os.close(descriptor)
    temp_path = root.joinpath(*LEDGER_DIRECTORY, INITIALIZING_NAME)
    try:
        connection = _connect(temp_path, readonly=False)
        try:
            initialize_schema(connection)
            validate_schema(connection)
        finally:
            connection.close()
        fsync_regular(ledger_fd, INITIALIZING_NAME)
        os.link(
            INITIALIZING_NAME,
            LEDGER_NAME,
            src_dir_fd=ledger_fd,
            dst_dir_fd=ledger_fd,
            follow_symlinks=False,
        )
        os.unlink(INITIALIZING_NAME, dir_fd=ledger_fd)
        os.fsync(ledger_fd)
    except BaseException as exc:
        with suppress(FileNotFoundError):
            os.unlink(INITIALIZING_NAME, dir_fd=ledger_fd)
            os.fsync(ledger_fd)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, FactoryBudgetLedgerError)):
            raise
        raise FactoryBudgetLedgerError(
            "initialization",
            "could not initialize ledger",
        ) from exc


def _connect(path: Path, *, readonly: bool) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        if readonly:
            uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, autocommit=True)
        else:
            connection = sqlite3.connect(
                path,
                timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
                autocommit=True,
            )
        _ = connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
        _ = connection.execute("PRAGMA trusted_schema = OFF")
        _ = connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
            raise FactoryBudgetLedgerError("database", "foreign key enforcement unavailable")
        if readonly:
            _ = connection.execute("PRAGMA query_only = ON")
        else:
            if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise FactoryBudgetLedgerError("database", "DELETE journal mode unavailable")
            _ = connection.execute("PRAGMA synchronous = EXTRA")
            page_size_row = cast(
                tuple[object] | None,
                connection.execute("PRAGMA page_size").fetchone(),
            )
            if (
                page_size_row is None
                or not isinstance(page_size_row[0], int)
                or page_size_row[0] < 512
                or page_size_row[0] > 65_536
                or page_size_row[0] & (page_size_row[0] - 1)
            ):
                raise FactoryBudgetLedgerError("database", "SQLite page size is invalid")
            max_page_count = MAX_LEDGER_BYTES // page_size_row[0]
            applied_page_cap = cast(
                tuple[int] | None,
                connection.execute(f"PRAGMA max_page_count = {max_page_count}").fetchone(),
            )
            if applied_page_cap != (max_page_count,):
                raise FactoryBudgetLedgerError("database", "SQLite page cap is unavailable")
            _ = connection.execute("PRAGMA journal_size_limit = 67108864")
        return connection
    except FactoryBudgetLedgerError:
        if connection is not None:
            connection.close()
        raise
    except sqlite3.DatabaseError as exc:
        if connection is not None:
            connection.close()
        raise FactoryBudgetLedgerError("database", "ledger database is malformed") from exc


@contextmanager
def _retention_guard(repo_root: Path) -> Generator[None, None, None]:
    try:
        with open_relative_directory(repo_root, (".entroping",), create=False) as state_fd:
            descriptor = open_lock(state_fd, "retention.lock")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH)
                yield
            finally:
                os.close(descriptor)
    except RetentionFsError as exc:
        raise FactoryBudgetLedgerError("path", "ledger state path is unsafe") from exc
