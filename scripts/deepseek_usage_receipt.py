from __future__ import annotations

import hashlib
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

MAX_USAGE_VALUE = 9_223_372_036_854_775_807
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=256)]
UsageCount = Annotated[int, Field(ge=0, le=MAX_USAGE_VALUE)]


class _ProviderUsage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore",
        strict=True,
        hide_input_in_errors=True,
    )

    prompt_tokens: UsageCount
    completion_tokens: UsageCount
    total_tokens: UsageCount


class _ProviderResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore",
        strict=True,
        hide_input_in_errors=True,
    )

    id: BoundedText
    model: BoundedText
    usage: _ProviderUsage


def usage_receipt_payload(
    response_payload: dict[str, object] | None,
    *,
    job_id: str | None,
    requested_model: str,
    run_id: str,
    request_dispatched: bool,
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "entroping.deepseek-usage-receipt.v1",
        "accounting_status": "unaccounted",
        "accounting_reason": _unaccounted_reason(
            job_id=job_id,
            request_dispatched=request_dispatched,
        ),
        "job_id": job_id,
        "requested_model": requested_model,
        "run_id": run_id,
    }
    if job_id is None or not request_dispatched or response_payload is None:
        return base
    try:
        response = _ProviderResponse.model_validate(response_payload)
    except ValidationError:
        base["accounting_reason"] = "malformed_provider_receipt"
        return base
    usage = response.usage
    if usage.total_tokens != usage.prompt_tokens + usage.completion_tokens:
        base["accounting_reason"] = "malformed_provider_receipt"
        return base
    return {
        "schema_version": "entroping.deepseek-usage-receipt.v1",
        "accounting_status": "accounted",
        "job_id": job_id,
        "requested_model": requested_model,
        "reported_model": response.model,
        "run_id": run_id,
        "provider_session_digest": hashlib.sha256(response.id.encode()).hexdigest(),
        "requests": 1,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def sanitized_response_payload(payload: dict[str, object]) -> dict[str, object]:
    sanitized = dict(payload)
    session_id = sanitized.pop("id", None)
    if isinstance(session_id, str) and session_id:
        sanitized["provider_session_digest"] = hashlib.sha256(
            session_id.encode()
        ).hexdigest()
    return sanitized


def _unaccounted_reason(
    *,
    job_id: str | None,
    request_dispatched: bool,
) -> Literal[
    "missing_job_id",
    "provider_receipt_unavailable",
    "request_not_dispatched",
]:
    if job_id is None:
        return "missing_job_id"
    if not request_dispatched:
        return "request_not_dispatched"
    return "provider_receipt_unavailable"
