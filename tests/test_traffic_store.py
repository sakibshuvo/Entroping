"""Tests for local SQLite traffic state."""

import hashlib
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Event, Lock, Thread
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlmodel import Session, col, create_engine, select

from entroping.core import traffic_store
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import (
    TRAFFIC_STORE_SCHEMA_VERSION,
    TrafficEventRow,
    TrafficStore,
    TrafficStoreError,
    TrafficStoreMetadataRow,
    list_project_exchanges_readonly,
)
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _exchange(secret: str = "secret-token") -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=11,
        request=TrafficRequest(
            method="GET",
            url=f"https://api.example.test/health?token={secret}",
            headers={"Authorization": f"Bearer {secret}"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(content_type="application/json", size_bytes=11, text='{"ok":true}'),
        ),
    )


_CREATE_METADATA = """
CREATE TABLE traffic_store_metadata (
    key VARCHAR NOT NULL PRIMARY KEY,
    value VARCHAR NOT NULL
)
"""
_CREATE_TRAFFIC_EXPLICIT = """
CREATE TABLE traffic_events (
    id INTEGER NOT NULL PRIMARY KEY,
    captured_at VARCHAR NOT NULL,
    method VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    host VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    exchange_json VARCHAR NOT NULL
)
"""
_CREATE_TRAFFIC_IMPLICIT = _CREATE_TRAFFIC_EXPLICIT.replace(
    "id INTEGER NOT NULL PRIMARY KEY", "id INTEGER PRIMARY KEY"
)
_CREATE_HISTORY = """
CREATE TABLE run_history (
    id INTEGER NOT NULL PRIMARY KEY,
    generated_at VARCHAR NOT NULL,
    project VARCHAR NOT NULL,
    environment VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('passed', 'failed', 'blocked')),
    exit_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    total INTEGER NOT NULL CHECK (total >= 0),
    passed INTEGER NOT NULL CHECK (passed >= 0),
    failed INTEGER NOT NULL CHECK (failed >= 0)
)
"""


def _create_traffic_fixture(
    db_path: Path,
    *,
    metadata_version: str | None,
    implicit_id: bool = False,
    indexes: bool = True,
    event_id: int | None = 7,
    metadata_ddl: str | None = None,
    traffic_ddl: str | None = None,
) -> None:
    with sqlite3.connect(db_path) as connection:
        _create_traffic_metadata(connection, metadata_version, metadata_ddl)
        connection.execute(
            traffic_ddl or (_CREATE_TRAFFIC_IMPLICIT if implicit_id else _CREATE_TRAFFIC_EXPLICIT)
        )
        if indexes:
            _create_traffic_indexes(connection)
        _insert_traffic_event(connection, event_id)


def _create_traffic_metadata(
    connection: sqlite3.Connection, version: str | None, ddl: str | None
) -> None:
    if version is not None:
        connection.execute(ddl or _CREATE_METADATA)
        connection.execute(
            "INSERT INTO traffic_store_metadata(key, value) VALUES ('schema_version', ?)",
            (version,),
        )


def _create_traffic_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (captured_at)"
    )
    connection.execute("CREATE INDEX idx_traffic_events_host_path ON traffic_events (host, path)")


