from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
UsageCount = Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
RECEIPT_PAYLOAD: TypeAdapter[dict[str, object]] = TypeAdapter(dict[str, object])


class AccountedReceipt(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["entroping.deepseek-usage-receipt.v1"]
    accounting_status: Literal["accounted"]
    job_id: BoundedText
    requested_model: BoundedText
    reported_model: BoundedText
    run_id: BoundedText
    provider_session_digest: Digest
    requests: Literal[1]
    input_tokens: UsageCount
    output_tokens: UsageCount
    total_tokens: UsageCount


class NotDispatchedReceipt(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["entroping.deepseek-usage-receipt.v1"]
    accounting_status: Literal["unaccounted"]
    accounting_reason: Literal["request_not_dispatched"]
    job_id: BoundedText
    requested_model: BoundedText
    run_id: BoundedText


def receipt_payload(value: object) -> dict[str, object]:
    return RECEIPT_PAYLOAD.validate_python(value, strict=True)
