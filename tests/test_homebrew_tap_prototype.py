"""Guardrails for the Homebrew tap prototype."""

from pathlib import Path

from _public_docs import public_doc_sources

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMULA_TEMPLATE = REPO_ROOT / "packaging" / "homebrew" / "Formula" / "entroping.rb.template"
TAP_DOC = REPO_ROOT / "docs" / "meta" / "HOMEBREW_TAP_PROTOTYPE.md"


def test_homebrew_formula_template_uses_package_index_source_and_hurl() -> None:
    formula = FORMULA_TEMPLATE.read_text(encoding="utf-8")

    required_terms = [
        "class Entroping < Formula",
        "include Language::Python::Virtualenv",
        'depends_on "python@3.12"',
        'depends_on "hurl"',
        "virtualenv_install_with_resources",
        'system bin/"entroping", "--version"',
        'system bin/"entroping", "doctor"',
        "REPLACE_WITH_PYPI_SDIST_URL",
        "REPLACE_WITH_PYPI_SDIST_SHA256",
        "brew update-python-resources",
    ]

    for term in required_terms:
        assert term in formula


def test_homebrew_formula_template_keeps_default_install_small() -> None:
    formula = FORMULA_TEMPLATE.read_text(encoding="utf-8").lower()

    blocked_default_terms = [
        "mitmproxy",
        "graphviz",
        "textual",
        "litellm",
        "openai",
        "anthropic",
    ]

    for term in blocked_default_terms:
        assert term not in formula


def test_homebrew_tap_prototype_documents_launch_blockers_and_smoke_path() -> None:
    doc = TAP_DOC.read_text(encoding="utf-8")

    required_terms = [
        "Prototype only",
        "Do not publish a public tap until the PyPI alpha is proven",
        "PyPI sdist",
        "Hurl",
        "not bundled",
        "brew tap-new",
        "brew audit --strict --formula",
        "brew install --build-from-source",
        "entroping doctor",
        "scripts/demo.sh",
        "mitmproxy, Graphviz, Studio, and AI extras stay out of the default formula",
    ]

    for term in required_terms:
        assert term in doc

    assert doc.index("## Decision") < doc.index("## Prototype Formula")
    assert doc.index("## Prototype Formula") < doc.index("## Local Tap Smoke")


def test_homebrew_tap_prototype_is_linked_from_distribution_docs() -> None:
    recommendation = (REPO_ROOT / "docs" / "meta" / "DISTRIBUTION_RECOMMENDATION.md").read_text(
        encoding="utf-8"
    )
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    changelog = (REPO_ROOT / ".context" / "changelog.md").read_text(encoding="utf-8")

    assert "HOMEBREW_TAP_PROTOTYPE.md" in recommendation
    assert "Homebrew tap prototype" in progress
    assert "issue #224" in changelog
    assert "docs/meta/HOMEBREW_TAP_PROTOTYPE.md" in public_doc_sources()
