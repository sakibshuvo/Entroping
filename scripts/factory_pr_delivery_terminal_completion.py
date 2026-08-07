"""Advance durable terminal completion proofs one bounded step."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_cleanup import run_strict_finish_issue
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_journal_cleanup_records import DeliveryCleanupRecord
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope, DeliveryGitError
from scripts.factory_pr_delivery_receipts import DeliveryReceipt
from scripts.factory_pr_delivery_scheduler import (
    SchedulerCompletionAuthority,
    validate_scheduler_authority,
)
from scripts.factory_pr_delivery_scheduler_completion import complete_scheduler_completion
from scripts.factory_pr_delivery_ssh import delete_remote_branch

__all__ = ["advance_terminal_completion"]


def advance_terminal_completion(
    root: Path,
    envelope: DeliveryEnvelope,
    *,
    now: Callable[[], datetime],
) -> DeliveryReceipt:
    resolved_root = _resolve_root(root, envelope)
    subject = DeliveryJournal(resolved_root)
    record = subject.read(envelope)
    if record is None:
        raise DeliveryJournalError("request-conflict")

    terminal = _extract_terminal(record)

    if _is_completed_replay(record, terminal):
        return terminal

    if terminal.lifecycle != "merged" or terminal.reason != "cleanup-pending":
        raise DeliveryJournalError("journal-invalid")

    if record.cleanup is None:
        authority = validate_scheduler_authority(resolved_root, envelope)
        observed_at = _proof_time(now=now, previous=terminal.updated_at)
        updated = subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
        return _extract_terminal(updated)

    cleanup = record.cleanup
    authority = _extract_authority(cleanup)

    if cleanup.phase_version == 1:
        _require_matching_authority(resolved_root, envelope, authority)
        if cleanup.cleanup_intent_at is None:
            raise DeliveryJournalError("journal-invalid")
        observed_at = _proof_time(now=now, previous=cleanup.cleanup_intent_at)
        run_strict_finish_issue(resolved_root, envelope, record)
        updated = subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
        return _extract_terminal(updated)

    if cleanup.phase_version == 2:
        _require_matching_authority(resolved_root, envelope, authority)
        if cleanup.finish_cleanup_at is None:
            raise DeliveryJournalError("journal-invalid")
        observed_at = _proof_time(now=now, previous=cleanup.finish_cleanup_at)
        _ = delete_remote_branch(
            envelope.worktree_path,
            branch=cleanup.remote_branch,
            expected_head=cleanup.expected_remote_head,
        )
        updated = subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
        return _extract_terminal(updated)

    if cleanup.phase_version == 3:
        _require_matching_authority(resolved_root, envelope, authority)
        if cleanup.remote_absent_at is None:
            raise DeliveryJournalError("journal-invalid")
        observed_at = _proof_time(now=now, previous=cleanup.remote_absent_at)
        _ = subject.scheduler_completion_intent(
            envelope,
            authority=authority,
            observed_at=observed_at,
        )
        phase_record = subject.read(envelope)
        if phase_record is None:
            raise DeliveryJournalError("journal-invalid")
        return _extract_terminal(phase_record)

    if cleanup.phase_version == 4:
        _ = complete_scheduler_completion(resolved_root, envelope)
        updated = subject.scheduler_completed(
            envelope,
            authority=authority,
        )
        return _extract_terminal(updated)

    if cleanup.phase_version == 5:
        updated = subject.completed(envelope)
        return _extract_terminal(updated)

    raise DeliveryJournalError("journal-invalid")


def _resolve_root(root: Path, envelope: DeliveryEnvelope) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_envelope = envelope.main_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DeliveryJournalError("journal-invalid") from exc
    if resolved_root != resolved_envelope:
        raise DeliveryJournalError("journal-invalid")
    return resolved_root


def _extract_terminal(record: DeliveryJournalRecord) -> DeliveryReceipt:
    terminal = read_terminal_receipt(record)
    if terminal is None:
        raise DeliveryJournalError("journal-invalid")
    return terminal


def _is_completed_replay(
    record: DeliveryJournalRecord,
    terminal: DeliveryReceipt,
) -> bool:
    cleanup = record.cleanup
    return (
        terminal.lifecycle == "completed"
        and terminal.reason == "completed"
        and cleanup is not None
        and terminal.updated_at == cleanup.scheduler_completed_at
        and cleanup.phase_version == 5
        and cleanup.scheduler_completion_at is not None
        and cleanup.scheduler_completed_at is not None
        and cleanup.scheduler_completion_at == cleanup.scheduler_completed_at
    )


def _extract_authority(cleanup: DeliveryCleanupRecord) -> SchedulerCompletionAuthority:
    start_marker = cleanup.scheduler_owner_start_token
    return SchedulerCompletionAuthority(
        owner_id=cleanup.scheduler_owner_id,
        owner_pid=cleanup.scheduler_owner_pid,
        owner_start_token=start_marker,
        epoch=cleanup.scheduler_owner_epoch,
        phase_version=cleanup.scheduler_phase_version,
    )


def _require_matching_authority(
    root: Path,
    envelope: DeliveryEnvelope,
    stored: SchedulerCompletionAuthority,
) -> None:
    live = validate_scheduler_authority(root, envelope)
    if live != stored:
        raise DeliveryGitError("authority-mismatch")


def _proof_time(*, now: Callable[[], datetime], previous: datetime) -> datetime:
    try:
        observed = now()
        if (
            not isinstance(observed, datetime)
            or observed.tzinfo is None
            or observed.utcoffset() is None
        ):
            raise TypeError("clock must return an aware datetime")
        if previous.tzinfo is None or previous.utcoffset() is None:
            raise TypeError("prior proof must include an aware datetime")
        observed_utc = observed.astimezone(UTC)
        previous_utc = previous.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DeliveryJournalError("journal-invalid") from exc

    if observed_utc < previous_utc:
        return previous_utc
    return observed_utc
