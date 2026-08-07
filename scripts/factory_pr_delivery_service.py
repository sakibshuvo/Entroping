"""Plan-first composition of accepted delivery, GitHub, and merge boundaries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_git import commit_exact_diff
from scripts.factory_pr_delivery_git_io import git_text
from scripts.factory_pr_delivery_github import REPOSITORY, GitHubDeliveryPort
from scripts.factory_pr_delivery_github_models import evaluate_ci
from scripts.factory_pr_delivery_io import DeliveryInputError, load_delivery_envelope
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import CommitResult, DeliveryEnvelope
from scripts.factory_pr_delivery_receipts import DeliveryReceipt, DeliveryReceiptReason
from scripts.factory_pr_delivery_scheduler import validate_scheduler_authority
from scripts.factory_pr_delivery_service_replay import prepare_delivery_apply
from scripts.factory_pr_delivery_service_support import (
    DeliveryServiceError,
    DeliveryServiceSupport,
    digest_model,
)
from scripts.factory_pr_delivery_ssh import PushResult, push_exact_commit

__all__ = ["DeliveryService", "DeliveryServiceError"]


class DeliveryService(DeliveryServiceSupport):
    def __init__(
        self,
        repo_root: Path,
        *,
        github: GitHubDeliveryPort,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.github = github
        self._now = now or (lambda: datetime.now(UTC))

    def deliver(self, request_path: Path, *, apply: bool) -> DeliveryReceipt:
        try:
            envelope = load_delivery_envelope(request_path)
        except DeliveryInputError as exc:
            raise DeliveryServiceError(exc.code) from None
        if envelope.main_root != self.repo_root:
            raise DeliveryServiceError("authority-mismatch")
        request = envelope.orchestration_request
        journal: DeliveryJournal | None = None
        if apply:
            try:
                journal, terminal = prepare_delivery_apply(
                    self.repo_root,
                    envelope,
                    now=self._aware_now,
                )
                if terminal is not None:
                    return terminal
            except DeliveryJournalError as exc:
                raise DeliveryServiceError(exc.code) from None
            except RuntimeError as exc:
                raise DeliveryServiceError(str(exc)) from None

        now = self._aware_now()
        issue = self._observe_issue(request.issue_number)
        self._validate_issue_and_body(envelope, issue)
        protection = self._observe_protection(request.base_commit)
        existing = self.github.observe_pull_requests(
            REPOSITORY,
            request.issue_number,
            request.branch,
        )
        if len(existing) > 1:
            return self._receipt(
                envelope,
                lifecycle="blocked",
                reason="pr-conflict",
                authoritative=apply,
                accepted_local_head=request.base_commit,
                now=now,
            )
        if not apply:
            return self._plan_receipt(
                envelope,
                existing,
                protection,
                issue.title,
                now,
            )

        if journal is None:
            raise DeliveryServiceError("journal-invalid")
        try:
            validate_scheduler_authority(self.repo_root, envelope)
            result, pushed = self._apply_git(envelope, now=now, journal=journal)
            pull = self._ensure_pull_request(envelope, issue.title)
            self._validate_pull(pull, envelope, result.committed_head, issue.title)
            protection = self._observe_protection(pull.base_sha)
            ci = self.github.observe_ci(
                REPOSITORY,
                pr_number=pull.number,
                head_sha=result.committed_head,
                protection=protection,
            )
            ready, ci_reason = evaluate_ci(protection, ci)
            ci_digest = digest_model(ci)
            if not ready:
                reason: DeliveryReceiptReason = (
                    "ci-pending"
                    if ci_reason
                    in {"visible-check-not-terminal", "required-check-not-green"}
                    else "ci-failed"
                )
                return self._receipt(
                    envelope,
                    lifecycle="pushed",
                    reason=reason,
                    authoritative=True,
                    accepted_local_head=result.accepted_local_head,
                    committed_head=result.committed_head,
                    remote_head=pushed.remote_head,
                    pr_number=pull.number,
                    ci_digest=ci_digest,
                    now=now,
                )
            journal.merge_intent(
                envelope,
                pr_number=pull.number,
                merge_head=result.committed_head,
                ci_digest=ci_digest,
                observed_at=now,
            )
            merged = self.github.merge_pull_request(
                REPOSITORY,
                pr_number=pull.number,
                head_sha=result.committed_head,
            )
            if merged.state == "uncertain":
                journal.recover(
                    envelope,
                    local_head=result.committed_head,
                    remote_head=result.committed_head,
                )
                raise DeliveryServiceError("uncertain-recovery-required")
            if merged.state not in {"merged", "already-merged"}:
                return self._receipt(
                    envelope=envelope,
                    lifecycle="blocked",
                    reason="merge-rejected",
                    authoritative=True,
                    accepted_local_head=result.accepted_local_head,
                    pr_number=pull.number,
                    ci_digest=ci_digest,
                    now=now,
                )
            if merged.merged_head is None:
                journal.recover(
                    envelope,
                    local_head=result.committed_head,
                    remote_head=pushed.remote_head,
                )
                raise DeliveryServiceError("uncertain-recovery-required")
            terminal = read_terminal_receipt(
                journal.merged(envelope, merged_head=merged.merged_head, observed_at=now)
            )
            if terminal is None:
                raise DeliveryServiceError("journal-invalid")
            return terminal
        except DeliveryJournalError as exc:
            raise DeliveryServiceError(exc.code) from None
        except RuntimeError as exc:
            raise DeliveryServiceError(str(exc)) from None

    def _apply_git(
        self, envelope: DeliveryEnvelope, *, now: datetime, journal: DeliveryJournal
    ) -> tuple[CommitResult, PushResult]:
        """Apply or replay the journaled local commit and exact branch push."""

        record = journal.read(envelope)
        request = envelope.orchestration_request
        receipt = envelope.orchestration_receipt
        if record is None or record.lifecycle == "prepared":
            result = commit_exact_diff(
                self.repo_root,
                envelope,
                committed_at=now,
                journal=journal,
            )
            _ = journal.push_intent(envelope, observed_at=now)
            pushed = push_exact_commit(
                envelope.worktree_path,
                branch=request.branch,
                committed_head=result.committed_head,
            )
            _ = journal.pushed(
                envelope, remote_head=pushed.remote_head, observed_at=now
            )
            return result, pushed
        if record.lifecycle == "uncertain":
            raise DeliveryServiceError("uncertain-recovery-required")
        if record.lifecycle == "commit-intent":
            local_head = git_text(envelope.worktree_path, "rev-parse", "HEAD")
            if local_head != record.committed_head:
                raise DeliveryServiceError("commit-recovery-required")
            _ = journal.recover(
                envelope,
                local_head=local_head,
                remote_head=request.base_commit,
            )
            record = journal.read(envelope)
            if record is None or record.lifecycle != "committed":
                raise DeliveryServiceError("uncertain-recovery-required")
        if record.committed_head is None:
            raise DeliveryServiceError("journal-invalid")
        committed_head = record.committed_head
        if record.lifecycle == "committed":
            _ = journal.push_intent(envelope, observed_at=now)
            record = journal.read(envelope)
            if record is None:
                raise DeliveryServiceError("journal-invalid")
        if record.lifecycle == "push-intent":
            pushed = push_exact_commit(
                envelope.worktree_path,
                branch=request.branch,
                committed_head=committed_head,
            )
            _ = journal.pushed(
                envelope, remote_head=pushed.remote_head, observed_at=now
            )
            record = journal.read(envelope)
            if record is None:
                raise DeliveryServiceError("journal-invalid")
        if record.lifecycle != "pushed" or record.remote_head is None:
            raise DeliveryServiceError("journal-invalid")
        commit_parent = record.commit_parent
        commit_tree = record.commit_tree
        if commit_parent is None or commit_tree is None:
            raise DeliveryServiceError("journal-invalid")
        if receipt.diff_sha256 is None or receipt.result_manifest_sha256 is None:
            raise DeliveryServiceError("journal-invalid")
        result = CommitResult(
            accepted_local_head=request.base_commit,
            committed_head=committed_head,
            commit_parent=commit_parent,
            commit_tree=commit_tree,
            accepted_diff_sha256=receipt.diff_sha256,
            committed_diff_sha256=receipt.diff_sha256,
            accepted_manifest_sha256=receipt.result_manifest_sha256,
            committed_manifest_sha256=receipt.result_manifest_sha256,
            approved_path_sha256=record.approved_path_sha256,
        )
        return result, PushResult("replay", record.remote_head)
