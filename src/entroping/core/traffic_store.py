"""SQLite persistence for redacted Eye traffic state."""

import re
import sqlite3
import unicodedata
from contextlib import suppress
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
from urllib.parse import quote

from sqlalchemy import delete
from sqlmodel import Field, Index, Session, SQLModel, col, create_engine, select

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.secrets import contains_secret_like_value
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
_TRAFFIC_DDLS: Final = (_CREATE_TRAFFIC, _CREATE_TRAFFIC.replace("id INTEGER NOT NULL PRIMARY KEY", "id INTEGER PRIMARY KEY"))  # fmt: skip  # noqa: E501
_TRAFFIC_INDEXES: Final[tuple[_IndexSpec, ...]] = (("idx_traffic_events_captured_at", ("captured_at",), "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (captured_at)"), ("idx_traffic_events_host_path", ("host", "path"), "CREATE INDEX idx_traffic_events_host_path ON traffic_events (host, path)"))  # fmt: skip  # noqa: E501
_HISTORY_INDEXES: Final[tuple[_IndexSpec, ...]] = (("idx_run_history_generated_at_id", ("generated_at", "id"), "CREATE INDEX idx_run_history_generated_at_id ON run_history (generated_at, id)"), ("idx_run_history_project_environment_generated_at_id", ("project", "environment", "generated_at", "id"), "CREATE INDEX idx_run_history_project_environment_generated_at_id ON run_history (project, environment, generated_at, id)"))  # fmt: skip  # noqa: E501
_FRESH_DDL: Final = (_CREATE_METADATA, _CREATE_TRAFFIC, *(spec[2] for spec in _TRAFFIC_INDEXES), _CREATE_HISTORY, *(spec[2] for spec in _HISTORY_INDEXES))  # fmt: skip  # noqa: E501
_HISTORY_DDL: Final = (_CREATE_HISTORY, *(spec[2] for spec in _HISTORY_INDEXES))
_LEGACY_DDL: Final = (_CREATE_METADATA, *(spec[2].replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1) for spec in _TRAFFIC_INDEXES), *_HISTORY_DDL)  # fmt: skip  # noqa: E501
_METADATA_COLUMNS: Final = (("key", "VARCHAR", 1, None, 1), ("value", "VARCHAR", 1, None, 0))  # fmt: skip  # noqa: E501
_TRAFFIC_COLUMNS: Final = (("captured_at", "VARCHAR", 1, None, 0), ("method", "VARCHAR", 1, None, 0), ("url", "VARCHAR", 1, None, 0), ("host", "VARCHAR", 1, None, 0), ("path", "VARCHAR", 1, None, 0), ("status_code", "INTEGER", 0, None, 0), ("duration_ms", "INTEGER", 0, None, 0), ("exchange_json", "VARCHAR", 1, None, 0))  # fmt: skip  # noqa: E501
_HISTORY_COLUMNS: Final = (("generated_at", "VARCHAR", 1, None, 0), ("project", "VARCHAR", 1, None, 0), ("environment", "VARCHAR", 1, None, 0), ("status", "VARCHAR", 1, None, 0), ("exit_code", "INTEGER", 1, None, 0), ("duration_ms", "INTEGER", 1, None, 0), ("total", "INTEGER", 1, None, 0), ("passed", "INTEGER", 1, None, 0), ("failed", "INTEGER", 1, None, 0))  # fmt: skip  # noqa: E501
_TRAFFIC_COLUMNS_EXPLICIT: Final = (("id", "INTEGER", 1, None, 1), *_TRAFFIC_COLUMNS)
_TRAFFIC_COLUMNS_LEGACY: Final = (("id", "INTEGER", 0, None, 1), *_TRAFFIC_COLUMNS)
_HISTORY_PRECHECK: Final = "SELECT 1 FROM run_history WHERE typeof(id) != 'integer' OR id < -9223372036854775808 OR id > 9223372036854775807 OR typeof(generated_at) != 'text' OR length(generated_at) != 27 OR typeof(project) != 'text' OR length(CAST(project AS BLOB)) NOT BETWEEN 1 AND 256 OR typeof(environment) != 'text' OR length(CAST(environment AS BLOB)) NOT BETWEEN 1 AND 256 OR typeof(status) != 'text' OR status NOT IN ('passed', 'failed', 'blocked') OR typeof(exit_code) != 'integer' OR exit_code < -9223372036854775808 OR exit_code > 9223372036854775807 OR typeof(duration_ms) != 'integer' OR duration_ms < 0 OR typeof(total) != 'integer' OR total < 0 OR typeof(passed) != 'integer' OR passed < 0 OR typeof(failed) != 'integer' OR failed < 0 LIMIT 1"  # fmt: skip  # noqa: E501


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


