from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from .factory_budget_ledger import (
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    UsageEnvelope,
)
from .factory_paid_dispatch_launch import revalidate_or_release_paid_dispatch
from .factory_paid_dispatch_models import PaidDispatchError, PaidDispatchReservation
from .factory_paid_dispatch_reservation import job_route, prepare_paid_dispatch
from .factory_quota_evidence_io import (
    FactoryProviderEvidenceError,
    read_provider_evidence_for_dispatch,
)
from .factory_quota_settlement_transition import QuotaSettlementOutcome
from .provider_capability_types import ProviderCapabilityRegistry


def prepare_queue_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    registry: ProviderCapabilityRegistry,
    policy_path: Path,
    test_provider_evidence_path: Path | None = None,
    occurred_at: datetime,
    worker_dry_run: bool,
) -> PaidDispatchReservation | None:
    route = job_route(registry, job)
    provider_evidence = read_provider_evidence_for_dispatch(
        project_root,
        required=not worker_dry_run and route.billing_kind != "offline",
        test_path=test_provider_evidence_path,
    )
    return prepare_paid_dispatch(
        project_root,
        job,
        registry=registry,
        policy_path=policy_path,
        occurred_at=occurred_at,
        worker_dry_run=worker_dry_run,
        provider_evidence=provider_evidence,
        work_purpose=job_work_purpose(job),
    )


def paid_launch_authorized(
    project_root: Path,
    job: dict[str, object],
    *,
    occurred_at: datetime,
) -> bool:
    try:
        return revalidate_or_release_paid_dispatch(
            project_root,
            job,
            occurred_at=occurred_at,
        )
    except PaidDispatchError:
        return False


def settle_quota_dispatch(
    project_root: Path,
    job: dict[str, object],
    usage: dict[str, object] | None,
    *,
    occurred_at: datetime,
) -> str | None:
    authorization_id = job.get("dispatch_authorization_id")
    if not isinstance(authorization_id, str):
        return "quota-settlement-missing-authorization"
    ledger = FactoryBudgetLedger.open_project(project_root)
    try:
        outcome = _quota_settlement(
            ledger,
            authorization_id,
            usage,
            occurred_at=occurred_at,
        )
    except FactoryBudgetLedgerError:
        job["settlement_state"] = "unresolved"
        return "quota-settlement-failed"
    job["settlement_state"] = (
        "settled" if outcome.state in {"settled", "released"} else "unresolved"
    )
    job["actual_microcents"] = 0
    if job["settlement_state"] == "settled":
        return None
    return "quota-settlement-unresolved"


def job_work_purpose(job: dict[str, object]) -> Literal["experiment", "essential"]:
    if job.get("work_purpose", "experiment") == "essential":
        return "essential"
    return "experiment"


def _quota_settlement(
    ledger: FactoryBudgetLedger,
    authorization_id: str,
    usage: dict[str, object] | None,
    *,
    occurred_at: datetime,
) -> QuotaSettlementOutcome:
    if usage is None:
        return ledger.mark_quota_authorization_uncertain(
            authorization_id,
            occurred_at=occurred_at,
        )
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
    ):
        return ledger.mark_quota_authorization_uncertain(
            authorization_id,
            occurred_at=occurred_at,
        )
    return ledger.settle_quota_authorization(
        authorization_id,
        UsageEnvelope(
            requests=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        occurred_at=occurred_at,
    )


__all__ = [
    "FactoryProviderEvidenceError",
    "job_work_purpose",
    "paid_launch_authorized",
    "prepare_queue_paid_dispatch",
    "settle_quota_dispatch",
]
