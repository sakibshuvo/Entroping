"""Durable intent-before-mutation lifecycle for exact proposal delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal_cleanup import persist_cleanup_intent
from scripts.factory_pr_delivery_journal_cleanup_proofs import persist_remote_absent
from scripts.factory_pr_delivery_journal_completed import persist_completed_receipt
from scripts.factory_pr_delivery_journal_finish_proof import persist_finish_cleaned
from scripts.factory_pr_delivery_journal_merge import (
    persist_merge_intent,
    persist_merged_receipt,
)
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    JournalLifecycle,
    JournalReason,
    read_record,
    validate_record,
)
from scripts.factory_pr_delivery_journal_scheduler_completed import (
    persist_scheduler_completed,
)
from scripts.factory_pr_delivery_journal_scheduler_intent import (
    persist_scheduler_completion_intent,
)
from scripts.factory_pr_delivery_journal_storage import journal_connection
from scripts.factory_pr_delivery_models import (
    DeliveryEnvelope,
    approved_path_digest,
)
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority


class DeliveryJournal:
    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def prepare(
        self, envelope: DeliveryEnvelope, *, observed_at: datetime | None = None
    ) -> DeliveryJournalRecord:
        with journal_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = read_record(connection, envelope.request.request_id)
            if existing is not None:
                connection.execute("COMMIT")
                validate_record(envelope, existing)
                if existing.lifecycle == "uncertain":
                    raise DeliveryJournalError("uncertain-recovery-required")
                return existing
            receipt = envelope.orchestration_receipt
            timestamp = _timestamp(observed_at)
            connection.execute(
                "INSERT INTO delivery_lifecycle("
                "request_id, request_digest, envelope_digest, issue_number, assignment_id, "
                "worktree_id, lifecycle, reason, accepted_local_head, accepted_diff_sha256, "
                "accepted_manifest_sha256, approved_path_sha256, body_sha256, phase_version, "
                "created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, 'prepared', 'none', "
                "?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    envelope.request.request_id,
                    envelope.request.request_digest,
                    envelope.envelope_digest,
                    envelope.orchestration_request.issue_number,
                    envelope.orchestration_request.assignment_id,
                    envelope.orchestration_request.worktree_id,
                    envelope.orchestration_request.base_commit,
                    receipt.diff_sha256,
                    receipt.result_manifest_sha256,
                    approved_path_digest(receipt.approved_paths),
                    envelope.request.pr_body_sha256,
                    1,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute("COMMIT")
            record = read_record(connection, envelope.request.request_id)
            if record is None:
                raise DeliveryJournalError("journal-invalid")
            return record

    def read(self, envelope: DeliveryEnvelope) -> DeliveryJournalRecord | None:
        """Read and validate one request without advancing its lifecycle."""

        with journal_connection(self._root) as connection:
            record = read_record(connection, envelope.request.request_id)
        if record is not None:
            validate_record(envelope, record)
        return record

    def commit_intent(
        self,
        envelope: DeliveryEnvelope,
        *,
        committed_head: str,
        commit_parent: str,
        commit_tree: str,
        observed_at: datetime | None = None,
    ) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="prepared",
            lifecycle="commit-intent",
            reason="none",
            committed_head=committed_head,
            commit_parent=commit_parent,
            commit_tree=commit_tree,
            observed_at=observed_at,
        )

    def committed(
        self, envelope: DeliveryEnvelope, *, observed_at: datetime | None = None
    ) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="commit-intent",
            lifecycle="committed",
            reason="committed",
            observed_at=observed_at,
        )

    def push_intent(
        self, envelope: DeliveryEnvelope, *, observed_at: datetime | None = None
    ) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="committed",
            lifecycle="push-intent",
            reason="committed",
            observed_at=observed_at,
        )

    def pushed(
        self,
        envelope: DeliveryEnvelope,
        *,
        remote_head: str,
        observed_at: datetime | None = None,
    ) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="push-intent",
            lifecycle="pushed",
            reason="pushed",
            remote_head=remote_head,
            observed_at=observed_at,
        )

    def merge_intent(
        self,
        envelope: DeliveryEnvelope,
        *,
        pr_number: int,
        merge_head: str,
        ci_digest: str,
        observed_at: datetime | None = None,
    ) -> DeliveryJournalRecord:
        return persist_merge_intent(
            self._root,
            envelope,
            pr_number=pr_number,
            merge_head=merge_head,
            ci_digest=ci_digest,
            observed_at=observed_at,
        )

    def merged(
        self,
        envelope: DeliveryEnvelope,
        *,
        merged_head: str,
        observed_at: datetime | None = None,
    ) -> DeliveryJournalRecord:
        return persist_merged_receipt(
            self._root,
            envelope,
            merged_head=merged_head,
            observed_at=observed_at,
        )

    def cleanup_intent(
        self,
        envelope: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
        observed_at: datetime,
    ) -> DeliveryJournalRecord:
        return persist_cleanup_intent(
            self._root,
            envelope,
            authority=authority,
            observed_at=observed_at,
        )

    def remote_absent(
        self,
        envelope: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
        observed_at: datetime,
    ) -> DeliveryJournalRecord:
        return persist_remote_absent(
            self._root,
            envelope,
            authority=authority,
            observed_at=observed_at,
        )

    def finish_cleaned(
        self,
        envelope: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
        observed_at: datetime,
    ) -> DeliveryJournalRecord:
        return persist_finish_cleaned(
            self._root,
            envelope,
            authority=authority,
            observed_at=observed_at,
        )

    def scheduler_completion_intent(
        self,
        envelope: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
        observed_at: datetime,
    ) -> DeliveryJournalRecord:
        return persist_scheduler_completion_intent(
            self._root,
            envelope,
            authority=authority,
            observed_at=observed_at,
        )

    def scheduler_completed(
        self,
        envelope: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
    ) -> DeliveryJournalRecord:
        return persist_scheduler_completed(
            self._root,
            envelope,
            authority=authority,
        )

    def completed(self, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
        return persist_completed_receipt(self._root, envelope)

    def recover(
        self,
        envelope: DeliveryEnvelope,
        *,
        local_head: str,
        remote_head: str,
    ) -> DeliveryJournalRecord:
        with journal_connection(self._root) as connection:
            record = read_record(connection, envelope.request.request_id)
        if record is None:
            raise DeliveryJournalError("request-conflict")
        validate_record(envelope, record)
        if record.lifecycle == "commit-intent" and local_head == record.committed_head:
            return self.committed(envelope)
        if record.lifecycle == "push-intent" and remote_head == record.committed_head:
            return self.pushed(envelope, remote_head=remote_head)
        safe_commit_retry = (
            record.lifecycle == "commit-intent"
            and local_head == record.accepted_local_head
            and remote_head == record.accepted_local_head
        )
        safe_push_retry = (
            record.lifecycle == "push-intent"
            and local_head == record.committed_head
            and remote_head == record.accepted_local_head
        )
        if safe_commit_retry or safe_push_retry:
            return record
        return self._transition(
            envelope,
            expected=record.lifecycle,
            lifecycle="uncertain",
            reason="interrupted",
        )

    def _transition(
        self,
        envelope: DeliveryEnvelope,
        *,
        expected: JournalLifecycle,
        lifecycle: JournalLifecycle,
        reason: JournalReason,
        committed_head: str | None = None,
        remote_head: str | None = None,
        commit_parent: str | None = None,
        commit_tree: str | None = None,
        observed_at: datetime | None = None,
    ) -> DeliveryJournalRecord:
        with journal_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = read_record(connection, envelope.request.request_id)
            if record is None or record.lifecycle != expected:
                connection.execute("ROLLBACK")
                raise DeliveryJournalError("request-conflict")
            validate_record(envelope, record)
            timestamp = _timestamp(observed_at, prior=record.updated_at)
            values = (
                lifecycle,
                reason,
                committed_head if committed_head is not None else record.committed_head,
                remote_head if remote_head is not None else record.remote_head,
                commit_parent if commit_parent is not None else record.commit_parent,
                commit_tree if commit_tree is not None else record.commit_tree,
                record.phase_version + 1,
                timestamp,
                record.request_id,
                expected,
            )
            changed = connection.execute(
                "UPDATE delivery_lifecycle SET lifecycle = ?, reason = ?, committed_head = ?, "
                "remote_head = ?, commit_parent = ?, commit_tree = ?, phase_version = ?, "
                "updated_at_utc = ? WHERE request_id = ? AND lifecycle = ?",
                values,
            ).rowcount
            if changed != 1:
                connection.execute("ROLLBACK")
                raise DeliveryJournalError("request-conflict")
            connection.execute("COMMIT")
            updated = read_record(connection, record.request_id)
            if updated is None:
                raise DeliveryJournalError("journal-invalid")
            return updated


def _timestamp(observed_at: datetime | None, *, prior: datetime | None = None) -> str:
    if observed_at is None:
        candidate = datetime.now(UTC)
    elif not isinstance(observed_at, datetime):
        raise DeliveryJournalError("journal-invalid")
    else:
        try:
            if observed_at.utcoffset() is None:
                raise DeliveryJournalError("journal-invalid")
            candidate = observed_at.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            raise DeliveryJournalError("journal-invalid") from None
    if prior is not None:
        candidate = max(candidate, prior.astimezone(UTC))
    return candidate.isoformat()
