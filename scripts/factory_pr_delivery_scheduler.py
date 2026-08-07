"""Scheduler completion authority revalidation for strict delivery replay."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import Field, ValidationError

from scripts.factory_pr_delivery_models import DeliveryEnvelope, DeliveryGitError
from scripts.factory_scheduler_execution_models import PhaseVersion
from scripts.factory_scheduler_models import Identifier, PositiveEpoch, ProcessToken
from scripts.factory_scheduler_queries import read_assignment, read_execution_for_job
from scripts.factory_scheduler_storage import readonly_connection
from scripts.factory_scheduler_storage_fs import SchedulerStateError


@dataclass(frozen=True, slots=True)
class SchedulerCompletionAuthority:
    owner_id: Identifier
    owner_pid: Annotated[int, Field(ge=1, le=2_147_483_647)]
    owner_start_token: ProcessToken
    epoch: PositiveEpoch
    phase_version: PhaseVersion


def validate_scheduler_authority(
    repo_root: Path,
    envelope: DeliveryEnvelope,
) -> SchedulerCompletionAuthority:
    """Read stored scheduler identity and completion evidence without live-lease checks."""

    request = envelope.orchestration_request
    try:
        with readonly_connection(repo_root) as connection:
            connection.execute("BEGIN")
            assignment = read_assignment(connection, job_id=request.job_id)
            execution = read_execution_for_job(connection, job_id=request.job_id)
            connection.execute("COMMIT")
        if assignment is None or execution is None:
            raise DeliveryGitError("authority-mismatch")
        stored = assignment.request
        authority = stored.delivery_authority
        if (
            assignment.state != "active"
            or assignment.assignment_id != request.assignment_id
            or stored.request_id != request.request_id
            or stored.issue_number != request.issue_number
            or stored.job_id != request.job_id
            or stored.worktree_id != request.worktree_id
            or stored.worker_class != "free-local"
            or stored.access_mode != "write"
            or authority is None
            or authority.selector_digest != request.selector_digest
            or authority.selection_digest != request.selection_digest
            or authority.autonomy_tier != request.autonomy_tier
            or authority.verification_lane != request.verification_lane
            or authority.allowed_scopes != request.allowed_scopes
            or authority.allowed_scope_digest != request.allowed_scope_digest
            or assignment.lease_owner_id != request.scheduler_owner_id
            or assignment.lease_owner_pid != request.scheduler_owner_pid
            or assignment.lease_owner_start_token != request.scheduler_owner_start_token
            or assignment.lease_epoch != request.scheduler_owner_epoch
            or execution.lease_owner_id != request.scheduler_owner_id
            or execution.lease_owner_pid != request.scheduler_owner_pid
            or execution.lease_owner_start_token != request.scheduler_owner_start_token
            or execution.lease_epoch != request.scheduler_owner_epoch
            or execution.assignment_id != request.assignment_id
            or execution.phase != "completed-unsettled"
            or execution.evidence_digest != request.proposal_sha256
        ):
            raise DeliveryGitError("authority-mismatch")
    except (
        SchedulerStateError,
        sqlite3.DatabaseError,
        ValidationError,
        TypeError,
        ValueError,
        AttributeError,
        DeliveryGitError,
    ):
        raise DeliveryGitError("authority-mismatch") from None
    start_marker = execution.lease_owner_start_token
    return SchedulerCompletionAuthority(
        owner_id=execution.lease_owner_id,
        owner_pid=execution.lease_owner_pid,
        owner_start_token=start_marker,
        epoch=execution.lease_epoch,
        phase_version=execution.phase_version,
    )
