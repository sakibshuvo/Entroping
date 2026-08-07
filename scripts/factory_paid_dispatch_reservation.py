from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from .deepseek_worker_limits import (
    DEFAULT_MAX_REQUEST_BYTES,
    DEFAULT_MAX_TOKENS,
    MAX_TIMEOUT_SECONDS,
)
from .factory_budget_ledger import (
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    UsageEnvelope,
)
from .factory_cost_policy_io import read_policy_document
from .factory_cost_policy_models import FactoryCostPolicy
from .factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at
from .factory_paid_dispatch_models import PaidDispatchError, PaidDispatchReservation
from .factory_paid_dispatch_policy import (
    cash_request,
    policy_lane,
    require_policy_quota_window,
)
from .factory_quota_evidence_io import AuthenticatedFactoryProviderEvidence
from .factory_quota_models import (
    DispatchAuthorizationRequest,
    QuotaObservation,
    QuotaRequirement,
    TopUpAttestation,
)
from .provider_capability_registry import load_provider_registry, resolve_queue_model
from .provider_capability_types import (
    ProviderCapabilityRegistry,
    ProviderRegistryError,
    ProviderRoute,
    QueueEngine,
)

QUEUE_ENGINE: TypeAdapter[QueueEngine] = TypeAdapter(QueueEngine)


def prepare_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    registry: ProviderCapabilityRegistry | None = None,
    policy_path: Path,
    occurred_at: datetime,
    worker_dry_run: bool,
    top_up_attestation: TopUpAttestation | None = None,
    quota_observations: tuple[QuotaObservation, ...] = (),
    provider_evidence: AuthenticatedFactoryProviderEvidence | None = None,
    work_purpose: Literal["experiment", "essential"] = "experiment",
) -> PaidDispatchReservation | None:
    if worker_dry_run:
        return None
    route = job_route(registry or load_provider_registry(), job)
    if route.billing_kind == "offline":
        return None
    if route.billing_kind == "metered" and job.get("engine") != "deepseek-api":
        raise PaidDispatchError(
            "unsupported_accounting",
            "metered OpenCode dispatch has no enforceable usage ceiling",
        )
    provider_id = route.lane.policy_provider_id or route.lane.cost_provider_id
    model_id = route.model.cost_model_id
    if provider_id is None:
        raise PaidDispatchError("route", "remote route lacks a policy identity")
    if route.billing_kind == "metered" and route.lane.cost_provider_id != provider_id:
        raise PaidDispatchError("route", "metered cost and policy identity are mismatched")
    policy = _load_policy(policy_path, occurred_at)
    lane = policy_lane(policy, provider_id, model_id, route.billing_kind)
    if provider_evidence is not None:
        if top_up_attestation is not None or quota_observations:
            raise PaidDispatchError("evidence", "provider evidence sources are ambiguous")
        top_up_attestation, quota_observations = provider_evidence.for_dispatch(
            provider_id=provider_id,
            provider_lane_id=route.lane.id,
            policy_id=policy.policy_id,
            policy_revision=policy.policy_revision,
        )
    timeout_seconds = _positive_timeout(job.get("timeout_seconds"))
    usage = UsageEnvelope(
        requests=1,
        input_tokens=DEFAULT_MAX_REQUEST_BYTES,
        output_tokens=DEFAULT_MAX_TOKENS,
        minutes=math.ceil(timeout_seconds / 60),
    )
    observations = {item.quota_id: item for item in quota_observations}
    quota_by_id = {item.id: item for item in policy.provider_quotas}
    for quota_id in lane.quota_ids:
        if quota_id in observations:
            require_policy_quota_window(
                policy,
                quota_by_id[quota_id],
                observations[quota_id],
                decision_at=occurred_at,
            )
    requirements = tuple(
        QuotaRequirement(
            quota_id=quota_id,
            unit=quota_by_id[quota_id].unit,
            limit=quota_by_id[quota_id].limit,
            observation=observations[quota_id],
        )
        for quota_id in lane.quota_ids
        if quota_id in observations
    )
    if len(requirements) != len(lane.quota_ids):
        raise PaidDispatchError("quota", "fresh quota observation is missing")
    cash_reservation = cash_request(
        lane,
        job_id=_required_job_id(job),
        requested_model=str(job["model"]),
        provider_lane_id=route.lane.id,
        policy=policy,
        occurred_at=occurred_at,
        usage=usage,
        model_id=model_id,
    )
    authorization_request = DispatchAuthorizationRequest(
        idempotency_key=f"authorization:{_required_job_id(job)}",
        job_id=_required_job_id(job),
        provider_lane_id=route.lane.id,
        provider_id=provider_id,
        cost_policy_lane_id=lane.id,
        policy_id=policy.policy_id,
        policy_revision=policy.policy_revision,
        billing_mode=lane.billing_mode,
        work_purpose=work_purpose,
        usage_envelope=usage,
        cash_reservation=cash_reservation,
        quota_requirements=requirements,
        top_up_attestation=top_up_attestation,
        decision_at=occurred_at,
        expires_at=min(policy.expires_at, occurred_at + timedelta(minutes=5)),
    )
    try:
        authorization_request.validate()
        ledger = FactoryBudgetLedger.open_project(project_root)
        _ = ledger.initialize_period(
            BudgetPeriodConfig(
                starts_on=occurred_at.date().replace(day=1),
                cash_cap_microcents=policy.cash.calendar_month_cap_microcents,
                emergency_reserve_microcents=policy.cash.emergency_reserve_microcents,
                currency=policy.currency,
                policy_id=policy.policy_id,
                policy_revision=policy.policy_revision,
                reserve_idempotency_key=(
                    f"period:{policy.policy_id}:{policy.policy_revision}:{occurred_at:%Y-%m}"
                ),
            )
        )
        receipt = ledger.authorize_dispatch(authorization_request)
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError(exc.code, exc.detail) from exc
    return PaidDispatchReservation(
        authorization_id=receipt.authorization_id,
        reservation_id=receipt.reservation_id,
        held_microcents=receipt.held_microcents,
        provider_lane_id=route.lane.id,
        provider_id=provider_id,
        model_id=model_id,
        requested_model=str(job["model"]),
    )


