from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from scripts.factory_budget_ledger_fs import LEDGER_DIRECTORY, LEDGER_NAME
from scripts.factory_budget_ledger_schema import validate_schema as validate_ledger_schema
from scripts.factory_scheduler_schema import validate_schema as validate_scheduler_schema

from .factory_status_database import open_status_database
from .factory_status_models import BudgetStatus, SchedulerStatus, StateCounts
from .factory_status_policy import cash_threshold_reason, policy_safety_reason

type LeaseState = Literal["uninitialized", "idle", "active", "expired", "unsafe"]
type Fingerprints = list[tuple[str, int, int, int]]


def collect_budget(
    root: Path,
    observed_at: datetime,
    fingerprints: Fingerprints,
) -> tuple[BudgetStatus, tuple[str, ...]]:
    """Summarize existing ledger authority without opening a write-capable connection."""

    path = root.joinpath(*LEDGER_DIRECTORY, LEDGER_NAME)
    connection, status = open_status_database(root, path, fingerprints)
    empty = StateCounts(active=0, uncertain=0, settled=0, released=0)
    if connection is None:
        policy_reason = policy_safety_reason(root, observed_at, fingerprints)
        if policy_reason == "budget-policy-unsafe":
            return BudgetStatus(status="unsafe", reservations=empty, authorizations=empty), (
                policy_reason,
            )
        return BudgetStatus(status=status, reservations=empty, authorizations=empty), (
            f"budget-{status}",
        )
    try:
        validate_ledger_schema(connection)
        row = connection.execute(
            "SELECT id, policy_id, policy_revision, cash_cap_microcents, "
            "emergency_reserve_microcents, net_spent_microcents, active_reserved_microcents "
            "FROM budget_periods "
            "WHERE period_start_utc <= ? AND period_end_utc > ? "
            "ORDER BY period_start_utc DESC LIMIT 1",
            (observed_at.isoformat(), observed_at.isoformat()),
        ).fetchone()
        reservations = _state_counts(
            connection, "cost_reservations", ("dispatching", "uncertain", "settled", "reconciled")
        )
        authorizations = _state_counts(
            connection, "dispatch_authorizations", ("active", "uncertain", "settled", "released")
        )
        if row is None:
            return BudgetStatus(
                status="unavailable", reservations=reservations, authorizations=authorizations
            ), ("budget-period-unavailable",)
        subscription = int(
            connection.execute(
                "SELECT COALESCE(SUM(amount_microcents), 0) FROM ledger_entries "
                "WHERE period_id = ? AND kind = 'fixed_subscription_charge' "
                "AND direction = 'debit'",
                (int(row[0]),),
            ).fetchone()[0]
        )
        cap, reserve, spent, held = (int(value) for value in row[3:])
        net_available = cap - reserve - spent - held
        if reservations.uncertain > 0 or authorizations.uncertain > 0:
            return BudgetStatus(
                status="unsafe",
                cash_cap_microcents=cap,
                reserve_microcents=reserve,
                net_available_microcents=net_available,
                subscription_charge_microcents=subscription,
                reservations=reservations,
                authorizations=authorizations,
            ), ("budget-authority-uncertain",)
        threshold = cash_threshold_reason(
            root, observed_at, str(row[1]), int(row[2]), cap, spent, held, fingerprints
        )
        if threshold is not None:
            return BudgetStatus(
                status="unsafe"
                if threshold in {"budget-authority-uncertain", "budget-policy-unsafe"}
                else "unavailable",
                cash_cap_microcents=cap,
                reserve_microcents=reserve,
                net_available_microcents=net_available,
                subscription_charge_microcents=subscription,
                reservations=reservations,
                authorizations=authorizations,
            ), (threshold,)
        return BudgetStatus(
            status="available",
            cash_cap_microcents=cap,
            reserve_microcents=reserve,
            net_available_microcents=net_available,
            subscription_charge_microcents=subscription,
            reservations=reservations,
            authorizations=authorizations,
        ), ()
    except (sqlite3.DatabaseError, ValueError):
        return BudgetStatus(status="unsafe", reservations=empty, authorizations=empty), (
            "budget-unsafe",
        )
    finally:
        connection.close()


