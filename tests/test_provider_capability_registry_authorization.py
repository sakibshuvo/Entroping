from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.provider_capability_registry import (  # noqa: E402
    load_provider_registry,
    resolve_queue_model,
)
from scripts.provider_capability_types import ProviderRegistryError  # noqa: E402


def _write_candidate(tmp_path: Path, payload: str) -> Path:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(payload, encoding="utf-8")
    return candidate


def test_queue_binding_requires_queue_dispatch_capability(tmp_path: Path) -> None:
    registry = load_provider_registry()
    queue_lane = registry.lanes[2]
    capabilities = tuple(
        capability
        for capability in queue_lane.capabilities
        if capability != "queue_dispatch"
    )
    invalid_lane = queue_lane.model_copy(update={"capabilities": capabilities})
    invalid_registry = registry.model_copy(
        update={"lanes": (*registry.lanes[:2], invalid_lane, *registry.lanes[3:])}
    )
    candidate = _write_candidate(tmp_path, invalid_registry.model_dump_json())

    with pytest.raises(ProviderRegistryError, match="queue_dispatch capability"):
        _ = load_provider_registry(candidate)


def test_queue_model_rejects_autonomy_above_lane_ceiling(tmp_path: Path) -> None:
    registry = load_provider_registry()
    queue_lane = registry.lanes[2].model_copy(update={"autonomy_ceiling": "tier_a"})
    restricted_registry = registry.model_copy(
        update={"lanes": (*registry.lanes[:2], queue_lane, *registry.lanes[3:])}
    )
    candidate = _write_candidate(tmp_path, restricted_registry.model_dump_json())
    loaded = load_provider_registry(candidate)

    with pytest.raises(ProviderRegistryError, match="autonomy tier exceeds"):
        _ = resolve_queue_model(
            loaded,
            "opencode",
            "deepseek/deepseek-v4-pro",
            autonomy_tier="tier_b",
        )


def test_metered_routes_expose_qualified_cost_identity() -> None:
    registry = load_provider_registry()
    direct_lane = registry.lanes[1]

    assert direct_lane.cost_provider_id == "deepseek"
    assert direct_lane.policy_provider_id == "deepseek"
    assert direct_lane.models[0].cost_model_id == "deepseek/deepseek-v4-flash"
    assert direct_lane.models[1].cost_model_id == "deepseek/deepseek-v4-pro"


@pytest.mark.parametrize("lane_index", [0, 3])
def test_quota_backed_routes_require_policy_provider_identity(
    tmp_path: Path,
    lane_index: int,
) -> None:
    registry = load_provider_registry()
    invalid_lane = registry.lanes[lane_index].model_copy(
        update={"policy_provider_id": None}
    )
    invalid_registry = registry.model_copy(
        update={
            "lanes": (
                *registry.lanes[:lane_index],
                invalid_lane,
                *registry.lanes[lane_index + 1 :],
            )
        }
    )
    candidate = _write_candidate(tmp_path, invalid_registry.model_dump_json())

    with pytest.raises(ProviderRegistryError, match="policy provider identity"):
        _ = load_provider_registry(candidate)


def test_metered_model_requires_qualified_cost_identity(tmp_path: Path) -> None:
    registry = load_provider_registry()
    direct_lane = registry.lanes[1]
    invalid_model = direct_lane.models[0].model_copy(update={"cost_model_id": None})
    invalid_lane = direct_lane.model_copy(
        update={"models": (invalid_model, *direct_lane.models[1:])}
    )
    invalid_registry = registry.model_copy(
        update={"lanes": (registry.lanes[0], invalid_lane, *registry.lanes[2:])}
    )
    candidate = _write_candidate(tmp_path, invalid_registry.model_dump_json())

    with pytest.raises(ProviderRegistryError, match="cost_provider_id and cost_model_id"):
        _ = load_provider_registry(candidate)


def test_inactive_model_cannot_own_queue_default(tmp_path: Path) -> None:
    registry = load_provider_registry()
    direct_lane = registry.lanes[1]
    inactive_model = direct_lane.models[1].model_copy(update={"lifecycle": "deprecated"})
    invalid_lane = direct_lane.model_copy(
        update={"models": (direct_lane.models[0], inactive_model)}
    )
    invalid_registry = registry.model_copy(
        update={"lanes": (registry.lanes[0], invalid_lane, *registry.lanes[2:])}
    )
    candidate = _write_candidate(tmp_path, invalid_registry.model_dump_json())

    with pytest.raises(ProviderRegistryError, match="defaults must reference an active"):
        _ = load_provider_registry(candidate)
