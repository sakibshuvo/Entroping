"""Plan-first composition of accepted delivery, GitHub, and merge boundaries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_git import commit_exact_diff
from scripts.factory_pr_delivery_github import (
    REPOSITORY,
    GitHubDeliveryError,
    GitHubDeliveryPort,
)
from scripts.factory_pr_delivery_github_models import evaluate_ci
from scripts.factory_pr_delivery_io import DeliveryInputError, load_delivery_envelope
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_journal_records import DeliveryJournalError
from scripts.factory_pr_delivery_receipts import DeliveryReceipt, DeliveryReceiptReason
from scripts.factory_pr_delivery_service_support import (
    DeliveryServiceError,
    DeliveryServiceSupport,
    digest_model,
)

__all__ = ["DeliveryService", "DeliveryServiceError"]
from scripts.factory_pr_delivery_ssh import push_exact_commit


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
        accepted_head = request.base_commit
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
                accepted_local_head=accepted_head,
                now=now,
            )
        if not apply:
            return self._plan_receipt(envelope, existing, protection, issue.title, now)

        journal = DeliveryJournal(self.repo_root)
        try:
            result = commit_exact_diff(
                self.repo_root,
                envelope,
                committed_at=now,
                journal=journal,
            )
            _ = journal.push_intent(envelope)
            pushed = push_exact_commit(
                envelope.worktree_path,
                branch=request.branch,
                committed_head=result.committed_head,
            )
            _ = journal.pushed(envelope, remote_head=pushed.remote_head)
        except DeliveryJournalError as exc:
            raise DeliveryServiceError(exc.code) from None
        except (GitHubDeliveryError, RuntimeError) as exc:
            raise DeliveryServiceError(str(exc)) from None

        pull = self._ensure_pull_request(envelope, issue.title)
        self._validate_pull(pull, envelope, result.committed_head, issue.title)
        current_protection = self._observe_protection(request.base_commit)
        ci = self.github.observe_ci(
            REPOSITORY,
            pr_number=pull.number,
            head_sha=result.committed_head,
            protection=current_protection,
        )
        ready, ci_reason = evaluate_ci(current_protection, ci)
        if not ready:
            reason: DeliveryReceiptReason = (
                "ci-pending"
                if ci_reason in {"visible-check-not-terminal", "required-check-not-green"}
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
                ci_digest=digest_model(ci),
                now=now,
            )
        merged = self.github.merge_pull_request(
            REPOSITORY,
            pr_number=pull.number,
            head_sha=result.committed_head,
        )
        if merged.state not in {"merged", "already-merged"}:
            return self._receipt(
                envelope,
                lifecycle="uncertain" if merged.state == "uncertain" else "blocked",
                reason="uncertain" if merged.state == "uncertain" else "merge-rejected",
                authoritative=True,
                accepted_local_head=result.accepted_local_head,
                committed_head=result.committed_head,
                remote_head=pushed.remote_head,
                pr_number=pull.number,
                ci_digest=digest_model(ci),
                now=now,
            )
        return self._receipt(
            envelope,
            lifecycle="merged",
            reason="cleanup-pending",
            authoritative=True,
            accepted_local_head=result.accepted_local_head,
            committed_head=result.committed_head,
            remote_head=pushed.remote_head,
            pr_number=pull.number,
            ci_digest=digest_model(ci),
            merge_head=merged.merged_head,
            now=now,
        )
