"""Value-free terminal and recoverable delivery receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^delivery_[a-f0-9]{64}$")]

type DeliveryReceiptLifecycle = Literal[
    "planned",
    "blocked",
    "committed",
    "pushed",
    "pr-ready",
    "ci-ready",
    "merged",
    "completed",
    "uncertain",
]
type DeliveryReceiptReason = Literal[
    "plan-only",
    "accepted",
    "authority-mismatch",
    "issue-invalid",
    "body-invalid",
    "pr-conflict",
    "ci-pending",
    "ci-failed",
    "merge-rejected",
    "cleanup-pending",
    "completed",
    "uncertain",
]


class DeliveryReceipt(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    schema_version: Literal["entroping.factory-pr-delivery-receipt.v1"] = (
        "entroping.factory-pr-delivery-receipt.v1"
    )
    request_id: RequestId
    lifecycle: DeliveryReceiptLifecycle
    reason: DeliveryReceiptReason
    authoritative: bool
    accepted_local_head: Commit
    committed_head: Commit | None = None
    remote_head: Commit | None = None
    pr_number: int | None = Field(default=None, ge=1, le=2_147_483_647)
    ci_digest: Digest | None = None
    merge_head: Commit | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_projection(self) -> DeliveryReceipt:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("delivery timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("delivery timestamps must be monotonic")
        committed = self.lifecycle in {
            "committed",
            "pushed",
            "pr-ready",
            "ci-ready",
            "merged",
            "completed",
        }
        if committed != (self.committed_head is not None):
            raise ValueError("delivery commit projection is inconsistent")
        if self.lifecycle in {"ci-ready", "merged", "completed"} and (
            self.pr_number is None or self.ci_digest is None
        ):
            raise ValueError("delivery CI projection is incomplete")
        if self.lifecycle == "merged" and self.merge_head != self.committed_head:
            raise ValueError("delivery merge projection is inconsistent")
        if self.lifecycle == "completed" and self.merge_head != self.committed_head:
            raise ValueError("completed delivery must retain merge head")
        return self
