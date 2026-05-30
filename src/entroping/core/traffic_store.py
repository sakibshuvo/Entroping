"""SQLite persistence for redacted Eye traffic state."""

from pathlib import Path

from sqlmodel import Field, Index, Session, SQLModel, col, create_engine, select

from entroping.models.traffic import TrafficExchange


class TrafficStoreError(ValueError):
    """Raised when traffic state cannot be persisted safely."""


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
        SQLModel.metadata.create_all(self._engine)

    def _enforce_retention(self, session: Session) -> None:
        stale_rows = session.exec(
            select(TrafficEventRow).order_by(col(TrafficEventRow.id).desc()).offset(self.max_events),
        ).all()
        for row in stale_rows:
            session.delete(row)


def _reject_symlink_path_components(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to use symlinked traffic state path component: {current}"
            raise TrafficStoreError(msg)
