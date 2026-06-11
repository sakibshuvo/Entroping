"""Guardrails for the public documentation site scaffold."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"


def test_public_docs_site_decision_compares_options_and_picks_mkdocs() -> None:
    decision = (
        REPO_ROOT / "docs" / "meta" / "PUBLIC_DOCS_SITE_DECISION.md"
    ).read_text(encoding="utf-8")

    required_terms = [
        "Decision: MkDocs Material",
        "MkDocs Material",
        "VitePress",
        "GitHub Pages/Jekyll",
        "Do not duplicate canonical docs",
        "canonical docs stay in `docs/`",
        "Obsidian links remain source-friendly",
        "uvx --with 'mkdocs-material==9.*' mkdocs build --strict",
        "GitHub Pages deployment is active",
        "Broken links fail CI through `mkdocs build --strict`",
    ]

    for term in required_terms:
        assert term in decision

    assert decision.index("## Options") < decision.index("## Decision")
    assert decision.index("## Decision") < decision.index("## Scaffold")


def test_mkdocs_scaffold_uses_existing_docs_tree_with_strict_deploy() -> None:
    config = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    workflows = {path.name for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml")}
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert config["site_name"] == "Entroping"
    assert config["docs_dir"] == "docs"
    assert config["site_dir"] == "site"
    assert config["strict"] is True
    assert config["theme"]["name"] == "material"
    assert "docs-site" not in config.values()
    assert "pages.yml" in workflows

    nav = config["nav"]
    top_level = [
        next(iter(item)) if isinstance(item, dict) else item
        for item in nav
    ]
    assert top_level[:6] == [
        "Introduction",
        "Getting Started",
        "User Guide",
        "Policy / QAnstitution Reference",
        "CI / Reports",
        "Technical Reference",
    ]
    assert "Roadmap / Status" not in top_level
    assert all(not str(item).startswith("meta/") for item in top_level)
    assert all(not str(item).startswith("technical/") for item in top_level)

    nav_text = repr(config["nav"])
    assert "index.md" in nav_text
    assert "user/USER_GUIDE.md" in nav_text
    assert "user/AI_PROVIDER_SETUP.md" in nav_text
    assert "technical/QANSTITUTION_REFERENCE.md" in nav_text
    assert "meta/PYPI_RELEASE_RUNBOOK.md" in nav_text
    assert "Maintainer Evidence" in nav_text
    assert "docs/evolution" not in nav_text
    assert "OBSIDIAN" not in nav_text
    assert "sources/" not in nav_text
    assert ".context/" not in nav_text
    assert "site/" in gitignore


def test_mkdocs_navigation_exposes_public_roadmap_without_duplicating_it() -> None:
    config = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert (REPO_ROOT / "ROADMAP.md").is_file()
    assert not (REPO_ROOT / "docs" / "ROADMAP.md").exists()
    assert {
        "Roadmap": "https://github.com/sakibshuvo/Entroping/blob/main/ROADMAP.md"
    } in config["nav"]


def test_pages_workflow_builds_strict_mkdocs_and_deploys_with_least_privilege() -> None:
    workflow = yaml.safe_load(PAGES_WORKFLOW.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert triggers["push"] == {"branches": ["main"]}
    assert "pull_request" not in triggers
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "pages": "write",
    }
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
    assert "uvx --with 'mkdocs-material==9.*' mkdocs build --strict" in build_run_blocks
    assert any(step.get("uses") == "actions/configure-pages@v6" for step in build["steps"])
    assert any(
        step.get("uses") == "actions/upload-pages-artifact@v5"
        and step.get("with", {}).get("path") == "site"
        for step in build["steps"]
    )
    assert any(
        step.get("uses") == "actions/deploy-pages@v5"
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
    assert "mkdocs.yml" in readme
    assert "Public docs site decision" in progress
