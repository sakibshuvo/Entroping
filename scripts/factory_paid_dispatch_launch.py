from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .factory_budget_ledger import FactoryBudgetLedger, FactoryBudgetLedgerError
from .factory_paid_dispatch_models import PaidDispatchError
from .factory_paid_dispatch_reservation import revalidate_paid_dispatch
from .factory_paid_dispatch_settlement import settle_paid_dispatch


def revalidate_or_release_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    occurred_at: datetime,
) -> bool:
    if "dispatch_authorization_id" not in job:
        return False
    try:
        _ = revalidate_paid_dispatch(
            project_root,
            job,
            occurred_at=occurred_at,
            consume_for_launch=True,
        )
    except PaidDispatchError as exc:
        if exc.code != "authorization_state":
            _release_verified_pre_network_block(
                project_root,
                job,
                occurred_at=occurred_at,
            )
        return False
    return True


def _release_verified_pre_network_block(
    project_root: Path,
    job: dict[str, object],
    *,
    occurred_at: datetime,
) -> None:
    authorization_id = job.get("dispatch_authorization_id")
    if not isinstance(authorization_id, str):
        return
    if not isinstance(job.get("reservation_id"), str):
        try:
            _ = FactoryBudgetLedger.open_project(project_root).release_quota_authorization(
                authorization_id,
                occurred_at=occurred_at,
            )
        except FactoryBudgetLedgerError as exc:
            raise PaidDispatchError(exc.code, exc.detail) from exc
        return
    job_id = _job_text(job, "job_id")
    requested_model = _job_text(job, "model")
    run_id = f"pre-network-{job_id}"[:256]
    _ = settle_paid_dispatch(
        project_root,
        job,
        {
            "usage_receipt": {
                "schema_version": "entroping.deepseek-usage-receipt.v1",
                "accounting_status": "unaccounted",
                "accounting_reason": "request_not_dispatched",
                "job_id": job_id,
                "requested_model": requested_model,
                "run_id": run_id,
            }
        },
        expected_run_id=run_id,
        occurred_at=occurred_at,
    )


def _job_text(job: dict[str, object], key: str) -> str:
    value = job.get(key)
    if not isinstance(value, str) or not value:
        raise PaidDispatchError("job", f"job {key} is missing")
    return value
