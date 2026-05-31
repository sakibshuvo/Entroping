"""Guardrails for distribution path recommendations."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATION = REPO_ROOT / "docs" / "meta" / "DISTRIBUTION_RECOMMENDATION.md"


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

    assert doc.index("## Standalone Binary Decision") < doc.index("## Follow-Up")


def test_distribution_recommendation_is_linked_from_project_docs() -> None:
    index = (REPO_ROOT / "00_INDEX.md").read_text(encoding="utf-8")
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
