"""Release-readiness documentation guardrails."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_links_alpha_release_gate_and_checklist() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "scripts/release_check.sh" in readme
    assert "scripts/package_check.sh" in readme
    assert "git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha" in readme
    assert "docs/meta/RELEASE_CHECKLIST.md" in readme


def test_public_roadmap_is_linked_from_front_door() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "00_INDEX.md").read_text(encoding="utf-8")

    assert "[ROADMAP.md](ROADMAP.md)" in readme
    assert "GitHub Project board" in readme
    assert "[[ROADMAP|ROADMAP]]" in index
    assert "v0.1.1-alpha Public Cleanup" in roadmap
    assert "v1.0 Stable Core" in roadmap
    assert "Explicitly Not Near-Term" in roadmap


def test_readme_is_demo_first_open_source_front_door() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Code at the speed of AI. Don't crash at the speed of AI." in readme
    assert "## Try It In Two Minutes" in readme
    assert "## Deep Docs" in readme
    assert "## Current Alpha" in readme
    assert readme.index("## Try It In Two Minutes") < readme.index("## Current Alpha")
    assert readme.index("## Try It In Two Minutes") < readme.index("## Deep Docs")

    first_read = readme.split("## Current Alpha", maxsplit=1)[0]
    assert "Available now:" not in first_read
    assert first_read.count("\n- ") <= 18


def test_readme_current_alpha_does_not_understate_alpha_as_scaffold() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    current_alpha = readme.split("## Current Alpha", maxsplit=1)[1].split(
        "## Install",
        maxsplit=1,
    )[0]
    repo_map = readme.split("## Repository Map", maxsplit=1)[1].split(
        "## Contributing And Community",
        maxsplit=1,
    )[0]

    assert "active alpha implementation" in current_alpha
    assert "initial Entroping knowledge base and implementation scaffold" not in readme
    assert "Python package scaffold" not in readme
    assert "Try the scaffolded CLI" not in readme
    assert "Python implementation scaffold" not in repo_map
    assert "Fast scaffold tests" not in repo_map


def test_alpha_release_checklist_documents_required_evidence() -> None:
    checklist = (REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "v0.1.1-alpha" in checklist
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


def test_context_plan_does_not_reintroduce_stale_post_alpha_status() -> None:
    plan = (REPO_ROOT / ".context" / "plan.md").read_text(encoding="utf-8")

    assert "Bridge compiler boundary modules exist but are mostly placeholders" not in plan
    assert "Next Slice: Architect Minimal Hardening" not in plan
    assert "Current Validation Queue" in plan
