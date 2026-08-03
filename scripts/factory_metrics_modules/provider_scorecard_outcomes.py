"""Later-outcome receipt model for provider-scorecard evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from .provider_scorecard_primitives import Digest, ReceiptIdentity, Revision


class LaterOutcomeReceipt(ReceiptIdentity):
    """A post-merge outcome bound to the original work identity."""

    status: Literal["passed", "regressed", "reverted", "inconclusive"]
    observed_at: datetime
    merge_commit_revision: Revision
    digest: Digest

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> Self:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise PydanticCustomError("naive_timestamp", "observed_at must include a timezone")
        return self
