"""Guardrails for policy-pack distribution and provenance docs."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_policy_pack_distribution_path_covers_required_decisions() -> None:
    doc = (
        REPO_ROOT / "docs" / "technical" / "POLICY_PACK_DISTRIBUTION.md"
    ).read_text(encoding="utf-8")

    required_sections = [
        "## Decision",
        "## Versioning",
        "## Distribution Modes",
        "## Import And Verification",
        "## Provenance And Attribution",
        "## Open-Core And Premium Boundary",
        "## Minimum Smoke Evidence",
        "## Follow-Up Issues",
    ]
    for section in required_sections:
        assert section in doc

    required_terms = [
        "local-first",
        "inspectable QAnstitution imports",
        "final-gate behavior",
        "entroping-policy-pack.yaml",
        "scripts/policy_pack_smoke.py --strict",
        "policy-pack source",
        "license",
        "attribution",
        "open-core packs",
        "premium packs",
        "no registry fetch",
        "no runtime manifest dependency",
        "issues/329",
        "issues/330",
        "issues/331",
        "issues/332",
    ]
    for term in required_terms:
        assert term in doc


def test_policy_pack_distribution_doc_is_linked_from_entrypoints() -> None:
    required_links = {
        "docs/technical/POLICY_PACK_LAYOUT.md": "POLICY_PACK_DISTRIBUTION.md",
        "docs/product/OPEN_CORE_BOUNDARIES.md": "POLICY_PACK_DISTRIBUTION.md",
        "docs/meta/VAULT_INDEX.md": (
            "[[docs/technical/POLICY_PACK_DISTRIBUTION|POLICY_PACK_DISTRIBUTION]]"
        ),
        "docs/index.md": "technical/POLICY_PACK_DISTRIBUTION.md",
        "mkdocs.yml": "Policy Pack Distribution: technical/POLICY_PACK_DISTRIBUTION.md",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
