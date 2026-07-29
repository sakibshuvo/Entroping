from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import override

from pydantic import TypeAdapter, ValidationError

from .deepseek_worker_limits import (
    DEFAULT_MAX_REQUEST_BYTES,
    DEFAULT_MAX_TOKENS,
    MAX_TIMEOUT_SECONDS,
)
from .factory_budget_ledger import (
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    PriceTerm,
    UsageEnvelope,
)
from .factory_cost_policy_io import read_policy_document
from .factory_cost_policy_models import FactoryCostPolicy
from .factory_cost_policy_types import MeteredLane, PriceSnapshot
from .factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at
from .provider_capability_registry import load_provider_registry, resolve_queue_model
from .provider_capability_types import (
    ProviderCapabilityRegistry,
    ProviderRegistryError,
    ProviderRoute,
    QueueEngine,
)

QUEUE_ENGINE: TypeAdapter[QueueEngine] = TypeAdapter(QueueEngine)


@dataclass(frozen=True, slots=True)
class PaidDispatchError(RuntimeError):
    code: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class PaidDispatchReservation:
    reservation_id: str
    held_microcents: int
    provider_lane_id: str
    provider_id: str
    model_id: str
    requested_model: str

    def job_projection(self) -> dict[str, object]:
        return {
            "reservation_id": self.reservation_id,
            "settlement_state": "unresolved",
            "cost_provider_lane_id": self.provider_lane_id,
            "cost_provider_id": self.provider_id,
            "cost_model_id": self.model_id,
            "reserved_microcents": self.held_microcents,
        }


def prepare_paid_dispatch(
    project_root: Path,
    job: dict[str, object],
    *,
    registry: ProviderCapabilityRegistry | None = None,
    policy_path: Path,
    occurred_at: datetime,
    worker_dry_run: bool,
) -> PaidDispatchReservation | None:
    if worker_dry_run:
        return None
    route = _job_route(registry or load_provider_registry(), job)
    if route.billing_kind != "metered":
        return None
    if job.get("engine") != "deepseek-api":
        raise PaidDispatchError(
            "unsupported_accounting",
            "metered OpenCode dispatch has no enforceable usage ceiling",
        )
    provider_id = route.lane.cost_provider_id
    model_id = route.model.cost_model_id
    if provider_id is None or model_id is None:
        raise PaidDispatchError("route", "metered route lacks a cost identity")
    policy = _load_policy(policy_path, occurred_at)
    lane, snapshots = _metered_lane(policy, provider_id, model_id)
    terms = tuple(_price_term(snapshot) for snapshot in snapshots)
    units = {term.unit for term in terms}
    if not {"input_token", "output_token"}.issubset(units) or "minute" in units:
        raise PaidDispatchError(
            "price_contract",
            "direct paid dispatch requires input/output token prices and no minute price",
        )
    timeout_seconds = _positive_timeout(job.get("timeout_seconds"))
    usage = UsageEnvelope(
        requests=1,
        input_tokens=DEFAULT_MAX_REQUEST_BYTES,
        output_tokens=DEFAULT_MAX_TOKENS,
        minutes=math.ceil(timeout_seconds / 60),
    )
    ledger = FactoryBudgetLedger.open_project(project_root)
    try:
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
        receipt = ledger.reserve_for_dispatch(
            CostReservationRequest(
                idempotency_key=f"dispatch:{_required_job_id(job)}",
                job_id=_required_job_id(job),
                provider_lane_id=route.lane.id,
                provider_id=provider_id,
                model_id=model_id,
                requested_model=str(job["model"]),
                cost_policy_lane_id=lane.id,
                policy_id=policy.policy_id,
                policy_revision=policy.policy_revision,
                occurred_at=occurred_at,
                usage_envelope=usage,
                price_terms=terms,
            )
        )
    except FactoryBudgetLedgerError as exc:
        raise PaidDispatchError("ledger", exc.detail) from exc
    return PaidDispatchReservation(
        reservation_id=receipt.reservation_id,
        held_microcents=receipt.held_microcents,
        provider_lane_id=route.lane.id,
        provider_id=provider_id,
        model_id=model_id,
        requested_model=str(job["model"]),
    )


def _job_route(
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


def _metered_lane(
    policy: FactoryCostPolicy,
    provider_id: str,
    model_id: str,
) -> tuple[MeteredLane, tuple[PriceSnapshot, ...]]:
    matches = tuple(
        lane
        for lane in policy.automation_lanes
        if isinstance(lane, MeteredLane)
        and lane.enabled
        and lane.provider_id == provider_id
        and lane.model_id == model_id
    )
    if len(matches) != 1:
        raise PaidDispatchError(
            "cost_policy",
            "cost policy must enable exactly one matching metered lane",
        )
    lane = matches[0]
    by_id = {snapshot.id: snapshot for snapshot in policy.price_snapshots}
    snapshots = tuple(by_id[snapshot_id] for snapshot_id in lane.price_snapshot_ids)
    return lane, snapshots


def _price_term(snapshot: PriceSnapshot) -> PriceTerm:
    return PriceTerm(
        snapshot_id=snapshot.id,
        unit=snapshot.unit,
        quantity=snapshot.quantity,
        price_microcents=snapshot.price_microcents,
        observed_at=snapshot.observed_at,
        expires_at=snapshot.expires_at,
    )


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
