from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .factory_budget_ledger import (
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    NoChargeReconciliationInput,
    SettlementOutcome,
    SettlementReceipt,
)
from .factory_budget_reservation_validation import canonical_digest
from .factory_paid_dispatch_receipt_models import (
    AccountedReceipt,
    NotDispatchedReceipt,
    receipt_payload,
)
from .factory_paid_dispatch_reservation import PaidDispatchError


def settle_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    worker_payload: dict[str, object],
    *,
    expected_run_id: str | None,
    occurred_at: datetime,
) -> SettlementOutcome | None:
    reservation_id = job.get("reservation_id")
    if not isinstance(reservation_id, str):
        return None
    raw_receipt = worker_payload.get("usage_receipt")
    try:
        parsed_receipt = receipt_payload(raw_receipt)
    except ValidationError:
        return _uncertain(
            project_root,
            job,
            reservation_id,
            {"receipt": "missing"},
            occurred_at,
            reason="partial_receipt",
        )
    if parsed_receipt.get("accounting_status") == "unaccounted":
        if parsed_receipt.get("accounting_reason") == "request_not_dispatched":
            try:
                no_charge = NotDispatchedReceipt.model_validate(parsed_receipt)
            except ValidationError:
                return _uncertain(
                    project_root,
                    job,
                    reservation_id,
                    parsed_receipt,
                    occurred_at,
                    reason="malformed_receipt",
                )
            identity_reason = _identity_reason(
                job,
                job_id=no_charge.job_id,
                requested_model=no_charge.requested_model,
                reported_model=no_charge.requested_model,
                run_id=no_charge.run_id,
                expected_run_id=expected_run_id,
            )
            if identity_reason is not None:
                return _uncertain(
                    project_root,
                    job,
                    reservation_id,
                    parsed_receipt,
                    occurred_at,
                    reason=identity_reason,
                )
            return _reconcile_not_dispatched(
                project_root,
                job,
                reservation_id,
                parsed_receipt,
                occurred_at,
            )
        return _uncertain(
            project_root,
            job,
            reservation_id,
            parsed_receipt,
            occurred_at,
            reason="partial_receipt",
        )
    try:
        receipt = AccountedReceipt.model_validate(parsed_receipt)
    except ValidationError:
        return _uncertain(
            project_root,
            job,
            reservation_id,
            parsed_receipt,
            occurred_at,
            reason="malformed_receipt",
        )
    if receipt.total_tokens != receipt.input_tokens + receipt.output_tokens:
        return _uncertain(
            project_root,
            job,
            reservation_id,
            parsed_receipt,
            occurred_at,
            reason="malformed_receipt",
        )
    identity_reason = _identity_reason(
        job,
        job_id=receipt.job_id,
        requested_model=receipt.requested_model,
        reported_model=receipt.reported_model,
        run_id=receipt.run_id,
        expected_run_id=expected_run_id,
    )
    if identity_reason is not None:
        return _uncertain(
            project_root,
            job,
            reservation_id,
            parsed_receipt,
            occurred_at,
            reason=identity_reason,
        )
    if receipt.total_tokens == 0:
        return _uncertain(
            project_root,
            job,
            reservation_id,
            parsed_receipt,
            occurred_at,
            reason="zero_usage_receipt",
        )
    job_id = _job_text(job, "job_id")
    requested_model = _job_text(job, "model")
    try:
        return FactoryBudgetLedger.open_project(project_root).settle_reservation(
            SettlementReceipt(
                idempotency_key=(f"settle:{job_id}:{receipt.provider_session_digest[:16]}"),
                reservation_id=reservation_id,
                job_id=job_id,
                provider_lane_id=_job_text(job, "cost_provider_lane_id"),
                provider_id=_job_text(job, "cost_provider_id"),
                model_id=_job_text(job, "cost_model_id"),
                requested_model=requested_model,
                provider_session_digest=receipt.provider_session_digest,
                input_tokens=receipt.input_tokens,
                output_tokens=receipt.output_tokens,
                requests=receipt.requests,
                minutes=0,
                occurred_at=occurred_at,
            )
        )
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError("ledger", exc.detail) from exc


def _uncertain(
    project_root: Path,
    job: dict[str, object],
    reservation_id: str,
    evidence: object,
    occurred_at: datetime,
    *,
    reason: Literal[
        "job_mismatch",
        "malformed_receipt",
        "model_mismatch",
        "partial_receipt",
        "run_mismatch",
        "zero_usage_receipt",
    ],
) -> SettlementOutcome:
    digest = canonical_digest(evidence)
    try:
        return FactoryBudgetLedger.open_project(project_root).mark_reservation_uncertain(
            reservation_id,
            idempotency_key=f"uncertain:{_job_text(job, 'job_id')}:{digest[:16]}",
            reason=reason,
            occurred_at=occurred_at,
            evidence_digest=digest,
        )
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError("ledger", exc.detail) from exc


def _reconcile_not_dispatched(
    project_root: Path,
    job: dict[str, object],
    reservation_id: str,
    evidence: object,
    occurred_at: datetime,
) -> SettlementOutcome:
    digest = canonical_digest(evidence)
    try:
        return FactoryBudgetLedger.open_project(project_root).reconcile_no_charge(
            NoChargeReconciliationInput(
                idempotency_key=(f"never-dispatched:{_job_text(job, 'job_id')}:{digest[:16]}"),
                reservation_id=reservation_id,
                evidence_digest=digest,
                occurred_at=occurred_at,
                reason="verified_never_dispatched",
            )
        )
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError("ledger", exc.detail) from exc


def _job_text(job: dict[str, object], field: str) -> str:
    value = job.get(field)
    if not isinstance(value, str) or not value:
        raise PaidDispatchError("job", f"paid dispatch job field {field!r} is invalid")
    return value


def _identity_reason(
    job: dict[str, object],
    *,
    job_id: str,
    requested_model: str,
    reported_model: str,
    run_id: str,
    expected_run_id: str | None,
) -> Literal["job_mismatch", "model_mismatch", "run_mismatch"] | None:
    if job_id != _job_text(job, "job_id"):
        return "job_mismatch"
    job_model = _job_text(job, "model")
    if requested_model != job_model or reported_model != job_model:
        return "model_mismatch"
    if expected_run_id is None or run_id != expected_run_id:
        return "run_mismatch"
    return None