_SCHEMA_STATES: Final = {frozenset(): _SchemaState.EMPTY, frozenset({"traffic_events"}): _SchemaState.LEGACY, frozenset({"traffic_store_metadata", "traffic_events"}): _SchemaState.METADATA_V1, frozenset({"traffic_store_metadata", "traffic_events", "run_history"}): _SchemaState.V2}  # fmt: skip  # noqa: E501


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
        _preflight_database_path(self.db_path, readonly=False)
        try:
            _ensure_schema_version(self.db_path)
        except (OSError, sqlite3.DatabaseError) as exc:
            raise TrafficStoreError("could not initialize traffic state") from exc
        self._engine = create_engine(
            f"sqlite:///{self.db_path}",
            creator=lambda: _create_runtime_connection(self.db_path, readonly=False),
        )

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
        _validate_limit(limit)
        statement = select(TrafficEventRow).order_by(col(TrafficEventRow.id))
        if limit is not None:
            statement = statement.limit(limit)
        with Session(self._engine) as session:
            rows = session.exec(statement).all()
        return tuple(TrafficExchange.model_validate_json(row.exchange_json) for row in rows)

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
    _validate_limit(limit)
    db_path = project_root.expanduser().resolve() / ".entroping" / "state.db"
    _preflight_database_path(db_path, readonly=True)  # Canonical state location.
    connection = _open_sqlite_connection(db_path, readonly=True)  # Validate and select here.
    try:
        _configure_sqlite_connection(connection, readonly=True)
        if _classify_schema(connection) is _SchemaState.EMPTY:
            raise TrafficStoreError("traffic store schema is invalid")
        _preflight_database_path(db_path, readonly=True)  # Recheck path; select validated inode.
        rows = tuple(row[0] for row in connection.execute("SELECT exchange_json FROM traffic_events ORDER BY id LIMIT COALESCE(?, -1)", (limit,)))  # fmt: skip  # noqa: E501
    except (OSError, sqlite3.DatabaseError) as exc:
        raise TrafficStoreError("could not read traffic state") from exc
    finally:
        connection.close()
    return tuple(TrafficExchange.model_validate_json(exchange_json) for exchange_json in rows)


