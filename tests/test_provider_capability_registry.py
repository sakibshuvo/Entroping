from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.provider_capability_registry import (  # noqa: E402
    default_queue_route,
    load_provider_registry,
    provider_lane_ids,
    resolve_provider_evidence,
    resolve_queue_model,
)
from scripts.provider_capability_schema import provider_capability_json_schema  # noqa: E402
from scripts.provider_capability_types import (  # noqa: E402
    ProviderEvidence,
    ProviderRegistryError,
)

REGISTRY_PATH = REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "meta" / "provider-capability-registry.v1.schema.json"


def test_committed_registry_has_versioned_json_schema() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == (
        provider_capability_json_schema()
    )


def test_registry_loader_does_not_require_product_runtime_import() -> None:
    script = "\n".join(
        (
            "import builtins",
            "real_import = builtins.__import__",
            "def guarded_import(name, *args, **kwargs):",
            "    if name == 'entroping' or name.startswith('entroping.'):",
            "        raise RuntimeError('product runtime import is forbidden')",
            "    return real_import(name, *args, **kwargs)",
            "builtins.__import__ = guarded_import",
            "from scripts.provider_capability_registry import load_provider_registry",
            "print(load_provider_registry().schema_version)",
        )
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "entroping.provider-capability-registry.v1"


def test_registry_contains_required_provider_lanes_and_queue_defaults() -> None:
    registry = load_provider_registry()

    assert provider_lane_ids(registry) == (
        "codex-spark",
        "deepseek-api/direct",
        "opencode/native-deepseek",
        "opencode-go/glm-5.2",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
        "local/offline",
    )
    assert default_queue_route(registry, "opencode", "tier_a").model.id == (
        "opencode/deepseek-v4-flash-free"
    )
    assert default_queue_route(registry, "deepseek-api", "tier_a").model.id == ("deepseek-v4-flash")


def test_local_offline_lane_explicitly_accepts_unlisted_local_model() -> None:
    registry = load_provider_registry()

    resolve_provider_evidence(
        registry,
        ProviderEvidence(
            lane_id="local/offline",
            provider_host="local runtime",
            billing_path="local/offline",
            model_id="ollama/qwen-local",
            autonomy_tier="tier_b",
        ),
    )


def test_unlisted_local_model_still_obeys_lane_autonomy_ceiling() -> None:
    registry = load_provider_registry()
    local_lane = registry.lanes[-1].model_copy(update={"autonomy_ceiling": "tier_a"})
    restricted_registry = registry.model_copy(update={"lanes": (*registry.lanes[:-1], local_lane)})

    with pytest.raises(ProviderRegistryError, match="autonomy tier exceeds"):
        resolve_provider_evidence(
            restricted_registry,
            ProviderEvidence(
                lane_id="local/offline",
                provider_host="local runtime",
                billing_path="local/offline",
                model_id="ollama/qwen-local",
                autonomy_tier="tier_b",
            ),
        )


def test_paid_route_reports_host_and_billing_mismatches() -> None:
    registry = load_provider_registry()
    evidence = ProviderEvidence(
        lane_id="deepseek-api/direct",
        provider_host="wrong host",
        billing_path="paid direct DeepSeek API",
        model_id="deepseek-v4-pro",
        autonomy_tier="tier_c",
    )

    with pytest.raises(ProviderRegistryError, match="provider host does not match"):
        resolve_provider_evidence(registry, evidence)

    with pytest.raises(ProviderRegistryError, match="billing path does not match"):
        resolve_provider_evidence(
            registry,
            ProviderEvidence(
                lane_id=evidence.lane_id,
                provider_host="repo-local DeepSeek worker",
                billing_path="unexpected subscription",
                model_id=evidence.model_id,
                autonomy_tier=evidence.autonomy_tier,
            ),
        )


def test_paid_lane_cannot_enable_unlisted_models(tmp_path: Path) -> None:
    registry = load_provider_registry()
    paid_lane = registry.lanes[1].model_copy(update={"unlisted_model_policy": "allow_non_paid"})
    invalid_registry = registry.model_copy(
        update={"lanes": (registry.lanes[0], paid_lane, *registry.lanes[2:])}
    )
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(invalid_registry.model_dump_json(), encoding="utf-8")

    with pytest.raises(ProviderRegistryError, match="paid provider lanes"):
        _ = load_provider_registry(candidate)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(
        '{"schema_version":"entroping.provider-capability-registry.v1",'
        + '"schema_version":"entroping.provider-capability-registry.v1"}',
        encoding="utf-8",
    )

    with pytest.raises(ProviderRegistryError, match="duplicate JSON key"):
        _ = load_provider_registry(candidate)


def test_queue_engine_model_identifier_cannot_resolve_to_multiple_lanes(
    tmp_path: Path,
) -> None:
    registry = load_provider_registry()
    direct_lane = registry.lanes[1]
    opencode_model = registry.lanes[2].models[0]
    assert opencode_model.queue is not None
    conflicting_model = direct_lane.models[0].model_copy(
        update={
            "id": opencode_model.id,
            "queue": opencode_model.queue.model_copy(
                update={"profile": "shadow", "default_for": ()}
            ),
        }
    )
    conflicting_lane = direct_lane.model_copy(
        update={"models": (*direct_lane.models, conflicting_model)}
    )
    invalid_registry = registry.model_copy(
        update={"lanes": (registry.lanes[0], conflicting_lane, *registry.lanes[2:])}
    )
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(invalid_registry.model_dump_json(), encoding="utf-8")

    with pytest.raises(ProviderRegistryError, match="duplicate queue model"):
        _ = load_provider_registry(candidate)


def test_deprecated_model_remains_evidence_but_is_not_dispatchable(
    tmp_path: Path,
) -> None:
    registry = load_provider_registry()
    direct_lane = registry.lanes[1]
    flash_model = direct_lane.models[0]
    pro_model = direct_lane.models[1]
    new_default = flash_model.model_copy(
        update={
            "queue": flash_model.queue.model_copy(
                update={"default_for": ("tier_a", "standard")}
            )
            if flash_model.queue is not None
            else None
        }
    )
    deprecated_model = pro_model.model_copy(
        update={
            "lifecycle": "deprecated",
            "queue": pro_model.queue.model_copy(update={"default_for": ()})
            if pro_model.queue is not None
            else None,
        }
    )
    deprecated_lane = direct_lane.model_copy(
        update={"models": (new_default, deprecated_model)}
    )
    deprecated_registry = registry.model_copy(
        update={"lanes": (registry.lanes[0], deprecated_lane, *registry.lanes[2:])}
    )
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(
        deprecated_registry.model_dump_json(),
        encoding="utf-8",
    )
    loaded = load_provider_registry(candidate)

    resolve_provider_evidence(
        loaded,
        ProviderEvidence(
            lane_id="deepseek-api/direct",
            provider_host="repo-local DeepSeek worker",
            billing_path="paid direct DeepSeek API",
            model_id="deepseek-v4-pro",
            autonomy_tier="tier_c",
        ),
    )
    with pytest.raises(ProviderRegistryError, match="not active for new dispatch"):
        _ = resolve_queue_model(loaded, "deepseek-api", "deepseek-v4-pro")
    assert default_queue_route(loaded, "deepseek-api", "standard").model.id == (
        "deepseek-v4-flash"
    )


def test_registry_rejects_secret_like_content(tmp_path: Path) -> None:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(
        REGISTRY_PATH.read_text(encoding="utf-8").replace(
            "repo-local DeepSeek worker",
            "sk-probablysecret000000000000000000000000",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProviderRegistryError, match="secret-like content"):
        _ = load_provider_registry(candidate)


def test_registry_rejects_json_escaped_secret_like_content(tmp_path: Path) -> None:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text(
        REGISTRY_PATH.read_text(encoding="utf-8").replace(
            "repo-local DeepSeek worker",
            r"sk-\u0070robablysecret000000000000000000000000",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProviderRegistryError, match="secret-like content"):
        _ = load_provider_registry(candidate)


def test_registry_rejects_non_finite_exponent_without_traceback(tmp_path: Path) -> None:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text('{"value":1e100000}', encoding="utf-8")

    with pytest.raises(ProviderRegistryError, match="non-finite JSON number"):
        _ = load_provider_registry(candidate)


def test_registry_normalizes_excessive_nesting_error(tmp_path: Path) -> None:
    candidate = tmp_path / "registry.json"
    _ = candidate.write_text("[" * 600 + "0" + "]" * 600, encoding="utf-8")

    with pytest.raises(ProviderRegistryError, match="registry_(?:json|schema)"):
        _ = load_provider_registry(candidate)


def test_model_billing_override_does_not_inherit_lane_aliases() -> None:
    registry = load_provider_registry()

    with pytest.raises(ProviderRegistryError, match="billing path does not match"):
        resolve_provider_evidence(
            registry,
            ProviderEvidence(
                lane_id="opencode/native-deepseek",
                provider_host="OpenCode",
                billing_path="paid DeepSeek inside OpenCode",
                model_id="opencode/deepseek-v4-flash-free",
                autonomy_tier="tier_a",
            ),
        )
