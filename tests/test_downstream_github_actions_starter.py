"""Guardrails for the downstream GitHub Actions starter workflow."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_WORKFLOW = REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml"
STARTER_DOC = REPO_ROOT / "docs" / "user" / "GITHUB_ACTIONS_STARTER.md"


def test_downstream_github_actions_starter_is_copyable_and_pinned() -> None:
    workflow = yaml.safe_load(STARTER_WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = STARTER_WORKFLOW.read_text(encoding="utf-8")

    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert triggers["push"] == {"branches": ["main"]}
    assert workflow["permissions"] == {"contents": "read"}

    job = workflow["jobs"]["entroping"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["env"]["HURL_VERSION"] == "8.0.1"
    assert len(job["env"]["HURL_SHA256"]) == 64
    assert all(character in "0123456789abcdef" for character in job["env"]["HURL_SHA256"])

    run_blocks = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "sha256sum \"$archive\"" in run_blocks
    assert "download_with_retry()" in run_blocks
    assert "for attempt in 1 2 3" in run_blocks
    assert 'echo "$RUNNER_TEMP/hurl-${HURL_VERSION}-x86_64-unknown-linux-gnu/bin"' in run_blocks
    assert (
        "uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha"
        in run_blocks
    )
    assert 'echo "$HOME/.local/bin" >> "$GITHUB_PATH"' in run_blocks
    assert "entroping doctor" in run_blocks
    assert "entroping run --ci --report json --report junit --report html" in run_blocks
    assert "entroping report github-annotations" in run_blocks
    assert "entroping report sarif" in run_blocks
    assert "entroping report review-summary" in run_blocks
    assert "secrets." not in workflow_text

    uses = [step.get("uses") for step in job["steps"]]
    assert "actions/checkout@v6" in uses
    assert "actions/setup-python@v6" in uses
    assert "astral-sh/setup-uv@v8.2.0" in uses
    assert "actions/upload-artifact@v7" in uses


def test_downstream_github_actions_docs_link_required_files_and_assumptions() -> None:
    doc = STARTER_DOC.read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    user_flows = (REPO_ROOT / "docs" / "user" / "USER_FLOWS.md").read_text(
        encoding="utf-8"
    )

    assert "examples/github-actions/entroping-ci.yml" in doc
    assert "entroping init --github-actions" in doc
    assert "entroping init --minimal --github-actions" in doc
    assert "refuses to overwrite" in doc
    assert "qanstitution.yaml" in doc
    assert "tests/**/*.hurl" in doc
    assert "envs/ci.env" in doc
    assert "No GitHub secrets are required by the starter workflow" in doc
    assert "entroping run --ci --report json --report junit --report html" in doc
    assert "entroping report github-annotations" in doc
    assert "entroping report sarif" in doc
    assert "github/codeql-action/upload-sarif@v4" in doc
    assert "reports/entroping.sarif" in doc
    assert "entroping report review-summary" in doc
    assert "reports/review-summary.md" in doc
    assert "HURL_SHA256" in doc
    assert "v0.1.1-alpha" in doc
    assert "GITHUB_ACTIONS_STARTER.md" in readme
    assert "[[docs/user/GITHUB_ACTIONS_STARTER|GITHUB_ACTIONS_STARTER]]" in index
    assert "docs/user/GITHUB_ACTIONS_STARTER.md" in user_flows
    assert "reports/run-latest.html" in user_flows
    assert "reports/html/index.html" not in user_flows
