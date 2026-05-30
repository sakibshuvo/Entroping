"""SQLite persistence for redacted Eye traffic state."""

import sqlite3
from pathlib import Path
from typing import cast

from entroping.models.traffic import TrafficExchange


class TrafficStoreError(ValueError):
    """Raised when traffic state cannot be persisted safely."""


class TrafficStore:
    """Local SQLite store for redacted traffic exchanges."""

    def __init__(self, db_path: Path, *, max_events: int = 1_000) -> None:
        if max_events <= 0:
            msg = "max_events must be positive"
            raise TrafficStoreError(msg)

        expanded = db_path.expanduser()
        _reject_symlink_path_components(expanded)
        self.db_path = expanded.resolve()
        self.max_events = max_events
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path_components(expanded)
        self._initialize()

    @classmethod
    def open_project(cls, project_root: Path, *, max_events: int = 1_000) -> "TrafficStore":
        """Open the standard ``.entroping/state.db`` traffic store for a project."""

        return cls(project_root / ".entroping" / "state.db", max_events=max_events)

    def record_exchange(self, exchange: TrafficExchange) -> int:
        """Persist one redacted exchange and enforce retention."""

        if not exchange.redacted:
            msg = "refusing to persist unredacted traffic"
            raise TrafficStoreError(msg)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO traffic_events (
                    captured_at,
                    method,
                    url,
                    host,
                    path,
                    status_code,
                    duration_ms,
                    exchange_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exchange.captured_at.isoformat(),
                    exchange.request.method,
                    exchange.request.url,
                    exchange.request.host,
                    exchange.request.path,
                    exchange.response.status_code if exchange.response is not None else None,
                    exchange.duration_ms,
                    exchange.model_dump_json(),
                ),
            )
            event_id = cursor.lastrowid
            if event_id is None:
                msg = "SQLite did not return an inserted traffic event id"
                raise TrafficStoreError(msg)
            self._enforce_retention(connection)
            return event_id

    def list_exchanges(self, *, limit: int | None = None) -> tuple[TrafficExchange, ...]:
        """Return persisted redacted exchanges in insertion order."""

        if limit is not None and limit <= 0:
            msg = "limit must be positive"
            raise TrafficStoreError(msg)

        sql = "SELECT exchange_json FROM traffic_events ORDER BY id"
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        return tuple(
            TrafficExchange.model_validate_json(cast(str, row["exchange_json"])) for row in rows
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS traffic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    host TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER,
                    duration_ms INTEGER,
                    exchange_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_traffic_events_captured_at "
                "ON traffic_events(captured_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_traffic_events_host_path "
                "ON traffic_events(host, path)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _enforce_retention(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM traffic_events
            WHERE id NOT IN (
                SELECT id FROM traffic_events ORDER BY id DESC LIMIT ?
            )
            """,
            (self.max_events,),
        )


def _reject_symlink_path_components(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to use symlinked traffic state path component: {current}"
            raise TrafficStoreError(msg)
