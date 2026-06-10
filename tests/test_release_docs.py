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


def test_onboarding_documents_typer_shell_completion_global_options() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )

    for document in (readme, user_guide):
        assert "entroping --install-completion" in document
        assert "entroping --show-completion" in document
        assert "Typer global option" in document
        assert "not an Entroping subcommand" in document


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


def test_project_progress_stays_a_short_daily_dashboard() -> None:
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    required_sections = [
        "## Daily Dashboard",
        "## Current Target",
        "## Next Three Issues",
        "## External Stable-Core Blockers",
        "## Latest Evidence",
        "## Source Of Truth",
        "## Update Rules",
    ]
    for section in required_sections:
        assert section in progress

    assert "## Milestone Progress" not in progress
    assert "## Later Roadmap" not in progress
    assert "after #491 closes" not in progress
    assert "traffic approval manifest redaction confidence" in progress
    assert progress.count("[Changed Hurl test runs]") == 1
    assert (
        progress.count(
            "Keep historical context in the vault and `.context/changelog.md`, not here."
        )
        == 1
    )
    assert len(progress.splitlines()) <= 150


def test_roadmap_separates_direction_sequence_and_external_blockers() -> None:
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    stable_core_blockers = roadmap.split(
        "## External Stable-Core Blockers", maxsplit=1
    )[1].split("## Future: v1.0 Stable Core", maxsplit=1)[0]

    required_sections = [
        "## Product Direction",
        "## Near-Term Sequence",
        "## External Stable-Core Blockers",
        "## Explicitly Not Near-Term",
    ]
    for section in required_sections:
        assert section in roadmap

    assert "GitHub Issues remain the backlog" in roadmap
    assert "Do not call the project stable just because alpha gates are green" in roadmap
    assert "package-index proof" in stable_core_blockers
    assert "compatibility policy" in stable_core_blockers
    assert "real downstream user feedback" in stable_core_blockers
    assert "provider-specific CI templates" in stable_core_blockers
    assert "repeated release evidence" not in stable_core_blockers


def test_doc_governance_blocks_strategy_doc_sprawl() -> None:
    governance = (REPO_ROOT / "docs" / "meta" / "DOCS_GOVERNANCE.md").read_text(
        encoding="utf-8"
    )

    assert "Do not create a new strategy document" in governance
    assert "existing canonical owner" in governance
    assert "GitHub Issues remain the backlog" in governance
    assert "Public Docs Curation Rule" in governance
    assert "Do not expose maintainer memory as first-level public navigation" in governance


def test_readme_surfaces_public_docs_before_project_context() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    public_docs_link = "[Public Docs](https://sakibshuvo.github.io/Entroping/)"
    assert public_docs_link in readme
    assert "[Two-Minute Demo](#try-it-in-two-minutes)" in readme
    assert "[Roadmap](ROADMAP.md)" in readme
    assert "[Project Context](#project-context)" in readme
    assert "[Vault Index](docs/meta/VAULT_INDEX.md)" in readme
    assert readme.index(public_docs_link) < readme.index("## Why Entroping")

    assert "## Deep Docs" not in readme
    project_context = readme.split("## Project Context", maxsplit=1)[1].split(
        "## Locked Alpha CLI Surface",
        maxsplit=1,
    )[0]
    expected_ownership_lines = [
        "Public Docs are the adoption path",
        "GitHub Issues track work",
        "Obsidian is project memory, not the backlog",
        "`docs/meta/DOCS_GOVERNANCE.md` decides which docs must change",
    ]
    for ownership_line in expected_ownership_lines:
        assert ownership_line in project_context
    assert "Product:" not in project_context
    assert "Technical:" not in project_context
    assert "Operating the project:" not in project_context
    assert project_context.count("\n- ") <= 8
    assert len(project_context.splitlines()) <= 45


def test_readme_keeps_backstage_context_out_of_product_pitch() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    public_pitch = readme.split("## Project Context", maxsplit=1)[0]
    project_context = readme.split("## Project Context", maxsplit=1)[1].split(
        "## Locked Alpha CLI Surface",
        maxsplit=1,
    )[0]

    backstage_terms = [
        "Obsidian",
        "knowledge base",
        ".context",
        "docs/meta/",
        "VAULT_INDEX",
    ]
    for term in backstage_terms:
        assert term not in public_pitch

    assert "Maintainer and agent context is backstage" in project_context
    assert "not required for first use" in project_context


def test_mkdocs_home_explains_repository_context_surfaces() -> None:
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert "How This Site Fits" in index
    expected_surfaces = [
        "public reading path",
        "GitHub Issues track work",
        "`ROADMAP.md` sequences releases",
        "`docs/meta/VAULT_INDEX.md` maps the Obsidian vault",
        "`docs/meta/DOCS_GOVERNANCE.md` defines update rules",
    ]
    for surface in expected_surfaces:
        assert surface in index


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
    assert "## Project Context" in readme
    assert "## Current Alpha" in readme
    assert readme.index("## Use Entroping When") < readme.index(
        "## Try It In Two Minutes"
    )
    assert readme.index("## Try It In Two Minutes") < readme.index("## Current Alpha")
    assert readme.index("## Try It In Two Minutes") < readme.index("## Project Context")

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


def test_readme_frontloads_owasp_policy_pack_wedge_without_overclaiming() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    first_read = readme.split("## Current Alpha", maxsplit=1)[0]
    normalized_first_read = " ".join(first_read.split())

    required_phrases = [
        "OWASP API Top 10 starter policy pack",
        "examples/policy-packs/owasp-api-top-10",
        "missing auth",
        "request ID",
        "before merge",
        "inspired starter pack",
        "not official OWASP endorsement",
        "not complete compliance",
    ]
    for phrase in required_phrases:
        assert phrase in normalized_first_read

    assert normalized_first_read.index(
        "OWASP API Top 10 starter policy pack"
    ) < normalized_first_read.index(
        "## What You Get"
    )


def test_launch_copy_keeps_advanced_surfaces_out_of_front_door() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    public_pitch = readme.split("## Project Context", maxsplit=1)[0]
    project_context = readme.split("## Project Context", maxsplit=1)[1].split(
        "## Locked Alpha CLI Surface",
        maxsplit=1,
    )[0]

    for advanced_surface in ["WireMock", "GraphQL", "SOAP", "Studio"]:
        assert advanced_surface not in public_pitch

    assert "REST/OpenAPI + QAnstitution + Hurl + CI reports" in project_context
    assert "advanced examples remain documented" in project_context
    assert "examples/graphql-api" not in project_context
    assert "examples/soap-api" not in project_context
    assert "Studio Mutation Workflow Design" not in docs_index.split(
        "## Project Context",
        maxsplit=1,
    )[0]
    assert "Advanced Boundaries" in mkdocs
    assert "Studio Mutation Workflow Design" in mkdocs


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
    assert "scripts/release_evidence.py --check-freshness" in checklist
    assert "scripts/package_check.sh" in checklist
    assert "scripts/local_wheel_install_smoke.py --skip-build" in checklist
    assert "scripts/downstream_smoke.py" in checklist
    assert "--skip-downstream-smoke" in checklist
    assert "License-Expression" in checklist
    assert "local wheel install smoke" in checklist
    assert "temporary project outside the repository" in checklist
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
    assert "scripts/release_evidence.py --check-freshness" in release_evidence
    assert "does not mutate the ledger" in release_evidence
    assert "scripts/stable_core_readiness.py --format json" in release_evidence
    assert "blocker_issue_map" in release_evidence
    assert "release-evidence.json" in stable_readiness
