"""Strict content-addressed contracts for Tier A proposal delivery."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from scripts.factory_orchestration_models import OrchestrationReceipt, OrchestrationRequest

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^delivery_[a-f0-9]{64}$")]
ReceiptId = Annotated[str, StringConstraints(pattern=r"^delivery_receipt_[a-f0-9]{64}$")]
type DeliveryLifecycle = Literal[
    "prepared", "commit-intent", "committed", "push-intent", "pushed", "uncertain"
]
type DeliveryReason = Literal["none", "committed", "pushed", "interrupted"]


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class DeliveryGitError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


class DeliveryRequest(StrictModel):
    schema_version: Literal["entroping.factory-pr-delivery-request.v1"]
    request_id: RequestId
    orchestration_request_path: str
    orchestration_request_sha256: Digest
    orchestration_receipt_path: str
    orchestration_receipt_sha256: Digest
    pr_body_path: str
    pr_body_sha256: Digest

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        for raw in (
            self.orchestration_request_path,
            self.orchestration_receipt_path,
            self.pr_body_path,
        ):
            path = Path(raw)
            if not path.is_absolute() or path != Path(path).resolve() or ".." in path.parts:
                raise ValueError("delivery paths must be absolute and normalized")
        if (
            len(
                {
                    self.orchestration_request_path,
                    self.orchestration_receipt_path,
                    self.pr_body_path,
                }
            )
            != 3
        ):
            raise ValueError("delivery artifact paths must be distinct")
        if self.request_id != delivery_request_id_for_payload(self.model_dump(mode="json")):
            raise ValueError("delivery request identity digest is invalid")
        return self

    @property
    def request_digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class DeliveryReceipt(StrictModel):
    schema_version: Literal["entroping.factory-pr-delivery-receipt.v1"]
    receipt_id: ReceiptId
    request_id: RequestId
    request_digest: Digest
    lifecycle: DeliveryLifecycle
    reason: DeliveryReason
    accepted_local_head: Commit
    committed_head: Commit | None
    remote_head: Commit | None
    commit_parent: Commit | None
    commit_tree: Commit | None
    accepted_diff_sha256: Digest
    committed_diff_sha256: Digest | None
    accepted_manifest_sha256: Digest
    committed_manifest_sha256: Digest | None
    approved_path_sha256: Digest
    body_sha256: Digest
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("delivery timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("delivery timestamps must be monotonic")
        committed = self.lifecycle in {"committed", "push-intent", "pushed"}
        pushed = self.lifecycle == "pushed"
        if committed != all(
            value is not None
            for value in (
                self.committed_head,
                self.commit_parent,
                self.commit_tree,
                self.committed_diff_sha256,
                self.committed_manifest_sha256,
            )
        ):
            raise ValueError("delivery commit projection is inconsistent")
        if pushed != (self.remote_head is not None):
            raise ValueError("delivery remote projection is inconsistent")
        if committed and (
            self.committed_diff_sha256 != self.accepted_diff_sha256
            or self.committed_manifest_sha256 != self.accepted_manifest_sha256
        ):
            raise ValueError("committed evidence must equal accepted evidence")
        payload = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != delivery_receipt_id_for_payload(payload):
            raise ValueError("delivery receipt identity digest is invalid")
        return self


class DeliveryEnvelope(StrictModel):
    request: DeliveryRequest
    orchestration_request: OrchestrationRequest
    orchestration_receipt: OrchestrationReceipt
    pr_body: str
    main_root: Path
    worktree_path: Path

    @property
    def envelope_digest(self) -> str:
        return _digest(
            {
                "request_digest": self.request.request_digest,
                "orchestration_request_digest": self.orchestration_request.request_digest,
                "orchestration_receipt_id": self.orchestration_receipt.receipt_id,
            }
        )


class CommitResult(StrictModel):
    accepted_local_head: Commit
    committed_head: Commit
    commit_parent: Commit
    commit_tree: Commit
    accepted_diff_sha256: Digest
    committed_diff_sha256: Digest
    accepted_manifest_sha256: Digest
    committed_manifest_sha256: Digest
    approved_path_sha256: Digest


def delivery_request_id_for_payload(payload: dict[str, object]) -> str:
    identity_payload = {key: value for key, value in payload.items() if key != "request_id"}
    return f"delivery_{_digest(identity_payload)}"


def delivery_receipt_id_for_payload(payload: dict[str, object]) -> str:
    return f"delivery_receipt_{_digest(payload)}"


def approved_path_digest(paths: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(list(paths), separators=(",", ":")).encode()).hexdigest()


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
