"""Durable intent-before-mutation lifecycle for exact proposal delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    JournalReason,
    read_record,
    validate_record,
)
from scripts.factory_pr_delivery_journal_storage import journal_connection
from scripts.factory_pr_delivery_models import (
    DeliveryEnvelope,
    DeliveryLifecycle,
    approved_path_digest,
)


class DeliveryJournal:
    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def prepare(self, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
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
                    _now(),
                    _now(),
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
    ) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="prepared",
            lifecycle="commit-intent",
            reason="none",
            committed_head=committed_head,
            commit_parent=commit_parent,
            commit_tree=commit_tree,
        )

    def committed(self, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="commit-intent",
            lifecycle="committed",
            reason="committed",
        )

    def push_intent(self, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="committed",
            lifecycle="push-intent",
            reason="committed",
        )

    def pushed(self, envelope: DeliveryEnvelope, *, remote_head: str) -> DeliveryJournalRecord:
        return self._transition(
            envelope,
            expected="push-intent",
            lifecycle="pushed",
            reason="pushed",
            remote_head=remote_head,
        )

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
        expected: DeliveryLifecycle,
        lifecycle: DeliveryLifecycle,
        reason: JournalReason,
        committed_head: str | None = None,
        remote_head: str | None = None,
        commit_parent: str | None = None,
        commit_tree: str | None = None,
    ) -> DeliveryJournalRecord:
        with journal_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = read_record(connection, envelope.request.request_id)
            if record is None or record.lifecycle != expected:
                connection.execute("ROLLBACK")
                raise DeliveryJournalError("request-conflict")
            validate_record(envelope, record)
            values = (
                lifecycle,
                reason,
                committed_head if committed_head is not None else record.committed_head,
                remote_head if remote_head is not None else record.remote_head,
                commit_parent if commit_parent is not None else record.commit_parent,
                commit_tree if commit_tree is not None else record.commit_tree,
                record.phase_version + 1,
                _now(),
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


def _now() -> str:
    return datetime.now(UTC).isoformat()
