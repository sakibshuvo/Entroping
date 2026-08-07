"""Value-free terminal and recoverable delivery receipts."""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from collections.abc import Mapping, Sequence
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


_MAX_RECEIPT_BYTES = 16 * 1024
_MAX_RECEIPT_DEPTH = 16
_MAX_RECEIPT_NODES = 512


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


def encode_delivery_receipt(receipt: DeliveryReceipt) -> tuple[str, str]:
    payload = _canonical_receipt_payload(receipt.model_dump(mode="json"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return payload, digest


def decode_delivery_receipt(raw_json: str, digest: str) -> DeliveryReceipt:
    if len(raw_json.encode("utf-8")) > _MAX_RECEIPT_BYTES:
        raise ValueError("receipt encoding exceeds 16KiB")
    try:
        received = json.loads(raw_json, object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, RecursionError, UnicodeEncodeError) as exc:
        raise ValueError("receipt encoding is malformed") from exc
    _validate_decoded_value(received)
    canonical = _canonical_receipt_payload(received)
    if raw_json != canonical:
        raise ValueError("receipt encoding must be canonical")
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != expected:
        raise ValueError("receipt digest mismatch")
    try:
        return DeliveryReceipt.model_validate_json(raw_json, strict=True)
    except ValueError as exc:
        raise ValueError("receipt projection is invalid") from exc


def _canonical_receipt_payload(payload: Mapping[str, object] | list[object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _reject_duplicate_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("receipt encoding has duplicate keys")
        values[key] = value
    return values


def _validate_decoded_value(value: object) -> None:
    stack: deque[tuple[object, int]] = deque(((value, 1),))
    nodes = 0
    while stack:
        current, depth = stack.popleft()
        nodes += 1
        if nodes > _MAX_RECEIPT_NODES:
            raise ValueError("receipt encoding exceeds node limit")
        if depth > _MAX_RECEIPT_DEPTH:
            raise ValueError("receipt encoding exceeds depth limit")
        if isinstance(current, dict):
            for item in current.values():
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            for item in current:
                stack.append((item, depth + 1))
        elif isinstance(current, (str, int, float, bool)) or current is None:
            if isinstance(current, float) and not math.isfinite(current):
                raise ValueError("receipt encoding has non-finite number")
        else:
            raise ValueError("receipt encoding has invalid JSON value")
