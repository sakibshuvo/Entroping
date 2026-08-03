"""Owner-only bounded input loading for orchestration requests and proposals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Never

from pydantic import ValidationError

from entroping.core.owner_only_evidence import read_owner_only_local_evidence_artifact_bytes
from scripts.factory_orchestration_models import OrchestrationRequest

REQUEST_MAX_BYTES = 32_768
PROPOSAL_MAX_BYTES = 1_048_576


class OrchestrationInputError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_request(path: Path) -> OrchestrationRequest:
    """Load one strict request through the owner-only descriptor reader."""

    raw, error = read_owner_only_local_evidence_artifact_bytes(
        path,
        max_bytes=REQUEST_MAX_BYTES,
    )
    if raw is None:
        raise OrchestrationInputError("request-invalid") from None
    try:
        _ = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        return OrchestrationRequest.model_validate_json(raw, strict=True)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValidationError):
        raise OrchestrationInputError("request-invalid") from None


def load_exact_proposal(request: OrchestrationRequest) -> bytes:
    """Read proposal bytes once and bind them to the declared SHA-256."""

    raw, error = read_owner_only_local_evidence_artifact_bytes(
        Path(request.proposal_path),
        max_bytes=PROPOSAL_MAX_BYTES,
    )
    if raw is None:
        raise OrchestrationInputError("proposal-invalid") from None
    if sha256_bytes(raw) != request.proposal_sha256:
        raise OrchestrationInputError("proposal-drift")
    return raw


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OrchestrationInputError("request-invalid")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Never:
    raise OrchestrationInputError("request-invalid")
