"""SQLite persistence for redacted Eye traffic state."""

import sqlite3
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never
from urllib.parse import quote

from sqlalchemy import delete, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, Index, Session, SQLModel, col, create_engine, select

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.traffic import TrafficExchange
from entroping.models.traffic_redaction import redacted_traffic_violation_summary

TRAFFIC_STORE_SCHEMA_VERSION: Final = 2
_SCHEMA_VERSION_KEY: Final = "schema_version"
_BUSY_TIMEOUT_MILLISECONDS: Final = 5_000
_SQLITE_HEADER: Final = b"SQLite format 3\x00"
_SIDECAR_SUFFIXES: Final = ("-wal", "-shm")
_CREATE_METADATA: Final = (
    "CREATE TABLE traffic_store_metadata (key VARCHAR NOT NULL PRIMARY KEY, value VARCHAR NOT NULL)"
)
_CREATE_TRAFFIC: Final = "CREATE TABLE traffic_events (id INTEGER NOT NULL PRIMARY KEY, captured_at VARCHAR NOT NULL, method VARCHAR NOT NULL, url VARCHAR NOT NULL, host VARCHAR NOT NULL, path VARCHAR NOT NULL, status_code INTEGER, duration_ms INTEGER, exchange_json VARCHAR NOT NULL)"  # noqa: E501
_CREATE_HISTORY: Final = "CREATE TABLE run_history (id INTEGER NOT NULL PRIMARY KEY, generated_at VARCHAR NOT NULL, project VARCHAR NOT NULL, environment VARCHAR NOT NULL, status VARCHAR NOT NULL CHECK (status IN ('passed', 'failed', 'blocked')), exit_code INTEGER NOT NULL, duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0), total INTEGER NOT NULL CHECK (total >= 0), passed INTEGER NOT NULL CHECK (passed >= 0), failed INTEGER NOT NULL CHECK (failed >= 0))"  # noqa: E501
type _IndexSpec = tuple[str, tuple[str, ...], str]
_TRAFFIC_INDEXES: Final[tuple[_IndexSpec, ...]] = (("idx_traffic_events_captured_at", ("captured_at",), "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (captured_at)"), ("idx_traffic_events_host_path", ("host", "path"), "CREATE INDEX idx_traffic_events_host_path ON traffic_events (host, path)"))  # fmt: skip  # noqa: E501
_HISTORY_INDEXES: Final[tuple[_IndexSpec, ...]] = (("idx_run_history_generated_at_id", ("generated_at", "id"), "CREATE INDEX idx_run_history_generated_at_id ON run_history (generated_at, id)"), ("idx_run_history_project_environment_generated_at_id", ("project", "environment", "generated_at", "id"), "CREATE INDEX idx_run_history_project_environment_generated_at_id ON run_history (project, environment, generated_at, id)"))  # fmt: skip  # noqa: E501
_METADATA_COLUMNS: Final = (("key", "VARCHAR", 1, None, 1), ("value", "VARCHAR", 1, None, 0))  # fmt: skip  # noqa: E501
_TRAFFIC_COLUMNS: Final = (("captured_at", "VARCHAR", 1, None, 0), ("method", "VARCHAR", 1, None, 0), ("url", "VARCHAR", 1, None, 0), ("host", "VARCHAR", 1, None, 0), ("path", "VARCHAR", 1, None, 0), ("status_code", "INTEGER", 0, None, 0), ("duration_ms", "INTEGER", 0, None, 0), ("exchange_json", "VARCHAR", 1, None, 0))  # fmt: skip  # noqa: E501
_HISTORY_COLUMNS: Final = (("generated_at", "VARCHAR", 1, None, 0), ("project", "VARCHAR", 1, None, 0), ("environment", "VARCHAR", 1, None, 0), ("status", "VARCHAR", 1, None, 0), ("exit_code", "INTEGER", 1, None, 0), ("duration_ms", "INTEGER", 1, None, 0), ("total", "INTEGER", 1, None, 0), ("passed", "INTEGER", 1, None, 0), ("failed", "INTEGER", 1, None, 0))  # fmt: skip  # noqa: E501
_TRAFFIC_COLUMNS_EXPLICIT: Final = (("id", "INTEGER", 1, None, 1), *_TRAFFIC_COLUMNS)
_TRAFFIC_COLUMNS_LEGACY: Final = (("id", "INTEGER", 0, None, 1), *_TRAFFIC_COLUMNS)
_SCHEMA_MARKERS: Final = (" CHECK ", " UNIQUE ", " REFERENCES ", " DEFAULT ", " AUTOINCREMENT", " WITHOUT ROWID", " STRICT", " COLLATE ", " GENERATED ")  # fmt: skip  # noqa: E501


