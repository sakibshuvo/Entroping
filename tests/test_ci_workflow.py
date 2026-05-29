"""Regression tests for GitHub Actions workflow coverage."""

from pathlib import Path

import yaml


def test_ci_workflow_runs_live_demo_smoke_with_pinned_hurl() -> None:
    workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    live_demo = workflow["jobs"]["live-demo-smoke"]
    steps = live_demo["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert live_demo["needs"] == "checks"
    assert 'HURL_VERSION: "8.0.1"' in workflow_path.read_text(encoding="utf-8")
    assert "sha256sum \"$archive\"" in run_blocks
    assert "scripts/live_demo_smoke.sh" in run_blocks
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "actions/checkout@v6" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "astral-sh/setup-uv@v8.1.0" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
