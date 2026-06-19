"""Regression tests for GitHub Actions workflow coverage."""

from pathlib import Path

import yaml

_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_SCORECARD_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "scorecard.yml"
)
_PERFORMANCE_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "performance-smoke.yml"
)
_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_runs_on_pull_requests_and_main_pushes_only() -> None:
    workflow = yaml.load(_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert triggers["push"] == {"branches": ["main"]}


def test_ci_workflow_enforces_security_and_quality_gates() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    checks = workflow["jobs"]["checks"]
    quality_audit = workflow["jobs"]["quality-audit"]
    checks_run_blocks = "\n".join(str(step.get("run", "")) for step in checks["steps"])
    quality_run_blocks = "\n".join(str(step.get("run", "")) for step in quality_audit["steps"])

    assert "scripts/regression.sh --security" in checks_run_blocks
    assert 'scripts/pr_body_check.py "$GITHUB_EVENT_PATH"' in checks_run_blocks
    assert "--changed-file" in checks_run_blocks
    assert "git diff --name-only" in checks_run_blocks
    assert "GITHUB_BASE_REF" in checks_run_blocks
    assert "scripts/regression.sh\n" not in checks_run_blocks
    assert quality_audit["needs"] == "checks"
    assert "scripts/audit_quality.sh" in quality_run_blocks
    assert any(
        step.get("uses") == "actions/upload-artifact@v7"
        and step.get("with", {}).get("path") == "reports"
        for step in quality_audit["steps"]
    )


def test_ci_workflow_runs_live_demo_smoke_with_pinned_hurl() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    live_demo = workflow["jobs"]["live-demo-smoke"]
    steps = live_demo["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
    live_demo_env = live_demo["env"]

    assert live_demo["needs"] == "checks"
    assert live_demo_env["HURL_VERSION"] == "8.0.1"
    assert len(live_demo_env["HURL_SHA256"]) == 64
    assert all(character in "0123456789abcdef" for character in live_demo_env["HURL_SHA256"])
    assert "sha256sum \"$archive\"" in run_blocks
    assert "HURL_SHA256" in run_blocks
    assert "download_with_retry()" in run_blocks
    assert "for attempt in 1 2 3" in run_blocks
    assert "sleep $((attempt * 2))" in run_blocks
    assert 'download_with_retry "$base_url/$archive" "$RUNNER_TEMP/$archive"' in run_blocks
    assert 'export PATH="$hurl_bin:$PATH"' in run_blocks
    assert "$archive.sha256" not in run_blocks
    assert "scripts/live_demo_smoke.sh" in run_blocks
    workflow_text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/checkout@v6" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "astral-sh/setup-uv@v8.2.0" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text


def test_ci_workflow_runs_optional_extras_runtime_smoke() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    optional_smoke = workflow["jobs"]["optional-extras-smoke"]
    steps = optional_smoke["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert optional_smoke["needs"] == "checks"
    assert "uv sync --dev --all-extras" in run_blocks
    assert "scripts/optional_extras_smoke.py" in run_blocks
    assert "pip-audit" not in run_blocks


def test_ci_workflow_runs_strict_public_docs_build() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    docs_site = workflow["jobs"]["docs-site"]
    steps = docs_site["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert docs_site["runs-on"] == "ubuntu-latest"
    assert docs_site["needs"] == "checks"
    assert "uvx --with 'mkdocs-material==9.*' mkdocs build --strict" in run_blocks
    assert any(step.get("uses") == "actions/checkout@v6" for step in steps)
    assert any(step.get("uses") == "actions/setup-python@v6" for step in steps)
    assert any(step.get("uses") == "astral-sh/setup-uv@v8.2.0" for step in steps)


def test_optional_extras_smoke_script_exercises_optional_runtime_boundaries() -> None:
    script = (_REPO_ROOT / "scripts" / "optional_extras_smoke.py").read_text(
        encoding="utf-8"
    )

    assert "_load_completion_func" in script
    assert "load_mitmproxy_runtime" in script
    assert "ensure_studio_available" in script
    assert "textual.app" in script
    assert "OPENAI_API_KEY" not in script


def test_docs_explain_ci_enforced_and_local_only_gates() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    test_strategy = (_REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )

    assert "CI enforces `scripts/regression.sh --security`" in readme
    assert "CI enforces `scripts/audit_quality.sh`" in readme
    assert "CI quality-audit runs `uv run python scripts/performance_smoke.py`" in readme
    assert "Local-only before release:" in readme
    assert "GitHub Actions Enforcement" in test_strategy
    assert "`scripts/regression.sh --security`" in test_strategy
    assert "`scripts/audit_quality.sh`" in test_strategy
    assert "quality-audit job also runs `uv run python scripts/performance_smoke.py`" in (
        test_strategy
    )
    assert "optional-extras-smoke" in test_strategy
    assert "scheduled/manual CI" in test_strategy
    assert "performance-smoke" in test_strategy


def test_release_docs_explain_hurl_checksum_bump_process() -> None:
    checklist = (_REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "HURL_SHA256" in checklist
    assert "sha256sum" in checklist
    assert "Update `.github/workflows/ci.yml`" in checklist


def test_scorecard_workflow_is_non_blocking_and_least_privilege() -> None:
    workflow = yaml.safe_load(_SCORECARD_WORKFLOW_PATH.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert "pull_request" not in triggers
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "17 9 * * 1"}]

    scorecard = workflow["jobs"]["scorecard"]
    assert scorecard["runs-on"] == "ubuntu-latest"
    assert scorecard["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }

    steps = scorecard["steps"]
    assert any(
        step.get("uses") == "actions/checkout@v6"
        and step.get("with", {}).get("persist-credentials") is False
        for step in steps
    )
    assert any(
        step.get("uses") == "ossf/scorecard-action@v2.4.3"
        and step.get("with", {}).get("publish_results") is True
        and step.get("with", {}).get("results_file") == "scorecard-results.json"
        and step.get("with", {}).get("results_format") == "json"
        for step in steps
    )
    assert any(
        step.get("uses") == "actions/upload-artifact@v7"
        and step.get("with", {}).get("path") == "scorecard-results.json"
        for step in steps
    )


def test_performance_smoke_workflow_is_scheduled_manual_and_non_blocking() -> None:
    workflow = yaml.safe_load(_PERFORMANCE_WORKFLOW_PATH.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert "pull_request" not in triggers
    assert "push" not in triggers
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "43 8 * * 2"}]

    performance_smoke = workflow["jobs"]["performance-smoke"]
    assert performance_smoke["runs-on"] == "ubuntu-latest"
    assert performance_smoke["permissions"] == {"contents": "read"}

    steps = performance_smoke["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
    assert "uv sync --dev" in run_blocks
    assert "uv run python scripts/performance_smoke.py" in run_blocks
    assert any(
        step.get("uses") == "actions/checkout@v6"
        and step.get("with", {}).get("persist-credentials") is False
        for step in steps
    )
    assert any(step.get("uses") == "actions/setup-python@v6" for step in steps)
    assert any(step.get("uses") == "astral-sh/setup-uv@v8.2.0" for step in steps)
    assert any(
        step.get("uses") == "actions/upload-artifact@v7"
        and step.get("with", {}).get("path") == "reports/performance-smoke.json"
        for step in steps
    )
