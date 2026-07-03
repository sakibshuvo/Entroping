"""Guardrails for the downstream GitHub Actions starter workflow."""

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_WORKFLOW = REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml"
PR_EVIDENCE_CARD_WORKFLOW = (
    REPO_ROOT / "examples" / "github-actions" / "pr-evidence-card.yml"
)
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


def _run_blocks(job: dict[str, object]) -> str:
    steps = job["steps"]
    assert isinstance(steps, list)
    return "\n".join(str(step.get("run", "")) for step in steps if isinstance(step, dict))


def _uses(job: dict[str, object]) -> list[object]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return [step.get("uses") for step in steps if isinstance(step, dict)]


def _upload_artifact_path(job: dict[str, object]) -> str:
    steps = job["steps"]
    assert isinstance(steps, list)
    upload_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("uses") == "actions/upload-artifact@v7"
    )
    with_block = upload_step["with"]
    assert isinstance(with_block, dict)
    return str(with_block["path"])


def _assert_contains_all(text: str, terms: tuple[str, ...]) -> None:
    missing = [term for term in terms if term not in text]
    assert missing == []


def _assert_contains_none(text: str, terms: tuple[str, ...]) -> None:
    found = [term for term in terms if term in text]
    assert found == []


def _assert_common_action_uses(uses: list[object]) -> None:
    assert {
        "actions/checkout@v6",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v8.2.0",
        "actions/upload-artifact@v7",
    } <= set(uses)


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

    run_blocks = _run_blocks(job)
    _assert_contains_all(
        run_blocks,
        (
            "sha256sum \"$archive\"",
            "download_with_retry()",
            "for attempt in 1 2 3",
            'echo "$RUNNER_TEMP/hurl-${HURL_VERSION}-x86_64-unknown-linux-gnu/bin"',
            'uv tool install "${ENTROPING_INSTALL_SPEC}"',
            'echo "$HOME/.local/bin" >> "$GITHUB_PATH"',
            "entroping doctor",
            "mkdir -p reports",
            "entroping doctor --ci --output json > reports/doctor-health.json",
            "entroping run --ci --report json --report junit --report html",
            "entroping report github-annotations",
            "entroping report sarif",
            "entroping report review-summary",
        ),
    )
    pinned_install_spec = re.escape(
        "git+https://github.com/sakibshuvo/Entroping.git@v"
    )
    assert re.search(rf"{pinned_install_spec}[0-9][A-Za-z0-9._-]*", run_blocks) is None
    assert "secrets." not in workflow_text

    _assert_common_action_uses(_uses(job))


def test_pr_evidence_card_actions_example_is_read_only_and_copyable() -> None:
    workflow = yaml.safe_load(PR_EVIDENCE_CARD_WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = PR_EVIDENCE_CARD_WORKFLOW.read_text(encoding="utf-8")

    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert workflow["permissions"] == {"contents": "read"}

    job = workflow["jobs"]["pr-evidence-card"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["env"]["HURL_VERSION"] == "8.0.1"
    assert len(job["env"]["HURL_SHA256"]) == 64
    assert (
        job["env"]["ENTROPING_INSTALL_SPEC"]
        == "git+https://github.com/sakibshuvo/Entroping.git"
    )

    run_blocks = _run_blocks(job)
    _assert_contains_all(
        run_blocks,
        (
            "entroping run --ci --report json --report junit --report html",
            "entroping report runtime-card --output json",
            "entroping report evidence-index --output json",
            "entroping report pr-evidence-card",
            "entroping report pr-evidence-card --output json",
            'cat reports/pr-evidence-card.md >> "$GITHUB_STEP_SUMMARY"',
        ),
    )
    assert run_blocks.index("entroping run --ci") < run_blocks.index(
        "entroping report pr-evidence-card"
    )

    _assert_common_action_uses(_uses(job))
    _assert_contains_all(
        _upload_artifact_path(job),
        (
            "reports/pr-evidence-card.md",
            "reports/pr-evidence-card.json",
            "reports/runtime-card.json",
            "reports/evidence-index.json",
        ),
    )
    _assert_contains_none(
        workflow_text,
        ("pull-requests: write", "issues: write", "gh pr", "gh issue", "secrets."),
    )


def test_downstream_github_actions_docs_link_required_files_and_assumptions() -> None:
    doc = STARTER_DOC.read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    user_flows = (REPO_ROOT / "docs" / "user" / "USER_FLOWS.md").read_text(
        encoding="utf-8"
    )

    _assert_contains_all(
        doc,
        (
            "examples/github-actions/entroping-ci.yml",
            "entroping init --github-actions",
            "entroping init --minimal --github-actions",
            "refuses to overwrite",
            "qanstitution.yaml",
            "tests/**/*.hurl",
            "envs/ci.env",
            "No GitHub secrets are required by the starter workflow",
            "entroping run --ci --report json --report junit --report html",
            "entroping report github-annotations",
            "entroping report sarif",
            "github/codeql-action/upload-sarif@v4",
            "reports/entroping.sarif",
            "entroping report review-summary",
            "reports/review-summary.md",
            "examples/github-actions/pr-evidence-card.yml",
            "entroping report pr-evidence-card",
            "reports/pr-evidence-card.md",
            "reports/pr-evidence-card.json",
            "reports/runtime-card.json",
            "reports/evidence-index.json",
            "GitHub job summary",
            "does not comment on or mutate pull requests",
            "permissions: contents: read",
            "reports/doctor-health.json",
            "HURL_SHA256",
            "ENTROPING_INSTALL_SPEC",
            "defaults to the latest GitHub source branch",
            "existing starter workflow",
            latest_release_tag(),
        ),
    )
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
