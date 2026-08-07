from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .factory_budget_ledger_models import FactoryBudgetLedgerError, canonical_occurred_at
from .factory_budget_ledger_storage import existing_writable_connection
from .factory_budget_reservation_models import CostReservationReceipt
from .factory_budget_reservations import reservation_for_job
from .factory_quota_authorization import validate_authorization
from .factory_quota_models import DispatchAuthorizationReceipt
from .factory_quota_store import authorization_by_job


@contextmanager
def reservation_handoff(
    project_root: Path,
    job_id: str,
) -> Generator[CostReservationReceipt | None, None, None]:
    with existing_writable_connection(project_root) as connection:
        try:
            _ = connection.execute("BEGIN IMMEDIATE")
            yield reservation_for_job(connection, job_id)
            _ = connection.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            _rollback(connection)
            detail = str(exc).casefold()
            if "locked" in detail or "busy" in detail:
                raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
            raise FactoryBudgetLedgerError(
                "database",
                "ledger reservation handoff failed",
            ) from exc
        except BaseException:
            _rollback(connection)
            raise


@contextmanager
def authorization_handoff(
    project_root: Path,
    job_id: str,
    *,
    as_of: datetime,
) -> Generator[DispatchAuthorizationReceipt | None, None, None]:
    with existing_writable_connection(project_root) as connection:
        try:
            _ = connection.execute("BEGIN IMMEDIATE")
            authorization = authorization_by_job(connection, job_id)
            if authorization is not None and not validate_authorization(
                connection,
                job_id,
                as_of=canonical_occurred_at(as_of),
            ):
                authorization = None
            yield authorization
            _ = connection.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            _rollback(connection)
            detail = str(exc).casefold()
            if "locked" in detail or "busy" in detail:
                raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
            raise FactoryBudgetLedgerError(
                "database",
                "ledger authorization handoff failed",
            ) from exc
        except BaseException:
            _rollback(connection)
            raise


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