def _validate_limit(limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise TrafficStoreError("limit must be positive")


def _ensure_schema_version(db_path: Path) -> None:
    connection: sqlite3.Connection | None = None  # Closed on every outcome.
    phase = "inspect"  # Own one DDL/validation transaction.
    try:
        connection = _open_sqlite_connection(db_path, readonly=False)
        _configure_sqlite_connection(connection, readonly=False)
        state = _classify_schema(connection)
        if state is _SchemaState.V2:  # Valid reopen is DDL-free.
            return
        phase = "begin"  # Exclusive lock bounds concurrent migration.
        _migration_execute(connection, "BEGIN EXCLUSIVE")
        phase = "migrate"
        locked_state = _migration_state_after_begin(connection)
        if locked_state is None:
            return
        _apply_migration(connection, locked_state)
        _validate_v2_schema(connection)
        _migration_quick_check(connection)
        phase = "commit"
        _migration_commit(connection)
    except (TrafficStoreError, OSError, sqlite3.DatabaseError) as exc:
        _migration_error(db_path, connection, phase, exc)
    finally:
        if connection is not None:
            connection.close()


def _migration_state_after_begin(connection: sqlite3.Connection) -> _SchemaState | None:
    state = _classify_schema(connection)  # Revalidate after waiting.
    if state is _SchemaState.V2:
        if connection.in_transaction:
            _migration_execute(connection, "ROLLBACK")
        return None
    return state


def _migration_error(
    db_path: Path,
    connection: sqlite3.Connection | None,
    phase: str,
    exc: TrafficStoreError | OSError | sqlite3.DatabaseError,
) -> None:
    if phase == "inspect" and not isinstance(exc, sqlite3.OperationalError):
        raise exc
    if phase in {"inspect", "begin", "commit"}:
        _migration_outcome(db_path, connection, phase, exc)
        return
    _migration_failure(connection, exc)


def _migration_outcome(db_path: Path, connection: sqlite3.Connection | None, phase: str, exc: TrafficStoreError | OSError | sqlite3.DatabaseError) -> None:  # fmt: skip  # noqa: E501
    if connection is not None:
        connection.close()
    outcome = _classify_after_failed_commit(db_path)
    if outcome is _SchemaState.V2:
        return
    if phase != "commit":
        raise TrafficStoreError("traffic state is busy") from exc
    if outcome in {_SchemaState.EMPTY, _SchemaState.METADATA_V1, _SchemaState.LEGACY}:
        raise TrafficStoreError("traffic state migration commit failed") from exc
    raise TrafficStoreError("traffic state migration outcome is uncertain") from exc


def _migration_failure(connection: sqlite3.Connection | None, exc: TrafficStoreError | OSError | sqlite3.DatabaseError) -> None:  # fmt: skip  # noqa: E501
    if connection is not None and connection.in_transaction:
        with suppress(sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
    raise TrafficStoreError("traffic state migration failed") from exc


def _apply_migration(connection: sqlite3.Connection, state: _SchemaState) -> None:
    plans = {_SchemaState.EMPTY: _FRESH_DDL, _SchemaState.METADATA_V1: _HISTORY_DDL, _SchemaState.LEGACY: _LEGACY_DDL}  # fmt: skip  # noqa: E501
    if state is _SchemaState.V2:
        raise TrafficStoreError("traffic store schema is invalid")
    for ddl in plans[state]:
        _migration_execute(connection, ddl)
    update = state is _SchemaState.METADATA_V1
    statement = "UPDATE traffic_store_metadata SET value = ? WHERE key = ?" if update else "INSERT INTO traffic_store_metadata(key, value) VALUES (?, ?)"  # fmt: skip  # noqa: E501
    parameters = (str(TRAFFIC_STORE_SCHEMA_VERSION), _SCHEMA_VERSION_KEY) if update else (_SCHEMA_VERSION_KEY, str(TRAFFIC_STORE_SCHEMA_VERSION))  # fmt: skip  # noqa: E501
    _migration_execute(connection, statement, parameters)


def _migration_quick_check(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
        raise TrafficStoreError("traffic state integrity check failed")


def _classify_schema(connection: sqlite3.Connection) -> _SchemaState:
    _migration_quick_check(connection)
    invalid = connection.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type NOT IN ('table', 'index') LIMIT 1").fetchone()  # fmt: skip  # noqa: E501
    if invalid is not None:
        raise TrafficStoreError("traffic store schema is invalid")
    tables = frozenset(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"))  # fmt: skip  # noqa: E501
    state = _SCHEMA_STATES.get(tables)
    if state is None:
        raise TrafficStoreError("traffic store schema is invalid")
    handler = {_SchemaState.LEGACY: _validate_legacy_schema, _SchemaState.METADATA_V1: _validate_metadata_v1_schema, _SchemaState.V2: _validate_v2_schema}.get(state)  # fmt: skip  # noqa: E501
    if handler is not None:
        handler(connection)
    return state


def _validate_legacy_schema(connection: sqlite3.Connection) -> None:
    _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_LEGACY, _TRAFFIC_DDLS)
    _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=False)


def _validate_metadata_v1_schema(connection: sqlite3.Connection) -> None:
    version = _metadata_version(connection)
    if version != "1":
        _validate_schema_version(version)
        raise TrafficStoreError("traffic store schema is invalid")
    _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_EXPLICIT, _TRAFFIC_DDLS)
    _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=True)


def _validate_v2_schema(connection: sqlite3.Connection) -> None:
    version = _metadata_version(connection)
    if version != "2":
        _validate_schema_version(version)
        raise TrafficStoreError("traffic store schema is invalid")
    traffic_info = connection.execute("PRAGMA table_info('traffic_events')").fetchall()
    if not traffic_info:  # Retain only the legacy traffic PK exception.
        raise TrafficStoreError("traffic store schema is invalid")
    _validate_shape(connection, "traffic_events", _TRAFFIC_COLUMNS_LEGACY if traffic_info[0][3] == 0 else _TRAFFIC_COLUMNS_EXPLICIT, _TRAFFIC_DDLS)  # fmt: skip  # noqa: E501
    _validate_indexes(connection, "traffic_events", _TRAFFIC_INDEXES, required=True)
    _validate_shape(connection, "run_history", (("id", "INTEGER", 1, None, 1), *_HISTORY_COLUMNS), (_CREATE_HISTORY,))  # fmt: skip  # noqa: E501
    _validate_indexes(connection, "run_history", _HISTORY_INDEXES, required=True)
    _validate_history_rows(connection)  # Shape selects the retained PK form.


