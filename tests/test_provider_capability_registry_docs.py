from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_REFERENCE = "docs/meta/provider-capability-registry.json"
QUEUE_COMMAND_RE = re.compile(
    r"scripts/ai_jobs\.py\s+(?:audit-routing|run-next|status|submit)\b"
)


class _RoleRegistry(TypedDict):
    provider_capability_registry: str
    worker_routing_defaults: dict[str, dict[str, object]]


def test_role_registry_delegates_provider_defaults_to_capability_registry() -> None:
    payload = cast(
        _RoleRegistry,
        yaml.safe_load(
            (REPO_ROOT / "docs/meta/AGENT_ROLE_REGISTRY.yaml").read_text(encoding="utf-8")
        ),
    )

    assert payload["provider_capability_registry"] == REGISTRY_REFERENCE
    routing = payload["worker_routing_defaults"]
    assert routing["tier_a"]["default_queue_engine"] == "opencode"
    assert routing["tier_a"]["default_queue_selector"] == "tier_a"
    duplicated_keys = {
        "default_profile",
        "default_model",
        "default_provider_lane",
        "fallback_provider_lanes",
    }
    assert all(not duplicated_keys.intersection(defaults) for defaults in routing.values())
    tier_a = routing["tier_a"]
    assert tier_a["context_manifest_command"] == (
        "scripts/context_pack.sh --mode implementation --manifest"
    )
    assert "request only the needed files/snippets" in cast(str, tier_a["context_rule"])
    assert tier_a["merge_authority"] == "Tier A autonomous after gates and green CI"
    assert routing["tier_b"]["merge_authority"] == "Codex/human required"
    assert routing["tier_c"]["merge_authority"] == "Codex/human required"
    assert "security-sensitive" in cast(str, routing["tier_c"]["stop_condition"])


def test_provider_workflow_surfaces_point_to_canonical_registry() -> None:
    surfaces = (
        ".github/pull_request_template.md",
        "docs/meta/AGENT_CONTROL_PLANE.md",
        "docs/meta/FACTORY_OPERATIONS.md",
        "docs/technical/TDS.md",
        "docs/meta/prompt-library/model-comparison-trial.md",
        "docs/meta/prompt-library/model-output-acceptance-gate.md",
        "docs/meta/prompt-library/opencode-codex-review-request.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
        "docs/meta/prompt-library/opencode-desktop-one-shot.md",
        "docs/meta/prompt-library/multi-agent-marathon.md",
    )

    for relative_path in surfaces:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert REGISTRY_REFERENCE in content, relative_path


def test_operational_queue_commands_use_project_environment() -> None:
    surfaces = (
        "docs/meta/AGENT_CONTROL_PLANE.md",
        "docs/meta/CONTEXT_MANAGEMENT.md",
        "docs/meta/prompt-library/deepseek-opencode-review.md",
        "docs/meta/prompt-library/opencode-codex-review-request.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
    )

    for relative_path in surfaces:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for match in QUEUE_COMMAND_RE.finditer(content):
            prefix = content[max(0, match.start() - len("uv run python ")) : match.start()]
            assert prefix == "uv run python ", (relative_path, match.group())


def test_prompt_placeholders_do_not_define_paid_lane_allowlists() -> None:
    prompt_paths = (
        ".github/pull_request_template.md",
        "docs/meta/prompt-library/model-comparison-trial.md",
        "docs/meta/prompt-library/model-output-acceptance-gate.md",
        "docs/meta/prompt-library/opencode-codex-review-request.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
        "docs/meta/prompt-library/opencode-desktop-one-shot.md",
        "docs/meta/prompt-library/multi-agent-marathon.md",
    )

    for relative_path in prompt_paths:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        provider_placeholders = [
            line for line in content.splitlines() if "registered lane id" in line
        ]
        assert provider_placeholders, relative_path
        assert all(REGISTRY_REFERENCE in line for line in provider_placeholders)
        assert all(" | " not in line for line in provider_placeholders)

    model_comparison = (REPO_ROOT / "docs/meta/prompt-library/model-comparison-trial.md").read_text(
        encoding="utf-8"
    )
    assert "codex/native" not in model_comparison
