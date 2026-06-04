"""Guardrails for non-GitHub CI provider guidance."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_PROVIDER_DOC = REPO_ROOT / "docs" / "user" / "CI_PROVIDER_RECIPES.md"


def test_ci_provider_recipes_cover_requested_providers_without_untested_templates() -> None:
    doc = CI_PROVIDER_DOC.read_text(encoding="utf-8")

    required_terms = [
        "GitHub Actions remains the only committed provider-specific template for now",
        "GitLab CI",
        "Buildkite",
        "CircleCI",
        "Generic Shell Recipe",
        "untested native templates are not copied into `examples/`",
        "HURL_VERSION",
        "HURL_SHA256",
        "uv tool install",
        "entroping doctor",
        "entroping run --ci --report json --report junit --report html",
        "entroping report sarif",
        "entroping report review-summary",
        "reports/",
        "No provider secrets are required by Entroping itself",
    ]
    for term in required_terms:
        assert term in doc

    uncommitted_templates = [
        REPO_ROOT / "examples" / "gitlab" / ".gitlab-ci.yml",
        REPO_ROOT / "examples" / "buildkite" / "pipeline.yml",
        REPO_ROOT / "examples" / "circleci" / "config.yml",
    ]
    for path in uncommitted_templates:
        assert not path.exists()


def test_ci_provider_recipes_are_linked_from_entrypoints() -> None:
    required_links = {
        "README.md": "CI_PROVIDER_RECIPES.md",
        "docs/meta/VAULT_INDEX.md": "[[docs/user/CI_PROVIDER_RECIPES|CI_PROVIDER_RECIPES]]",
        "docs/index.md": "user/CI_PROVIDER_RECIPES.md",
        "docs/user/USER_GUIDE.md": "docs/user/CI_PROVIDER_RECIPES.md",
        "docs/user/USER_FLOWS.md": "docs/user/CI_PROVIDER_RECIPES.md",
        "mkdocs.yml": "CI Provider Recipes: user/CI_PROVIDER_RECIPES.md",
        "docs/meta/PROJECT_PROGRESS.md": "Non-GitHub CI provider recipes",
        ".context/plan.md": "Issue #204 documents non-GitHub CI provider recipes",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
