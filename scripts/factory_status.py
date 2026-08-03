from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_scheduler_root import SchedulerRootError, resolve_scheduler_root

from .factory_status_dispatch import collect_dispatch_lanes
from .factory_status_filesystem import (
    FactoryStatusError,
    collect_queue,
    collect_retention,
    unsafe_retention,
)
from .factory_status_models import (
    BudgetStatus,
    DispatchLanesStatus,
    FactoryStatusReport,
    QueueStatus,
    SchedulerStatus,
    StateCounts,
    StatusState,
)
from .factory_status_sqlite import collect_budget, collect_scheduler


@dataclass(frozen=True, slots=True)
class _Collected:
    """A public report with its bounded metadata identity snapshot."""

    report: FactoryStatusReport
    fingerprint: tuple[tuple[str, int, int, int], ...]


def collect_factory_status(project_root: Path) -> FactoryStatusReport:
    """Return a bounded, physically read-only factory status projection."""

    observed_at = datetime.now(UTC)
    try:
        root = resolve_scheduler_root(project_root)
    except SchedulerRootError:
        return _unsafe_report(observed_at, "root-unsafe")
    try:
        first = _collect_once(root, observed_at)
        second = _collect_once(root, observed_at)
    except (FactoryStatusError, OSError, sqlite3.DatabaseError, ValueError):
        return _unsafe_report(observed_at, "collection-unsafe")
    if first.fingerprint != second.fingerprint:
        return _with_snapshot_change(second.report)
    return first.report


def render_human(report: FactoryStatusReport) -> str:
    """Render the public human view solely from the typed report."""

    reasons = ", ".join(report.reason_codes) if report.reason_codes else "none"
    retention = ", ".join(
        f"{item.artifact_class}={item.count}/{item.byte_ceiling or 0}:{item.pressure}"
        for item in report.retention.classes
    )
    return "\n".join(
        (
            f"Factory status: {report.state}",
            f"Consistency: {report.snapshot_consistency}",
            f"Reasons: {reasons}",
            "Budget: "
            f"{report.budget.status}; cap={report.budget.cash_cap_microcents}; "
            f"reserve={report.budget.reserve_microcents}; "
            f"available={report.budget.net_available_microcents}; "
            f"subscriptions={report.budget.subscription_charge_microcents}; "
            f"reservations={report.budget.reservations.active}/{report.budget.reservations.uncertain}/"
            f"{report.budget.reservations.settled}/{report.budget.reservations.released}; "
            f"authorizations={report.budget.authorizations.active}/"
            f"{report.budget.authorizations.uncertain}/{report.budget.authorizations.settled}/"
            f"{report.budget.authorizations.released}",
            "Dispatch lanes: "
            f"{report.dispatch_lanes.status}; ready={report.dispatch_lanes.ready_routes}/"
            f"{report.dispatch_lanes.active_routes}; quota={report.dispatch_lanes.quota_status}",
            "Scheduler: "
            f"{report.scheduler.status}; lease={report.scheduler.lease_state}; "
            f"paid={report.scheduler.active_paid}; free={report.scheduler.active_free_reviews}; "
            f"writers={report.scheduler.active_writers}; retry={report.scheduler.retry_waiting}; "
            f"uncertain={report.scheduler.uncertain}",
            "Queue: "
            f"{report.queue.status}; queued={report.queue.queued}; running={report.queue.running}; "
            f"completed={report.queue.completed}; failed={report.queue.failed}; "
            f"invalid={report.queue.invalid}",
            f"Retention: {report.retention.status}; {retention}",
        )
    )


def render_json(report: FactoryStatusReport) -> str:
    """Serialize the strict public report deterministically."""

    return json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def status_exit_code(report: FactoryStatusReport) -> int:
    """Map the public ordered status to its command exit code."""

    match report.state:
        case "healthy":
            return 0
        case "paused":
            return 1
        case "unsafe":
            return 2


def _collect_once(root: Path, observed_at: datetime) -> _Collected:
    fingerprints: list[tuple[str, int, int, int]] = []
    budget, budget_reasons = collect_budget(root, observed_at, fingerprints)
    lanes, lane_reasons = collect_dispatch_lanes(root, observed_at, fingerprints)
    scheduler, scheduler_reasons = collect_scheduler(root, observed_at, fingerprints)
    queue, queue_reasons = collect_queue(root, fingerprints)
    retention, retention_reasons = collect_retention(root, fingerprints)
    reasons = tuple(
        sorted(
            set(
                (
                    *budget_reasons,
                    *lane_reasons,
                    *scheduler_reasons,
                    *queue_reasons,
                    *retention_reasons,
                )
            )
        )
    )
    sections = (budget.status, lanes.status, scheduler.status, queue.status, retention.status)
    state: StatusState
    if "unsafe" in sections:
        state = "unsafe"
    elif all(value == "available" for value in sections):
        state = (
            "paused"
            if {
                "scheduler-lease-expired",
                "scheduler-retry-waiting",
                "scheduler-retry-stale",
                "retention-pressure",
            }.intersection(reasons)
            else "healthy"
        )
    else:
        state = "paused"
    return _Collected(
        report=FactoryStatusReport(
            observed_at_utc=observed_at,
            state=state,
            snapshot_consistency="stable",
            reason_codes=reasons,
            budget=budget,
            dispatch_lanes=lanes,
            scheduler=scheduler,
            queue=queue,
            retention=retention,
        ),
        fingerprint=tuple(sorted(fingerprints)),
    )


def _unsafe_report(observed_at: datetime, reason: str) -> FactoryStatusReport:
    empty = StateCounts(active=0, uncertain=0, settled=0, released=0)
    return FactoryStatusReport(
        observed_at_utc=observed_at,
        state="unsafe",
        snapshot_consistency="unavailable",
        reason_codes=(reason,),
        budget=BudgetStatus(status="unsafe", reservations=empty, authorizations=empty),
        dispatch_lanes=DispatchLanesStatus(
            status="unsafe", active_routes=0, ready_routes=0, quota_status="unsafe"
        ),
        scheduler=SchedulerStatus(
            status="unsafe",
            lease_state="unsafe",
            active_paid=0,
            active_free_reviews=0,
            active_writers=0,
            executing=0,
            retry_waiting=0,
            uncertain=0,
        ),
        queue=QueueStatus(status="unsafe", queued=0, running=0, completed=0, failed=0, invalid=0),
        retention=unsafe_retention(),
    )


def _with_snapshot_change(report: FactoryStatusReport) -> FactoryStatusReport:
    return report.model_copy(
        update={
            "state": "unsafe",
            "snapshot_consistency": "changed",
            "reason_codes": tuple(sorted(set((*report.reason_codes, "snapshot-changed")))),
        }
    )
