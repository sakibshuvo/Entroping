from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from urllib.parse import quote

from .factory_status_filesystem import FactoryStatusError, fingerprint_file
from .factory_status_models import SourceState

type Fingerprints = list[tuple[str, int, int, int]]


def open_status_database(
    root: Path, path: Path, fingerprints: Fingerprints
) -> tuple[sqlite3.Connection | None, SourceState]:
    """Open an existing private state database in immutable query-only mode."""

    try:
        expected = file_identity(path)
        fingerprint_file(root, path, fingerprints, strict_state_file=True)
    except FileNotFoundError:
        return None, "uninitialized"
    except (FactoryStatusError, OSError):
        return None, "unsafe"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{quote(path.as_posix(), safe='/')}?mode=ro&immutable=1",
            uri=True,
            autocommit=True,
            timeout=0.1,
        )
        _ = connection.execute("PRAGMA query_only = ON")
        _ = connection.execute("PRAGMA trusted_schema = OFF")
        _ = connection.execute("BEGIN")
        if file_identity(path) != expected:
            connection.close()
            return None, "unsafe"
        return connection, "available"
    except (OSError, sqlite3.DatabaseError):
        if connection is not None:
            connection.close()
        return None, "unsafe"


def file_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Return a private regular file's identity without following links."""

    metadata = path.lstat()
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
