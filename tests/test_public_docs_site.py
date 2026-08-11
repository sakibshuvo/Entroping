import json
import re
from pathlib import Path
from typing import cast

import yaml
from _public_docs import (
    PUBLIC_DOCS_MANIFEST,
    PublicDocsManifest,
    public_doc_slugs,
    public_doc_sources,
    public_sidebar_labels,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "package.json"
ASTRO_CONFIG = REPO_ROOT / "astro.config.mjs"
CONTENT_CONFIG = REPO_ROOT / "src" / "content.config.ts"
SITE_CHECK = REPO_ROOT / "scripts" / "check-site-build.mjs"
CLEAN_SITE_BUILD = REPO_ROOT / "scripts" / "clean-site-build.mjs"
MOBILE_MENU_TOGGLE = (
    REPO_ROOT / "src" / "components" / "docs" / "MobileMenuToggle.astro"
)
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"
CHECKOUT_PIN = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
SETUP_NODE_PIN = "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020"
CONFIGURE_PAGES_PIN = "actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d"
UPLOAD_PAGES_ARTIFACT_PIN = "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9"
DEPLOY_PAGES_PIN = "actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128"
GENERIC_SITE_DESCRIPTION = (
    "Local-first runtime governance for AI-assisted backend development."
)


def _manifest() -> PublicDocsManifest:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    return cast(
        PublicDocsManifest,
        json.loads(PUBLIC_DOCS_MANIFEST.read_text(encoding="utf-8")),
    )


def _frontmatter(source: str) -> dict[str, object]:
    lines = (REPO_ROOT / source).read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{source}: missing YAML frontmatter"
    try:
        closing_index = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError(f"{source}: unterminated YAML frontmatter") from exc
    payload = yaml.safe_load("\n".join(lines[1:closing_index]))
    assert isinstance(payload, dict), f"{source}: frontmatter must be a mapping"
    return cast(dict[str, object], payload)


def test_public_docs_manifest_uses_canonical_markdown() -> None:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    sources = public_doc_sources()

    assert "docs/index.md" in sources
    assert "docs/user/QANSTITUTION_FIRST_HOUR.md" in sources
    assert "docs/technical/QANSTITUTION_REFERENCE.md" in sources
    assert "docs/technical/TDS.md" in sources
    assert all((REPO_ROOT / source).is_file() for source in sources)
    assert len(sources) == len(set(sources))


def test_public_docs_manifest_requires_page_specific_descriptions() -> None:
    descriptions: dict[str, str] = {}

    for source in public_doc_sources():
        raw_description = _frontmatter(source).get("description")
        assert isinstance(raw_description, str), f"{source}: missing description"
        description = raw_description.strip()
        assert description == raw_description, f"{source}: description has edge whitespace"
        assert description, f"{source}: description is empty"
        assert 40 <= len(description) <= 160, (
            f"{source}: description must be a concise search snippet"
        )
        assert description != GENERIC_SITE_DESCRIPTION, (
            f"{source}: description must be page-specific"
        )
        normalized = description.casefold()
        assert normalized not in descriptions, (
            f"{source}: duplicate description from {descriptions.get(normalized)}"
        )
        descriptions[normalized] = source

    assert len(descriptions) == len(public_doc_sources())


def test_public_docs_manifest_has_unique_url_safe_slugs() -> None:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    slugs = public_doc_slugs()

    assert slugs[0] == "docs"
    assert all(slug == slug.lower() for slug in slugs)
    assert all(re.fullmatch(r"docs(?:/[a-z0-9-]+)*", slug) for slug in slugs)
    assert len(slugs) == len(set(slugs))


def test_public_docs_manifest_keeps_internal_context_out_of_navigation() -> None:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    sources = public_doc_sources()

    assert not any("prompt-library" in source for source in sources)
    assert not any("AGENT_CONTROL_PLANE" in source for source in sources)
    assert not any("docs/evolution/" in source for source in sources)
    assert not any(source.startswith(".context/") for source in sources)


def test_public_docs_manifest_preserves_curated_sidebar_order() -> None:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    manifest = _manifest()

    assert public_sidebar_labels() == [
        "Introduction",
        "Getting started",
        "Workflows",
        "Policy and QAnstitution",
        "CI and reports",
        "Technical reference",
        "Maintainer reference",
    ]
    assert manifest["groups"][-1].get("collapsed") is True
    assert [item["label"] for item in manifest["external"]] == ["Roadmap"]
    assert manifest["external"][0].get("url") == (
        "https://github.com/sakibshuvo/Entroping/blob/main/ROADMAP.md"
    )


def test_public_docs_manifest_prioritizes_users_over_asset_maintenance() -> None:
    manifest = _manifest()
    groups = {group["label"]: group for group in manifest["groups"]}

    getting_started = groups["Getting started"]["items"]
    assert [item["label"] for item in getting_started] == [
        "User Guide",
        "Policy First Hour",
    ]

    demo_assets = next(
        item
        for item in groups["Maintainer reference"]["items"]
        if item["source"] == "docs/assets/launch/README.md"
    )
    assert demo_assets["label"] == "Demo Asset Reference"


def test_public_guides_distinguish_contract_version_from_product_maturity() -> None:
    user_guide = (REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    use_cases = (REPO_ROOT / "docs" / "user" / "USE_CASES.md").read_text(
        encoding="utf-8"
    )

    for guide in (user_guide, use_cases):
        assert "**Product maturity:** Alpha" in guide
        assert "**Contract version:** 4.1" in guide
        assert "**Version:** 4.1 Stable" not in guide

    assert "Commit artifacts" not in user_guide
    assert "Commit reviewed tests and policy" in user_guide

    first_hour = (
        REPO_ROOT / "docs" / "user" / "QANSTITUTION_FIRST_HOUR.md"
    ).read_text(encoding="utf-8")
    assert "scripts/demo.sh" in first_hour
    assert "entroping init --minimal\nentroping doctor\nentroping run" not in first_hour


def test_public_docs_manifest_items_have_exact_route_or_external_shapes() -> None:
    manifest = _manifest()

    for group in manifest["groups"]:
        assert group["items"]
        for route in group["items"]:
            assert set(route) == {"label", "source", "slug"}
            assert route["source"].startswith("docs/")

    for external_item in manifest["external"]:
        assert set(external_item) == {"label", "url"}


def test_public_docs_manifest_keeps_existing_public_entries() -> None:
    assert PUBLIC_DOCS_MANIFEST.is_file()
    sources = public_doc_sources()

    expected_sources = {
        "docs/assets/launch/README.md",
        "docs/user/USER_GUIDE.md",
        "docs/user/AI_PROVIDER_SETUP.md",
        "docs/user/DRIFT_BASELINE_WORKFLOW.md",
        "docs/technical/POLICY_PACK_LAYOUT.md",
        "docs/technical/POLICY_PACK_DISTRIBUTION.md",
        "docs/product/OPEN_CORE_BOUNDARIES.md",
        "docs/user/GITHUB_ACTIONS_STARTER.md",
        "docs/user/CI_PROVIDER_RECIPES.md",
        "docs/technical/REPORT_SCHEMAS.md",
        "docs/technical/THREAT_MODEL.md",
        "docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md",
        "docs/meta/RELEASE_CHECKLIST.md",
        "docs/meta/PYPI_RELEASE_RUNBOOK.md",
        "docs/meta/HOMEBREW_TAP_PROTOTYPE.md",
        "docs/meta/DOWNSTREAM_FEEDBACK_KIT.md",
    }
    assert expected_sources <= set(sources)


def test_site_scaffold_is_astro_not_mkdocs() -> None:
    assert PACKAGE.is_file()
    assert ASTRO_CONFIG.is_file()
    assert not (REPO_ROOT / "mkdocs.yml").exists()

    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    package_lock = json.loads(
        (REPO_ROOT / "package-lock.json").read_text(encoding="utf-8")
    )
    assert package["scripts"]["build"] == "astro build"
    assert package["scripts"]["test:deps"] == "npm ls --all"
    assert package["scripts"]["test:security"] == "npm audit --omit=dev"
    assert package["scripts"]["test:site"] == "node scripts/check-site-build.mjs"
    assert package["dependencies"]["@astrojs/starlight"] == "0.41.3"
    astro_version = package["dependencies"]["astro"]
    assert tuple(int(part) for part in astro_version.split(".")) >= (7, 1, 0)
    assert package_lock["packages"][""]["dependencies"]["astro"] == astro_version
    assert 'PageTitle: "./src/components/docs/Empty.astro"' in (
        ASTRO_CONFIG.read_text(encoding="utf-8")
    )
    assert "docsSchema" in ASTRO_CONFIG.read_text(encoding="utf-8") or (
        CONTENT_CONFIG.is_file()
    )
    assert SITE_CHECK.is_file()


def test_playwright_builds_from_clean_generated_site_state() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    playwright_config = (REPO_ROOT / "playwright.config.ts").read_text(
        encoding="utf-8"
    )

    assert CLEAN_SITE_BUILD.is_file()
    assert package["scripts"]["build:clean"] == (
        "node scripts/clean-site-build.mjs && astro build"
    )
    assert "npm run build:clean && npm run preview" in playwright_config
    assert "reuseExistingServer: false" in playwright_config
    assert "{platform}" in playwright_config
    assert package["scripts"]["test:e2e:ci"] == "playwright test --grep-invert @visual"


def test_site_scaffold_tracks_manifest_and_ignores_generated_output() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "node_modules/" in gitignore
    assert ".astro/" in gitignore
    assert ".pagefind/" in gitignore
    assert "site/" not in gitignore
    assert "dist/" in gitignore


def test_docs_mobile_menu_reports_expanded_state_on_the_button() -> None:
    config = ASTRO_CONFIG.read_text(encoding="utf-8")

    assert 'MobileMenuToggle: "./src/components/docs/MobileMenuToggle.astro"' in config
    assert MOBILE_MENU_TOGGLE.is_file()

    component = MOBILE_MENU_TOGGLE.read_text(encoding="utf-8")
    assert 'attributeFilter: ["aria-expanded"]' in component
    assert 'button.setAttribute("aria-expanded", expanded)' in component


def test_public_docs_site_decision_preserves_and_supersedes_mkdocs_history() -> None:
    decision = (
        REPO_ROOT / "docs" / "meta" / "PUBLIC_DOCS_SITE_DECISION.md"
    ).read_text(encoding="utf-8")

    for term in [
        "Original decision",
        "MkDocs Material",
        "Superseding decision",
        "Astro",
        "Starlight",
        "Do not duplicate canonical docs",
        "canonical docs stay in `docs/`",
        "GitHub Pages deployment is active",
    ]:
        assert term in decision

    assert decision.index("Original decision") < decision.index("Superseding decision")


def test_docs_landing_keeps_release_runbooks_below_first_hour_content() -> None:
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    start_here = index.split("## How This Site Fits", maxsplit=1)[0]
    project_context = index.split("## Project Context", maxsplit=1)[1]

    assert "PyPI Release Runbook" not in start_here
    assert "maintainer and release evidence" in project_context
    assert "PyPI Release Runbook" in project_context


def test_pages_workflow_builds_astro_and_deploys_with_least_privilege() -> None:
    workflow = yaml.safe_load(PAGES_WORKFLOW.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert triggers["push"] == {"branches": ["main"]}
    assert "pull_request" not in triggers
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "cancel-in-progress": False,
        "group": "pages",
    }

    build = workflow["jobs"]["build"]
    deploy = workflow["jobs"]["deploy"]
    build_run_blocks = "\n".join(str(step.get("run", "")) for step in build["steps"])

    assert build["runs-on"] == "ubuntu-latest"
    assert deploy["needs"] == "build"
    assert deploy["environment"]["name"] == "github-pages"
    assert deploy["environment"]["url"] == "${{ steps.deployment.outputs.page_url }}"
    assert deploy["permissions"] == {
        "id-token": "write",
        "pages": "write",
    }
    assert "npm ci" in build_run_blocks
    assert "npm run test:deps" in build_run_blocks
    assert "npm run test:security" in build_run_blocks
    assert "npm run format:check" in build_run_blocks
    assert "npm run check" in build_run_blocks
    assert "npm run build" in build_run_blocks
    assert "mkdocs" not in build_run_blocks.lower()
    assert any(
        step.get("uses") == SETUP_NODE_PIN
        and step.get("with", {}).get("node-version") == "24"
        and step.get("with", {}).get("cache") == "npm"
        and step.get("with", {}).get("cache-dependency-path") == "package-lock.json"
        for step in build["steps"]
    )
    assert any(step.get("uses") == CONFIGURE_PAGES_PIN for step in build["steps"])
    assert any(
        step.get("uses") == CHECKOUT_PIN
        and step.get("with", {}).get("persist-credentials") is False
        for step in build["steps"]
    )
    assert any(
        step.get("uses") == UPLOAD_PAGES_ARTIFACT_PIN
        and step.get("with", {}).get("path") == "dist"
        for step in build["steps"]
    )
    assert any(
        step.get("uses") == DEPLOY_PAGES_PIN
        and step.get("id") == "deployment"
        for step in deploy["steps"]
    )


def test_public_docs_landing_is_linked_from_project_entrypoints() -> None:
    landing = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    assert "Entroping Documentation" in landing
    assert "Project Context" in landing
    assert "[User Guide](user/USER_GUIDE.md)" in landing
    assert "[GitHub Actions Starter](user/GITHUB_ACTIONS_STARTER.md)" in landing
    assert "[QAnstitution Reference](technical/QANSTITUTION_REFERENCE.md)" in landing
    assert "[[docs/meta/PUBLIC_DOCS_SITE_DECISION|PUBLIC_DOCS_SITE_DECISION]]" in index
    assert "https://sakibshuvo.github.io/Entroping/docs/" in readme
    assert "Public launch and docs site" in progress