class TrafficStoreError(ValueError):
    pass


class TrafficStoreMetadataRow(SQLModel, table=True):
    __tablename__ = "traffic_store_metadata"
    key: str = Field(primary_key=True)
    value: str


class TrafficEventRow(SQLModel, table=True):
    __tablename__ = "traffic_events"
    __table_args__ = (
        Index("idx_traffic_events_captured_at", "captured_at"),
        Index("idx_traffic_events_host_path", "host", "path"),
    )
    id: int | None = Field(default=None, primary_key=True)
    captured_at: str
    method: str
    url: str
    host: str
    path: str
    status_code: int | None = None
    duration_ms: int | None = None
    exchange_json: str


class _SchemaState(StrEnum):
    EMPTY = "empty"
    METADATA_V1 = "metadata-v1"
    LEGACY = "legacy"
    V2 = "v2"


class TrafficStore:
    def __init__(self, db_path: Path, *, max_events: int = 1_000) -> None:
        if max_events <= 0:
            raise TrafficStoreError("max_events must be positive")
        expanded = db_path.expanduser()
        _reject_symlink_path_components(expanded)
        self.db_path = expanded.resolve()
        self.max_events = max_events
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path_components(expanded)
        self._initialize()
        self._engine = _create_runtime_engine(self.db_path)

    @classmethod
    def open_project(cls, project_root: Path, *, max_events: int = 1_000) -> "TrafficStore":
        return cls(project_root / ".entroping" / "state.db", max_events=max_events)

    def record_exchange(self, exchange: TrafficExchange) -> int:
        if not exchange.redacted:
            raise TrafficStoreError("refusing to persist unredacted traffic")
        violation_summary = redacted_traffic_violation_summary(exchange)
        if violation_summary is not None:
            raise TrafficStoreError(f"refusing to persist {violation_summary}")
        row = TrafficEventRow(
            captured_at=exchange.captured_at.isoformat(),
            method=exchange.request.method,
            url=exchange.request.url,
            host=exchange.request.host,
            path=exchange.request.path,
            status_code=exchange.response.status_code if exchange.response is not None else None,
            duration_ms=exchange.duration_ms,
            exchange_json=exchange.model_dump_json(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            if row.id is None:
                raise TrafficStoreError("SQLite did not return an inserted traffic event id")
            self._enforce_retention(session)
            session.commit()
            return row.id

    def list_exchanges(self, *, limit: int | None = None) -> tuple[TrafficExchange, ...]:
        if limit is not None and limit <= 0:
            raise TrafficStoreError("limit must be positive")
        statement = select(TrafficEventRow).order_by(col(TrafficEventRow.id))
        if limit is not None:
            statement = statement.limit(limit)
        with Session(self._engine) as session:
            rows = session.exec(statement).all()
        return tuple(TrafficExchange.model_validate_json(row.exchange_json) for row in rows)

    def _initialize(self) -> None:
        _preflight_database_path(self.db_path, readonly=False)
        try:
            _ensure_schema_version(self.db_path)
        except TrafficStoreError:
            raise
        except (OSError, SQLAlchemyError, sqlite3.DatabaseError) as exc:
            raise TrafficStoreError("could not initialize traffic state") from exc

    def _enforce_retention(self, session: Session) -> None:
        stale_ids = tuple(
            row_id
            for row_id in session.exec(
                select(TrafficEventRow.id)
                .order_by(col(TrafficEventRow.id).desc())
                .offset(self.max_events)
            ).all()
            if row_id is not None
        )
        if stale_ids:
            session.execute(delete(TrafficEventRow).where(col(TrafficEventRow.id).in_(stale_ids)))


def list_project_exchanges_readonly(
    project_root: Path, *, limit: int | None = None
) -> tuple[TrafficExchange, ...]:
    if limit is not None and limit <= 0:
        raise TrafficStoreError("limit must be positive")
    db_path = project_root.expanduser().resolve() / ".entroping" / "state.db"
    _reject_symlink_path_components(db_path)
    _preflight_database_path(db_path, readonly=True)
    connection = _open_sqlite_connection(db_path, readonly=True)
    try:
        _configure_sqlite_connection(connection, readonly=True)
        _validate_existing_schema_version(connection)
    except TrafficStoreError:
        raise
    except SQLAlchemyError as exc:
        raise TrafficStoreError("could not read traffic store schema version") from exc
    except (OSError, sqlite3.DatabaseError) as exc:
        raise TrafficStoreError("could not read traffic store schema") from exc
    finally:
        connection.close()
    engine = _create_runtime_engine(db_path, readonly=True)
    statement = select(TrafficEventRow).order_by(col(TrafficEventRow.id))
    if limit is not None:
        statement = statement.limit(limit)
    try:
        with Session(engine) as session:
            rows = session.exec(statement).all()
    except SQLAlchemyError as exc:
        raise TrafficStoreError("could not read traffic state") from exc
    finally:
        engine.dispose()
    return tuple(TrafficExchange.model_validate_json(row.exchange_json) for row in rows)


def _ensure_schema_version(db_path: Path) -> None:
    connection: sqlite3.Connection | None = None
    phase = "inspect"
    try:
        connection = _open_sqlite_connection(db_path, readonly=False)
        _configure_sqlite_connection(connection, readonly=False)
        state = _classify_schema(connection)
        if state is _SchemaState.V2:
            return
        phase = "begin"
        _migration_execute(connection, "BEGIN EXCLUSIVE")
        phase = "migrate"
        state = _classify_schema(connection)
        if state is _SchemaState.V2:
            if connection.in_transaction:
                _migration_execute(connection, "ROLLBACK")
            return
        _apply_migration(connection, state)
        _validate_v2_schema(connection)
        phase = "commit"
        _migration_commit(connection)
    except TrafficStoreError as exc:
        _migration_error(db_path, connection, phase, exc)
    except (OSError, sqlite3.DatabaseError) as exc:
        _migration_error(db_path, connection, phase, exc)
    finally:
        if connection is not None:
            connection.close()


def _migration_error(
    db_path: Path,
    connection: sqlite3.Connection | None,
    phase: str,
    exc: TrafficStoreError | OSError | sqlite3.DatabaseError,
) -> None:
    if phase == "inspect" and not isinstance(exc, sqlite3.OperationalError):
        raise exc
    if phase in {"inspect", "begin"} and isinstance(exc, sqlite3.OperationalError):
        if connection is not None:
            connection.close()
        if _classify_after_failed_commit(db_path) is _SchemaState.V2:
            return
        raise TrafficStoreError("traffic state is busy") from exc
    if phase == "commit":
        if connection is not None:
            connection.close()
        outcome = _classify_after_failed_commit(db_path)
        if outcome is _SchemaState.V2:
            return
        if outcome in {_SchemaState.EMPTY, _SchemaState.METADATA_V1, _SchemaState.LEGACY}:
            raise TrafficStoreError("traffic state migration commit failed") from exc
        raise TrafficStoreError("traffic state migration outcome is uncertain") from exc
    if connection is not None and connection.in_transaction:
        with suppress(sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
    raise TrafficStoreError("traffic state migration failed") from exc


def _apply_migration(connection: sqlite3.Connection, state: _SchemaState) -> None:
    match state:
        case _SchemaState.EMPTY:
            statements = (
                _CREATE_METADATA,
                _CREATE_TRAFFIC,
                *(spec[2] for spec in _TRAFFIC_INDEXES),
                _CREATE_HISTORY,
                *(spec[2] for spec in _HISTORY_INDEXES),
            )
            for statement in statements:
                _migration_execute(connection, statement)
            _migration_execute(
                connection,
                "INSERT INTO traffic_store_metadata(key, value) VALUES (?, ?)",
                (_SCHEMA_VERSION_KEY, str(TRAFFIC_STORE_SCHEMA_VERSION)),
            )
        case _SchemaState.METADATA_V1:
            for statement in (_CREATE_HISTORY, *(spec[2] for spec in _HISTORY_INDEXES)):
                _migration_execute(connection, statement)
            _migration_execute(
                connection,
                "UPDATE traffic_store_metadata SET value = ? WHERE key = ?",
                (str(TRAFFIC_STORE_SCHEMA_VERSION), _SCHEMA_VERSION_KEY),
            )
        case _SchemaState.LEGACY:
            _migration_execute(connection, _CREATE_METADATA)
            existing = frozenset(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"  # noqa: E501
                ).fetchall()
            )
            for name, _, statement in _TRAFFIC_INDEXES:
                if name not in existing:
                    _migration_execute(connection, statement)
            for statement in (_CREATE_HISTORY, *(spec[2] for spec in _HISTORY_INDEXES)):
                _migration_execute(connection, statement)
            _migration_execute(
                connection,
                "INSERT INTO traffic_store_metadata(key, value) VALUES (?, ?)",
                (_SCHEMA_VERSION_KEY, str(TRAFFIC_STORE_SCHEMA_VERSION)),
            )
        case _SchemaState.V2:
            raise TrafficStoreError("traffic store schema is invalid")
        case unreachable:
            assert_never(unreachable)


def _validate_existing_schema_version(connection: sqlite3.Connection) -> None:
    if _classify_schema(connection) is _SchemaState.EMPTY:
        raise TrafficStoreError("traffic store schema is invalid")


def _classify_schema(connection: sqlite3.Connection) -> _SchemaState:
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise TrafficStoreError("traffic state integrity check failed")
    objects = tuple(
        connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )  # noqa: E501
    if any(row[0] not in {"table", "index"} for row in objects):
        raise TrafficStoreError("traffic store schema is invalid")
    tables = frozenset(row[1] for row in objects if row[0] == "table")
    if not tables:
        return _SchemaState.EMPTY
    if "traffic_store_metadata" not in tables:
        if tables != {"traffic_events"}:
            raise TrafficStoreError("traffic store schema is invalid")
        _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_LEGACY, markers=True)
        _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=False)
        return _SchemaState.LEGACY
    if tables == {"traffic_store_metadata", "traffic_events"}:
        version = _metadata_version(connection)
        if version == "1":
            _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_EXPLICIT, markers=True)
            _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=True)
            return _SchemaState.METADATA_V1
        _validate_schema_version(version)
    if tables == {"traffic_store_metadata", "traffic_events", "run_history"}:
        version = _metadata_version(connection)
        if version == "2":
            _validate_v2_schema(connection)
            return _SchemaState.V2
        _validate_schema_version(version)
    raise TrafficStoreError("traffic store schema is invalid")


