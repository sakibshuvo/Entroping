"""Release-readiness documentation guardrails."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_links_alpha_release_gate_and_checklist() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "scripts/release_check.sh" in readme
    assert "scripts/package_check.sh" in readme
    assert "git+https://github.com/sakibshuvo/Entroping.git@v0.1.0-alpha" in readme
    assert "docs/meta/RELEASE_CHECKLIST.md" in readme


def test_alpha_release_checklist_documents_required_evidence() -> None:
    checklist = (REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "v0.1.0-alpha" in checklist
    assert "scripts/package_check.sh" in checklist
    assert "License-Expression" in checklist
    assert "PyPI/TestPyPI tokens" in checklist
    assert "scripts/regression.sh --security" in checklist
    assert "scripts/live_demo_smoke.sh" in checklist
    assert "Not Built Yet" in checklist


def test_public_alpha_has_explicit_apache_license_metadata() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Development Status :: 5 - Production/Stable" not in project["classifiers"]
    assert not any(classifier.startswith("License ::") for classifier in project["classifiers"])
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Entroping Core is licensed under Apache-2.0" in readme
    assert "No license has been selected yet" not in readme


def test_progress_dashboard_marks_license_blocker_done() -> None:
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    assert (
        "| [Open-source license and package metadata]"
        "(https://github.com/sakibshuvo/Entroping/issues/58) | Done |"
    ) in progress
    assert "license/package metadata is the remaining public-release blocker" not in progress