def _insert_traffic_event(connection: sqlite3.Connection, event_id: int | None) -> None:
    if event_id is not None:
        connection.execute(
            """
            INSERT INTO traffic_events(
                id, captured_at, method, url, host, path, status_code, duration_ms,
                exchange_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                "2026-05-30T12:00:00+00:00",
                "GET",
                "https://api.example.test/health",
                "api.example.test",
                "/health",
                200,
                11,
                '{"redacted":true}',
            ),
        )


_VALID_HISTORY_ROW = (
    1,
    "2026-05-30T12:00:00.000000Z",
    "project",
    "environment",
    "passed",
    0,
    1,
    1,
    1,
    0,
)


def _create_v2_fixture(tmp_path: Path) -> Path:
    store = TrafficStore.open_project(tmp_path)
    store._engine.dispose()
    return store.db_path


def _create_custom_v2_fixture(
    tmp_path: Path,
    *,
    traffic_ddl: str = _CREATE_TRAFFIC_EXPLICIT,
    history_ddl: str = _CREATE_HISTORY,
    traffic_indexes: tuple[str, ...] = (
        "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (captured_at)",
        "CREATE INDEX idx_traffic_events_host_path ON traffic_events (host, path)",
    ),
    history_indexes: tuple[str, ...] = (
        "CREATE INDEX idx_run_history_generated_at_id ON run_history (generated_at, id)",
        "CREATE INDEX idx_run_history_project_environment_generated_at_id "
        "ON run_history (project, environment, generated_at, id)",
    ),
) -> Path:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    with sqlite3.connect(state_path) as connection:
        connection.execute(_CREATE_METADATA)
        connection.execute(traffic_ddl)
        for statement in traffic_indexes:
            connection.execute(statement)
        connection.execute(" ".join(history_ddl.split()).replace("( ", "(").replace(" )", ")"))
        for statement in history_indexes:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO traffic_store_metadata(key, value) VALUES ('schema_version', '2')"
        )
    return state_path


def _insert_history_row(db_path: Path, row: tuple[object, ...]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("INSERT INTO run_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)


def _create_history_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX idx_run_history_generated_at_id ON run_history (generated_at, id)"
    )
    connection.execute(
        "CREATE INDEX idx_run_history_project_environment_generated_at_id "
        "ON run_history (project, environment, generated_at, id)"
    )


def _assert_invalid_history_row(tmp_path: Path, row: tuple[object, ...]) -> None:
    state_path = _create_v2_fixture(tmp_path)
    _insert_history_row(state_path, row)
    before = _schema_snapshot(state_path)

    real_connect = cast(Callable[..., sqlite3.Connection], sqlite3.connect)

    def connect_with_checks_ignored(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        connection.execute("PRAGMA ignore_check_constraints = ON")
        return connection

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect_with_checks_ignored)
        with pytest.raises(TrafficStoreError, match="history") as exc:
            TrafficStore.open_project(tmp_path)

    assert str(exc.value) == "traffic store history is invalid"
    assert _schema_snapshot(state_path) == before


def _schema_snapshot(db_path: Path) -> tuple[bytes, int, tuple[tuple[str, str, str | None], ...]]:
    digest = hashlib.sha256(db_path.read_bytes()).digest()
    mtime_ns = db_path.stat().st_mtime_ns
    with sqlite3.connect(db_path) as connection:
        objects = tuple(
            connection.execute(
                """
                SELECT type, name, sql FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name
                """
            ).fetchall()
        )
    return digest, mtime_ns, objects


def _user_objects(db_path: Path) -> tuple[tuple[str, str, str | None], ...]:
    with sqlite3.connect(db_path) as connection:
        return tuple(
            connection.execute(
                """
                SELECT type, name, sql FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name
                """
            ).fetchall()
        )


def test_store_uses_entroping_state_db_by_default(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)

    assert store.db_path == tmp_path / ".entroping" / "state.db"
    assert store.db_path.parent.is_dir()


def test_store_records_current_schema_version(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    engine = create_engine(f"sqlite:///{store.db_path}")

    with Session(engine) as session:
        rows = session.exec(select(TrafficStoreMetadataRow)).all()

    assert [(row.key, row.value) for row in rows] == [
        ("schema_version", str(TRAFFIC_STORE_SCHEMA_VERSION))
    ]


def test_store_wraps_schema_initialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_schema_version(engine: object) -> None:
        _ = engine
        raise sqlite3.DatabaseError("metadata unavailable")

    monkeypatch.setattr(traffic_store, "_ensure_schema_version", fail_schema_version)

    with pytest.raises(TrafficStoreError, match="could not initialize traffic state"):
        TrafficStore.open_project(tmp_path)


def test_store_rejects_future_schema_version(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    db_path = state_dir / "state.db"
    _create_traffic_fixture(
        db_path, metadata_version=str(TRAFFIC_STORE_SCHEMA_VERSION + 1), event_id=None
    )

    with pytest.raises(TrafficStoreError, match="newer than supported"):
        TrafficStore.open_project(tmp_path)


@pytest.mark.parametrize(
    ("schema_version", "message"),
    [
        ("not-an-integer", "schema version is invalid"),
        ("0", "older than supported"),
    ],
)
def test_store_rejects_invalid_or_unsupported_schema_versions(
    tmp_path: Path,
    schema_version: str,
    message: str,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    db_path = state_dir / "state.db"
    _create_traffic_fixture(db_path, metadata_version=schema_version, event_id=None)

    with pytest.raises(TrafficStoreError, match=message):
        TrafficStore.open_project(tmp_path)


@pytest.mark.parametrize(
    ("schema_version", "message"),
    [
        ("3", "newer than supported"),
        ("0", "older than supported"),
        ("not-an-integer", "schema version is invalid"),
    ],
)
def test_schema_version_diagnostic_precedes_supported_ddl_validation(
    tmp_path: Path,
    schema_version: str,
    message: str,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    metadata_ddl = "CREATE TABLE traffic_store_metadata (key VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (key))"  # noqa: E501
    _create_traffic_fixture(
        state_dir / "state.db",
        metadata_version=schema_version,
        event_id=None,
        metadata_ddl=metadata_ddl,
    )

    with pytest.raises(TrafficStoreError, match=message):
        TrafficStore.open_project(tmp_path)


def test_schema_classification_rejects_non_table_index_objects() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE events (id INTEGER)")
        connection.execute(
            "CREATE TRIGGER rogue_trigger AFTER INSERT ON events BEGIN SELECT 1; END"
        )

        with pytest.raises(TrafficStoreError, match="schema is invalid"):
            traffic_store._classify_schema(connection)


def test_metadata_v1_layout_rejects_v2_version(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    _create_traffic_fixture(state_dir / "state.db", metadata_version="2", event_id=None)

    with pytest.raises(TrafficStoreError, match="schema is invalid"):
        TrafficStore.open_project(tmp_path)


def test_v2_layout_rejects_v1_version(tmp_path: Path) -> None:
    state_path = _create_v2_fixture(tmp_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            "UPDATE traffic_store_metadata SET value = '1' WHERE key = 'schema_version'"
        )

    with pytest.raises(TrafficStoreError, match="schema is invalid"):
        TrafficStore.open_project(tmp_path)


def test_v2_validator_rejects_missing_traffic_table() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute(_CREATE_METADATA)
        connection.execute(
            "INSERT INTO traffic_store_metadata(key, value) VALUES ('schema_version', '2')"
        )

        with pytest.raises(TrafficStoreError, match="schema is invalid"):
            traffic_store._validate_v2_schema(connection)


def test_store_rejects_non_positive_retention_limit(tmp_path: Path) -> None:
    with pytest.raises(TrafficStoreError, match="max_events must be positive"):
        TrafficStore.open_project(tmp_path, max_events=0)


def test_store_refuses_unredacted_exchange(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)

    with pytest.raises(TrafficStoreError, match="refusing to persist unredacted traffic"):
        store.record_exchange(_exchange())


def test_store_refuses_redacted_exchange_with_secret_like_content(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    token = "sk-proj-" + ("a" * 24)
    unsafe = _exchange(secret=token).model_copy(update={"redacted": True})

    with pytest.raises(TrafficStoreError, match="unredacted secret-like traffic content") as exc:
        store.record_exchange(unsafe)

    assert token not in str(exc.value)
    assert store.list_exchanges() == ()


def test_store_persists_redacted_exchange_without_plaintext_secrets(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    redacted = redact_traffic_exchange(_exchange(secret="live-secret"))

    event_id = store.record_exchange(redacted)
    loaded = store.list_exchanges()

    assert (event_id, len(loaded), loaded[0].redacted, loaded[0].request.headers["Authorization"], "live-secret" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")) == (1, 1, True, "[REDACTED]", True)  # fmt: skip  # noqa: E501


def test_store_list_exchanges_rejects_non_positive_limit(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)

    with pytest.raises(TrafficStoreError, match="limit must be positive"):
        store.list_exchanges(limit=0)


def test_store_list_exchanges_applies_positive_limit(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    first = _exchange(secret="first-secret")
    second = _exchange(secret="second-secret").model_copy(
        update={"captured_at": datetime(2026, 5, 30, 12, 1, tzinfo=UTC)}
    )
    store.record_exchange(redact_traffic_exchange(first))
    store.record_exchange(redact_traffic_exchange(second))

    loaded = store.list_exchanges(limit=1)

    assert len(loaded) == 1
    assert loaded[0].captured_at.minute == 0


def test_readonly_project_exchange_listing_does_not_create_missing_state(
    tmp_path: Path,
) -> None:
    with pytest.raises(TrafficStoreError, match="traffic state not found"):
        list_project_exchanges_readonly(tmp_path)

    assert not (tmp_path / ".entroping").exists()


def test_readonly_project_exchange_listing_rejects_non_positive_limit(tmp_path: Path) -> None:
    with pytest.raises(TrafficStoreError, match="limit must be positive"):
        list_project_exchanges_readonly(tmp_path, limit=0)


def test_readonly_project_exchange_listing_preserves_existing_state_file(
    tmp_path: Path,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(_exchange(secret="readonly-secret")))
    state_path = tmp_path / ".entroping" / "state.db"
    before = state_path.stat().st_mtime_ns

    loaded = list_project_exchanges_readonly(tmp_path)
    after = state_path.stat().st_mtime_ns

    assert len(loaded) == 1
    assert loaded[0].request.headers["Authorization"] == "[REDACTED]"
    assert after == before


def test_readonly_project_exchange_listing_accepts_legacy_store_without_metadata(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    db_path = state_dir / "state.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE traffic_events (
                    id INTEGER PRIMARY KEY,
                    captured_at VARCHAR NOT NULL,
                    method VARCHAR NOT NULL,
                    url VARCHAR NOT NULL,
                    host VARCHAR NOT NULL,
                    path VARCHAR NOT NULL,
                    status_code INTEGER,
                    duration_ms INTEGER,
                    exchange_json VARCHAR NOT NULL
                )
                """
            )
        )

    assert list_project_exchanges_readonly(tmp_path) == ()