def _validate_v2_schema(connection: sqlite3.Connection) -> None:
    traffic_info = connection.execute("PRAGMA table_info('traffic_events')").fetchall()
    if not traffic_info:
        raise TrafficStoreError("traffic store schema is invalid")
    _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_LEGACY if traffic_info[0][3] == 0 else _TRAFFIC_COLUMNS_EXPLICIT, markers=True)  # fmt: skip  # noqa: E501
    _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=True)
    _validate_shape(connection, "run_history", (("id", "INTEGER", 1, None, 1), *_HISTORY_COLUMNS), ddl=_CREATE_HISTORY)  # fmt: skip  # noqa: E501
    _validate_indexes(connection, "run_history", _HISTORY_INDEXES, required=True)


def _metadata_version(connection: sqlite3.Connection) -> str:
    columns = tuple((row[1], row[2], row[3], row[4], row[5]) for row in connection.execute("PRAGMA table_info('traffic_store_metadata')").fetchall() if len(row) >= 6)  # fmt: skip  # noqa: E501
    if columns != _METADATA_COLUMNS:
        raise TrafficStoreError("traffic store schema is invalid")
    rows = tuple(
        connection.execute("SELECT key, value FROM traffic_store_metadata ORDER BY key").fetchall()
    )  # noqa: E501
    if len(rows) != 1 or rows[0][0] != _SCHEMA_VERSION_KEY or not isinstance(rows[0][1], str):
        raise TrafficStoreError("traffic store schema is invalid")
    return rows[0][1]


