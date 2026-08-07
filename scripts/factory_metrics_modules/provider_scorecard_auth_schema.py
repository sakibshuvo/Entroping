"""Authentication envelope model for provider-scorecard evidence."""

from __future__ import annotations

from typing import Literal

from .provider_scorecard_primitives import Digest, StrictScorecardModel


class ScorecardAuthentication(StrictScorecardModel):
    """Fixed-key-id HMAC-SHA256 maintainer attestation envelope."""

    scheme: Literal["hmac-sha256"]
    key_id: Literal["maintainer-local-v1"]
    signature: Digest
