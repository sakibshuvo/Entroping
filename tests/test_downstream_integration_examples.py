"""Guardrails for downstream integration examples."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_only_github_actions_has_a_committed_provider_native_example() -> None:
    provider_templates = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "examples").glob("**/*")
        if path.is_file() and path.name in {".gitlab-ci.yml", "pipeline.yml", "config.yml"}
    )

    assert provider_templates == []
    assert (REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml").is_file()


def test_github_actions_example_is_pinned_and_artifact_backed() -> None:
    workflow = (REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "HURL_VERSION:",
        "HURL_SHA256:",
        "sha256sum",
        "uv tool install",
        "entroping doctor",
        "entroping run --ci",
        "reports/",
    ]
    for term in required_terms:
        assert term in workflow


def test_ci_provider_recipes_require_real_runner_proof_for_new_templates() -> None:
    doc = (REPO_ROOT / "docs" / "user" / "CI_PROVIDER_RECIPES.md").read_text(encoding="utf-8")

    assert "Promote a native provider template into `examples/` only when" in doc
    assert "real runner environment" in doc
    assert "provider secrets are optional and never required by Entroping itself" in doc
