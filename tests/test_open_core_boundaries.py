"""Guardrails for open-core monetization boundaries."""

from pathlib import Path

from _public_docs import public_doc_sources

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_open_core_boundary_document_defines_public_core_and_commercial_edges() -> None:
    doc = (REPO_ROOT / "docs" / "product" / "OPEN_CORE_BOUNDARIES.md").read_text(
        encoding="utf-8"
    )

    required_sections = [
        "## Public Core Commitments",
        "## Commercial Surfaces",
        "## Boundary Rules",
        "## Decision Checklist",
    ]
    for section in required_sections:
        assert section in doc

    required_terms = [
        "Apache-2.0",
        "Local CLI",
        "Hurl execution",
        "QAnstitution parser",
        "Basic reports",
        "OpenAPI generation",
        "Traffic capture, freeze, and map MVP",
        "Local-first Brain integration",
        "Premium policy packs",
        "Hosted team dashboard",
        "Team audit history",
        "Support and implementation services",
        "Do not weaken the public core",
        "Do not make `entroping run` depend on a paid service",
        "Do not require telemetry",
    ]
    for term in required_terms:
        assert term in doc

    assert doc.index("## Public Core Commitments") < doc.index("## Commercial Surfaces")
    assert doc.index("## Commercial Surfaces") < doc.index("## Boundary Rules")
    assert doc.index("## Boundary Rules") < doc.index("## Decision Checklist")


def test_open_core_boundary_document_is_linked_from_entrypoints() -> None:
    boundary_link = "OPEN_CORE_BOUNDARIES.md"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    growth = (
        REPO_ROOT / "docs" / "product" / "GROWTH_AND_MONETIZATION.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    vault_index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert boundary_link in readme
    assert boundary_link in roadmap
    assert boundary_link in growth
    assert "product/OPEN_CORE_BOUNDARIES.md" in docs_index
    assert "[[docs/product/OPEN_CORE_BOUNDARIES|OPEN_CORE_BOUNDARIES]]" in vault_index
    assert "docs/product/OPEN_CORE_BOUNDARIES.md" in public_doc_sources()
