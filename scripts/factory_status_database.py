from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError
from scripts.factory_budget_ledger_parent_fs import open_private_relative_directory
from scripts.factory_retention_fs import RetentionFsError

from .factory_status_errors import FactoryStatusError
from .factory_status_models import SourceState

type Fingerprints = list[tuple[str, int, int, int]]


class _StatusConnection(sqlite3.Connection):
    _descriptor: int | None = None

    def bind_descriptor(self, descriptor: int) -> None:
        self._descriptor = descriptor

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._descriptor is not None:
                os.close(self._descriptor)
                self._descriptor = None


def open_status_database(
    root: Path, path: Path, fingerprints: Fingerprints
) -> tuple[sqlite3.Connection | None, SourceState]:
    """Open an existing private state database in immutable query-only mode."""

    descriptor: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        _ = path.lstat()
    except FileNotFoundError:
        return None, "uninitialized"
    except OSError:
        return None, "unsafe"
    try:
        relative = path.relative_to(root)
        with open_private_relative_directory(root, relative.parts[:-1], create=False) as parent:
            descriptor = os.open(
                relative.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent
            )
            _reject_sidecars(parent, relative.name)
            expected = file_identity_from_metadata(os.fstat(descriptor))
            _fingerprint_descriptor(root, path, descriptor, fingerprints)
            connection = sqlite3.connect(
                f"file:/dev/fd/{descriptor}?mode=ro&immutable=1",
                uri=True,
                autocommit=True,
                timeout=0.1,
                factory=_StatusConnection,
            )
            assert isinstance(connection, _StatusConnection)
            connection.bind_descriptor(descriptor)
            descriptor = None
            _ = connection.execute("PRAGMA query_only = ON")
            _ = connection.execute("PRAGMA trusted_schema = OFF")
            _ = connection.execute("BEGIN")
            if not _descriptor_matches_expected(connection, expected):
                connection.close()
                return None, "unsafe"
            _reject_sidecars(parent, relative.name)
        return connection, "available"
    except FileNotFoundError:
        return None, "unsafe"
    except (
        FactoryBudgetLedgerError,
        FactoryStatusError,
        OSError,
        RetentionFsError,
        sqlite3.DatabaseError,
    ):
        if connection is not None:
            connection.close()
        return None, "unsafe"
    finally:
        if descriptor is not None:
            os.close(descriptor)


def file_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Return a private regular file's identity without following links."""

    return file_identity_from_metadata(path.lstat())


def file_identity_from_metadata(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise FactoryStatusError("unsafe state file")
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def _fingerprint_descriptor(
    root: Path, path: Path, descriptor: int, fingerprints: Fingerprints
) -> None:
    metadata = os.fstat(descriptor)
    fingerprints.append(
        (path.relative_to(root).as_posix(), metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
    )


def _descriptor_matches_expected(
    connection: sqlite3.Connection, expected: tuple[int, int, int, int, int]
) -> bool:
    if not isinstance(connection, _StatusConnection) or connection._descriptor is None:
        return False
    metadata = os.fstat(connection._descriptor)
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
    ) == expected[:4] and metadata.st_nlink <= 1


def _reject_sidecars(parent: int, filename: str) -> None:
    for suffix in ("-journal", "-wal", "-shm"):
        try:
            _ = os.stat(f"{filename}{suffix}", dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise FactoryStatusError("hot SQLite sidecar")
