from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from scripts.factory_retention_fs import RetentionFsError

from .factory_budget_ledger_fs import (
    INITIALIZING_NAME,
    LEDGER_DIRECTORY,
    LEDGER_NAME,
    LOCK_NAME,
    MAX_LEDGER_BYTES,
    FileIdentity,
    discard_initializing_file,
    entry_exists,
    fsync_regular,
    nofollow_flag,
    open_lock,
    path_file_identity,
    recover_published_initialization,
    reject_unsafe_sidecars,
    validate_delete_journal_header,
    validate_existing_entry,
    validate_regular,
    validated_root,
)
from .factory_budget_ledger_migration import migrate_schema_v1_to_v2
from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_parent_fs import open_private_relative_directory
from .factory_budget_ledger_rows import integer_row
from .factory_budget_ledger_schema import initialize_schema, validate_schema

BUSY_TIMEOUT_MILLISECONDS = 5_000


def migrate_ledger(repo_root: Path) -> bool:
    root = validated_root(repo_root)
    db_path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
    if not db_path.exists():
        raise FactoryBudgetLedgerError("missing", "ledger database not found")
    with _retention_guard(root):
        identity = validate_existing_entry(root, LEDGER_NAME)
        connection = _connect(db_path, readonly=False, expected_identity=identity)
        try:
            return migrate_schema_v1_to_v2(connection)
        finally:
            connection.close()


def prepare_ledger(repo_root: Path) -> Path:
    root = validated_root(repo_root)
    try:
        with open_private_relative_directory(
            root,
            (".entroping",),
            create=True,
        ) as state_fd:
            retention_fd = open_lock(state_fd, "retention.lock")
            try:
                fcntl.flock(retention_fd, fcntl.LOCK_SH)
                with open_private_relative_directory(
                    root,
                    LEDGER_DIRECTORY,
                    create=True,
                ) as ledger_fd:
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
        identity = validate_existing_entry(root, LEDGER_NAME)
        connection = _connect(db_path, readonly=False, expected_identity=identity)
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
        identity = validate_existing_entry(root, LEDGER_NAME)
        connection = _connect(db_path, readonly=True, expected_identity=identity)
        try:
            validate_schema(connection)
            yield connection
        finally:
            connection.close()


def _prepare_locked(root: Path, ledger_fd: int) -> None:
    reject_unsafe_sidecars(ledger_fd)
    if entry_exists(ledger_fd, LEDGER_NAME):
        recover_published_initialization(ledger_fd)
        identity = validate_regular(ledger_fd, LEDGER_NAME)
        db_path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
        connection = _connect(db_path, readonly=False, expected_identity=identity)
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
        identity = validate_regular(ledger_fd, INITIALIZING_NAME)
        connection = _connect(temp_path, readonly=False, expected_identity=identity)
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
    except (OSError, sqlite3.DatabaseError) as exc:
        raise FactoryBudgetLedgerError(
            "initialization",
            "could not initialize ledger",
        ) from exc
    finally:
        with suppress(FileNotFoundError):
            os.unlink(INITIALIZING_NAME, dir_fd=ledger_fd)
            os.fsync(ledger_fd)


def _connect(
    path: Path,
    *,
    readonly: bool,
    expected_identity: FileIdentity,
) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        validate_delete_journal_header(path, expected_identity)
        mode = "ro" if readonly else "rw"
        uri = f"file:{quote(path.as_posix(), safe='/')}?mode={mode}"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
            autocommit=True,
        )
        if path_file_identity(path) != expected_identity:
            raise FactoryBudgetLedgerError("path", "ledger database changed during open")
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
            page_size = integer_row(
                connection.execute("PRAGMA page_size"),
                detail="SQLite page size is invalid",
            )
            if page_size < 512 or page_size > 65_536 or page_size & (page_size - 1):
                raise FactoryBudgetLedgerError("database", "SQLite page size is invalid")
            max_page_count = MAX_LEDGER_BYTES // page_size
            applied_page_cap = integer_row(
                connection.execute(f"PRAGMA max_page_count = {max_page_count}"),
                detail="SQLite page cap is invalid",
            )
            if applied_page_cap != max_page_count:
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
        with open_private_relative_directory(
            repo_root,
            (".entroping",),
            create=False,
        ) as state_fd:
            descriptor = open_lock(state_fd, "retention.lock")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH)
                yield
            finally:
                os.close(descriptor)
    except RetentionFsError as exc:
        raise FactoryBudgetLedgerError("path", "ledger state path is unsafe") from exc
