"""Guardrails for the downstream GitHub Actions starter workflow."""

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_WORKFLOW = REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml"
STARTER_DOC = REPO_ROOT / "docs" / "user" / "GITHUB_ACTIONS_STARTER.md"
DISTRIBUTION_DOC = REPO_ROOT / "docs" / "meta" / "DISTRIBUTION_RECOMMENDATION.md"
DECISION_REGISTRY = REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml"
TDS_DOC = REPO_ROOT / "docs" / "technical" / "TDS.md"


def latest_release_tag() -> str:
    release_evidence = json.loads(
        (REPO_ROOT / "docs" / "meta" / "release-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    return str(release_evidence["releases"][0]["tag"])


def test_downstream_github_actions_starter_is_copyable_and_configurable() -> None:
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
    assert (
        job["env"]["ENTROPING_INSTALL_SPEC"]
        == "git+https://github.com/sakibshuvo/Entroping.git"
    )

    run_blocks = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "sha256sum \"$archive\"" in run_blocks
    assert "download_with_retry()" in run_blocks
    assert "for attempt in 1 2 3" in run_blocks
    assert 'echo "$RUNNER_TEMP/hurl-${HURL_VERSION}-x86_64-unknown-linux-gnu/bin"' in run_blocks
    assert 'uv tool install "${ENTROPING_INSTALL_SPEC}"' in run_blocks
    pinned_install_spec = re.escape(
        "git+https://github.com/sakibshuvo/Entroping.git@v"
    )
    assert re.search(rf"{pinned_install_spec}[0-9][A-Za-z0-9._-]*", run_blocks) is None
    assert 'echo "$HOME/.local/bin" >> "$GITHUB_PATH"' in run_blocks
    assert "entroping doctor" in run_blocks
    assert "mkdir -p reports" in run_blocks
    assert "entroping doctor --ci --output json > reports/doctor-health.json" in run_blocks
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
    assert "reports/doctor-health.json" in doc
    assert "HURL_SHA256" in doc
    assert "ENTROPING_INSTALL_SPEC" in doc
    assert "defaults to the latest GitHub source branch" in doc
    assert "existing starter workflow" in doc
    assert latest_release_tag() in doc
    assert "GITHUB_ACTIONS_STARTER.md" in readme
    assert "[[docs/user/GITHUB_ACTIONS_STARTER|GITHUB_ACTIONS_STARTER]]" in index
    assert "docs/user/GITHUB_ACTIONS_STARTER.md" in user_flows
    assert "reports/run-latest.html" in user_flows
    assert "reports/html/index.html" not in user_flows


def test_official_reusable_action_design_is_explicitly_deferred() -> None:
    doc = STARTER_DOC.read_text(encoding="utf-8")
    distribution = DISTRIBUTION_DOC.read_text(encoding="utf-8")
    registry = yaml.safe_load(DECISION_REGISTRY.read_text(encoding="utf-8"))
    tds = TDS_DOC.read_text(encoding="utf-8")

    required_doc_terms = [
        "Official Reusable Action Boundary",
        "generated starter workflow",
        "future reusable `entroping/action`",
        "dedicated `entroping/action` repository",
        "blocked until package-index install proof exists",
        "tagged GitHub release fallback",
        "released Entroping package",
        "installs or verifies Hurl",
        "`entroping run --ci`",
        "must not call LLM providers",
        "default permissions remain `contents: read`",
        "`pull-requests: write`",
        "uploads `reports/`",
        "does not upload `.entroping/`",
    ]
    for term in required_doc_terms:
        assert term in doc

    assert "official GitHub Action should trail package-index proof" in distribution
    assert "do not replace the generated starter workflow" in distribution
    assert "latest GitHub source branch" in tds
    assert "future reusable `entroping/action`" in tds

    decisions = registry["decisions"]
    action_decisions = [
        decision
        for decision in decisions
        if decision["id"] == "ENT-DEC-0017"
    ]
    assert len(action_decisions) == 1
    action_decision = action_decisions[0]
    assert action_decision["status"] == "accepted"
    assert "official-action" in action_decision["tags"]
    assert "#594" in action_decision["related_issues"]
