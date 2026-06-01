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
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert "[ROADMAP.md](ROADMAP.md)" in readme
    assert "GitHub Project board" in readme
    assert "[[ROADMAP|ROADMAP]]" in index
    assert "v0.1.1-alpha Public Cleanup" in roadmap
    assert "v1.0 Stable Core" in roadmap
    assert "Explicitly Not Near-Term" in roadmap


def test_public_roadmap_does_not_reopen_completed_alpha_phases() -> None:
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    assert "## Completed: v0.2.0-alpha Adoption And Onboarding" in roadmap
    assert "## Completed: v0.3.0-alpha CLI/report-first Product Depth" in roadmap
    assert "## Current: v0.4.0-alpha Integrations" in roadmap
    assert "## Next: v0.2.0-alpha Adoption And Onboarding" not in roadmap
    assert "## Next: v0.3.0-alpha CLI/report-first product depth" not in roadmap
    assert "finish the v0.4 integration path" in progress
    assert "finish the v0.2 adoption path" not in progress


def test_readme_is_demo_first_open_source_front_door() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Code at the speed of AI. Don't crash at the speed of AI." in readme
    assert "## Use Entroping When" in readme
    assert "## Try It In Two Minutes" in readme
    assert "## Deep Docs" in readme
    assert "## Current Alpha" in readme
    assert readme.index("## Use Entroping When") < readme.index(
        "## Try It In Two Minutes"
    )
    assert readme.index("## Try It In Two Minutes") < readme.index("## Current Alpha")
    assert readme.index("## Try It In Two Minutes") < readme.index("## Deep Docs")

    use_cases = readme.split("## Use Entroping When", maxsplit=1)[1].split(
        "## Try It In Two Minutes",
        maxsplit=1,
    )[0]
    expected_use_cases = [
        "AI changed your API",
        "Your spec exists but tests do not",
        "Legacy behavior is undocumented",
        "Rules should apply everywhere",
        "PRs need evidence",
    ]
    for use_case in expected_use_cases:
        assert use_case in use_cases

    first_read = readme.split("## Current Alpha", maxsplit=1)[0]
    assert "Available now:" not in first_read
    assert first_read.count("\n- ") <= 18


def test_readme_promotes_demo_wrapper_without_expanding_cli_surface() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    command_cheat_sheet = (
        REPO_ROOT / "docs" / "technical" / "COMMAND_CHEAT_SHEET.md"
    ).read_text(encoding="utf-8")

    try_it = readme.split("## Try It In Two Minutes", maxsplit=1)[1].split(
        "## What You Get",
        maxsplit=1,
    )[0]

    assert "scripts/demo.sh" in try_it
    assert "scripts/live_demo_smoke.sh" in try_it
    assert "docs/assets/launch/checkout-demo.gif" in try_it
    assert "docs/assets/launch/ai-regression-proof.gif" in try_it
    assert "entroping demo" not in command_cheat_sheet


def test_zero_config_demo_decision_keeps_live_smoke_as_release_gate() -> None:
    decision = (
        REPO_ROOT / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md"
    ).read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert "scripts/demo.sh" in decision
    assert "scripts/live_demo_smoke.sh" in decision
    assert "Do not add `entroping demo`" in decision
    assert "Do not add `init --demo`" in decision
    assert "[[docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT|ZERO_CONFIG_DEMO_ENTRYPOINT]]" in index


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
    assert "RELEASE_EVIDENCE.md" in checklist
    assert "scripts/release_evidence.py --strict" in checklist
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


def test_clean_checkout_smoke_evidence_is_documented() -> None:
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    changelog = (REPO_ROOT / ".context" / "changelog.md").read_text(encoding="utf-8")

    assert "[Public clean-checkout onboarding smoke]" in progress
    assert "scripts/release_check.sh --require-live-demo" in progress
    assert "clean-checkout onboarding smoke" in changelog


def test_context_plan_does_not_reintroduce_stale_post_alpha_status() -> None:
    plan = (REPO_ROOT / ".context" / "plan.md").read_text(encoding="utf-8")

    assert "Bridge compiler boundary modules exist but are mostly placeholders" not in plan
    assert "Next Slice: Architect Minimal Hardening" not in plan
    assert "Current Validation Queue" in plan


def test_release_evidence_ledger_is_discoverable_from_vault_and_docs() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    release_evidence = (
        REPO_ROOT / "docs" / "meta" / "RELEASE_EVIDENCE.md"
    ).read_text(encoding="utf-8")
    stable_readiness = (
        REPO_ROOT / "scripts" / "stable_core_readiness.py"
    ).read_text(encoding="utf-8")

    assert "[[docs/meta/RELEASE_EVIDENCE|RELEASE_EVIDENCE]]" in index
    assert "docs/meta/release-evidence.json" in release_evidence
    assert "scripts/release_evidence.py --strict" in release_evidence
    assert "release-evidence.json" in stable_readiness
