from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AccountingStatus = Literal["accounted", "unaccounted"]
AccountingReason = Literal[
    "complete",
    "usage_absent",
    "missing_cost",
    "ambiguous_zero_cost",
    "malformed_event",
    "malformed_usage",
    "conflicting_duplicate_usage",
    "inconsistent_session",
    "error_event",
    "text_limit_exceeded",
]
ReceiptReason = Literal[
    "complete",
    "usage_absent",
    "missing_cost",
    "ambiguous_zero_cost",
    "malformed_event",
    "malformed_usage",
    "conflicting_duplicate_usage",
    "inconsistent_session",
    "error_event",
    "text_limit_exceeded",
    "dry_run",
    "timed_out",
    "output_limit_exceeded",
    "process_failed",
    "secret_like_output",
]
UsagePayload = dict[str, int | float]
ReceiptPayloadValue = str | int | None | UsagePayload


class UsageReceiptError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UsageTotals:
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float

    def to_payload(self) -> UsagePayload:
        return {
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


@dataclass(frozen=True, slots=True)
class OpenCodeStreamSummary:
    output_text: str
    accounting_status: AccountingStatus
    accounting_reason: AccountingReason
    session_fingerprint: str | None
    usage: UsageTotals | None
    unique_step_count: int
    saw_error_event: bool

    def to_sanitized_payload(self) -> dict[str, ReceiptPayloadValue]:
        payload: dict[str, ReceiptPayloadValue] = {
            "accounting_reason": self.accounting_reason,
            "accounting_status": self.accounting_status,
            "schema_version": "entroping.opencode-event-summary.v1",
            "session_fingerprint": self.session_fingerprint,
            "unique_step_count": self.unique_step_count,
        }
        if self.usage is not None:
            payload["usage"] = self.usage.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class OpenCodeUsageReceipt:
    accounting_status: AccountingStatus
    accounting_reason: ReceiptReason
    job_id: str | None
    requested_model: str
    run_id: str
    session_fingerprint: str | None
    unique_step_count: int
    usage: UsageTotals | None

    def to_payload(self) -> dict[str, ReceiptPayloadValue]:
        payload: dict[str, ReceiptPayloadValue] = {
            "accounting_reason": self.accounting_reason,
            "accounting_status": self.accounting_status,
            "job_id": self.job_id,
            "requested_model": self.requested_model,
            "run_id": self.run_id,
            "schema_version": "entroping.opencode-usage-receipt.v1",
            "session_fingerprint": self.session_fingerprint,
            "unique_step_count": self.unique_step_count,
        }
        if self.usage is not None:
            payload["usage"] = self.usage.to_payload()
        return payload


def build_usage_receipt(
    summary: OpenCodeStreamSummary | None,
    *,
    job_id: str | None,
    requested_model: str,
    run_id: str,
    override_reason: ReceiptReason | None = None,
) -> OpenCodeUsageReceipt:
    if summary is None:
        if override_reason is None:
            raise UsageReceiptError("receipt without event summary requires a reason")
        return OpenCodeUsageReceipt(
            accounting_status="unaccounted",
            accounting_reason=override_reason,
            job_id=job_id,
            requested_model=requested_model,
            run_id=run_id,
            session_fingerprint=None,
            unique_step_count=0,
            usage=None,
        )
    reason: ReceiptReason = override_reason or summary.accounting_reason
    accounted = reason == "complete"
    return OpenCodeUsageReceipt(
        accounting_status="accounted" if accounted else "unaccounted",
        accounting_reason=reason,
        job_id=job_id,
        requested_model=requested_model,
        run_id=run_id,
        session_fingerprint=summary.session_fingerprint,
        unique_step_count=summary.unique_step_count,
        usage=summary.usage if accounted else None,
    )
