"""Tests for local SQLite traffic state."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

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
        raise SQLAlchemyError("metadata unavailable")

    monkeypatch.setattr(traffic_store, "_ensure_schema_version", fail_schema_version)

    with pytest.raises(TrafficStoreError, match="could not initialize traffic state"):
        TrafficStore.open_project(tmp_path)


def test_store_rejects_future_schema_version(tmp_path: Path) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    db_path = state_dir / "state.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            TrafficStoreMetadataRow(
                key="schema_version",
                value=str(TRAFFIC_STORE_SCHEMA_VERSION + 1),
            )
        )
        session.commit()

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
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(TrafficStoreMetadataRow(key="schema_version", value=schema_version))
        session.commit()

    with pytest.raises(TrafficStoreError, match=message):
        TrafficStore.open_project(tmp_path)


def test_store_rejects_non_positive_retention_limit(tmp_path: Path) -> None:
    with pytest.raises(TrafficStoreError, match="max_events must be positive"):
        TrafficStore.open_project(tmp_path, max_events=0)


def test_store_refuses_unredacted_exchange(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)

    with pytest.raises(TrafficStoreError, match="refusing to persist unredacted traffic"):
        store.record_exchange(_exchange())


def test_store_persists_redacted_exchange_without_plaintext_secrets(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    redacted = redact_traffic_exchange(_exchange(secret="live-secret"))

    event_id = store.record_exchange(redacted)
    loaded = store.list_exchanges()

    assert event_id == 1
    assert len(loaded) == 1
    assert loaded[0].redacted is True
    assert loaded[0].request.headers["Authorization"] == "[REDACTED]"
    assert "live-secret" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


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


def test_readonly_project_exchange_listing_wraps_schema_version_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "state.db").write_text("placeholder\n", encoding="utf-8")

    class FailingSchemaSession:
        def __init__(self, engine: object) -> None:
            _ = engine

        def __enter__(self) -> "FailingSchemaSession":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            _ = (exc_type, exc_value, traceback)

        def exec(self, statement: object) -> object:
            _ = statement
            raise SQLAlchemyError("schema read failed")

    monkeypatch.setattr(traffic_store, "Session", FailingSchemaSession)

    with pytest.raises(TrafficStoreError, match="could not read traffic store schema version"):
        list_project_exchanges_readonly(tmp_path)


def test_readonly_project_exchange_listing_wraps_sqlalchemy_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "state.db").write_text("placeholder\n", encoding="utf-8")

    class FailingReadSession:
        def __init__(self, engine: object) -> None:
            _ = engine

        def __enter__(self) -> "FailingReadSession":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            _ = (exc_type, exc_value, traceback)

        def exec(self, statement: object) -> object:
            _ = statement
            raise SQLAlchemyError("read failed")

    monkeypatch.setattr(traffic_store, "_validate_existing_schema_version", lambda engine: None)
    monkeypatch.setattr(traffic_store, "Session", FailingReadSession)

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


def test_store_persists_events_through_sqlmodel_mapping(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    redacted = redact_traffic_exchange(_exchange(secret="live-secret"))

    event_id = store.record_exchange(redacted)
    engine = create_engine(f"sqlite:///{store.db_path}")
    with Session(engine) as session:
        rows = session.exec(select(TrafficEventRow)).all()

    assert len(rows) == 1
    assert rows[0].id == event_id
    assert rows[0].method == "GET"
    assert rows[0].host == "api.example.test"
    assert rows[0].status_code == 200
    assert "live-secret" not in rows[0].exchange_json


def test_store_retention_keeps_latest_redacted_events(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path, max_events=2)

    for index in range(3):
        exchange = _exchange(secret=f"secret-{index}").model_copy(
            update={
                "captured_at": datetime(2026, 5, 30, 12, index, tzinfo=UTC),
            }
        )
        store.record_exchange(redact_traffic_exchange(exchange))

    loaded = store.list_exchanges()

    assert len(loaded) == 2
    assert [item.captured_at.minute for item in loaded] == [1, 2]
    assert "secret-" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


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
