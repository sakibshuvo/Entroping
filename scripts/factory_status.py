from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_cost_policy_io import read_policy_document
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at
from scripts.factory_scheduler_root import SchedulerRootError, resolve_scheduler_root
from scripts.provider_capability_io import load_provider_registry
from scripts.provider_capability_types import ProviderRegistryError

from .factory_status_filesystem import (
    FactoryStatusError,
    collect_queue,
    collect_retention,
    exists_lstat,
    fingerprint_file,
    unsafe_retention,
)
from .factory_status_models import (
    BudgetStatus,
    DispatchLanesStatus,
    FactoryStatusReport,
    QueueStatus,
    SchedulerStatus,
    SourceState,
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
    first = _collect_once(root, observed_at)
    second = _collect_once(root, observed_at)
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
            f"{report.budget.status}; available={report.budget.net_available_microcents}; "
            f"reservations={report.budget.reservations.active}/"
            f"{report.budget.reservations.uncertain}",
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
    lanes, lane_reasons = _dispatch_lanes(root, observed_at, fingerprints)
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


def _dispatch_lanes(
    root: Path,
    observed_at: datetime,
    fingerprints: list[tuple[str, int, int, int]],
) -> tuple[DispatchLanesStatus, tuple[str, ...]]:
    policy_path = root / ".entroping" / "factory-cost-policy.json"
    if not exists_lstat(policy_path):
        policy_path = root / "docs" / "meta" / "factory-cost-policy.example.json"
    registry_path = root / "docs" / "meta" / "provider-capability-registry.json"
    try:
        fingerprint_file(root, policy_path, fingerprints)
        fingerprint_file(root, registry_path, fingerprints)
        policy = FactoryCostPolicy.model_validate_json(
            read_policy_document(policy_path), strict=True
        )
        validate_policy_at(policy, observed_at)
        registry = load_provider_registry(registry_path)
    except FactoryStatusError:
        return DispatchLanesStatus(
            status="unsafe", active_routes=0, ready_routes=0, quota_status="unsafe"
        ), ("dispatch-policy-unsafe",)
    except (FactoryCostPolicyError, ProviderRegistryError, ValidationError, OSError, ValueError):
        return DispatchLanesStatus(
            status="unavailable", active_routes=0, ready_routes=0, quota_status="unavailable"
        ), ("dispatch-policy-unavailable",)
    active = tuple(lane for lane in registry.lanes if lane.lifecycle == "active")
    policy_providers = {lane.provider_id for lane in policy.automation_lanes}
    ready = tuple(
        lane
        for lane in active
        if "queue_dispatch" in lane.capabilities and lane.policy_provider_id in policy_providers
    )
    status: SourceState = "available" if ready else "unavailable"
    reasons = () if ready else ("dispatch-route-unavailable",)
    return DispatchLanesStatus(
        status=status,
        active_routes=len(active),
        ready_routes=len(ready),
        quota_status=status,
    ), reasons


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
