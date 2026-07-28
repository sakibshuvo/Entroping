from __future__ import annotations

from typing import Final

from .provider_capability_io import load_provider_registry as load_provider_registry
from .provider_capability_types import (
    AutonomyTier,
    ProviderCapabilityRegistry,
    ProviderEvidence,
    ProviderRegistryError,
    ProviderRoute,
    QueueDefault,
    QueueEngine,
)

__all__ = [
    "default_queue_route",
    "load_provider_registry",
    "provider_lane_ids",
    "queue_profile_entries",
    "resolve_provider_evidence",
    "resolve_queue_model",
    "supported_queue_engines",
]

AUTONOMY_RANK: Final = {"tier_a": 0, "tier_b": 1, "tier_c": 2}


def provider_lane_ids(registry: ProviderCapabilityRegistry) -> tuple[str, ...]:
    return tuple(lane.id for lane in registry.lanes)


def supported_queue_engines(
    registry: ProviderCapabilityRegistry,
) -> tuple[QueueEngine, ...]:
    return tuple(
        dict.fromkeys(
            model.queue.engine
            for lane in registry.lanes
            for model in lane.models
            if (
                model.queue is not None
                and lane.lifecycle == "active"
                and model.lifecycle == "active"
            )
        )
    )


def queue_profile_entries(
    registry: ProviderCapabilityRegistry,
    engine: QueueEngine,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (model.queue.profile, model.id)
        for lane in registry.lanes
        for model in lane.models
        if (
            model.queue is not None
            and model.queue.engine == engine
            and lane.lifecycle == "active"
            and model.lifecycle == "active"
        )
    )


def default_queue_route(
    registry: ProviderCapabilityRegistry,
    engine: QueueEngine,
    selector: QueueDefault,
) -> ProviderRoute:
    for route in _queue_routes(registry, engine):
        if selector in route.queue.default_for:
            if route.model.lifecycle != "active" or route.lane.lifecycle != "active":
                raise ProviderRegistryError(
                    code="inactive_queue_model",
                    detail="queue model is not active for new dispatch",
                )
            return route
    raise ProviderRegistryError(
        code="queue_default",
        detail=f"provider registry has no {selector!r} default for engine {engine!r}",
    )


def resolve_queue_model(
    registry: ProviderCapabilityRegistry,
    engine: QueueEngine,
    model_id: str,
    *,
    autonomy_tier: AutonomyTier | None = None,
) -> ProviderRoute:
    for route in _queue_routes(registry, engine):
        if model_id == route.model.id or model_id in route.model.aliases:
            if route.model.lifecycle != "active" or route.lane.lifecycle != "active":
                raise ProviderRegistryError(
                    code="inactive_queue_model",
                    detail="queue model is not active for new dispatch",
                )
            if "queue_dispatch" not in route.lane.capabilities:
                raise ProviderRegistryError(
                    code="queue_dispatch_capability",
                    detail="queue route does not declare the queue_dispatch capability",
                )
            if (
                autonomy_tier is not None
                and AUTONOMY_RANK[autonomy_tier]
                > AUTONOMY_RANK[route.lane.autonomy_ceiling]
            ):
                raise ProviderRegistryError(
                    code="autonomy_ceiling",
                    detail=f"autonomy tier exceeds the ceiling for lane {route.lane.id!r}",
                )
            return route
    raise ProviderRegistryError(
        code="unknown_paid_provider_model",
        detail=(
            f"unknown paid provider/model combination for queue engine {engine!r}; "
            "register the model before dispatch"
        ),
    )


def resolve_provider_evidence(
    registry: ProviderCapabilityRegistry,
    evidence: ProviderEvidence,
) -> None:
    lane = next((item for item in registry.lanes if item.id == evidence.lane_id), None)
    if lane is None:
        raise ProviderRegistryError(
            code="unknown_provider_lane",
            detail=f"unknown provider lane {evidence.lane_id!r}",
        )
    if evidence.provider_host not in (lane.provider_host, *lane.provider_host_aliases):
        raise ProviderRegistryError(
            code="provider_host",
            detail=f"provider host does not match lane {lane.id!r}",
        )
    if AUTONOMY_RANK[evidence.autonomy_tier] > AUTONOMY_RANK[lane.autonomy_ceiling]:
        raise ProviderRegistryError(
            code="autonomy_ceiling",
            detail=f"autonomy tier exceeds the ceiling for lane {lane.id!r}",
        )
    model = next(
        (
            item
            for item in lane.models
            if evidence.model_id == item.id or evidence.model_id in item.aliases
        ),
        None,
    )
    if model is None:
        if lane.unlisted_model_policy == "allow_non_paid":
            if evidence.billing_path not in (lane.billing_path, *lane.billing_path_aliases):
                raise ProviderRegistryError(
                    code="billing_path",
                    detail=f"billing path does not match lane {lane.id!r}",
                )
            return
        raise ProviderRegistryError(
            code="unknown_paid_provider_model",
            detail=(
                f"unknown paid provider/model combination for lane {lane.id!r}; "
                "register the model before using this evidence"
            ),
        )
    billing_path = model.billing_path or lane.billing_path
    billing_aliases = (
        model.billing_path_aliases
        if model.billing_path is not None
        else lane.billing_path_aliases
    )
    if evidence.billing_path not in (billing_path, *billing_aliases):
        raise ProviderRegistryError(
            code="unknown_paid_provider_model",
            detail=(
                f"unknown paid provider/model combination for lane {lane.id!r}; "
                "billing path does not match the registered model"
            ),
        )


def _queue_routes(
    registry: ProviderCapabilityRegistry,
    engine: QueueEngine,
) -> tuple[ProviderRoute, ...]:
    routes: list[ProviderRoute] = []
    for lane in registry.lanes:
        for model in lane.models:
            if model.queue is None or model.queue.engine != engine:
                continue
            routes.append(
                ProviderRoute(
                    lane=lane,
                    model=model,
                    queue=model.queue,
                    billing_path=model.billing_path or lane.billing_path,
                    billing_kind=model.billing_kind or lane.billing_kind,
                    usage_accounting=model.usage_accounting or lane.usage_accounting,
                )
            )
    return tuple(routes)
