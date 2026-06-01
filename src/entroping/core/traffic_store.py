"""SQLite persistence for redacted Eye traffic state."""

from pathlib import Path
from urllib.parse import quote

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, Index, Session, SQLModel, col, create_engine, select

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.traffic import TrafficExchange

TRAFFIC_STORE_SCHEMA_VERSION = 1
_SCHEMA_VERSION_KEY = "schema_version"


class TrafficStoreError(ValueError):
    """Raised when traffic state cannot be persisted safely."""


class TrafficStoreMetadataRow(SQLModel, table=True):
    """SQLModel row for traffic-store metadata."""

    __tablename__ = "traffic_store_metadata"

    key: str = Field(primary_key=True)
    value: str


class TrafficEventRow(SQLModel, table=True):
    """SQLModel row for one redacted traffic exchange."""

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
        self._engine = create_engine(f"sqlite:///{self.db_path}")
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
            event_id = row.id
            if event_id is None:
                msg = "SQLite did not return an inserted traffic event id"
                raise TrafficStoreError(msg)
            self._enforce_retention(session)
            session.commit()
            return event_id

    def list_exchanges(self, *, limit: int | None = None) -> tuple[TrafficExchange, ...]:
        """Return persisted redacted exchanges in insertion order."""

        if limit is not None and limit <= 0:
            msg = "limit must be positive"
            raise TrafficStoreError(msg)

        statement = select(TrafficEventRow).order_by(col(TrafficEventRow.id))
        if limit is not None:
            statement = statement.limit(limit)

        with Session(self._engine) as session:
            rows = session.exec(statement).all()

        return tuple(TrafficExchange.model_validate_json(row.exchange_json) for row in rows)

    def _initialize(self) -> None:
        try:
            SQLModel.metadata.create_all(self._engine)
            _ensure_schema_version(self._engine)
        except TrafficStoreError:
            raise
        except SQLAlchemyError as exc:
            msg = f"could not initialize traffic state: {exc}"
            raise TrafficStoreError(msg) from exc

    def _enforce_retention(self, session: Session) -> None:
        stale_rows = session.exec(
            select(TrafficEventRow).order_by(col(TrafficEventRow.id).desc()).offset(self.max_events),
        ).all()
        for row in stale_rows:
            session.delete(row)


def list_project_exchanges_readonly(
    project_root: Path,
    *,
    limit: int | None = None,
) -> tuple[TrafficExchange, ...]:
    """Return project traffic exchanges without creating or migrating state."""

    if limit is not None and limit <= 0:
        msg = "limit must be positive"
        raise TrafficStoreError(msg)

    root = project_root.expanduser().resolve()
    db_path = root / ".entroping" / "state.db"
    _reject_symlink_path_components(db_path)
    if not db_path.is_file():
        msg = "traffic state not found"
        raise TrafficStoreError(msg)

    engine = create_engine(_readonly_sqlite_url(db_path))
    _validate_existing_schema_version(engine)
    statement = select(TrafficEventRow).order_by(col(TrafficEventRow.id))
    if limit is not None:
        statement = statement.limit(limit)

    try:
        with Session(engine) as session:
            rows = session.exec(statement).all()
    except SQLAlchemyError as exc:
        msg = f"could not read traffic state: {exc}"
        raise TrafficStoreError(msg) from exc

    return tuple(TrafficExchange.model_validate_json(row.exchange_json) for row in rows)


def _ensure_schema_version(engine: Engine) -> None:
    with Session(engine) as session:
        row = _get_schema_version_row(session)
        if row is None:
            session.add(
                TrafficStoreMetadataRow(
                    key=_SCHEMA_VERSION_KEY,
                    value=str(TRAFFIC_STORE_SCHEMA_VERSION),
                )
            )
            session.commit()
            return
        _validate_schema_version(row.value)


def _validate_existing_schema_version(engine: Engine) -> None:
    try:
        with Session(engine) as session:
            row = _get_schema_version_row(session)
    except SQLAlchemyError as exc:
        if "no such table: traffic_store_metadata" in str(exc):
            return
        msg = f"could not read traffic store schema version: {exc}"
        raise TrafficStoreError(msg) from exc

    if row is not None:
        _validate_schema_version(row.value)


def _get_schema_version_row(session: Session) -> TrafficStoreMetadataRow | None:
    statement = select(TrafficStoreMetadataRow).where(
        col(TrafficStoreMetadataRow.key) == _SCHEMA_VERSION_KEY
    )
    return session.exec(statement).first()


def _validate_schema_version(raw_value: str) -> None:
    try:
        version = int(raw_value)
    except ValueError as exc:
        msg = f"traffic store schema version is invalid: {raw_value!r}"
        raise TrafficStoreError(msg) from exc

    if version > TRAFFIC_STORE_SCHEMA_VERSION:
        msg = (
            f"traffic store schema version {version} is newer than supported "
            f"version {TRAFFIC_STORE_SCHEMA_VERSION}; upgrade Entroping before reading state.db"
        )
        raise TrafficStoreError(msg)
    if version < TRAFFIC_STORE_SCHEMA_VERSION:
        msg = (
            f"traffic store schema version {version} is older than supported "
            f"version {TRAFFIC_STORE_SCHEMA_VERSION}; no automatic migration is available"
        )
        raise TrafficStoreError(msg)


def _reject_symlink_path_components(path: Path) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        msg = (
            "Refusing to use symlinked traffic state path component: "
            f"{symlink_component}"
        )
        raise TrafficStoreError(msg)


def _readonly_sqlite_url(db_path: Path) -> str:
    quoted_path = quote(db_path.as_posix(), safe="/")
    return f"sqlite:///file:{quoted_path}?mode=ro&uri=true"