def test_readonly_project_exchange_listing_rejects_empty_schema(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    with sqlite3.connect(state_dir / "state.db") as connection:
        connection.execute("CREATE TABLE transient (id INTEGER)")
        connection.execute("DROP TABLE transient")

    with pytest.raises(TrafficStoreError, match="schema is invalid"):
        list_project_exchanges_readonly(tmp_path)


def test_readonly_project_exchange_listing_wraps_schema_version_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    TrafficStore.open_project(tmp_path)

    monkeypatch.setattr(
        traffic_store,
        "_classify_schema",
        lambda connection: (_ for _ in ()).throw(sqlite3.DatabaseError("schema read failed")),
    )

    with pytest.raises(TrafficStoreError, match="could not read traffic state"):
        list_project_exchanges_readonly(tmp_path)


def test_readonly_project_exchange_listing_applies_limit(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    for index in range(2):
        exchange = _exchange(secret=f"readonly-secret-{index}").model_copy(
            update={"captured_at": datetime(2026, 5, 30, 12, index, tzinfo=UTC)}
        )
        store.record_exchange(redact_traffic_exchange(exchange))

    loaded = list_project_exchanges_readonly(tmp_path, limit=1)

    assert len(loaded) == 1
    assert loaded[0].captured_at.minute == 0


def test_readonly_validation_and_select_share_the_same_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(_exchange(secret="readonly-original")))
    state_path = store.db_path
    real_classify = traffic_store._classify_schema

    def replace_after_validation(
        connection: sqlite3.Connection,
    ) -> traffic_store._SchemaState:
        state = real_classify(connection)
        state_path.unlink()
        with sqlite3.connect(state_path) as replacement:
            replacement.execute(_CREATE_TRAFFIC_EXPLICIT)
            replacement.execute("CREATE TABLE unknown_user_table (value VARCHAR)")
        return state

    monkeypatch.setattr(traffic_store, "_classify_schema", replace_after_validation)

    loaded = list_project_exchanges_readonly(tmp_path)

    assert len(loaded) == 1
    assert loaded[0].request.headers["Authorization"] == "[REDACTED]"


def test_store_persists_events_through_sqlmodel_mapping(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    redacted = redact_traffic_exchange(_exchange(secret="live-secret"))

    event_id = store.record_exchange(redacted)
    engine = create_engine(f"sqlite:///{store.db_path}")
    with Session(engine) as session:
        rows = session.exec(select(TrafficEventRow)).all()

    assert (len(rows), rows[0].id, rows[0].method, rows[0].host, rows[0].status_code, "live-secret" not in rows[0].exchange_json) == (1, event_id, "GET", "api.example.test", 200, True)  # fmt: skip  # noqa: E501


def test_store_retention_keeps_latest_redacted_events_with_sql_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path, max_events=2)

    def fail_row_delete(self: Session, instance: object) -> None:
        _ = self, instance
        raise AssertionError("retention should use SQL-level delete")

    monkeypatch.setattr(Session, "delete", fail_row_delete)

    for index in range(3):
        exchange = _exchange(secret=f"secret-{index}").model_copy(
            update={
                "captured_at": datetime(2026, 5, 30, 12, index, tzinfo=UTC),
            }
        )
        store.record_exchange(redact_traffic_exchange(exchange))

    loaded = store.list_exchanges()
    engine = create_engine(f"sqlite:///{store.db_path}")
    with Session(engine) as session:
        retained_rows = session.exec(
            select(TrafficEventRow).order_by(col(TrafficEventRow.id))
        ).all()

    assert (len(loaded), [item.captured_at.minute for item in loaded], [row.id for row in retained_rows], "secret-" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")) == (2, [1, 2], [2, 3], True)  # fmt: skip  # noqa: E501


def test_store_wraps_missing_inserted_row_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)

    class EmptyResult:
        def all(self) -> list[TrafficEventRow]:
            return []

    class MissingIdSession:
        def __init__(self, engine: object) -> None:
            _ = engine

        def __enter__(self) -> "MissingIdSession":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            _ = (exc_type, exc_value, traceback)

        def add(self, row: TrafficEventRow) -> None:
            row.id = None

        def commit(self) -> None:
            return None

        def refresh(self, row: TrafficEventRow) -> None:
            row.id = None

        def exec(self, statement: object) -> EmptyResult:
            _ = statement
            return EmptyResult()

        def delete(self, row: TrafficEventRow) -> None:
            _ = row

    monkeypatch.setattr(traffic_store, "Session", MissingIdSession)

    with pytest.raises(TrafficStoreError, match="did not return an inserted traffic event id"):
        store.record_exchange(redact_traffic_exchange(_exchange()))


def test_store_refuses_symlinked_state_directory(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside-state"
    outside_dir.mkdir()
    (tmp_path / ".entroping").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(TrafficStoreError, match="symlinked traffic state path component"):
        TrafficStore.open_project(tmp_path)

    assert not (outside_dir / "state.db").exists()


def test_fresh_open_creates_empty_schema_v2_and_reopen_is_idempotent(
    tmp_path: Path,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    state_path = store.db_path

    with sqlite3.connect(state_path) as connection:
        objects = tuple(
            connection.execute(
                """
                SELECT type, name FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name
                """
            ).fetchall()
        )
        metadata = tuple(
            connection.execute("SELECT key, value FROM traffic_store_metadata").fetchall()
        )
        history_rows = tuple(connection.execute("SELECT * FROM run_history").fetchall())
        history_indexes = tuple(connection.execute("PRAGMA index_list('run_history')").fetchall())

    assert (objects, metadata, history_rows, {row[1] for row in history_indexes}) == (
        (
            ("index", "idx_run_history_generated_at_id"),
            ("index", "idx_run_history_project_environment_generated_at_id"),
            ("index", "idx_traffic_events_captured_at"),
            ("index", "idx_traffic_events_host_path"),
            ("table", "run_history"),
            ("table", "traffic_events"),
            ("table", "traffic_store_metadata"),
        ),
        (("schema_version", "2"),),
        (),
        {
            "idx_run_history_generated_at_id",
            "idx_run_history_project_environment_generated_at_id",
        },
    )

    before = _schema_snapshot(state_path)
    TrafficStore.open_project(tmp_path)
    assert _schema_snapshot(state_path) == before


def test_metadata_v1_migration_preserves_rows_indexes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    with sqlite3.connect(state_path) as connection:
        connection.execute("CREATE INDEX extra_traffic_index ON traffic_events (method)")

    before_rows = ((7, "GET", "api.example.test", "/health"),)
    TrafficStore.open_project(tmp_path)

    with sqlite3.connect(state_path) as connection:
        metadata = tuple(
            connection.execute("SELECT key, value FROM traffic_store_metadata").fetchall()
        )
        rows = tuple(
            connection.execute("SELECT id, method, host, path FROM traffic_events").fetchall()
        )
        history_rows = tuple(connection.execute("SELECT * FROM run_history").fetchall())
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('traffic_events')").fetchall()
        }

    assert (metadata, rows, history_rows, {"idx_traffic_events_captured_at", "idx_traffic_events_host_path"} <= indexes, "extra_traffic_index" in indexes) == ((("schema_version", "2"),), before_rows, (), True, True)  # fmt: skip  # noqa: E501

    before = _schema_snapshot(state_path)
    TrafficStore.open_project(tmp_path)
    assert _schema_snapshot(state_path) == before


def test_legacy_implicit_primary_key_migrates_without_rewriting_rows(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(
        state_path,
        metadata_version=None,
        implicit_id=True,
        indexes=False,
    )

    with sqlite3.connect(state_path) as connection:
        before_traffic_info = tuple(connection.execute("PRAGMA table_info('traffic_events')"))

    TrafficStore.open_project(tmp_path)

    with sqlite3.connect(state_path) as connection:
        after_traffic_info = tuple(connection.execute("PRAGMA table_info('traffic_events')"))
        metadata = tuple(
            connection.execute("SELECT key, value FROM traffic_store_metadata").fetchall()
        )
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('traffic_events')").fetchall()
        }

    assert (before_traffic_info[0][2:6], after_traffic_info, metadata, {"idx_traffic_events_captured_at", "idx_traffic_events_host_path"} <= indexes) == (("INTEGER", 0, None, 1), before_traffic_info, (("schema_version", "2"),), True)  # fmt: skip  # noqa: E501

    before = _schema_snapshot(state_path)
    TrafficStore.open_project(tmp_path)
    assert _schema_snapshot(state_path) == before


@pytest.mark.parametrize("metadata_version", ["1", "2"])
def test_readonly_listing_accepts_legacy_and_v2_without_mutation(
    tmp_path: Path,
    metadata_version: str,
) -> None:
    state_dir, state_path = _create_readonly_fixture(tmp_path, metadata_version)

    before = _schema_snapshot(state_path)
    before_entries = tuple(sorted(item.name for item in state_dir.iterdir()))
    assert (list_project_exchanges_readonly(tmp_path), _schema_snapshot(state_path), tuple(sorted(item.name for item in state_dir.iterdir())), not (state_dir / "state.db-wal").exists(), not (state_dir / "state.db-shm").exists()) == ((), before, before_entries, True, True)  # fmt: skip  # noqa: E501


def _create_readonly_fixture(tmp_path: Path, metadata_version: str) -> tuple[Path, Path]:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    if metadata_version == "1":
        _create_traffic_fixture(state_path, metadata_version="1", event_id=None)
    else:
        TrafficStore.open_project(tmp_path)
    return state_dir, state_path


def test_readonly_listing_accepts_no_metadata_legacy_without_adding_v2_objects(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version=None, implicit_id=True, event_id=None)
    before = _schema_snapshot(state_path)

    assert list_project_exchanges_readonly(tmp_path) == ()
    assert _schema_snapshot(state_path) == before
    assert _user_objects(state_path) == before[2]


def test_missing_required_traffic_index_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1", event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute("DROP INDEX idx_traffic_events_host_path")
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_required_traffic_index_on_wrong_table_is_rejected(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1", event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute("DROP INDEX idx_traffic_events_host_path")
        connection.execute("CREATE TABLE other_events (path VARCHAR NOT NULL)")
        connection.execute("CREATE INDEX idx_traffic_events_host_path ON other_events (path)")
        with pytest.raises(TrafficStoreError, match="schema is invalid"):
            traffic_store._validate_indexes(
                connection, "traffic_events", traffic_store._TRAFFIC_INDEXES, required=True
            )


def test_unknown_user_table_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1", event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute("CREATE TABLE unknown_user_table (value VARCHAR)")
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


@pytest.mark.parametrize("version", ["", "0", "not-an-integer", "3"])
def test_invalid_metadata_versions_fail_closed_without_mutation(
    tmp_path: Path,
    version: str,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version=version, event_id=None)
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema version"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_malformed_history_constraint_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="2", event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute(_CREATE_HISTORY.replace("failed INTEGER NOT NULL", "failed INTEGER"))
        _create_history_indexes(connection)
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_wrong_required_history_index_order_is_rejected_before_mutation(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="2", event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute(_CREATE_HISTORY)
        _create_history_indexes(connection)
        connection.execute("DROP INDEX idx_run_history_generated_at_id")
        connection.execute(
            "CREATE INDEX idx_run_history_generated_at_id ON run_history (id, generated_at)"
        )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_empty_metadata_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version=None, event_id=None)
    with sqlite3.connect(state_path) as connection:
        connection.execute(_CREATE_METADATA)
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_unknown_traffic_column_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    traffic_ddl = _CREATE_TRAFFIC_EXPLICIT.replace(
        "exchange_json VARCHAR NOT NULL", "exchange_json VARCHAR NOT NULL, extra VARCHAR"
    )
    _create_traffic_fixture(
        state_path,
        metadata_version="1",
        event_id=None,
        traffic_ddl=traffic_ddl,
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_partial_history_table_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="2", event_id=None)
    partial_history = _CREATE_HISTORY.replace(
        ",\n    failed INTEGER NOT NULL CHECK (failed >= 0)", ""
    )
    with sqlite3.connect(state_path) as connection:
        connection.execute(partial_history)
        _create_history_indexes(connection)
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_extra_history_column_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="2", event_id=None)
    extra_history = _CREATE_HISTORY.replace(
        "failed INTEGER NOT NULL", "failed INTEGER NOT NULL, extra VARCHAR NOT NULL"
    )
    with sqlite3.connect(state_path) as connection:
        connection.execute(extra_history)
        _create_history_indexes(connection)
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_malformed_traffic_constraint_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    traffic_ddl = _CREATE_TRAFFIC_EXPLICIT.replace(
        "exchange_json VARCHAR NOT NULL",
        "exchange_json VARCHAR NOT NULL CHECK (length(exchange_json) > 0)",
    )
    _create_traffic_fixture(
        state_path,
        metadata_version="1",
        event_id=None,
        traffic_ddl=traffic_ddl,
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


@pytest.mark.parametrize(
    "metadata_constraint",
    (
        "CHECK(value IN ('1','2'))",
        "UNIQUE(value)",
        "CHECK(\n        \"value\" IN ('1', '2')\n    )",
    ),
)
def test_metadata_constraint_drift_is_rejected_before_mutation(
    tmp_path: Path, metadata_constraint: str
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    metadata_ddl = f"""
    CREATE TABLE traffic_store_metadata (
        key VARCHAR NOT NULL PRIMARY KEY,
        value VARCHAR NOT NULL,
        {metadata_constraint}
    )
    """
    _create_traffic_fixture(
        state_path,
        metadata_version="1",
        event_id=None,
        metadata_ddl=metadata_ddl,
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


@pytest.mark.parametrize("status_literal", ("'PASSED'", "'pAsSeD'"))
def test_history_literal_case_drift_is_rejected_before_mutation(
    tmp_path: Path, status_literal: str
) -> None:
    state_path = _create_custom_v2_fixture(
        tmp_path,
        history_ddl=_CREATE_HISTORY.replace("'passed'", status_literal, 1),
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_traffic_primary_key_desc_drift_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_path = _create_custom_v2_fixture(
        tmp_path,
        traffic_ddl=_CREATE_TRAFFIC_EXPLICIT.replace(
            "id INTEGER NOT NULL PRIMARY KEY", "id INTEGER NOT NULL PRIMARY KEY DESC"
        ),
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


@pytest.mark.parametrize(
    "index_sql",
    (
        "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (captured_at DESC)",
        "CREATE INDEX idx_traffic_events_captured_at ON traffic_events "
        "(captured_at COLLATE NOCASE)",
        "CREATE INDEX idx_traffic_events_captured_at ON traffic_events (substr(captured_at, 1))",
    ),
)
def test_required_index_semantic_drift_is_rejected_before_mutation(
    tmp_path: Path, index_sql: str
) -> None:
    state_path = _create_custom_v2_fixture(
        tmp_path,
        traffic_indexes=(
            index_sql,
            "CREATE INDEX idx_traffic_events_host_path ON traffic_events (host, path)",
        ),
    )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_implicit_unique_autoindex_is_rejected_by_index_validator(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            "CREATE TABLE target (key VARCHAR NOT NULL, value VARCHAR NOT NULL, UNIQUE(value))"
        )
        autoindexes = connection.execute("PRAGMA index_list('target')").fetchall()
        assert any(row[3] == "u" and row[2] == 1 for row in autoindexes)
        before = tuple(connection.execute("SELECT sql FROM sqlite_master ORDER BY name"))

        with pytest.raises(TrafficStoreError, match="schema"):
            traffic_store._validate_indexes(connection, "target", (), required=False)

        assert tuple(connection.execute("SELECT sql FROM sqlite_master ORDER BY name")) == before


def test_runtime_engine_uses_disk_file_pool(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    normal_disk_engine = create_engine(f"sqlite:///{store.db_path}")
    try:
        assert type(store._engine.pool) is type(normal_disk_engine.pool)
        assert type(store._engine.pool).__name__ != "SingletonThreadPool"
    finally:
        normal_disk_engine.dispose()
        store._engine.dispose()


def test_runtime_creator_closes_connection_on_configuration_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _create_v2_fixture(tmp_path)
    real_open = traffic_store._open_sqlite_connection
    opened: list[sqlite3.Connection] = []

    def track_open(
        db_path: Path, *, readonly: bool, require_existing: bool = False
    ) -> sqlite3.Connection:
        connection = real_open(db_path, readonly=readonly, require_existing=require_existing)
        opened.append(connection)
        return connection

    def fail_configuration(connection: sqlite3.Connection, *, readonly: bool) -> None:
        _ = connection, readonly
        raise TrafficStoreError("injected runtime configuration failure")

    monkeypatch.setattr(traffic_store, "_open_sqlite_connection", track_open)
    monkeypatch.setattr(traffic_store, "_configure_sqlite_connection", fail_configuration)

    with pytest.raises(TrafficStoreError, match="injected runtime configuration failure"):
        traffic_store._create_runtime_connection(state_path, readonly=False)

    assert opened
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_runtime_pool_connection_can_be_reused_across_threads(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    first_errors: list[Exception] = []
    second_errors: list[Exception] = []
    first_returned = Event()
    release_first = Event()

    def list_in_thread(errors: list[Exception]) -> None:
        try:
            assert store.list_exchanges() == ()
        except Exception as exc:
            errors.append(exc)

    def list_first_thread() -> None:
        list_in_thread(first_errors)
        first_returned.set()
        release_first.wait(timeout=5)

    first = Thread(target=list_first_thread)
    first.start()
    assert first_returned.wait(timeout=5)
    assert first_errors == []

    second = Thread(target=list_in_thread, args=(second_errors,))
    second.start()
    second.join()
    release_first.set()
    first.join()
    assert second_errors == []


def test_runtime_writer_rejects_late_sidecar_before_underlying_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store._engine.dispose()
    sidecar = store.db_path.with_name("state.db-wal")
    sidecar.write_bytes(b"late-sidecar")
    calls = 0

    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        raise AssertionError("late sidecar must be rejected before sqlite connect")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    with pytest.raises(TrafficStoreError, match="sidecar"):
        store.list_exchanges()

    assert calls == 0
    assert sidecar.read_bytes() == b"late-sidecar"


def test_runtime_writer_rejects_late_header_before_underlying_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store._engine.dispose()
    corrupted = bytearray(store.db_path.read_bytes())
    corrupted[18:20] = b"\x02\x02"
    store.db_path.write_bytes(corrupted)
    calls = 0

    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        raise AssertionError("late header must be rejected before sqlite connect")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    with pytest.raises(TrafficStoreError, match="header"):
        store.list_exchanges()

    assert calls == 0
    assert store.db_path.read_bytes() == bytes(corrupted)


def test_runtime_writer_does_not_recreate_deleted_state_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store._engine.dispose()
    store.db_path.unlink()
    calls = 0

    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        raise AssertionError("deleted state must not be recreated")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    with pytest.raises(TrafficStoreError, match="not found"):
        store.list_exchanges()

    assert calls == 0
    assert not store.db_path.exists()


def test_readonly_second_open_rechecks_late_sidecar_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    state_path = store.db_path
    sidecar = state_path.with_name("state.db-wal")
    real_open = traffic_store._open_sqlite_connection
    real_connect = cast(Callable[..., sqlite3.Connection], sqlite3.connect)
    connect_calls = 0
    injected = False

    def track_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal connect_calls
        connect_calls += 1
        return real_connect(*args, **kwargs)

    def inject_sidecar(
        db_path: Path,
        *,
        readonly: bool,
        require_existing: bool = False,
    ) -> sqlite3.Connection:
        nonlocal injected
        connection = real_open(db_path, readonly=readonly, require_existing=require_existing)
        if readonly and not injected:
            injected = True
            sidecar.write_bytes(b"late-sidecar")
        return connection

    monkeypatch.setattr(sqlite3, "connect", track_connect)
    monkeypatch.setattr(traffic_store, "_open_sqlite_connection", inject_sidecar)
    with pytest.raises(TrafficStoreError, match="sidecar"):
        list_project_exchanges_readonly(tmp_path)

    assert injected
    assert connect_calls == 1
    assert sidecar.read_bytes() == b"late-sidecar"


def test_preflight_uses_bounded_prefix_read_not_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store._engine.dispose()

    def fail_read_bytes(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("preflight must not load the entire database")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    TrafficStore.open_project(tmp_path)


def test_preflight_permission_errors_are_bounded_for_write_and_readonly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    state_path = store.db_path
    real_open = Path.open

    def fail_state_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == state_path:
            raise PermissionError("permission denied /private/state-secret")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_state_open)
    for operation in (
        lambda: TrafficStore.open_project(tmp_path),
        lambda: list_project_exchanges_readonly(tmp_path),
    ):
        with pytest.raises(TrafficStoreError, match="preflight") as exc:
            operation()
        assert "/private/state-secret" not in str(exc.value)


def test_preflight_rejects_state_directory(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    state_path.mkdir()

    with pytest.raises(TrafficStoreError, match="state file is invalid"):
        traffic_store._preflight_database_path(state_path, readonly=False)


def test_sqlite_configuration_rejects_non_delete_journal_mode() -> None:
    with (
        sqlite3.connect(":memory:") as connection,
        pytest.raises(TrafficStoreError, match="journal mode is unsupported"),
    ):
        traffic_store._configure_sqlite_connection(connection, readonly=False)


def test_existing_valid_history_row_is_accepted_without_mutation(tmp_path: Path) -> None:
    state_path = _create_v2_fixture(tmp_path)
    _insert_history_row(state_path, _VALID_HISTORY_ROW)
    before = _schema_snapshot(state_path)

    TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_oversized_history_identifier_is_rejected_before_row_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _create_v2_fixture(tmp_path)
    _insert_history_row(
        state_path,
        (*_VALID_HISTORY_ROW[:2], "x" * 1_000_000, *_VALID_HISTORY_ROW[3:]),
    )

    def fail_row_validation(row: tuple[object, ...]) -> bool:
        _ = row
        raise AssertionError("oversized history text reached Python validation")

    monkeypatch.setattr(traffic_store, "_valid_history_row", fail_row_validation)
    with pytest.raises(TrafficStoreError, match="history"):
        TrafficStore.open_project(tmp_path)


@pytest.mark.parametrize(
    "timestamp",
    ("2026-05-30T12:00:00Z", "2026-05- 3T12:00:00.000000Z"),
)
def test_existing_history_timestamp_shape_is_validated(tmp_path: Path, timestamp: str) -> None:
    row = (*_VALID_HISTORY_ROW[:1], timestamp, *_VALID_HISTORY_ROW[2:])
    _assert_invalid_history_row(tmp_path, row)


def test_history_scalar_validators_reject_malformed_values() -> None:
    assert not traffic_store._valid_history_timestamp("not-a-timestamp")
    assert not traffic_store._valid_history_timestamp("2026-02-30T12:00:00.000000Z")
    assert not traffic_store._valid_history_identifier(None)
    assert not traffic_store._valid_history_identifier("\ud800")


def test_existing_history_identifiers_require_nfc(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:2], "e\u0301", *_VALID_HISTORY_ROW[3:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_identifiers_have_bounded_utf8_size(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:2], "x" * 257, *_VALID_HISTORY_ROW[3:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_identifiers_reject_controls(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:3], "prod\n", *_VALID_HISTORY_ROW[4:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_identifiers_reject_secret_like_tokens(tmp_path: Path) -> None:
    row = (
        *_VALID_HISTORY_ROW[:2],
        "sk-proj-aaaaaaaaaaaaaaaaaaaaaaaa",
        *_VALID_HISTORY_ROW[3:],
    )
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_status_is_allowlisted(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:4], "running", *_VALID_HISTORY_ROW[5:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_integer_columns_reject_text(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:5], "zero", *_VALID_HISTORY_ROW[6:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_exit_code_range_is_bounded(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:5], float(2**63), *_VALID_HISTORY_ROW[6:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_duration_is_nonnegative(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:6], -1, *_VALID_HISTORY_ROW[7:])
    _assert_invalid_history_row(tmp_path, row)


def test_existing_history_counters_are_nonnegative(tmp_path: Path) -> None:
    row = (*_VALID_HISTORY_ROW[:7], -1, *_VALID_HISTORY_ROW[8:])
    _assert_invalid_history_row(tmp_path, row)


def test_harmless_extra_history_index_is_preserved(tmp_path: Path) -> None:
    state_path = _create_v2_fixture(tmp_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute("CREATE INDEX extra_history_index ON run_history (project)")

    TrafficStore.open_project(tmp_path)

    with sqlite3.connect(state_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'extra_history_index'"
        ).fetchone() == ("extra_history_index",)


def test_unique_extra_history_index_is_rejected(tmp_path: Path) -> None:
    state_path = _create_v2_fixture(tmp_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute("CREATE UNIQUE INDEX extra_unique_history ON run_history (project)")
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_partial_extra_history_index_is_rejected(tmp_path: Path) -> None:
    state_path = _create_v2_fixture(tmp_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            "CREATE INDEX extra_partial_history ON run_history (project) WHERE status = 'passed'"
        )
    before = _schema_snapshot(state_path)

    with pytest.raises(TrafficStoreError, match="schema"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_private_migration_guards_and_quick_check_failure() -> None:
    with (
        sqlite3.connect(":memory:") as connection,
        pytest.raises(TrafficStoreError, match="schema is invalid"),
    ):
        traffic_store._apply_migration(connection, traffic_store._SchemaState.V2)

    class BrokenQuickCheck:
        def execute(self, statement: str) -> "BrokenQuickCheck":
            assert statement == "PRAGMA quick_check(1)"
            return self

        def fetchone(self) -> tuple[str]:
            return ("not ok",)

    with pytest.raises(TrafficStoreError, match="integrity check failed"):
        traffic_store._migration_quick_check(cast(sqlite3.Connection, BrokenQuickCheck()))


def test_migration_outcome_reports_busy_and_uncertain_states(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1", event_id=None)

    with pytest.raises(TrafficStoreError, match="traffic state is busy"):
        traffic_store._migration_outcome(
            state_path,
            sqlite3.connect(":memory:"),
            "begin",
            sqlite3.OperationalError("busy"),
        )

    missing_path = state_dir / "missing.db"
    assert traffic_store._classify_after_failed_commit(missing_path) is None
    with pytest.raises(TrafficStoreError, match="outcome is uncertain"):
        traffic_store._migration_outcome(
            missing_path,
            sqlite3.connect(":memory:"),
            "commit",
            sqlite3.OperationalError("commit uncertain"),
        )


def test_final_quick_check_failure_rolls_back_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    before = _schema_snapshot(state_path)
    real_quick_check = getattr(traffic_store, "_migration_quick_check", None)
    calls = 0

    def fail_final_quick_check(connection: sqlite3.Connection) -> bool:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise TrafficStoreError("injected final quick check failure")
        assert real_quick_check is not None
        return cast(bool, real_quick_check(connection))

    monkeypatch.setattr(
        traffic_store,
        "_migration_quick_check",
        fail_final_quick_check,
        raising=False,
    )
    with pytest.raises(TrafficStoreError, match="migration"):
        TrafficStore.open_project(tmp_path)

    assert calls >= 3
    assert _schema_snapshot(state_path) == before


def test_wal_header_and_sidecars_are_rejected_before_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    state_path = store.db_path
    original = state_path.read_bytes()
    wal_path = state_path.with_name("state.db-wal")
    shm_path = state_path.with_name("state.db-shm")
    wal_path.write_bytes(b"wal-sidecar")
    shm_path.write_bytes(b"shm-sidecar")
    opened = False

    def fail_open(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal opened
        opened = True
        raise AssertionError("pre-connect rejection must avoid sqlite connect")

    monkeypatch.setattr(traffic_store, "_open_sqlite_connection", fail_open, raising=False)
    _assert_both_openers_reject(tmp_path, "sidecar")

    assert (not opened, state_path.read_bytes(), wal_path.read_bytes(), shm_path.read_bytes()) == (
        True,
        original,
        b"wal-sidecar",
        b"shm-sidecar",
    )

    wal_path.unlink()
    shm_path.unlink()
    corrupted = bytearray(original)
    corrupted[18:20] = b"\x02\x02"
    state_path.write_bytes(corrupted)
    _assert_both_openers_reject(tmp_path, "header")
    assert state_path.read_bytes() == bytes(corrupted)


def _assert_both_openers_reject(tmp_path: Path, match: str) -> None:
    with pytest.raises(TrafficStoreError, match=match):
        TrafficStore.open_project(tmp_path)
    with pytest.raises(TrafficStoreError, match=match):
        list_project_exchanges_readonly(tmp_path)


def test_migration_ddl_failure_rolls_back_to_original_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    before = _schema_snapshot(state_path)
    real_execute = traffic_store._migration_execute
    calls = 0

    def fail_after_first_ddl(
        connection: sqlite3.Connection,
        statement: str,
        parameters: tuple[str, ...] = (),
    ) -> sqlite3.Cursor:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("injected DDL failure")
        return real_execute(connection, statement, parameters)

    monkeypatch.setattr(traffic_store, "_migration_execute", fail_after_first_ddl, raising=False)
    with pytest.raises(TrafficStoreError, match="migration"):
        TrafficStore.open_project(tmp_path)

    assert calls >= 2
    assert _schema_snapshot(state_path) == before


def test_migration_state_after_begin_rolls_back_valid_v2_transaction(
    tmp_path: Path,
) -> None:
    state_path = _create_v2_fixture(tmp_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute("BEGIN")
        assert traffic_store._migration_state_after_begin(connection) is None
        assert not connection.in_transaction


def test_schema_ensure_returns_when_locked_state_is_already_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1", event_id=None)
    before = _schema_snapshot(state_path)

    monkeypatch.setattr(traffic_store, "_migration_state_after_begin", lambda connection: None)

    def fail_apply(connection: sqlite3.Connection, state: traffic_store._SchemaState) -> None:
        _ = connection, state
        raise AssertionError("migration must not run after locked state is complete")

    monkeypatch.setattr(traffic_store, "_apply_migration", fail_apply)
    traffic_store._ensure_schema_version(state_path)

    assert _schema_snapshot(state_path) == before


def test_migration_validation_failure_rolls_back_to_original_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    before = _schema_snapshot(state_path)

    def fail_validation(connection: sqlite3.Connection) -> None:
        _ = connection
        raise TrafficStoreError("injected validation failure")

    monkeypatch.setattr(traffic_store, "_validate_v2_schema", fail_validation, raising=False)
    with pytest.raises(TrafficStoreError, match="migration"):
        TrafficStore.open_project(tmp_path)

    assert _schema_snapshot(state_path) == before


def test_commit_then_raise_is_classified_as_committed_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    real_commit = traffic_store._migration_commit
    calls = 0

    def commit_then_raise(connection: sqlite3.Connection) -> None:
        nonlocal calls
        calls += 1
        real_commit(connection)
        raise sqlite3.OperationalError("commit outcome uncertain")

    monkeypatch.setattr(traffic_store, "_migration_commit", commit_then_raise, raising=False)
    TrafficStore.open_project(tmp_path)
    assert calls == 1

    with sqlite3.connect(state_path) as connection:
        assert connection.execute(
            "SELECT value FROM traffic_store_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("2",)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'run_history'"
        ).fetchone() == ("run_history",)


def test_precommit_failure_is_reported_without_retry_or_partial_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    _create_traffic_fixture(state_path, metadata_version="1")
    before = _schema_snapshot(state_path)
    calls = 0

    def fail_commit(connection: sqlite3.Connection) -> None:
        nonlocal calls
        _ = connection
        calls += 1
        raise sqlite3.OperationalError("commit failed")

    monkeypatch.setattr(traffic_store, "_migration_commit", fail_commit, raising=False)
    with pytest.raises(TrafficStoreError, match="commit"):
        TrafficStore.open_project(tmp_path)

    assert calls == 1
    assert _schema_snapshot(state_path) == before


def test_concurrent_openers_leave_one_complete_v2_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    state_path = state_dir / "state.db"
    with sqlite3.connect(state_path) as connection:
        connection.execute("PRAGMA user_version = 0")
    open_barrier = Barrier(2)
    inspect_barrier = Barrier(2)
    inspect_lock = Lock()
    inspect_calls = 0
    real_open = traffic_store._open_sqlite_connection
    real_classify = traffic_store._classify_schema

    def coordinate_open(
        db_path: Path,
        *,
        readonly: bool,
    ) -> sqlite3.Connection:
        connection = real_open(db_path, readonly=readonly)
        if not readonly:
            open_barrier.wait(timeout=5)
        return connection

    def coordinate_inspect(connection: sqlite3.Connection) -> traffic_store._SchemaState:
        nonlocal inspect_calls
        with inspect_lock:
            initial_inspect = inspect_calls < 2
            inspect_calls += 1
        if initial_inspect:
            inspect_barrier.wait(timeout=5)
        return real_classify(connection)

    monkeypatch.setattr(traffic_store, "_open_sqlite_connection", coordinate_open)
    monkeypatch.setattr(traffic_store, "_classify_schema", coordinate_inspect)

    def open_store() -> str:
        try:
            TrafficStore.open_project(tmp_path)
        except TrafficStoreError as exc:
            return str(exc)
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: open_store(), range(2)))

    assert set(results) <= {
        "ok",
        "traffic state is busy",
        "traffic state migration failed",
        "traffic state migration commit failed",
        "traffic state migration outcome is uncertain",
    }
    with sqlite3.connect(tmp_path / ".entroping" / "state.db") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {"traffic_store_metadata", "traffic_events", "run_history"}
        assert connection.execute(
            "SELECT value FROM traffic_store_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("2",)
