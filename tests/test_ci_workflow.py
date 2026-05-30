"""Regression tests for GitHub Actions workflow coverage."""

from pathlib import Path

import yaml

_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_on_pull_requests_and_main_pushes_only() -> None:
    workflow = yaml.load(_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert triggers["push"] == {"branches": ["main"]}


def test_ci_workflow_runs_live_demo_smoke_with_pinned_hurl() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    live_demo = workflow["jobs"]["live-demo-smoke"]
    steps = live_demo["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert live_demo["needs"] == "checks"
    assert 'HURL_VERSION: "8.0.1"' in _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "sha256sum \"$archive\"" in run_blocks
    assert "download_with_retry()" in run_blocks
    assert "for attempt in 1 2 3" in run_blocks
    assert "sleep $((attempt * 2))" in run_blocks
    assert 'download_with_retry "$base_url/$archive" "$RUNNER_TEMP/$archive"' in run_blocks
    assert (
        'download_with_retry "$base_url/$archive.sha256" "$RUNNER_TEMP/$archive.sha256"'
        in run_blocks
    )
    assert "scripts/live_demo_smoke.sh" in run_blocks
    workflow_text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/checkout@v6" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "astral-sh/setup-uv@v8.1.0" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