def _validate_history_rows(connection: sqlite3.Connection) -> None:
    if connection.execute(_HISTORY_PRECHECK).fetchone() is not None:  # Reject coarse values first.
        raise TrafficStoreError("traffic store history is invalid")
    rows = connection.execute("SELECT id, generated_at, project, environment, status, exit_code, duration_ms, total, passed, failed FROM run_history ORDER BY id")  # fmt: skip  # noqa: E501
    for row in rows:  # Cursor iteration keeps memory bounded.
        if not _valid_history_row(row):
            raise TrafficStoreError("traffic store history is invalid")


def _valid_history_row(row: tuple[object, ...]) -> bool:
    return len(row) == 10 and _valid_history_timestamp(row[1]) and _valid_history_identifier(row[2]) and _valid_history_identifier(row[3])  # fmt: skip  # noqa: E501


def _valid_history_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 27 or not value.endswith("Z"):
        return False
    with suppress(ValueError):
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return True
    return False


def _valid_history_identifier(value: object) -> bool:
    if not isinstance(value, str):  # Require normalized values before future APIs.
        return False
    try:
        encoded = value.encode("utf-8")  # Enforce the byte, not codepoint, bound.
    except UnicodeEncodeError:
        return False
    checks = (1 <= len(encoded) <= 256, unicodedata.normalize("NFC", value) == value, not any(unicodedata.category(char) == "Cc" for char in value), not contains_secret_like_value(value))  # fmt: skip  # noqa: E501
    return all(checks)


def _metadata_version(connection: sqlite3.Connection) -> str:
    _validate_shape(connection, "traffic_store_metadata", _METADATA_COLUMNS, (_CREATE_METADATA,))
    _validate_indexes(connection, "traffic_store_metadata", (), required=False)
    rows = tuple(connection.execute("SELECT CASE WHEN length(key) <= 64 THEN key END, CASE WHEN length(value) <= 64 THEN value END FROM traffic_store_metadata ORDER BY key LIMIT 2").fetchall())  # fmt: skip  # noqa: E501
    if len(rows) != 1 or rows[0][0] != _SCHEMA_VERSION_KEY or not isinstance(rows[0][1], str):
        raise TrafficStoreError("traffic store schema is invalid")
    return rows[0][1]


def _validate_shape(
    connection: sqlite3.Connection,
    table: str,
    expected: tuple[tuple[str, str, int, str | None, int], ...],
    ddls: tuple[str, ...],
) -> None:
    rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    sql = connection.execute("SELECT COALESCE((SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?), '')", (table,)).fetchone()[0]  # fmt: skip  # noqa: E501
    columns = tuple((item[1], item[2], item[3], item[4], item[5]) for item in rows if len(item) >= 6)  # fmt: skip  # noqa: E501
    actual = (columns, _normalise_ddl(sql))
    if actual not in {(expected, _normalise_ddl(item)) for item in ddls}:
        raise TrafficStoreError("traffic store schema is invalid")


def _normalise_ddl(sql: str) -> str:
    return "".join(part if part.startswith("'") else re.sub(r"\s*([(),;])\s*", r"\1", " ".join(part.replace('"', "").replace("`", "").upper().split())) for part in re.split(r"('(?:''|[^'])*')", sql) if part).rstrip(";")  # fmt: skip  # noqa: E501


def _validate_indexes(connection: sqlite3.Connection, table: str, expected: tuple[_IndexSpec, ...], *, required: bool) -> None:  # fmt: skip  # noqa: E501
    indexes, listed = _index_catalog(connection, table)
    required_names = frozenset(spec[0] for spec in expected)  # Preserve full index semantics.
    if any(_invalid_index_entry(name, row, required_names) for name, row in listed.items()):
        raise TrafficStoreError("traffic store schema is invalid")
    for spec in expected:
        _validate_required_index(connection, table, indexes, listed, spec, required)


def _index_catalog(connection: sqlite3.Connection, table: str) -> tuple[dict[str, str], dict[str, tuple[object, ...]]]:  # fmt: skip  # noqa: E501
    indexes = {row[0]: row[1] for row in connection.execute("SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'").fetchall()}  # fmt: skip  # noqa: E501
    listed = {row[1]: row for row in connection.execute(f"PRAGMA index_list('{table}')")}
    return indexes, listed


