from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Literal, Protocol, cast, runtime_checkable

SCHEMA_VERSION = "entroping.package-index-readiness.v1"
WORKFLOW_PATH = Path(".github") / "workflows" / "publish-python-package.yml"
RUNBOOK_PATH = Path("docs") / "meta" / "PYPI_RELEASE_RUNBOOK.md"
RELEASE_EVIDENCE_PATH = Path("docs") / "meta" / "release-evidence.json"
PYPROJECT_PATH = Path("pyproject.toml")
Status = Literal["pass", "fail"]


@dataclass(frozen=True)
class CheckResult:
    key: str
    status: Status
    detail: str
    failures: tuple[str, ...] = ()


@runtime_checkable
class _YamlModule(Protocol):
    YAMLError: type[Exception]

    def safe_load(self, stream: str) -> object: ...


def build_payload(root: Path) -> dict[str, object]:
    checks = (
        _validate_publish_workflow(root),
        _validate_release_evidence_boundary(root),
        _validate_runbook_preflight(root),
        _validate_pyproject_version_guard(root),
    )
    repo_failures = [failure for check in checks for failure in check.failures]
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_guardrails_ready": not repo_failures,
        "package_index_ready": False,
        "checks": {
            check.key: {
                "status": check.status,
                "detail": check.detail,
                "failures": list(check.failures),
            }
            for check in checks
        },
        "repo_failures": repo_failures,
        "external_requirements": [
            "TestPyPI project exists for entroping or package-name decision is documented",
            "TestPyPI Trusted Publisher is configured for the testpypi environment",
            "PyPI Trusted Publisher is configured for the pypi environment after TestPyPI proof",
            "A PEP 440 alpha version is chosen before the manual publish workflow runs",
            "Fresh TestPyPI/PyPI install smoke evidence is recorded after publish",
        ],
    }


def _validate_publish_workflow(root: Path) -> CheckResult:
    workflow_path = root / WORKFLOW_PATH
    workflow_text = _read_text(workflow_path)
    failures: list[str] = []
    if workflow_text is None:
        return _missing_result("publish_workflow", WORKFLOW_PATH)

    lowered = workflow_text.lower()
    if "secrets." in workflow_text or ".pypirc" in workflow_text or "password" in lowered:
        failures.append("publish workflow must not reference a long-lived package-index secret")

    try:
        yaml_module = _load_yaml_module()
    except ModuleNotFoundError as exc:
        return CheckResult(
            key="publish_workflow",
            status="fail",
            detail=f"{WORKFLOW_PATH.as_posix()} cannot be parsed without PyYAML",
            failures=(f"publish workflow YAML parser unavailable: {exc}",),
        )
    except TypeError as exc:
        return CheckResult(
            key="publish_workflow",
            status="fail",
            detail=f"{WORKFLOW_PATH.as_posix()} YAML parser is invalid",
            failures=(f"publish workflow YAML parser invalid: {exc}",),
        )

    try:
        loaded = yaml_module.safe_load(workflow_text)
    except yaml_module.YAMLError as exc:
        return CheckResult(
            key="publish_workflow",
            status="fail",
            detail=f"{WORKFLOW_PATH.as_posix()} is not valid YAML",
            failures=(f"publish workflow YAML parse failed: {exc}",),
        )
    workflow = _mapping(loaded, "workflow", failures)
    triggers = _mapping(workflow.get("on"), "workflow.on", failures)
    if set(triggers) != {"workflow_dispatch"}:
        failures.append("publish workflow must be manual-only through workflow_dispatch")
    target = _mapping(
        _mapping(
            _mapping(triggers.get("workflow_dispatch"), "workflow_dispatch", failures).get(
                "inputs"
            ),
            "workflow_dispatch.inputs",
            failures,
        ).get("target"),
        "workflow_dispatch.inputs.target",
        failures,
    )
    if target.get("type") != "choice":
        failures.append("publish target input must be a choice")
    if target.get("default") != "testpypi":
        failures.append("publish target default must be testpypi")
    if target.get("options") != ["testpypi", "pypi"]:
        failures.append("publish target options must be testpypi then pypi")
    if workflow.get("permissions") != {"contents": "read"}:
        failures.append("publish workflow top-level permissions must be contents: read")

    jobs = _mapping(workflow.get("jobs"), "workflow.jobs", failures)
    _validate_build_job(jobs, failures)
    _validate_publish_job(jobs, "publish-testpypi", "testpypi", failures)
    _validate_publish_job(jobs, "publish-pypi", "pypi", failures)
    return _check_result(
        key="publish_workflow",
        detail="manual token-free Trusted Publishing workflow shape",
        failures=failures,
    )


def _load_yaml_module() -> _YamlModule:
    module = import_module("yaml")
    if not isinstance(module, _YamlModule):
        msg = "yaml module must expose safe_load and YAMLError"
        raise TypeError(msg)
    return module


def _validate_build_job(jobs: dict[str, object], failures: list[str]) -> None:
    build = _mapping(jobs.get("build-dist"), "jobs.build-dist", failures)
    if build.get("permissions") != {"contents": "read"}:
        failures.append("build-dist permissions must be contents: read")
    if "id-token" in _mapping(build.get("permissions"), "build-dist.permissions", failures):
        failures.append("build-dist must not request id-token")
    run_blocks = "\n".join(
        str(step.get("run", ""))
        for step in _steps(build.get("steps"), "build-dist.steps", failures)
    )
    for required in (
        "scripts/regression.sh --security",
        "Current 0.1.1 must not be published to package indexes",
        "scripts/package_check.sh",
        "uvx twine check dist/*",
    ):
        if required not in run_blocks:
            failures.append(f"build-dist must run {required}")


