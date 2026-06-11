"""Guardrails for distribution path recommendations."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATION = REPO_ROOT / "docs" / "meta" / "DISTRIBUTION_RECOMMENDATION.md"
CI_RECIPES = REPO_ROOT / "docs" / "user" / "CI_PROVIDER_RECIPES.md"
DECISION_REGISTRY = REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml"


def test_distribution_recommendation_compares_install_paths() -> None:
    doc = RECOMMENDATION.read_text(encoding="utf-8")

    required_terms = [
        "Recommendation: uv first, PyPI next, Homebrew tap after PyPI, standalone later",
        "uv tool install",
        "Homebrew tap",
        "standalone binary",
        "Python",
        "Hurl",
        "mitmproxy",
        "Graphviz",
        "Studio",
        "Do not start with signing or notarization",
    ]

    for term in required_terms:
        assert term in doc

    assert doc.index("## Options") < doc.index("## Recommendation")
    assert doc.index("## Recommendation") < doc.index("## Dependency Handling")


def test_distribution_recommendation_defers_premature_packaging_work() -> None:
    doc = RECOMMENDATION.read_text(encoding="utf-8")

    required_terms = [
        "Do not add a Homebrew formula in this issue",
        "Do not add a Dockerfile, container registry workflow, or Docker image publish job",
        "Do not add standalone binary automation in this issue",
        "PyPI/TestPyPI path must land first",
        "Nuitka",
        "PyInstaller",
        "macOS signing",
        "notarization",
        "follow-up implementation issues",
    ]

    for term in required_terms:
        assert term in doc


def test_standalone_binary_decision_requires_tap_demand_before_automation() -> None:
    doc = RECOMMENDATION.read_text(encoding="utf-8")

    required_terms = [
        "## Standalone Binary Decision",
        "Standalone binary decision: defer.",
        "Nuitka",
        "PyInstaller",
        "macOS signing",
        "notarization",
        "Windows signing",
        "Linux packaging",
        "Hurl",
        "Graphviz",
        "mitmproxy",
        "Studio",
        "Do not add binary build/signing automation",
        "after PyPI alpha and Homebrew tap demand are proven",
        "release-owner runbook",
    ]

    for term in required_terms:
        assert term in doc

    assert doc.index("## Standalone Binary Decision") < doc.index(
        "## Follow-Up Implementation Issues"
    )


def test_docker_ci_image_decision_is_deferred_and_pinnable() -> None:
    doc = RECOMMENDATION.read_text(encoding="utf-8")
    ci_recipes = CI_RECIPES.read_text(encoding="utf-8")
    registry = DECISION_REGISTRY.read_text(encoding="utf-8")

    required_distribution_terms = [
        "## Docker CI Image Decision",
        "Docker CI image decision: defer until package-index proof.",
        "GHCR",
        "ghcr.io/sakibshuvo/entroping-ci",
        "pinned Entroping, Hurl, and hurlfmt versions",
        "non-root runtime user",
        "OCI labels",
        "version tags",
        "rollback policy",
        "smoke checks",
        "pin by immutable digest",
        "Do not make Docker the only supported path",
        "GitHub release artifact fallback",
        "ADR-0018",
    ]
    for term in required_distribution_terms:
        assert term in doc

    required_ci_terms = [
        "## Future Docker CI Image",
        "not a supported CI path yet",
        "ghcr.io/sakibshuvo/entroping-ci",
        "pin by immutable digest",
        "does not replace the generic shell recipe",
        "package-index proof",
        "ADR-0018",
    ]
    for term in required_ci_terms:
        assert term in ci_recipes

    assert "ENT-DEC-0018" in registry
    assert "docker-ci-image" in registry
    assert "#595" in registry


def test_distribution_recommendation_is_linked_from_project_docs() -> None:
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    tds = (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")

    assert "[[docs/meta/DISTRIBUTION_RECOMMENDATION|DISTRIBUTION_RECOMMENDATION]]" in index
    assert "DISTRIBUTION_RECOMMENDATION.md" in readme
    assert "Distribution path recommendation" in progress
    assert "Standalone binary distribution decision" in progress
    assert "docs/meta/DISTRIBUTION_RECOMMENDATION.md" in tds
