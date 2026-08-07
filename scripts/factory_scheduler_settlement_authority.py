from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Literal

from scripts.factory_budget_ledger_models import FactoryBudgetLedgerError
from scripts.factory_budget_ledger_storage import (
    existing_writable_connection,
    readonly_connection,
)
from scripts.factory_budget_reservations import reservation_for_job
from scripts.factory_quota_store import authorization_by_job, quota_authorization_state
from scripts.factory_scheduler_models import StoredAssignment

type SettlementAuthorityState = Literal[
    "not-required",
    "dispatching",
    "launched",
    "uncertain",
    "settled",
    "invalid",
    "unavailable",
]


def read_settlement_authority(
    project_root: Path,
    assignment: StoredAssignment,
) -> SettlementAuthorityState:
    if assignment.request.worker_class == "free-local":
        return "not-required"
    try:
        with readonly_connection(project_root) as connection:
            return _settlement_authority(connection, assignment)
    except (FactoryBudgetLedgerError, sqlite3.DatabaseError):
        return "unavailable"


@contextmanager
def settlement_authority_handoff(
    project_root: Path,
    assignment: StoredAssignment,
) -> Generator[SettlementAuthorityState, None, None]:
    if assignment.request.worker_class == "free-local":
        yield "not-required"
        return
    stack = ExitStack()
    connection: sqlite3.Connection | None = None
    try:
        connection = stack.enter_context(existing_writable_connection(project_root))
        _ = connection.execute("BEGIN IMMEDIATE")
        authority = _settlement_authority(connection, assignment)
    except (FactoryBudgetLedgerError, sqlite3.DatabaseError, sqlite3.OperationalError):
        if connection is not None and connection.in_transaction:
            _ = connection.execute("ROLLBACK")
        stack.close()
        yield "unavailable"
        return
    try:
        yield authority
    finally:
        if connection.in_transaction:
            _ = connection.execute("ROLLBACK")
        stack.close()


def _settlement_authority(
    connection: sqlite3.Connection,
    assignment: StoredAssignment,
) -> SettlementAuthorityState:
    request = assignment.request
    if request.reservation_id is not None:
        reservation = reservation_for_job(connection, request.job_id)
        if reservation is None or reservation.reservation_id != request.reservation_id:
            return "invalid"
        if reservation.state == "dispatching":
            return "dispatching"
        if reservation.state == "uncertain":
            return "uncertain"
        return "settled"
    if request.authorization_id is None:
        return "invalid"
    authorization = authorization_by_job(connection, request.job_id)
    if (
        authorization is None
        or authorization.authorization_id != request.authorization_id
        or authorization.reservation_id is not None
    ):
        return "invalid"
    state = quota_authorization_state(connection, request.authorization_id)
    if state == "active":
        return "dispatching"
    if state == "launched":
        return "launched"
    if state == "uncertain":
        return "uncertain"
    if state in {"settled", "released"}:
        return "settled"
    return "invalid"
