"""Owner-only bounded loading for delivery requests and referenced evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Never

from pydantic import BaseModel, ValidationError

from entroping.core.owner_only_evidence import read_owner_only_local_evidence_artifact_bytes
from scripts.factory_orchestration_models import OrchestrationReceipt, OrchestrationRequest
from scripts.factory_pr_delivery_models import DeliveryEnvelope, DeliveryRequest

REQUEST_MAX_BYTES = 32_768
ORCHESTRATION_REQUEST_MAX_BYTES = 32_768
ORCHESTRATION_RECEIPT_MAX_BYTES = 262_144
PR_BODY_MAX_BYTES = 65_536


class DeliveryInputError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


def load_delivery_envelope(path: Path) -> DeliveryEnvelope:
    """Load and cross-bind one accepted delivery envelope."""

    request_raw = _read(path, REQUEST_MAX_BYTES, "request-invalid")
    request = _parse_model(request_raw, DeliveryRequest, "request-invalid")
    orchestration_raw = _read(
        Path(request.orchestration_request_path),
        ORCHESTRATION_REQUEST_MAX_BYTES,
        "artifact-invalid",
    )
    receipt_raw = _read(
        Path(request.orchestration_receipt_path),
        ORCHESTRATION_RECEIPT_MAX_BYTES,
        "artifact-invalid",
    )
    body_raw = _read(Path(request.pr_body_path), PR_BODY_MAX_BYTES, "artifact-invalid")
    if (
        _sha(orchestration_raw) != request.orchestration_request_sha256
        or _sha(receipt_raw) != request.orchestration_receipt_sha256
        or _sha(body_raw) != request.pr_body_sha256
    ):
        raise DeliveryInputError("request-invalid")
    orchestration = _parse_model(orchestration_raw, OrchestrationRequest, "artifact-invalid")
    receipt = _parse_model(receipt_raw, OrchestrationReceipt, "artifact-invalid")
    try:
        body = body_raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise DeliveryInputError("artifact-invalid") from None
    _validate_accepted(orchestration, receipt)
    common = Path(orchestration.common_git_dir)
    main_root = common.parent if common.name == ".git" else common
    return DeliveryEnvelope(
        request=request,
        orchestration_request=orchestration,
        orchestration_receipt=receipt,
        pr_body=body,
        main_root=main_root.resolve(),
        worktree_path=Path(orchestration.worktree_path).resolve(),
    )


def _read(path: Path, limit: int, code: str) -> bytes:
    raw, _error = read_owner_only_local_evidence_artifact_bytes(path, max_bytes=limit)
    if raw is None:
        raise DeliveryInputError(code)
    return raw


def _parse_model[ModelT: BaseModel](raw: bytes, model: type[ModelT], code: str) -> ModelT:
    try:
        _ = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return model.model_validate_json(raw, strict=True)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValidationError):
        raise DeliveryInputError(code) from None


def _validate_accepted(request: OrchestrationRequest, receipt: OrchestrationReceipt) -> None:
    if (
        receipt.lifecycle != "accepted"
        or receipt.reason != "accepted"
        or not receipt.authoritative
        or receipt.request_id != request.request_id
        or receipt.request_digest != request.request_digest
        or receipt.issue_number != request.issue_number
        or receipt.job_id != request.job_id
        or receipt.assignment_id != request.assignment_id
        or receipt.selector_digest != request.selector_digest
        or receipt.selection_digest != request.selection_digest
        or receipt.scheduler_owner_id != request.scheduler_owner_id
        or receipt.scheduler_owner_epoch != request.scheduler_owner_epoch
        or receipt.worktree_id != request.worktree_id
        or receipt.worktree_path_sha256
        != hashlib.sha256(str(Path(request.worktree_path).resolve()).encode()).hexdigest()
        or receipt.branch != request.branch
        or receipt.verification_lane != request.verification_lane
        or receipt.proposal_sha256 != request.proposal_sha256
        or receipt.allowed_scope_digest != request.allowed_scope_digest
        or receipt.base_commit != request.base_commit
        or receipt.result_head != request.base_commit
        or receipt.approved_paths != tuple(sorted(set(receipt.approved_paths)))
        or not receipt.approved_paths
    ):
        raise DeliveryInputError("authority-mismatch")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DeliveryInputError("request-invalid")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Never:
    raise DeliveryInputError("request-invalid")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
