"""Read-only scheduler ownership and applied-integrity revalidation."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_delivery_admission import DeliveryAdmissionError, selector_policy_digest
from scripts.factory_orchestration_errors import OrchestrationGitError, OrchestrationServiceError
from scripts.factory_orchestration_git import (
    PatchTruth,
    applied_integrity_matches,
)
from scripts.factory_orchestration_git_process import checkout_identity_sha256
from scripts.factory_orchestration_models import OrchestrationRequest
from scripts.factory_scheduler_queries import lease_row, read_assignment, read_execution_for_job
from scripts.factory_scheduler_receipts import parse_utc
from scripts.factory_scheduler_storage import readonly_connection
from scripts.factory_scheduler_storage_fs import SchedulerStateError


def validate_scheduler_authority(root: Path, request: OrchestrationRequest) -> None:
    try:
        with readonly_connection(root) as connection:
            connection.execute("BEGIN")
            assignment = read_assignment(connection, job_id=request.job_id)
            execution = read_execution_for_job(connection, job_id=request.job_id)
            current_lease = lease_row(connection)
            connection.execute("COMMIT")
    except (SchedulerStateError, sqlite3.DatabaseError, ValidationError) as exc:
        raise OrchestrationServiceError("authority-mismatch") from exc
    if assignment is None or execution is None or current_lease is None:
        raise OrchestrationServiceError("authority-mismatch")
    candidate = assignment.request
    delivery = candidate.delivery_authority
    if (
        assignment.state != "active"
        or assignment.assignment_id != request.assignment_id
        or candidate.issue_number != request.issue_number
        or candidate.job_id != request.job_id
        or candidate.worktree_id != request.worktree_id
        or candidate.access_mode != "write"
        or delivery is None
        or delivery.selector_digest != request.selector_digest
        or delivery.selection_digest != request.selection_digest
        or delivery.autonomy_tier != request.autonomy_tier
        or delivery.verification_lane != request.verification_lane
        or delivery.allowed_scopes != request.allowed_scopes
        or delivery.allowed_scope_digest != request.allowed_scope_digest
        or assignment.lease_owner_id != request.scheduler_owner_id
        or assignment.lease_owner_pid != request.scheduler_owner_pid
        or assignment.lease_owner_start_token != request.scheduler_owner_start_token
        or assignment.lease_epoch != request.scheduler_owner_epoch
        or execution.lease_owner_id != request.scheduler_owner_id
        or execution.lease_owner_pid != request.scheduler_owner_pid
        or execution.lease_owner_start_token != request.scheduler_owner_start_token
        or execution.lease_epoch != request.scheduler_owner_epoch
        or execution.phase != "completed-unsettled"
        or execution.evidence_digest != request.proposal_sha256
        or current_lease[0] != request.scheduler_owner_id
        or current_lease[1] != request.scheduler_owner_pid
        or current_lease[2] != request.scheduler_owner_start_token
        or current_lease[3] != request.scheduler_owner_epoch
        or parse_utc(current_lease[6]) <= datetime.now(UTC)
    ):
        raise OrchestrationServiceError("authority-mismatch")


def validate_delivery_policy(root: Path, request: OrchestrationRequest) -> None:
    try:
        matches = selector_policy_digest(root) == request.selector_digest
    except DeliveryAdmissionError as exc:
        raise OrchestrationServiceError("authority-mismatch") from exc
    if not matches:
        raise OrchestrationServiceError("authority-mismatch")


def authority_and_integrity(
    root: Path,
    request: OrchestrationRequest,
    truth: PatchTruth,
    *,
    main_identity: str | None = None,
) -> bool:
    try:
        validate_scheduler_authority(root, request)
        validate_delivery_policy(root, request)
        return applied_integrity_matches(request, truth) and (
            main_identity is None or checkout_identity_sha256(root) == main_identity
        )
    except (OrchestrationGitError, OrchestrationServiceError):
        return False
