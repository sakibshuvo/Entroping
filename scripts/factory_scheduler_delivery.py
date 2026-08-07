"""Specialized scheduler-owned live delivery admission."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_delivery_admission import (
    DeliveryAdmissionError,
    _prepare_delivery_admission,
)
from scripts.factory_issue_selector_github import GitHubStateError, refresh_snapshot
from scripts.factory_orchestration_errors import OrchestrationGitError
from scripts.factory_scheduler_active_state import (
    ActiveDeliveryState,
    active_delivery_state,
    read_assignment_by_request,
)
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
    SchedulerLimits,
)
from scripts.factory_scheduler_process import probe_owner
from scripts.factory_scheduler_receipts import blocked_state_receipt
from scripts.factory_scheduler_storage import (
    database_exists,
    readonly_connection,
)
from scripts.factory_scheduler_storage_fs import SchedulerStateError
from scripts.factory_scheduler_tick import _tick_selected_state, immutable_request_decision
from scripts.factory_scheduler_validation import validate_lease_seconds

type HealthCheck = Callable[[LeaseOwner], bool | None]


def tick_selected_delivery(
    project_root: Path,
    limits: SchedulerLimits,
    *,
    request: AssignmentRequest,
    owner: LeaseOwner,
    as_of: datetime | None,
    lease_seconds: int,
    plan_only: bool,
    owner_health: HealthCheck | None,
) -> DecisionReceipt:
    """Fetch, select, revalidate, and atomically admit free-local Tier A work."""

    validate_lease_seconds(lease_seconds)
    observed_at = datetime.now(UTC) if as_of is None else as_of
    if request.worker_class != "free-local" or request.access_mode != "write":
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason="selection-invalid",
            authoritative=not plan_only,
        )
    try:
        active = ActiveDeliveryState(True, frozenset(), ())
        if database_exists(project_root):
            with readonly_connection(project_root) as connection:
                stored = read_assignment_by_request(
                    connection,
                    request_id=request.request_id,
                )
                if stored is not None:
                    expected = stored.request.model_copy(
                        update={"delivery_authority": None}
                    )
                    if expected != request:
                        return blocked_state_receipt(
                            request=request,
                            observed_at=observed_at,
                            reason="request-id-conflict",
                            authoritative=not plan_only,
                        )
                    replay = immutable_request_decision(
                        project_root,
                        stored.request,
                        observed_at,
                    )
                    if replay is not None:
                        return replay
                active = active_delivery_state(connection)
                if not active.complete:
                    raise DeliveryAdmissionError("selection-invalid")
        snapshot = refresh_snapshot(
            repo="sakibshuvo/Entroping",
            as_of=observed_at,
            ttl_seconds=60,
        )
        candidate, admission = _prepare_delivery_admission(
            project_root,
            request,
            snapshot,
            active_issues=active.issue_numbers,
            active_scopes=active.scopes,
            active_state_complete=active.complete,
            as_of=observed_at,
        )
    except (
        DeliveryAdmissionError,
        OrchestrationGitError,
        SchedulerStateError,
        sqlite3.DatabaseError,
        ValidationError,
        GitHubStateError,
    ):
        return blocked_state_receipt(
            request=request,
            observed_at=observed_at,
            reason="selection-unavailable",
            authoritative=not plan_only,
        )
    return _tick_selected_state(
        project_root,
        limits,
        request=candidate,
        owner=owner,
        as_of=as_of,
        lease_seconds=lease_seconds,
        plan_only=plan_only,
        health=owner_health or probe_owner,
        delivery_admission=admission,
    )
