from __future__ import annotations

import sqlite3

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_reservation_models import UsageEnvelope
from .factory_quota_integrity import require_monotonic_authorization_transition
from .factory_quota_settlement_transition import (
    QuotaSettlementOutcome as _QuotaSettlementOutcome,
)
from .factory_quota_settlement_transition import (
    _set_authorization_state,
    _usage_digest,
)
from .factory_quota_settlement_transition import (
    mark_quota_authorization_uncertain as _mark_quota_authorization_uncertain,
)
from .factory_quota_settlement_transition import (
    release_quota_authorization as _release_quota_authorization,
)
from .factory_quota_settlement_transition import (
    settle_quota_authorization as _settle_quota_authorization,
)
from .factory_quota_windows import quota_units

QuotaSettlementOutcome = _QuotaSettlementOutcome
mark_quota_authorization_uncertain = _mark_quota_authorization_uncertain
release_quota_authorization = _release_quota_authorization
settle_quota_authorization = _settle_quota_authorization


def settle_quota_holds(
    connection: sqlite3.Connection,
    *,
    cash_reservation_id: int,
    usage: UsageEnvelope,
    occurred_at: str,
) -> None:
    authorization = connection.execute(
        "SELECT id, state, state_changed_at_utc FROM dispatch_authorizations "
        "WHERE cash_reservation_id = ?",
        (cash_reservation_id,),
    ).fetchone()
    if authorization is None:
        return
    require_monotonic_authorization_transition(occurred_at, authorization[2])
    if authorization[1] not in {"active", "launched"}:
        raise FactoryBudgetLedgerError("authorization", "dispatch authorization is terminal")
    units = quota_units(usage)
    holds = connection.execute(
        "SELECT id, unit, held_units FROM quota_holds WHERE authorization_id = ?",
        (authorization[0],),
    ).fetchall()
    for hold_id, unit, held_units in holds:
        match unit:
            case "requests" | "input_tokens" | "output_tokens" | "tokens":
                actual = units[unit]
            case _:
                raise FactoryBudgetLedgerError("database", "quota hold unit is invalid")
        if actual > int(held_units):
            raise FactoryBudgetLedgerError("quota", "actual quota usage exceeds held units")
        _ = connection.execute(
            "UPDATE quota_holds SET actual_units = ?, state = 'settled' "
            "WHERE id = ? AND state = 'active'",
            (actual, hold_id),
        )
    _set_authorization_state(
        connection,
        authorization_id=int(authorization[0]),
        state="settled",
        occurred_at=occurred_at,
        settlement_digest=_usage_digest(usage),
    )


def release_quota_holds(
    connection: sqlite3.Connection,
    *,
    cash_reservation_id: int,
    occurred_at: str,
) -> None:
    authorization = connection.execute(
        "SELECT id, state, state_changed_at_utc FROM dispatch_authorizations "
        "WHERE cash_reservation_id = ?",
        (cash_reservation_id,),
    ).fetchone()
    if authorization is None:
        return
    require_monotonic_authorization_transition(occurred_at, authorization[2])
    if authorization[1] not in {"active", "launched", "uncertain"}:
        raise FactoryBudgetLedgerError("authorization", "dispatch authorization is terminal")
    _ = connection.execute(
        """
        UPDATE quota_holds SET actual_units = 0, state = 'released'
        WHERE authorization_id = (
            SELECT id FROM dispatch_authorizations WHERE cash_reservation_id = ?
        ) AND state IN ('active', 'uncertain')
        """,
        (cash_reservation_id,),
    )
    _set_authorization_state(
        connection,
        authorization_id=int(authorization[0]),
        state="released",
        occurred_at=occurred_at,
    )


def mark_quota_holds_uncertain(
    connection: sqlite3.Connection,
    *,
    cash_reservation_id: int,
    occurred_at: str,
) -> None:
    authorization = connection.execute(
        "SELECT id, state, state_changed_at_utc FROM dispatch_authorizations "
        "WHERE cash_reservation_id = ?",
        (cash_reservation_id,),
    ).fetchone()
    if authorization is None:
        return
    require_monotonic_authorization_transition(occurred_at, authorization[2])
    if authorization[1] in {"settled", "released"}:
        return
    _ = connection.execute(
        "UPDATE quota_holds SET state = 'uncertain' "
        "WHERE authorization_id = ? AND state = 'active'",
        (authorization[0],),
    )
    _set_authorization_state(
        connection,
        authorization_id=int(authorization[0]),
        state="uncertain",
        occurred_at=occurred_at,
    )
