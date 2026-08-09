"""Guardrails for the PyPI/TestPyPI release runbook."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "meta" / "PYPI_RELEASE_RUNBOOK.md"


def test_pypi_release_runbook_defines_token_free_testpypi_first_path() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    required_terms = [
        "TestPyPI first",
        "Trusted Publishing",
        "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247",
        "id-token: write",
        "environment: testpypi",
        "environment: pypi",
        "repository-url: https://test.pypi.org/legacy/",
        "No PyPI or TestPyPI tokens in GitHub secrets",
        "GitHub environment required reviewers",
        "scripts/release_check.sh --require-live-demo",
        "scripts/package_check.sh",
        "scripts/local_wheel_install_smoke.py --skip-build",
        "uv build",
        "uvx twine check dist/*",
    ]

    for term in required_terms:
        assert term in runbook

    assert runbook.index("## Policy") < runbook.index("## Preflight")
    assert runbook.index("## TestPyPI First") < runbook.index("## PyPI Publish")


def test_pypi_release_runbook_documents_versions_and_rollback() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    required_terms = [
        "Versioning And Prerelease Naming",
        "PEP 440",
        "0.2.0a1",
        "Do not upload the current `0.1.1` package version to PyPI as an alpha",
        "Rollback And Yank Notes",
        "Yank",
        "releases are immutable",
        "new fixed version",
    ]

    for term in required_terms:
        assert term in runbook


def test_pypi_release_runbook_is_linked_from_release_docs_and_index() -> None:
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    release_checklist = (
        REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    tds = (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")

    assert "[[docs/meta/PYPI_RELEASE_RUNBOOK|PYPI_RELEASE_RUNBOOK]]" in index
    assert "PYPI_RELEASE_RUNBOOK.md" in readme
    assert "docs/meta/PYPI_RELEASE_RUNBOOK.md" in release_checklist
    assert "docs/meta/PYPI_RELEASE_RUNBOOK.md" in tds
