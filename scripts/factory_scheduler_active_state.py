"""Typed scheduler active-state projection for delivery admission."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pydantic import ValidationError

from scripts.factory_scheduler_models import DeliveryAuthorityEnvelope, StoredAssignment
from scripts.factory_scheduler_queries import integer_value, read_assignment, text_value


@dataclass(frozen=True, slots=True)
class ActiveDeliveryState:
    complete: bool
    issue_numbers: frozenset[int]
    scopes: tuple[str, ...]


def active_delivery_state(connection: sqlite3.Connection) -> ActiveDeliveryState:
    """Project immutable issue/scope authority from every active writer."""

    rows = connection.execute(
        "SELECT issue_number, delivery_authority_json FROM scheduler_assignments "
        "WHERE state = 'active' AND access_mode = 'write' ORDER BY issue_number"
    )
    issues: set[int] = set()
    scopes: set[str] = set()
    for row in rows:
        issues.add(integer_value(row[0]))
        encoded = row[1]
        if not isinstance(encoded, str):
            return ActiveDeliveryState(False, frozenset(issues), tuple(sorted(scopes)))
        try:
            envelope = DeliveryAuthorityEnvelope.model_validate_json(encoded, strict=True)
        except (ValidationError, ValueError, TypeError):
            return ActiveDeliveryState(False, frozenset(issues), tuple(sorted(scopes)))
        scopes.update(envelope.allowed_scopes)
    return ActiveDeliveryState(True, frozenset(issues), tuple(sorted(scopes)))


def active_issue_numbers(connection: sqlite3.Connection) -> frozenset[int]:
    rows = connection.execute(
        "SELECT issue_number FROM scheduler_assignments WHERE state = 'active' "
        "ORDER BY issue_number"
    )
    return frozenset(integer_value(row[0]) for row in rows)


def read_assignment_by_request(
    connection: sqlite3.Connection,
    *,
    request_id: str,
) -> StoredAssignment | None:
    row = connection.execute(
        "SELECT job_id FROM scheduler_assignments WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    return read_assignment(connection, job_id=text_value(row[0]))
