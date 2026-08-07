"""Private SQLite storage for the separate PR delivery lifecycle."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import quote

import scripts.factory_pr_delivery_journal_migration as _journal_migration
from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_DDL as _SCHEMA_CLEANUP_DDL,
)
from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_TRIGGER_CREATORS,
)
from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_TRIGGER_IMMUTABLE_IDENTITY as _SCHEMA_CLEANUP_TRIGGER_IMMUTABLE_IDENTITY,
)
from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_TRIGGER_NO_DELETE as _SCHEMA_CLEANUP_TRIGGER_NO_DELETE,
)
from scripts.factory_pr_delivery_journal_cleanup_schema import (
    CLEANUP_TRIGGER_NO_REWRITE_PROOFS as _SCHEMA_CLEANUP_TRIGGER_NO_REWRITE_PROOFS,
)
from scripts.factory_pr_delivery_journal_records import DeliveryJournalError

_MAX_BYTES = 67_108_864
type FileIdentity = tuple[int, int, int, int, int]

# Re-export schema constants for compatibility with existing callers/tests.
METADATA_DDL = _journal_migration.METADATA_DDL
METADATA_DDL_V2 = _journal_migration.METADATA_DDL_V2
METADATA_DDL_V1 = _journal_migration.METADATA_DDL_V1
METADATA_DDL_V3 = _journal_migration.METADATA_DDL_V3
LIFECYCLE_DDL = _journal_migration.LIFECYCLE_DDL
LIFECYCLE_DDL_V2 = _journal_migration.LIFECYCLE_DDL_V2
LIFECYCLE_DDL_V1 = _journal_migration.LIFECYCLE_DDL_V1
LIFECYCLE_DDL_V3 = _journal_migration.LIFECYCLE_DDL_V3
CLEANUP_DDL = _SCHEMA_CLEANUP_DDL
CLEANUP_TRIGGER_IMMUTABLE_IDENTITY = _SCHEMA_CLEANUP_TRIGGER_IMMUTABLE_IDENTITY
CLEANUP_TRIGGER_NO_REWRITE_PROOFS = _SCHEMA_CLEANUP_TRIGGER_NO_REWRITE_PROOFS
CLEANUP_TRIGGER_NO_DELETE = _SCHEMA_CLEANUP_TRIGGER_NO_DELETE


@contextmanager
def journal_connection(root: Path) -> Generator[sqlite3.Connection, None, None]:
    state = _private_state_directory(root)
    lock_fd: int | None = None
    try:
        lock_fd = os.open(
            state / "delivery.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        _require_private_file(lock_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _reject_sidecars(state)
        database = state / "delivery.sqlite3"
        created = not database.exists()
        if created:
            descriptor = os.open(
                database,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.close(descriptor)
        state_identity = _path_identity(state, directory=True)
        database_identity = _validated_database_identity(database)
        connection = _open_connection(database, database_identity)
        try:
            _require_stable_paths(state, state_identity, database, database_identity)
            if created:
                connection.execute(METADATA_DDL_V3)
                connection.execute(
                    "INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 3)"
                )
                connection.execute(LIFECYCLE_DDL)
                connection.execute(CLEANUP_DDL)
                for trigger in CLEANUP_TRIGGER_CREATORS:
                    connection.execute(trigger)
            _journal_migration.validate_journal_schema(connection)
            yield connection
            _require_stable_paths(state, state_identity, database, database_identity)
            _reject_sidecars(state)
        finally:
            connection.close()
    except DeliveryJournalError:
        raise
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
        raise DeliveryJournalError("journal-invalid") from None
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def _private_state_directory(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise DeliveryJournalError("journal-invalid")
    current = root
    for name in (".entroping", "factory-pr-delivery"):
        candidate = current / name
        with suppress(FileExistsError):
            candidate.mkdir(mode=0o700)
        metadata = candidate.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise DeliveryJournalError("journal-invalid")
        current = candidate
    return current


def _open_connection(database: Path, expected: FileIdentity) -> sqlite3.Connection:
    _validate_header(database, expected)
    uri = f"file:{quote(database.as_posix(), safe='/')}?mode=rw"
    connection = sqlite3.connect(uri, uri=True, timeout=0.1, autocommit=True)
    try:
        if _path_identity(database) != expected:
            raise DeliveryJournalError("journal-invalid")
        connection.execute("PRAGMA busy_timeout = 100")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
            raise DeliveryJournalError("journal-invalid")
        if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            raise DeliveryJournalError("journal-invalid")
        connection.execute("PRAGMA synchronous = EXTRA")
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        connection.execute(f"PRAGMA max_page_count = {_MAX_BYTES // page_size}")
        return connection
    except (DeliveryJournalError, sqlite3.DatabaseError, TypeError, ValueError):
        connection.close()
        raise


def _validated_database_identity(database: Path) -> FileIdentity:
    descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        _require_private_file(descriptor)
        metadata = os.fstat(descriptor)
        if metadata.st_size > _MAX_BYTES:
            raise DeliveryJournalError("journal-invalid")
        return _identity(metadata)
    finally:
        os.close(descriptor)


def _require_private_file(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        raise DeliveryJournalError("journal-invalid")


def _path_identity(path: Path, *, directory: bool = False) -> FileIdentity:
    metadata = path.lstat()
    valid = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not valid:
        raise DeliveryJournalError("journal-invalid")
    return _identity(metadata)


def _identity(metadata: os.stat_result) -> FileIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def _validate_header(database: Path, expected: FileIdentity) -> None:
    descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if _identity(os.fstat(descriptor)) != expected:
            raise DeliveryJournalError("journal-invalid")
        header = os.pread(descriptor, 16, 0)
    finally:
        os.close(descriptor)
    if header and header != b"SQLite format 3\x00":
        raise DeliveryJournalError("journal-invalid")


def _require_stable_paths(
    state: Path,
    state_identity: FileIdentity,
    database: Path,
    database_identity: FileIdentity,
) -> None:
    if (
        _path_identity(state, directory=True) != state_identity
        or _path_identity(database) != database_identity
    ):
        raise DeliveryJournalError("journal-invalid")


def _reject_sidecars(state: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if (state / f"delivery.sqlite3{suffix}").exists():
            raise DeliveryJournalError("journal-invalid")