def _validate_shape(
    connection: sqlite3.Connection,
    table: str,
    expected: tuple[tuple[str, str, int, str | None, int], ...],
    *,
    ddl: str | None = None,
    markers: bool = False,
) -> None:
    rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    if tuple((row[1], row[2], row[3], row[4], row[5]) for row in rows if len(row) >= 6) != expected:
        raise TrafficStoreError("traffic store schema is invalid")
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise TrafficStoreError("traffic store schema is invalid")
    normalised_ddl = " ".join(row[0].replace('"', "").replace("`", "").split()).rstrip(";").upper()
    expected_ddl = (
        " ".join(ddl.replace('"', "").replace("`", "").split()).rstrip(";").upper()
        if ddl is not None
        else None
    )
    sql = f" {normalised_ddl} "
    if (expected_ddl is not None and normalised_ddl != expected_ddl) or (
        markers and any(marker in sql for marker in _SCHEMA_MARKERS)
    ):
        raise TrafficStoreError("traffic store schema is invalid")


def _validate_indexes(
    connection: sqlite3.Connection,
    table: str,
    expected: tuple[_IndexSpec, ...],
    *,
    required: bool,
) -> None:
    indexes = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"  # noqa: E501
        ).fetchall()
    }
    listed = {row[1]: row for row in connection.execute(f"PRAGMA index_list('{table}')").fetchall()}
    for name, columns, _ in expected:
        if name not in indexes:
            if required:
                raise TrafficStoreError("traffic store schema is invalid")
            continue
        if (
            indexes[name] != table
            or name not in listed
            or listed[name][2] != 0
            or (len(listed[name]) > 4 and listed[name][4] != 0)
        ):
            raise TrafficStoreError("traffic store schema is invalid")
        actual = tuple(
            row[2] for row in connection.execute(f"PRAGMA index_info('{name}')").fetchall()
        )
        if actual != columns:
            raise TrafficStoreError("traffic store schema is invalid")