def _invalid_index_entry(name: str, row: tuple[object, ...], required: frozenset[str]) -> bool:
    if name.startswith("sqlite_"):
        return row[2:5] != (1, "pk", 0)
    return name not in required and (row[2] != 0 or (len(row) > 4 and row[4] != 0))


def _validate_required_index(connection: sqlite3.Connection, table: str, indexes: dict[str, str], listed: dict[str, tuple[object, ...]], spec: _IndexSpec, required: bool) -> None:  # fmt: skip  # noqa: E501
    name, columns, _ = spec
    if name not in indexes:
        if required:
            raise TrafficStoreError("traffic store schema is invalid")
        return
    if (indexes.get(name), listed.get(name, ())[2:5]) != (table, (0, "c", 0)):
        raise TrafficStoreError("traffic store schema is invalid")
    if not _index_columns_match(connection, name, columns):
        raise TrafficStoreError("traffic store schema is invalid")


def _index_columns_match(connection: sqlite3.Connection, name: str, columns: tuple[str, ...]) -> bool:  # fmt: skip  # noqa: E501
    rows = tuple(connection.execute(f"PRAGMA index_xinfo('{name}')"))
    actual = tuple((row[0], row[2], row[3], row[4], row[5]) for row in rows if len(row) >= 6 and row[5] == 1)  # fmt: skip  # noqa: E501
    expected = tuple((index, column, 0, "BINARY", 1) for index, column in enumerate(columns))
    return actual == expected


def _validate_schema_version(raw_value: str) -> None:
    if raw_value in {"1", "2"}:
        return
    try:  # Never echo attacker metadata.
        version = int(raw_value)
    except ValueError as exc:
        raise TrafficStoreError("traffic store schema version is invalid") from exc
    if version > TRAFFIC_STORE_SCHEMA_VERSION:
        raise TrafficStoreError("traffic store schema version is newer than supported")
    raise TrafficStoreError("traffic store schema version is older than supported")


def _preflight_database_path(db_path: Path, *, readonly: bool) -> None:
    try:
        _reject_symlink_path_components(db_path)  # Reject sidecars before connect.
        if any(db_path.with_name(db_path.name + suffix).exists() or db_path.with_name(db_path.name + suffix).is_symlink() for suffix in _SIDECAR_SUFFIXES):  # fmt: skip  # noqa: E501
            raise TrafficStoreError("traffic state sidecar is present")
        if not db_path.exists():
            if readonly:
                raise TrafficStoreError("traffic state not found")
            return
        if not db_path.is_file():
            raise TrafficStoreError("traffic state file is invalid")
        with db_path.open("rb") as stream:
            header = stream.read(100)
    except OSError as exc:
        raise TrafficStoreError("traffic state preflight failed") from exc
    header_valid = (len(header) >= 100, header[:16], header[18:20]) == (True, _SQLITE_HEADER, b"\x01\x01")  # fmt: skip  # noqa: E501
    if not header_valid:
        raise TrafficStoreError("traffic state header is invalid")


def _open_sqlite_connection(
    db_path: Path, *, readonly: bool, require_existing: bool = False
) -> sqlite3.Connection:
    _preflight_database_path(db_path, readonly=readonly or require_existing)
    mode = "ro" if readonly else ("rw" if require_existing else "rwc")
    return sqlite3.connect(f"file:{quote(db_path.as_posix(), safe='/')}?mode={mode}", uri=True, timeout=_BUSY_TIMEOUT_MILLISECONDS / 1_000, check_same_thread=False)  # fmt: skip  # noqa: E501


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


def _create_runtime_connection(db_path: Path, *, readonly: bool) -> sqlite3.Connection:
    connection = _open_sqlite_connection(db_path, readonly=readonly, require_existing=True)  # fmt: skip  # noqa: E501
    try:  # Configuration failure closes this connection.
        _configure_sqlite_connection(connection, readonly=readonly)
    except (TrafficStoreError, sqlite3.DatabaseError):
        connection.close()  # Return ready or closed.
        raise
    return connection


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
        return None  # Ambiguity remains fail-closed and value-free.
    finally:
        if connection is not None:
            connection.close()


def _reject_symlink_path_components(path: Path) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        raise TrafficStoreError(f"Refusing to use symlinked traffic state path component: {symlink_component}")  # fmt: skip  # noqa: E501
