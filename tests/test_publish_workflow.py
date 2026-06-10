"""Guardrails for the manual PyPI/TestPyPI Trusted Publishing workflow."""

from pathlib import Path
from typing import cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-python-package.yml"


def test_publish_workflow_is_manual_and_token_free() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = WORKFLOW.read_text(encoding="utf-8")

    triggers = _mapping(workflow["on"])
    inputs = _mapping(_mapping(triggers["workflow_dispatch"])["inputs"])
    target = _mapping(inputs["target"])

    assert "push" not in triggers
    assert "pull_request" not in triggers
    assert target["type"] == "choice"
    assert target["default"] == "testpypi"
    assert target["options"] == ["testpypi", "pypi"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "password" not in workflow_text.lower()
    assert "secrets." not in workflow_text
    assert ".pypirc" not in workflow_text


def test_publish_workflow_builds_unprivileged_artifacts_before_publish() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    build = _mapping(_mapping(workflow["jobs"])["build-dist"])
    steps = _steps(build)
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert build["runs-on"] == "ubuntu-latest"
    assert build["permissions"] == {"contents": "read"}
    assert "id-token" not in build["permissions"]
    assert "uv sync --dev" in run_blocks
    assert "scripts/regression.sh --security" in run_blocks
    assert "Current 0.1.1 must not be published to package indexes" in run_blocks
    assert "scripts/package_check.sh" in run_blocks
    assert "uvx twine check dist/*" in run_blocks
    assert any(step.get("uses") == "actions/checkout@v6" for step in steps)
    assert any(step.get("uses") == "actions/setup-python@v6" for step in steps)
    assert any(step.get("uses") == "astral-sh/setup-uv@v8.2.0" for step in steps)
    assert any(
        step.get("uses") == "actions/upload-artifact@v7"
        and _step_with(step).get("name") == "python-distributions"
        and _step_with(step).get("path") == "dist/"
        and _step_with(step).get("if-no-files-found") == "error"
        for step in steps
    )


def test_publish_workflow_uses_separate_trusted_publisher_environments() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = _mapping(workflow["jobs"])
    testpypi = _mapping(jobs["publish-testpypi"])
    pypi = _mapping(jobs["publish-pypi"])

    assert testpypi["if"] == "${{ github.event.inputs.target == 'testpypi' }}"
    assert pypi["if"] == "${{ github.event.inputs.target == 'pypi' }}"
    assert testpypi["needs"] == "build-dist"
    assert pypi["needs"] == "build-dist"
    assert testpypi["environment"] == "testpypi"
    assert pypi["environment"] == "pypi"
    assert testpypi["permissions"] == {"contents": "read", "id-token": "write"}
    assert pypi["permissions"] == {"contents": "read", "id-token": "write"}

    testpypi_steps = _steps(testpypi)
    pypi_steps = _steps(pypi)
    assert any(step.get("uses") == "actions/download-artifact@v8" for step in testpypi_steps)
    assert any(step.get("uses") == "actions/download-artifact@v8" for step in pypi_steps)
    assert any(
        step.get("uses") == "pypa/gh-action-pypi-publish@release/v1"
        and _step_with(step).get("repository-url") == "https://test.pypi.org/legacy/"
        for step in testpypi_steps
    )
    assert any(
        step.get("uses") == "pypa/gh-action-pypi-publish@release/v1"
        and "with" not in step
        for step in pypi_steps
    )


def test_publish_workflow_is_documented_as_active_manual_path() -> None:
    runbook = (REPO_ROOT / "docs" / "meta" / "PYPI_RELEASE_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    progress = (REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    changelog = (REPO_ROOT / ".context" / "changelog.md").read_text(encoding="utf-8")

    assert ".github/workflows/publish-python-package.yml" in runbook
    assert "Active protected manual workflow" in runbook
    assert "testpypi` and `pypi` GitHub environments require reviewer approval" in runbook
    assert "No PyPI or TestPyPI tokens" in runbook
    assert "PyPI/TestPyPI trusted publishing workflow" in progress
    assert "issue #223" in changelog


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        assert isinstance(step, dict)
    return cast(list[dict[str, object]], steps)


def _step_with(step: dict[str, object]) -> dict[str, object]:
    value = step.get("with", {})
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
