"""Replay completion from the durable merged/cleanup scheduler proof."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_orchestration_models import OrchestrationRequest
from scripts.factory_pr_delivery_journal_cleanup_records import DeliveryCleanupRecord
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_record,
    read_terminal_receipt,
    validate_record,
)
from scripts.factory_pr_delivery_journal_storage import journal_connection
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_execution_models import ExecutionState
from scripts.factory_scheduler_models import LeaseOwner, StoredAssignment
from scripts.factory_scheduler_queries import read_assignment, read_execution_for_job
from scripts.factory_scheduler_storage import readonly_connection
from scripts.factory_scheduler_storage_fs import SchedulerStateError

__all__ = ["DeliverySchedulerCompletionError", "complete_scheduler_completion"]


class DeliverySchedulerCompletionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class _SchedulerSnapshot:
    assignment: StoredAssignment
    execution: ExecutionState


def complete_scheduler_completion(
    root: Path,
    envelope: DeliveryEnvelope,
) -> DeliveryJournalRecord:
    record = _load_journal_snapshot(root, envelope)
    cleanup = record.cleanup
    if cleanup is None:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    _assert_terminal(cleanup=cleanup, record=record)

    if record.lifecycle != "merged" or record.reason != "cleanup-pending":
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")

    request = envelope.orchestration_request
    snapshot = _read_scheduler_state(root, request)

    if _is_exact_completed(request, cleanup, snapshot):
        return record

    if cleanup.phase_version == 5:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    if cleanup.phase_version != 4:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    if not _is_active_for_completion(request, cleanup, snapshot):
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")

    try:
        _complete_scheduler(root=root, request=request, cleanup=cleanup)
    except RuntimeError:
        _ensure_exact_completion_after_call(root, request, cleanup)
        return record

    _ensure_exact_completion_after_call(root, request, cleanup)
    return record


def _load_journal_snapshot(
    root: Path,
    envelope: DeliveryEnvelope,
) -> DeliveryJournalRecord:
    try:
        resolved = root.resolve(strict=True)
        envelope_root = envelope.main_root.resolve(strict=True)
        if resolved != envelope_root:
            raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
        with journal_connection(resolved) as connection:
            record = read_record(connection, envelope.request.request_id)
        if record is None:
            raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
        validate_record(envelope, record)
        if record.cleanup is None:
            raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
        return record
    except (
        sqlite3.DatabaseError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        DeliveryJournalError,
    ):
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid") from None


def _read_scheduler_state(
    root: Path,
    request: OrchestrationRequest,
) -> _SchedulerSnapshot:
    try:
        with readonly_connection(root) as connection:
            assignment = read_assignment(connection, job_id=request.job_id)
            execution = read_execution_for_job(connection, job_id=request.job_id)
    except (
        sqlite3.DatabaseError,
        ValidationError,
        TypeError,
        ValueError,
        SchedulerStateError,
    ):
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid") from None
    if assignment is None or execution is None:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    return _SchedulerSnapshot(
        assignment=assignment,
        execution=execution,
    )


def _read_scheduler_after(
    root: Path,
    request: OrchestrationRequest,
) -> _SchedulerSnapshot:
    snapshot = _read_scheduler_state(root, request)
    if not _common_scheduler_binding(request, snapshot):
        raise DeliverySchedulerCompletionError("scheduler-completion-uncertain")
    return snapshot


def _ensure_exact_completion_after_call(
    root: Path,
    request: OrchestrationRequest,
    cleanup: DeliveryCleanupRecord,
) -> None:
    try:
        snapshot = _read_scheduler_after(root, request)
    except DeliverySchedulerCompletionError:
        raise DeliverySchedulerCompletionError("scheduler-completion-uncertain") from None
    if not _is_exact_completed(request, cleanup, snapshot):
        raise DeliverySchedulerCompletionError("scheduler-completion-uncertain")


def _complete_scheduler(
    *,
    root: Path,
    request: OrchestrationRequest,
    cleanup: DeliveryCleanupRecord,
) -> None:
    completed_at = cleanup.scheduler_completion_at
    if completed_at is None:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    start_marker = cleanup.scheduler_owner_start_token
    FactoryScheduler(root).complete_assignment(
        assignment_id=request.assignment_id,
        owner=LeaseOwner(
            owner_id=cleanup.scheduler_owner_id,
            pid=cleanup.scheduler_owner_pid,
            process_start_token=start_marker,
        ),
        epoch=cleanup.scheduler_owner_epoch,
        expected_phase_version=cleanup.scheduler_phase_version,
        completed_at=completed_at,
    )


def _assert_terminal(
    *,
    cleanup: DeliveryCleanupRecord,
    record: DeliveryJournalRecord,
) -> None:
    terminal = read_terminal_receipt(record)
    if terminal is None:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    if terminal.lifecycle != "merged" or terminal.reason != "cleanup-pending":
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")
    if cleanup.request_id != record.request_id:
        raise DeliverySchedulerCompletionError("scheduler-completion-invalid")


def _common_scheduler_binding(
    request: OrchestrationRequest,
    snapshot: _SchedulerSnapshot,
) -> bool:
    authority = snapshot.assignment.request.delivery_authority
    return (
        snapshot.assignment.assignment_id == request.assignment_id
        and snapshot.assignment.request.request_id == request.request_id
        and snapshot.assignment.request.job_id == request.job_id
        and snapshot.assignment.request.issue_number == request.issue_number
        and snapshot.assignment.request.worktree_id == request.worktree_id
        and snapshot.assignment.request.worker_class == "free-local"
        and snapshot.assignment.request.access_mode == "write"
        and authority is not None
        and authority.selector_digest == request.selector_digest
        and authority.selection_digest == request.selection_digest
        and authority.autonomy_tier == request.autonomy_tier
        and authority.verification_lane == request.verification_lane
        and authority.allowed_scopes == request.allowed_scopes
        and authority.allowed_scope_digest == request.allowed_scope_digest
        and snapshot.assignment.lease_owner_id == request.scheduler_owner_id
        and snapshot.assignment.lease_owner_pid == request.scheduler_owner_pid
        and snapshot.assignment.lease_owner_start_token == request.scheduler_owner_start_token
        and snapshot.assignment.lease_epoch == request.scheduler_owner_epoch
        and snapshot.execution.lease_owner_id == request.scheduler_owner_id
        and snapshot.execution.lease_owner_pid == request.scheduler_owner_pid
        and snapshot.execution.lease_owner_start_token == request.scheduler_owner_start_token
        and snapshot.execution.lease_epoch == request.scheduler_owner_epoch
        and snapshot.execution.assignment_id == request.assignment_id
        and snapshot.execution.evidence_digest == request.proposal_sha256
    )


def _is_active_for_completion(
    request: OrchestrationRequest,
    cleanup: DeliveryCleanupRecord,
    snapshot: _SchedulerSnapshot,
) -> bool:
    return (
        snapshot.assignment.state == "active"
        and snapshot.assignment.completed_at is None
        and snapshot.execution.phase == "completed-unsettled"
        and snapshot.execution.phase_version == cleanup.scheduler_phase_version
        and snapshot.execution.terminal_outcome is None
        and _common_scheduler_binding(request, snapshot)
    )


def _is_exact_completed(
    request: OrchestrationRequest,
    cleanup: DeliveryCleanupRecord,
    snapshot: _SchedulerSnapshot,
) -> bool:
    return (
        snapshot.assignment.state == "completed"
        and snapshot.assignment.completed_at == cleanup.scheduler_completion_at
        and snapshot.execution.phase == "completed"
        and snapshot.execution.phase_changed_at == cleanup.scheduler_completion_at
        and snapshot.execution.phase_version == cleanup.scheduler_phase_version + 1
        and snapshot.execution.terminal_outcome == "completed"
        and _common_scheduler_binding(request, snapshot)
    )
