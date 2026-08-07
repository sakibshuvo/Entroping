from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_models import UsageEnvelope
from .factory_budget_reservation_validation import canonical_digest
from .factory_quota_integrity import require_monotonic_authorization_transition
from .factory_quota_windows import QuotaUnit, quota_units


@dataclass(frozen=True, slots=True)
class QuotaSettlementOutcome:
    created: bool
    authorization_id: str
    state: Literal["settled", "released", "uncertain"]
    actual_microcents: Literal[0]


def settle_quota_authorization(
    connection: sqlite3.Connection,
    *,
    authorization_id: str,
    usage: UsageEnvelope,
    occurred_at: str,
) -> QuotaSettlementOutcome:
    return _transition_authorization(
        connection,
        authorization_id=authorization_id,
        target="settled",
        units=quota_units(usage),
        settlement_digest=_usage_digest(usage),
        occurred_at=occurred_at,
    )


def release_quota_authorization(
    connection: sqlite3.Connection,
    *,
    authorization_id: str,
    occurred_at: str,
) -> QuotaSettlementOutcome:
    return _transition_authorization(
        connection,
        authorization_id=authorization_id,
        target="released",
        units=None,
        settlement_digest=None,
        occurred_at=occurred_at,
    )


def mark_quota_authorization_uncertain(
    connection: sqlite3.Connection,
    *,
    authorization_id: str,
    occurred_at: str,
) -> QuotaSettlementOutcome:
    return _transition_authorization(
        connection,
        authorization_id=authorization_id,
        target="uncertain",
        units=None,
        settlement_digest=None,
        occurred_at=occurred_at,
    )


def _transition_authorization(
    connection: sqlite3.Connection,
    *,
    authorization_id: str,
    target: Literal["settled", "released", "uncertain"],
    units: dict[QuotaUnit, int] | None,
    settlement_digest: str | None,
    occurred_at: str,
) -> QuotaSettlementOutcome:
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, cash_reservation_id, state, settlement_digest, "
            "state_changed_at_utc "
            "FROM dispatch_authorizations WHERE public_id = ?",
            (authorization_id,),
        ).fetchone()
        if row is None:
            raise FactoryBudgetLedgerError("authorization", "dispatch authorization not found")
        require_monotonic_authorization_transition(occurred_at, row[4])
        if row[1] is not None:
            raise FactoryBudgetLedgerError(
                "authorization",
                "cash-backed authorization requires cash settlement",
            )
        state = str(row[2])
        if state == target:
            holds = _quota_holds(connection, int(row[0]))
            _require_terminal_replay(
                holds,
                target=target,
                units=units,
                stored_settlement_digest=None if row[3] is None else str(row[3]),
                requested_settlement_digest=settlement_digest,
            )
            _ = connection.execute("COMMIT")
            return QuotaSettlementOutcome(False, authorization_id, target, 0)
        allowed = {"active", "launched"} if target != "released" else {"active"}
        if state not in allowed:
            raise FactoryBudgetLedgerError(
                "authorization",
                "quota authorization is already terminal",
            )
        holds = _quota_holds(connection, int(row[0]))
        _apply_transition(connection, holds, target=target, units=units)
        _set_authorization_state(
            connection,
            authorization_id=int(row[0]),
            state=target,
            occurred_at=occurred_at,
            settlement_digest=settlement_digest,
        )
        _ = connection.execute("COMMIT")
        return QuotaSettlementOutcome(True, authorization_id, target, 0)
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError(
            "database",
            "quota authorization settlement failed",
        ) from exc


def _quota_holds(
    connection: sqlite3.Connection,
    authorization_id: int,
) -> list[tuple[int, QuotaUnit, int, int | None, str]]:
    result: list[tuple[int, QuotaUnit, int, int | None, str]] = []
    rows = connection.execute(
        "SELECT id, unit, held_units, actual_units, state FROM quota_holds "
        "WHERE authorization_id = ? ORDER BY id",
        (authorization_id,),
    ).fetchall()
    for raw_id, raw_unit, raw_held, raw_actual, raw_state in rows:
        unit = _quota_unit(raw_unit)
        state = str(raw_state)
        if state not in {"active", "settled", "released", "uncertain"}:
            raise FactoryBudgetLedgerError("database", "quota hold state is invalid")
        result.append(
            (
                int(raw_id),
                unit,
                int(raw_held),
                None if raw_actual is None else int(raw_actual),
                state,
            )
        )
    return result


def _quota_unit(value: object) -> QuotaUnit:
    if value == "requests":
        return "requests"
    if value == "input_tokens":
        return "input_tokens"
    if value == "output_tokens":
        return "output_tokens"
    if value == "tokens":
        return "tokens"
    raise FactoryBudgetLedgerError("database", "quota hold unit is invalid")


def _apply_transition(
    connection: sqlite3.Connection,
    holds: list[tuple[int, QuotaUnit, int, int | None, str]],
    *,
    target: Literal["settled", "released", "uncertain"],
    units: dict[QuotaUnit, int] | None,
) -> None:
    for hold_id, unit, held_units, _actual_units, state in holds:
        actual = None if units is None else units[unit]
        if state != "active":
            raise FactoryBudgetLedgerError(
                "authorization",
                "quota authorization is already terminal",
            )
        if target == "settled":
            if actual is None or actual > held_units:
                raise FactoryBudgetLedgerError(
                    "quota",
                    "actual quota usage exceeds held units",
                )
            _ = connection.execute(
                "UPDATE quota_holds SET actual_units = ?, state = 'settled' WHERE id = ?",
                (actual, hold_id),
            )
        elif target == "released":
            _ = connection.execute(
                "UPDATE quota_holds SET actual_units = 0, state = 'released' WHERE id = ?",
                (hold_id,),
            )
        else:
            _ = connection.execute(
                "UPDATE quota_holds SET state = 'uncertain' WHERE id = ?",
                (hold_id,),
            )


def _require_terminal_replay(
    holds: list[tuple[int, QuotaUnit, int, int | None, str]],
    *,
    target: Literal["settled", "released", "uncertain"],
    units: dict[QuotaUnit, int] | None,
    stored_settlement_digest: str | None,
    requested_settlement_digest: str | None,
) -> None:
    if target == "settled" and (
        units is None or stored_settlement_digest != requested_settlement_digest
    ):
        raise FactoryBudgetLedgerError(
            "idempotency",
            "quota settlement conflicts with terminal usage",
        )
    for _hold_id, unit, _held_units, actual_units, state in holds:
        actual = None if units is None else units[unit]
        if state != target or (target == "settled" and actual_units != actual):
            raise FactoryBudgetLedgerError(
                "idempotency",
                "quota settlement conflicts with terminal usage",
            )


def _set_authorization_state(
    connection: sqlite3.Connection,
    *,
    authorization_id: int,
    state: Literal["settled", "released", "uncertain"],
    occurred_at: str,
    settlement_digest: str | None = None,
) -> None:
    cursor = connection.execute(
        "UPDATE dispatch_authorizations SET state = ?, state_changed_at_utc = ?, "
        "settlement_digest = ? WHERE id = ?",
        (state, occurred_at, settlement_digest, authorization_id),
    )
    if cursor.rowcount != 1:
        raise FactoryBudgetLedgerError("database", "authorization state was not updated")


def _usage_digest(usage: UsageEnvelope) -> str:
    return canonical_digest(
        {
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "minutes": usage.minutes,
        }
    )


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
