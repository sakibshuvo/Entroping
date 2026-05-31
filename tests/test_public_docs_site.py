"""Guardrails for the public documentation site scaffold."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


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
        "No active deployment workflow yet",
    ]

    for term in required_terms:
        assert term in decision

    assert decision.index("## Options") < decision.index("## Decision")
    assert decision.index("## Decision") < decision.index("## Scaffold")


def test_mkdocs_scaffold_uses_existing_docs_tree_without_active_deploy() -> None:
    config = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    workflows = {path.name for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml")}
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert config["site_name"] == "Entroping"
    assert config["docs_dir"] == "docs"
    assert config["site_dir"] == "site"
    assert config["theme"]["name"] == "material"
    assert "docs-site" not in config.values()
    assert "docs.yml" not in workflows

    nav_text = repr(config["nav"])
    assert "index.md" in nav_text
    assert "user/USER_GUIDE.md" in nav_text
    assert "user/AI_PROVIDER_SETUP.md" in nav_text
    assert "technical/QANSTITUTION_REFERENCE.md" in nav_text
    assert "meta/PYPI_RELEASE_RUNBOOK.md" in nav_text
    assert "site/" in gitignore


def test_public_docs_landing_is_linked_from_project_entrypoints() -> None:
    landing = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "00_INDEX.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    assert "Entroping Documentation" in landing
    assert "[User Guide](user/USER_GUIDE.md)" in landing
    assert "[GitHub Actions Starter](user/GITHUB_ACTIONS_STARTER.md)" in landing
    assert "[QAnstitution Reference](technical/QANSTITUTION_REFERENCE.md)" in landing
    assert "[[docs/meta/PUBLIC_DOCS_SITE_DECISION|PUBLIC_DOCS_SITE_DECISION]]" in index
    assert "mkdocs.yml" in readme
    assert "Public docs site decision" in progress
