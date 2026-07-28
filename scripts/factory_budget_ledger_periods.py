from __future__ import annotations

import sqlite3
from datetime import date

from .factory_budget_ledger_integrity import (
    require_entry_capacity,
    require_period_capacity,
)
from .factory_budget_ledger_models import (
    BudgetPeriodConfig,
    BudgetPeriodSummary,
    FactoryBudgetLedgerError,
    PeriodInitialization,
    idempotency_digest,
    month_boundary,
)
from .factory_budget_ledger_rows import (
    ReserveSignature,
    period_summary_row,
    reserve_signature,
)


def initialize_period(
    connection: sqlite3.Connection,
    config: BudgetPeriodConfig,
) -> PeriodInitialization:
    digest = idempotency_digest(config.reserve_idempotency_key)
    try:
        _ = connection.execute("BEGIN IMMEDIATE")
        existing = reserve_signature(
            connection.execute(
                """
                SELECT e.kind, e.direction, e.amount_microcents, e.occurred_at_utc,
                       e.currency, e.source_id, e.reference_entry_id, p.period_start_utc,
                       p.cash_cap_microcents, p.policy_revision
                FROM ledger_entries AS e
                JOIN budget_periods AS p ON p.id = e.period_id
                WHERE e.idempotency_digest = ?
                """,
                (digest,),
            )
        )
        expected: ReserveSignature = (
            "emergency_reserve_allocation",
            "allocation",
            config.emergency_reserve_microcents,
            config.period_start_utc,
            config.currency,
            config.policy_id,
            None,
            config.period_start_utc,
            config.cash_cap_microcents,
            config.policy_revision,
        )
        if existing is not None:
            if existing != expected:
                raise FactoryBudgetLedgerError(
                    "idempotency",
                    "idempotency key conflicts with an existing ledger entry",
                )
            summary = period_summary_at(connection, config.period_start_utc)
            _ = connection.execute("COMMIT")
            return PeriodInitialization(created=False, summary=summary)
        _require_new_period(connection, config.period_start_utc)
        require_period_capacity(connection)
        require_entry_capacity(connection)
        period_id = _insert_period(connection, config)
        _ = connection.execute(
            """
            INSERT INTO ledger_entries(
                idempotency_digest, period_id, kind, direction,
                amount_microcents, occurred_at_utc, currency, source_id,
                reference_entry_id
            ) VALUES (?, ?, 'emergency_reserve_allocation', 'allocation', ?, ?, ?, ?, NULL)
            """,
            (
                digest,
                period_id,
                config.emergency_reserve_microcents,
                config.period_start_utc,
                config.currency,
                config.policy_id,
            ),
        )
        summary = period_summary_at(connection, config.period_start_utc)
        _ = connection.execute("COMMIT")
        return PeriodInitialization(created=True, summary=summary)
    except FactoryBudgetLedgerError:
        _rollback(connection)
        raise
    except sqlite3.OperationalError as exc:
        _rollback(connection)
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise FactoryBudgetLedgerError("busy", "ledger database is busy") from exc
        raise FactoryBudgetLedgerError("database", "ledger write failed") from exc
    except sqlite3.DatabaseError as exc:
        _rollback(connection)
        raise FactoryBudgetLedgerError("database", "ledger write failed") from exc


def period_summary(
    connection: sqlite3.Connection,
    starts_on: date,
) -> BudgetPeriodSummary:
    if starts_on.day != 1:
        raise FactoryBudgetLedgerError("period", "period must start on day 1")
    return period_summary_at(connection, month_boundary(starts_on))


def period_summary_at(
    connection: sqlite3.Connection,
    period_start_utc: str,
) -> BudgetPeriodSummary:
    try:
        row = period_summary_row(
            connection.execute(
                """
                SELECT period_start_utc, period_end_utc, currency,
                       cash_cap_microcents, emergency_reserve_microcents,
                       net_spent_microcents, entry_count, policy_id, policy_revision
                FROM budget_periods
                WHERE period_start_utc = ?
                """,
                (period_start_utc,),
            )
        )
    except sqlite3.DatabaseError as exc:
        raise FactoryBudgetLedgerError("database", "ledger summary failed") from exc
    if row is None:
        raise FactoryBudgetLedgerError("period", "budget period not found")
    spendable = row[3] - row[4]
    available = spendable - max(row[5], 0)
    return BudgetPeriodSummary(
        period_start_utc=row[0],
        period_end_utc=row[1],
        currency=row[2],
        cash_cap_microcents=row[3],
        emergency_reserve_microcents=row[4],
        net_spent_microcents=row[5],
        available_paid_microcents=max(available, 0),
        entry_count=row[6],
        policy_id=row[7],
        policy_revision=row[8],
    )


def _require_new_period(connection: sqlite3.Connection, period_start: str) -> None:
    if (
        connection.execute(
            "SELECT 1 FROM budget_periods WHERE period_start_utc = ?",
            (period_start,),
        ).fetchone()
        is not None
    ):
        raise FactoryBudgetLedgerError(
            "period",
            "budget period is already initialized with different evidence",
        )


def _insert_period(connection: sqlite3.Connection, config: BudgetPeriodConfig) -> int:
    cursor = connection.execute(
        """
        INSERT INTO budget_periods(
            period_start_utc, period_end_utc, currency,
            cash_cap_microcents, emergency_reserve_microcents,
            policy_id, policy_revision, net_spent_microcents, entry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)
        """,
        (
            config.period_start_utc,
            config.period_end_utc,
            config.currency,
            config.cash_cap_microcents,
            config.emergency_reserve_microcents,
            config.policy_id,
            config.policy_revision,
        ),
    )
    if cursor.lastrowid is None:
        raise FactoryBudgetLedgerError("database", "ledger period id is unavailable")
    return cursor.lastrowid


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        _ = connection.execute("ROLLBACK")
