"""Validation and receipt helpers for the delivery service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from scripts.factory_pr_delivery_github import REPOSITORY, GitHubDeliveryError, GitHubDeliveryPort
from scripts.factory_pr_delivery_github_models import (
    IssueObservation,
    ProtectionObservation,
    PullRequestObservation,
    evaluate_ci,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_pr_delivery_receipts import (
    DeliveryReceipt,
    DeliveryReceiptLifecycle,
    DeliveryReceiptReason,
)
from scripts.pr_body_check import validate_body


class DeliveryServiceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


class DeliveryServiceSupport:
    repo_root: Path
    github: GitHubDeliveryPort
    _now: Callable[[], datetime]

    def _plan_receipt(
        self,
        envelope: DeliveryEnvelope,
        existing: tuple[PullRequestObservation, ...],
        protection: ProtectionObservation,
        title: str,
        now: datetime,
    ) -> DeliveryReceipt:
        request = envelope.orchestration_request
        lifecycle: DeliveryReceiptLifecycle = "planned"
        reason: DeliveryReceiptReason = "plan-only"
        if existing:
            self._validate_pull(existing[0], envelope, existing[0].head_sha, title)
            ci = self.github.observe_ci(
                REPOSITORY,
                pr_number=existing[0].number,
                head_sha=existing[0].head_sha,
                protection=protection,
            )
            ready, _ = evaluate_ci(protection, ci)
            lifecycle = "ci-ready" if ready else "blocked"
            reason = "accepted" if ready else "ci-pending"
            ci_digest = digest_model(ci)
            pr_number = existing[0].number
        else:
            ci_digest = None
            pr_number = None
        return self._receipt(
            envelope,
            lifecycle=lifecycle,
            reason=reason,
            authoritative=False,
            accepted_local_head=request.base_commit,
            committed_head=existing[0].head_sha if existing and lifecycle == "ci-ready" else None,
            pr_number=pr_number,
            ci_digest=ci_digest,
            now=now,
        )

    def _ensure_pull_request(
        self, envelope: DeliveryEnvelope, title: str
    ) -> PullRequestObservation:
        request = envelope.orchestration_request
        pulls = self.github.observe_pull_requests(REPOSITORY, request.issue_number, request.branch)
        if len(pulls) > 1:
            raise DeliveryServiceError("pr-conflict")
        if not pulls:
            return self.github.create_pull_request(
                REPOSITORY,
                title=title,
                body=envelope.pr_body,
                head_branch=request.branch,
                base_ref="main",
            )
        pull = pulls[0]
        if (
            pull.body_sha256 != hashlib.sha256(envelope.pr_body.encode()).hexdigest()
            or pull.title != title
        ):
            return self.github.update_pull_request(
                REPOSITORY,
                pr_number=pull.number,
                title=title,
                body=envelope.pr_body,
            )
        return pull

    def _validate_pull(
        self,
        pull: PullRequestObservation,
        envelope: DeliveryEnvelope,
        expected_head: str,
        expected_title: str,
    ) -> None:
        request = envelope.orchestration_request
        receipt = envelope.orchestration_receipt
        if (
            pull.repo != REPOSITORY
            or pull.state != "open"
            or pull.draft
            or pull.head_branch != request.branch
            or pull.head_sha != expected_head
            or pull.base_ref != "main"
            or pull.base_sha != request.base_commit
            or pull.title != expected_title
            or pull.changed_files != receipt.approved_paths
            or pull.closing_issue_numbers != (request.issue_number,)
            or pull.body_sha256 != hashlib.sha256(envelope.pr_body.encode()).hexdigest()
        ):
            raise DeliveryServiceError("pr-conflict")

    def _observe_issue(self, issue_number: int) -> IssueObservation:
        try:
            return self.github.observe_issue(REPOSITORY, issue_number)
        except GitHubDeliveryError as exc:
            raise DeliveryServiceError(exc.code) from None

    def _observe_protection(self, base_sha: str) -> ProtectionObservation:
        try:
            return self.github.observe_protection(REPOSITORY, base_ref="main", base_sha=base_sha)
        except GitHubDeliveryError as exc:
            raise DeliveryServiceError(exc.code) from None

    def _validate_issue_and_body(
        self, envelope: DeliveryEnvelope, issue: IssueObservation
    ) -> None:
        request = envelope.orchestration_request
        if (
            issue.number != request.issue_number
            or issue.repo != REPOSITORY
            or issue.state != "open"
            or issue.is_pull_request
            or issue.labels.count("autonomy:tier-a") != 1
        ):
            raise DeliveryServiceError("issue-invalid")
        failures = validate_body(
            envelope.pr_body,
            issue=str(request.issue_number),
            changed_files=list(envelope.orchestration_receipt.approved_paths),
            trusted_issue_autonomy_tier="tier_a",
        )
        if failures:
            raise DeliveryServiceError("body-invalid")

    def _receipt(
        self,
        envelope: DeliveryEnvelope,
        *,
        lifecycle: DeliveryReceiptLifecycle,
        reason: DeliveryReceiptReason,
        authoritative: bool,
        accepted_local_head: str,
        committed_head: str | None = None,
        remote_head: str | None = None,
        pr_number: int | None = None,
        ci_digest: str | None = None,
        merge_head: str | None = None,
        now: datetime,
    ) -> DeliveryReceipt:
        return DeliveryReceipt(
            request_id=envelope.request.request_id,
            created_at=now,
            updated_at=now,
            lifecycle=lifecycle,
            reason=reason,
            authoritative=authoritative,
            accepted_local_head=accepted_local_head,
            committed_head=committed_head,
            remote_head=remote_head,
            pr_number=pr_number,
            ci_digest=ci_digest,
            merge_head=merge_head,
        )

    def _aware_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise DeliveryServiceError("timestamp-invalid")
        return value


def digest_model(model: BaseModel) -> str:
    payload = model.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
