"""Shared immutable primitives for provider-scorecard schema modules."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Identifier = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._/-]*$")
]
TaskType = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Revision = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
ReceiptRunId = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._/-]*$")
]
IssueNumber = Annotated[int, Field(ge=1, le=9_999_999)]
CostUsd = Annotated[float, Field(ge=0.0, le=1_000_000.0, allow_inf_nan=False)]
VerificationLane = Literal[
    "tiny-docs",
    "docs-guardrail",
    "tests-only",
    "normal-code",
    "security-runtime",
    "release-ci-architecture",
]
AutonomyTier = Literal["tier_a", "tier_b", "tier_c"]


class StrictScorecardModel(BaseModel):
    """Immutable schema boundary for local provider-scorecard evidence."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class ReceiptIdentity(StrictScorecardModel):
    """Immutable identifiers that bind every scorecard receipt."""

    job_id: Identifier
    reservation_id: Identifier | None
    issue_number: IssueNumber
    provider_lane_id: Identifier
    provider_host: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    billing_path: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    model_id: Identifier
    cost_provider_id: Identifier | None
    cost_model_id: Identifier | None
    autonomy_tier: AutonomyTier
    base_revision: Revision
    head_revision: Revision
    diff_sha256: Digest

    def correlation_digest(self) -> str:
        """Return the deterministic digest for immutable case correlation."""

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()


def identity_cost_digest(identity: ReceiptIdentity, cost_usd: float) -> str:
    """Return the deterministic digest binding a known cost to its identity."""

    payload = {"identity": identity.model_dump(mode="json"), "cost_usd": cost_usd}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