def _validate_schema_version(raw_value: str) -> None:
    if raw_value in {"1", "2"}:
        return
    try:
        version = int(raw_value)
    except ValueError as exc:
        raise TrafficStoreError("traffic store schema version is invalid") from exc
    if version > TRAFFIC_STORE_SCHEMA_VERSION:
        raise TrafficStoreError("traffic store schema version is newer than supported")
    raise TrafficStoreError("traffic store schema version is older than supported")


def _preflight_database_path(db_path: Path, *, readonly: bool) -> None:
    if any(
        db_path.with_name(db_path.name + suffix).exists()
        or db_path.with_name(db_path.name + suffix).is_symlink()
        for suffix in _SIDECAR_SUFFIXES
    ):
        raise TrafficStoreError("traffic state sidecar is present")
    if not db_path.exists():
        if readonly:
            raise TrafficStoreError("traffic state not found")
        return
    if not db_path.is_file():
        raise TrafficStoreError("traffic state file is invalid")
    header = db_path.read_bytes()[:100]
    if len(header) < 100 or header[:16] != _SQLITE_HEADER or header[18:20] != b"\x01\x01":
        raise TrafficStoreError("traffic state header is invalid")


def _open_sqlite_connection(db_path: Path, *, readonly: bool) -> sqlite3.Connection:
    _preflight_database_path(db_path, readonly=readonly)
    mode = "ro" if readonly else "rwc"
    return sqlite3.connect(f"file:{quote(db_path.as_posix(), safe='/')}?mode={mode}", uri=True, timeout=_BUSY_TIMEOUT_MILLISECONDS / 1_000)  # fmt: skip  # noqa: E501


def _configure_sqlite_connection(connection: sqlite3.Connection, *, readonly: bool) -> None:
    connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}")
    connection.execute("PRAGMA foreign_keys = ON")
    with suppress(sqlite3.DatabaseError):
        connection.execute("PRAGMA trusted_schema = OFF")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
    elif connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
        raise TrafficStoreError("traffic state journal mode is unsupported")
    else:
        connection.execute("PRAGMA synchronous = EXTRA")


def _create_runtime_engine(db_path: Path, *, readonly: bool = False) -> Engine:
    engine = create_engine(f"sqlite:///file:{quote(db_path.as_posix(), safe='/')}?mode=ro&uri=true" if readonly else f"sqlite:///{db_path}")  # fmt: skip  # noqa: E501
    event.listen(engine, "connect", lambda connection, _: _configure_sqlite_connection(connection, readonly=readonly))  # fmt: skip  # noqa: E501
    return engine


def _migration_execute(connection: sqlite3.Connection, statement: str, parameters: tuple[str, ...] = ()) -> sqlite3.Cursor:  # fmt: skip  # noqa: E501
    return connection.execute(statement, parameters)


def _migration_commit(connection: sqlite3.Connection) -> None:  # fmt: skip
    _migration_execute(connection, "COMMIT")  # fmt: skip


def _classify_after_failed_commit(db_path: Path) -> _SchemaState | None:
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_sqlite_connection(db_path, readonly=True)
        _configure_sqlite_connection(connection, readonly=True)
        return _classify_schema(connection)
    except (OSError, sqlite3.DatabaseError, TrafficStoreError):
        return None
    finally:
        if connection is not None:
            connection.close()


def _reject_symlink_path_components(path: Path) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        raise TrafficStoreError(f"Refusing to use symlinked traffic state path component: {symlink_component}")  # fmt: skip  # noqa: E501