def _validate_publish_job(
    jobs: dict[str, object],
    job_name: str,
    environment: str,
    failures: list[str],
) -> None:
    job = _mapping(jobs.get(job_name), f"jobs.{job_name}", failures)
    if job.get("needs") != "build-dist":
        failures.append(f"{job_name} must depend on build-dist")
    if job.get("environment") != environment:
        failures.append(f"{job_name} must use the {environment} environment")
    if job.get("permissions") != {"contents": "read", "id-token": "write"}:
        failures.append(f"{job_name} permissions must include id-token: write")
    steps = _steps(job.get("steps"), f"{job_name}.steps", failures)
    if not any(step.get("uses") == "actions/download-artifact@v8" for step in steps):
        failures.append(f"{job_name} must download built distributions")
    publish_steps = [
        step for step in steps if step.get("uses") == "pypa/gh-action-pypi-publish@release/v1"
    ]
    if len(publish_steps) != 1:
        failures.append(f"{job_name} must publish with the PyPA Trusted Publishing action")
        return
    publish_with = _mapping(publish_steps[0].get("with", {}), f"{job_name}.publish.with", failures)
    if environment == "testpypi":
        if publish_with.get("repository-url") != "https://test.pypi.org/legacy/":
            failures.append("publish-testpypi must target https://test.pypi.org/legacy/")
    elif publish_with:
        failures.append("publish-pypi must use the default PyPI repository")


def _validate_release_evidence_boundary(root: Path) -> CheckResult:
    ledger_path = root / RELEASE_EVIDENCE_PATH
    ledger_text = _read_text(ledger_path)
    failures: list[str] = []
    if ledger_text is None:
        return _missing_result("release_evidence_boundary", RELEASE_EVIDENCE_PATH)
    try:
        ledger = cast(object, json.loads(ledger_text))
    except json.JSONDecodeError as exc:
        return CheckResult(
            key="release_evidence_boundary",
            status="fail",
            detail=f"{RELEASE_EVIDENCE_PATH.as_posix()} is invalid JSON",
            failures=(f"release evidence JSON parse failed: {exc}",),
        )
    payload = _mapping(ledger, "release-evidence", failures)
    if payload.get("stable_core_ready") is not False:
        failures.append("release evidence must keep stable_core_ready false")
    blockers = payload.get("stable_core_blockers")
    if not isinstance(blockers, list) or "package-index proof" not in blockers:
        failures.append("release evidence must preserve package-index proof as a blocker")
    package_index = _mapping(
        payload.get("package_index"),
        "release-evidence.package_index",
        failures,
    )
    if package_index.get("status") != "not-published":
        failures.append("release evidence package_index.status must remain not-published")
    if package_index.get("runbook") != RUNBOOK_PATH.as_posix():
        failures.append("release evidence package_index.runbook must point to the PyPI runbook")
    return _check_result(
        key="release_evidence_boundary",
        detail="release evidence preserves package-index and stable-core boundaries",
        failures=failures,
    )


def _validate_runbook_preflight(root: Path) -> CheckResult:
    runbook_text = _read_text(root / RUNBOOK_PATH)
    failures: list[str] = []
    if runbook_text is None:
        return _missing_result("runbook_preflight", RUNBOOK_PATH)
    for required in (
        "scripts/package_index_readiness.py --strict",
        "No PyPI or TestPyPI tokens",
        "TestPyPI first",
        ".github/workflows/publish-python-package.yml",
    ):
        if required not in runbook_text:
            failures.append(f"PyPI release runbook must mention {required}")
    return _check_result(
        key="runbook_preflight",
        detail="runbook documents token-free package-index preflight",
        failures=failures,
    )


def _validate_pyproject_version_guard(root: Path) -> CheckResult:
    pyproject_text = _read_text(root / PYPROJECT_PATH)
    if pyproject_text is None:
        return _missing_result("pyproject_version_guard", PYPROJECT_PATH)
    if 'version = "0.1.1"' not in pyproject_text:
        return CheckResult(
            key="pyproject_version_guard",
            status="pass",
            detail="package metadata is no longer the source-distribution-only version",
        )
    return CheckResult(
        key="pyproject_version_guard",
        status="pass",
        detail=(
            "pyproject is still 0.1.1; publish workflow guard prevents package-index "
            "upload until a PEP 440 alpha is chosen"
        ),
    )


def _check_result(*, key: str, detail: str, failures: list[str]) -> CheckResult:
    if failures:
        return CheckResult(key=key, status="fail", detail=detail, failures=tuple(failures))
    return CheckResult(key=key, status="pass", detail=detail)


def _missing_result(key: str, path: Path) -> CheckResult:
    display = path.as_posix()
    return CheckResult(
        key=key,
        status="fail",
        detail=f"{display} is missing or unreadable",
        failures=(f"{display} must exist",),
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
    except UnicodeDecodeError:
        return None


def _mapping(value: object, name: str, failures: list[str]) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    failures.append(f"{name} must be an object")
    return {}


def _steps(value: object, name: str, failures: list[str]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        failures.append(f"{name} must be a list")
        return []
    steps: list[dict[str, object]] = []
    items = cast(list[object], value)
    for index, item in enumerate(items):
        if isinstance(item, dict):
            steps.append(cast(dict[str, object], item))
        else:
            failures.append(f"{name}[{index}] must be an object")
    return steps
