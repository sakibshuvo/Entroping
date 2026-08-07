"""Strict value-free provider scorecard evidence contracts."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from .provider_scorecard_auth_schema import ScorecardAuthentication
from .provider_scorecard_outcomes import LaterOutcomeReceipt
from .provider_scorecard_primitives import (
    CostUsd,
    Digest,
    IssueNumber,
    ReceiptIdentity,
    ReceiptRunId,
    Revision,
    StrictScorecardModel,
    TaskType,
    VerificationLane,
    identity_cost_digest,
)

PROVIDER_SCORECARD_SCHEMA_VERSION = "entroping.provider-scorecard-evidence.v1"
PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION = "entroping.provider-scorecard-report.v1"


class ReviewReceipt(ReceiptIdentity):
    decision: Literal["accepted", "rejected", "needs_review", "inconclusive"]
    digest: Digest


class VerificationReceipt(ReceiptIdentity):
    verification_lane: VerificationLane
    quality: Literal["pass", "fail", "inconclusive"]
    security: Literal["pass", "fail", "inconclusive"]
    digest: Digest


class CiReceipt(ReceiptIdentity):
    run_id: ReceiptRunId
    status: Literal["success", "failure", "cancelled", "pending", "stale"]
    digest: Digest


class MergeReceipt(ReceiptIdentity):
    pr_number: IssueNumber
    status: Literal["merged", "not_merged", "inconclusive"]
    merge_commit_revision: Revision | None
    digest: Digest

    @model_validator(mode="after")
    def validate_merge_commit(self) -> Self:
        if self.status == "merged" and self.merge_commit_revision is None:
            raise PydanticCustomError(
                "merge_commit", "merged receipt requires merge_commit_revision"
            )
        if self.status != "merged" and self.merge_commit_revision is not None:
            raise PydanticCustomError(
                "merge_commit", "non-merged receipt forbids merge_commit_revision"
            )
        return self


class ProviderScorecardCase(StrictScorecardModel):
    task_type: TaskType
    verification_lane: VerificationLane
    observed_at: datetime
    cost_usd: CostUsd | None = None
    cost_receipt_digest: Digest | None = None
    identity: ReceiptIdentity
    review: ReviewReceipt | None = None
    verification: VerificationReceipt | None = None
    ci: CiReceipt | None = None
    merge: MergeReceipt | None = None
    later_outcomes: Annotated[tuple[LaterOutcomeReceipt, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def validate_case_links(self) -> Self:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise PydanticCustomError("naive_timestamp", "observed_at must include a timezone")
        for receipt in (self.review, self.verification, self.ci, self.merge, *self.later_outcomes):
            if (
                receipt is not None
                and receipt.model_dump(
                    exclude={
                        "digest",
                        "decision",
                        "verification_lane",
                        "quality",
                        "security",
                        "run_id",
                        "status",
                        "pr_number",
                        "merge_commit_revision",
                        "observed_at",
                    }
                )
                != self.identity.model_dump()
            ):
                raise PydanticCustomError(
                    "receipt_identity", "receipt identity must exactly match case identity"
                )
        if (
            self.verification is not None
            and self.verification.verification_lane != self.verification_lane
        ):
            raise PydanticCustomError(
                "verification_lane", "verification receipt lane must match case verification_lane"
            )
        if (self.merge is None or self.merge.status != "merged") and self.later_outcomes:
            raise PydanticCustomError("outcome_merge", "later outcomes require a merged receipt")
        if self.merge is not None:
            for outcome in self.later_outcomes:
                if outcome.merge_commit_revision != self.merge.merge_commit_revision:
                    raise PydanticCustomError(
                        "outcome_merge", "later outcome must match merge commit revision"
                    )
                if outcome.observed_at < self.observed_at:
                    raise PydanticCustomError(
                        "outcome_time", "later outcome must not predate case observation"
                    )
        if len({item.digest for item in self.later_outcomes}) != len(self.later_outcomes):
            raise PydanticCustomError("outcome_digest", "later outcomes contain a duplicate digest")
        if self.cost_usd is None and self.cost_receipt_digest is not None:
            raise PydanticCustomError("cost_receipt", "unknown cost forbids cost receipt digest")
        if (
            self.cost_usd is not None
            and self.cost_receipt_digest != self.expected_cost_receipt_digest()
        ):
            raise PydanticCustomError(
                "cost_receipt", "cost receipt digest must bind identity and cost"
            )
        return self

    def expected_cost_receipt_digest(self) -> str:
        """Return the deterministic identity-bound digest for a known cost."""

        if self.cost_usd is None:
            raise ValueError("unknown cost has no receipt digest")
        return identity_cost_digest(self.identity, self.cost_usd)


class ProviderScorecardEvidence(StrictScorecardModel):
    schema_version: Literal["entroping.provider-scorecard-evidence.v1"]
    cases: Annotated[tuple[ProviderScorecardCase, ...], Field(max_length=512)]
    authentication: ScorecardAuthentication

    @model_validator(mode="after")
    def validate_unique_cases(self) -> Self:
        job_ids = tuple(case.identity.job_id for case in self.cases)
        digests = tuple(case.identity.correlation_digest() for case in self.cases)
        receipt_digests = tuple(
            receipt.digest
            for case in self.cases
            for receipt in (
                case.review,
                case.verification,
                case.ci,
                case.merge,
                *case.later_outcomes,
            )
            if receipt is not None
        ) + tuple(
            case.cost_receipt_digest
            for case in self.cases
            if case.cost_receipt_digest is not None
        )
        work_ids = tuple(
            (
                case.identity.issue_number,
                case.identity.base_revision,
                case.identity.head_revision,
                case.identity.diff_sha256,
            )
            for case in self.cases
        )
        reservations = tuple(
            case.identity.reservation_id
            for case in self.cases
            if case.identity.reservation_id is not None
        )
        ci_run_ids = tuple(case.ci.run_id for case in self.cases if case.ci is not None)
        merged_prs = tuple(
            case.merge.pr_number
            for case in self.cases
            if case.merge is not None and case.merge.status == "merged"
        )
        if len(set(job_ids)) != len(job_ids):
            raise PydanticCustomError("duplicate_job", "cases contain a duplicate job_id")
        if len(set(digests)) != len(digests):
            raise PydanticCustomError(
                "duplicate_correlation", "cases contain a duplicate correlation digest"
            )
        if len(set(receipt_digests)) != len(receipt_digests):
            raise PydanticCustomError(
                "duplicate_receipt_digest", "cases contain a duplicate receipt digest"
            )
        if len(set(work_ids)) != len(work_ids):
            raise PydanticCustomError("duplicate_work", "cases contain duplicate underlying work")
        if len(set(reservations)) != len(reservations):
            raise PydanticCustomError(
                "duplicate_reservation", "cases contain a duplicate reservation"
            )
        if len(set(ci_run_ids)) != len(ci_run_ids):
            raise PydanticCustomError("duplicate_ci_run", "cases contain a duplicate CI run")
        if len(set(merged_prs)) != len(merged_prs):
            raise PydanticCustomError("duplicate_merged_pr", "cases contain a duplicate merged PR")
        return self