def revalidate_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    occurred_at: datetime,
    consume_for_launch: bool = False,
) -> PaidDispatchReservation:
    job_id = _required_job_id(job)
    authorization_id = job.get("dispatch_authorization_id")
    if not isinstance(authorization_id, str):
        raise PaidDispatchError("authorization", "dispatch authorization is missing")
    try:
        ledger = FactoryBudgetLedger.open_project(project_root)
        authorization = ledger.authorization_for_job(job_id)
        if authorization is None or authorization.authorization_id != authorization_id:
            raise PaidDispatchError(
                "authorization",
                "dispatch authorization is invalid or expired",
            )
        if consume_for_launch:
            _ = ledger.consume_dispatch_authorization_for_launch(
                job_id,
                as_of=occurred_at,
            )
        elif not ledger.validate_dispatch_authorization(job_id, as_of=occurred_at):
            raise PaidDispatchError(
                "authorization",
                "dispatch authorization is invalid or expired",
            )
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError(exc.code, exc.detail) from exc
    return PaidDispatchReservation(
        authorization_id=authorization.authorization_id,
        reservation_id=authorization.reservation_id,
        held_microcents=authorization.held_microcents,
        provider_lane_id=_job_text(job, "cost_provider_lane_id"),
        provider_id=_job_text(job, "cost_provider_id"),
        model_id=(value if isinstance((value := job.get("cost_model_id")), str) else None),
        requested_model=_job_text(job, "model"),
    )


def _job_text(job: dict[str, object], key: str) -> str:
    value = job.get(key)
    if not isinstance(value, str) or not value:
        raise PaidDispatchError("job", f"job {key} is missing")
    return value


def job_route(
    registry: ProviderCapabilityRegistry,
    job: dict[str, object],
) -> ProviderRoute:
    model = job.get("model")
    if not isinstance(model, str):
        raise PaidDispatchError("route", "job route is invalid")
    try:
        engine = QUEUE_ENGINE.validate_python(job.get("engine"), strict=True)
        return resolve_queue_model(registry, engine, model)
    except ValidationError:
        raise PaidDispatchError("route", "job route is invalid") from None
    except ProviderRegistryError as exc:
        raise PaidDispatchError("route", exc.detail) from exc


def _load_policy(path: Path, occurred_at: datetime) -> FactoryCostPolicy:
    try:
        policy = FactoryCostPolicy.model_validate_json(read_policy_document(path))
        validate_policy_at(policy, occurred_at)
        return policy
    except (FactoryCostPolicyError, ValidationError, OSError) as exc:
        raise PaidDispatchError(
            "cost_policy",
            "cost policy is unavailable or invalid",
        ) from exc


def _required_job_id(job: dict[str, object]) -> str:
    value = job.get("job_id")
    if not isinstance(value, str) or not value:
        raise PaidDispatchError("job", "job id is missing")
    return value


def _positive_timeout(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > MAX_TIMEOUT_SECONDS
    ):
        raise PaidDispatchError("job", "job timeout is invalid")
    return float(value)
