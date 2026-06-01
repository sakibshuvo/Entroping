"""Guardrails for Entroping's public terminology and brand decisions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PHILOSOPHY = "The QAnstitution is Law. Traffic is Truth. Hurl is the Enforcer."
ADR = REPO_ROOT / "decisions" / "ADR-0012-brand-integrity-and-qanstitution-name.md"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_qanstitution_name_stays_canonical_without_compatibility_alias() -> None:
    adr = ADR.read_text(encoding="utf-8")
    glossary = _read("docs/meta/GLOSSARY.md")
    reference = _read("docs/technical/QANSTITUTION_REFERENCE.md")
    readme = _read("README.md")

    required_terms = [
        "qanstitution.yaml remains the canonical policy filename",
        "Do not add `entroping.yaml` or `entroping-policy.yaml` as aliases",
        "QAnstitution is not a placeholder name",
    ]
    for term in required_terms:
        assert term in adr

    assert "canonical policy filename" in glossary
    assert "canonical policy filename" in reference
    assert "`qanstitution.yaml`" in readme
    assert "entroping.yaml" not in readme
    assert "entroping-policy.yaml" not in readme


def test_core_philosophy_is_preserved_in_public_brand_surfaces() -> None:
    for relative_path in [
        "README.md",
        "docs/product/PRODUCT_SPEC.md",
        "docs/product/MARKETING_NOTE.md",
        "docs/meta/GLOSSARY.md",
        "decisions/ADR-0012-brand-integrity-and-qanstitution-name.md",
    ]:
        assert PHILOSOPHY in _read(relative_path)


def test_public_positioning_rejects_autonomous_agent_swarm_claims() -> None:
    product_spec = _read("docs/product/PRODUCT_SPEC.md")
    marketing = _read("docs/product/MARKETING_NOTE.md")
    readme = _read("README.md")

    assert "runtime governance and compliance-evidence layer" in product_spec
    assert "not an autonomous agent swarm" in product_spec
    assert "not an autonomous coding-agent orchestrator" in marketing
    assert "runtime governance" in readme

    public_launch_text = "\n".join(
        [readme, _read("docs/index.md"), _read("docs/user/USER_GUIDE.md")]
    )
    banned_public_phrases = [
        "Multi-Agent Swarm",
        "autonomous agent swarm",
        "directing fleets of coding agents",
    ]
    for phrase in banned_public_phrases:
        assert phrase not in public_launch_text


def test_branded_role_names_are_explained_not_removed() -> None:
    glossary = _read("docs/meta/GLOSSARY.md")
    product_spec = _read("docs/product/PRODUCT_SPEC.md")

    for term in ["Architect", "Builder", "Auditor", "Breaker", "Eye", "Enforcer"]:
        assert f"| {term} |" in glossary

    assert "The Architect is an AI-assisted subsystem" in product_spec
    assert "The Eye records" in product_spec
    assert "The Enforcer wraps the external Rust `hurl` binary" in product_spec
