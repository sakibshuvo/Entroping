from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from .factory_scheduler_storage_fs import (
    BUSY_TIMEOUT_MILLISECONDS,
    MAX_DATABASE_BYTES,
    FileIdentity,
    SchedulerStateError,
    is_busy,
    path_identity,
    validate_header,
)


def open_scheduler_connection(
    path: Path,
    *,
    readonly: bool,
    identity: FileIdentity,
) -> sqlite3.Connection:
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