def collect_scheduler(
    root: Path,
    observed_at: datetime,
    fingerprints: Fingerprints,
) -> tuple[SchedulerStatus, tuple[str, ...]]:
    """Summarize existing scheduler state without exposing lease identity."""

    path = root / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection, status = open_status_database(root, path, fingerprints)
    blank_lease: LeaseState = "uninitialized" if status == "uninitialized" else "unsafe"
    blank = SchedulerStatus(
        status=status,
        lease_state=blank_lease,
        active_paid=0,
        active_free_reviews=0,
        active_writers=0,
        executing=0,
        retry_waiting=0,
        uncertain=0,
    )
    if connection is None:
        return blank, (f"scheduler-{status}",)
    try:
        validate_scheduler_schema(connection)
        lease = connection.execute(
            "SELECT expires_at_utc FROM scheduler_lease WHERE id = 1"
        ).fetchone()
        lease_state: LeaseState
        if lease is None:
            lease_state = "idle"
        elif str(lease[0]) > observed_at.isoformat():
            lease_state = "active"
        else:
            lease_state = "expired"
        counts = connection.execute(
            "SELECT COALESCE(SUM(worker_class = 'paid' AND state = 'active'), 0), "
            "COALESCE(SUM(worker_class = 'free-local' AND access_mode = 'read-only' "
            "AND state = 'active'), 0), COALESCE(SUM(access_mode = 'write' "
            "AND state = 'active'), 0) FROM scheduler_assignments"
        ).fetchone()
        phases = connection.execute(
            "SELECT COALESCE(SUM(phase NOT IN ('completed', 'failed')), 0), "
            "COALESCE(SUM(phase = 'retry-wait' AND retry_not_before_utc > ?), 0), "
            "COALESCE(SUM(phase = 'retry-wait' AND retry_not_before_utc <= ?), 0), "
            "COALESCE(SUM(phase = 'uncertain'), 0) FROM scheduler_execution_state",
            (observed_at.isoformat(), observed_at.isoformat()),
        ).fetchone()
        concurrency = int(
            connection.execute(
                "SELECT COUNT(*) FROM scheduler_execution_state AS e "
                "LEFT JOIN scheduler_lease AS l ON l.id = 1 "
                "WHERE e.phase NOT IN ('completed', 'failed') AND (l.id IS NULL "
                "OR l.expires_at_utc <= ? OR e.lease_expires_at_utc <= ? "
                "OR e.lease_owner_id != l.owner_id "
                "OR e.lease_owner_pid != l.owner_pid "
                "OR e.lease_owner_start_token != l.owner_start_token "
                "OR e.lease_epoch != l.epoch)",
                (observed_at.isoformat(), observed_at.isoformat()),
            ).fetchone()[0]
        )
        reasons: tuple[str, ...] = ()
        if lease_state == "expired":
            reasons = ("scheduler-lease-expired",)
        if int(phases[1]) > 0:
            reasons = (*reasons, "scheduler-retry-waiting")
        if int(phases[2]) > 0:
            reasons = (*reasons, "scheduler-retry-stale")
        if concurrency:
            return SchedulerStatus(
                status="unsafe",
                lease_state=lease_state,
                active_paid=int(counts[0]),
                active_free_reviews=int(counts[1]),
                active_writers=int(counts[2]),
                executing=int(phases[0]),
                retry_waiting=int(phases[1]),
                uncertain=int(phases[3]),
            ), (*reasons, "scheduler-concurrency-unsafe")
        if int(phases[3]) > 0:
            return SchedulerStatus(
                status="unsafe",
                lease_state=lease_state,
                active_paid=int(counts[0]),
                active_free_reviews=int(counts[1]),
                active_writers=int(counts[2]),
                executing=int(phases[0]),
                retry_waiting=int(phases[1]),
                uncertain=int(phases[3]),
            ), (*reasons, "scheduler-authority-uncertain")
        return SchedulerStatus(
            status="available",
            lease_state=lease_state,
            active_paid=int(counts[0]),
            active_free_reviews=int(counts[1]),
            active_writers=int(counts[2]),
            executing=int(phases[0]),
            retry_waiting=int(phases[1]),
            uncertain=int(phases[3]),
        ), reasons
    except (sqlite3.DatabaseError, ValueError):
        return SchedulerStatus(
            status="unsafe",
            lease_state="unsafe",
            active_paid=0,
            active_free_reviews=0,
            active_writers=0,
            executing=0,
            retry_waiting=0,
            uncertain=0,
        ), ("scheduler-unsafe",)
    finally:
        connection.close()


def _state_counts(
    connection: sqlite3.Connection, table: str, states: tuple[str, str, str, str]
) -> StateCounts:
    values = [
        int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE state = ?", (state,)
            ).fetchone()[0]
        )
        for state in states
    ]
    return StateCounts(active=values[0], uncertain=values[1], settled=values[2], released=values[3])
