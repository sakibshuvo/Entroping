"""Private, identity-pinned SQLite storage for orchestration lifecycle state."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from scripts.factory_orchestration_errors import OrchestrationJournalError

_MAX_DATABASE_BYTES = 67_108_864
type FileIdentity = tuple[int, int, int, int, int]
_METADATA_DDL = (
    "CREATE TABLE orchestration_metadata("
    "id INTEGER PRIMARY KEY CHECK(id = 1), schema_version INTEGER NOT NULL "
    "CHECK(schema_version = 1)) STRICT"
)
_LIFECYCLE_DDL = (
    "CREATE TABLE orchestration_lifecycle("
    "request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
    "issue_number INTEGER NOT NULL, worktree_id TEXT NOT NULL, "
    "lifecycle TEXT NOT NULL CHECK(lifecycle IN "
    "('prepared','applying','applied','gating','accepted','failed','cancelled','uncertain')), "
    "reason TEXT NOT NULL CHECK(reason IN ('none','interrupted')), receipt_json TEXT, "
    "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL) STRICT"
)


@contextmanager
def journal_connection(root: Path) -> Generator[sqlite3.Connection, None, None]:
    state = _private_state_directory(root)
    lock_fd: int | None = None
    try:
        lock_fd = os.open(
            state / "orchestration.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        _require_private_file(lock_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _reject_sidecars(state)
        database = state / "orchestration.sqlite3"
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
                _initialize(connection)
            _validate_schema(connection)
            yield connection
            _require_stable_paths(state, state_identity, database, database_identity)
            _reject_sidecars(state)
        finally:
            connection.close()
    except OrchestrationJournalError:
        raise
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
        raise OrchestrationJournalError("journal-invalid") from exc
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def _open_connection(database: Path, expected: FileIdentity) -> sqlite3.Connection:
    _validate_header(database, expected)
    uri = f"file:{quote(database.as_posix(), safe='/')}?mode=rw"
    connection = sqlite3.connect(uri, uri=True, timeout=0.1, autocommit=True)
    try:
        if _path_identity(database) != expected:
            raise OrchestrationJournalError("journal-invalid")
        _ = connection.execute("PRAGMA busy_timeout = 100")
        _ = connection.execute("PRAGMA trusted_schema = OFF")
        _ = connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            raise OrchestrationJournalError("journal-invalid")
        _ = connection.execute("PRAGMA synchronous = EXTRA")
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        _ = connection.execute(f"PRAGMA max_page_count = {_MAX_DATABASE_BYTES // page_size}")
        _ = connection.execute("PRAGMA journal_size_limit = 8388608")
        return connection
    except (OrchestrationJournalError, sqlite3.DatabaseError, TypeError, ValueError):
        connection.close()
        raise


def _private_state_directory(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise OrchestrationJournalError("journal-invalid")
    current = root
    for name in (".entroping", "factory-orchestration"):
        candidate = current / name
        with suppress(FileExistsError):
            candidate.mkdir(mode=0o700)
        metadata = candidate.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise OrchestrationJournalError("journal-invalid")
        current = candidate
    return current


def _validated_database_identity(database: Path) -> FileIdentity:
    descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        _require_private_file(descriptor)
        metadata = os.fstat(descriptor)
        if metadata.st_size > _MAX_DATABASE_BYTES:
            raise OrchestrationJournalError("journal-invalid")
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
        raise OrchestrationJournalError("journal-invalid")


def _path_identity(path: Path, *, directory: bool = False) -> FileIdentity:
    metadata = path.lstat()
    valid_kind = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not valid_kind:
        raise OrchestrationJournalError("journal-invalid")
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
            raise OrchestrationJournalError("journal-invalid")
        header = os.pread(descriptor, 16, 0)
    finally:
        os.close(descriptor)
    if header and header != b"SQLite format 3\x00":
        raise OrchestrationJournalError("journal-invalid")


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
        raise OrchestrationJournalError("journal-invalid")


def _reject_sidecars(state: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if (state / f"orchestration.sqlite3{suffix}").exists():
            raise OrchestrationJournalError("journal-invalid")


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(_METADATA_DDL)
    connection.execute("INSERT INTO orchestration_metadata(id, schema_version) VALUES (1, 1)")
    connection.execute(_LIFECYCLE_DDL)


def _validate_schema(connection: sqlite3.Connection) -> None:
    objects = tuple(
        connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    )
    if objects != (
        ("table", "orchestration_lifecycle", "orchestration_lifecycle", _LIFECYCLE_DDL),
        ("table", "orchestration_metadata", "orchestration_metadata", _METADATA_DDL),
    ):
        raise OrchestrationJournalError("journal-invalid")
    if connection.execute(
        "SELECT schema_version FROM orchestration_metadata WHERE id = 1"
    ).fetchone() != (1,):
        raise OrchestrationJournalError("journal-invalid")
    columns = tuple(
        row[1] for row in connection.execute("PRAGMA table_info(orchestration_lifecycle)")
    )
    if columns != (
        "request_id",
        "request_digest",
        "issue_number",
        "worktree_id",
        "lifecycle",
        "reason",
        "receipt_json",
        "created_at_utc",
        "updated_at_utc",
    ):
        raise OrchestrationJournalError("journal-invalid")
