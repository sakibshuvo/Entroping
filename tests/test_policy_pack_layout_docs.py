"""Guardrails for reusable QAnstitution policy-pack design."""

from pathlib import Path

import yaml

from entroping.core.config_loader import load_qanstitution

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_policy_pack_layout_design_covers_required_boundaries() -> None:
    design = (
        REPO_ROOT / "docs" / "technical" / "POLICY_PACK_LAYOUT.md"
    ).read_text(encoding="utf-8")

    required_sections = [
        "## Decision",
        "## Pack Layout",
        "## Import Semantics",
        "## Versioning",
        "## Conflict And Final-Gate Behavior",
        "## Open-Core Boundary",
        "## Runtime Non-Goals",
    ]
    for section in required_sections:
        assert section in design

    required_terms = [
        "No runtime behavior changes are introduced by this design note.",
        "entroping-policy-pack.yaml",
        "qanstitution.yaml",
        "rules/",
        "examples/consumer-qanstitution.yaml",
        "Local imports remain root-bounded",
        "HTTP(S) policy-pack imports remain future work",
        "Semantic Versioning",
        "final: true",
        "Premium policy packs can be commercial",
        "starter packs stay inspectable and runnable in the public core",
    ]
    for term in required_terms:
        assert term in design


def test_example_policy_pack_shape_is_loadable_and_runtime_neutral() -> None:
    pack_root = REPO_ROOT / "examples" / "policy-packs" / "api-baseline"
    manifest = yaml.safe_load(
        (pack_root / "entroping-policy-pack.yaml").read_text(encoding="utf-8")
    )

    assert manifest["id"] == "entroping.api-baseline"
    assert manifest["version"] == "0.1.0-alpha"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["entrypoint"] == "qanstitution.yaml"
    assert manifest["runtime_contract"] == "qanstitution-import"

    expected_files = [
        "README.md",
        "entroping-policy-pack.yaml",
        "qanstitution.yaml",
        "rules/security.yaml",
        "rules/reliability.yaml",
        "examples/consumer-qanstitution.yaml",
    ]
    for relative_path in expected_files:
        assert (pack_root / relative_path).is_file()

    effective_pack = load_qanstitution(pack_root / "qanstitution.yaml")
    gate_ids = {gate.id for gate in effective_pack.gates}

    assert "api-security.no_5xx" in gate_ids
    assert "api-security.request_id" in gate_ids
    assert "api-reliability.latency" in gate_ids
    assert any(gate.id == "api-security.no_5xx" and gate.final for gate in effective_pack.gates)
    assert effective_pack.agents == {}
    assert effective_pack.sources is None


def test_policy_pack_layout_is_linked_from_entrypoints() -> None:
    required_links = {
        "README.md": "POLICY_PACK_LAYOUT.md",
        "00_INDEX.md": "[[docs/technical/POLICY_PACK_LAYOUT|POLICY_PACK_LAYOUT]]",
        "docs/index.md": "technical/POLICY_PACK_LAYOUT.md",
        "mkdocs.yml": "Policy Pack Layout: technical/POLICY_PACK_LAYOUT.md",
        "docs/technical/QANSTITUTION_REFERENCE.md": "POLICY_PACK_LAYOUT.md",
        "docs/technical/TDS.md": "POLICY_PACK_LAYOUT.md",
        "docs/product/OPEN_CORE_BOUNDARIES.md": "POLICY_PACK_LAYOUT.md",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
