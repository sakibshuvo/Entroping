from __future__ import annotations

import shutil
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from .demo_fixtures import DemoFixtureError, copy_demo_fixture

DemoPlanStatus = Literal["ready", "blocked"]
DemoCommandStatus = Literal["not_run", "passed", "failed", "error", "blocked"]
DemoRunStatus = Literal["ready", "passed", "failed", "blocked"]

DEMO_DEFAULT_FIXTURE: Final = "checkout-api"
DEMO_DEFAULT_REPORT_FORMATS: Final = ("json", "junit", "html")
DEMO_RUNNER_SCHEMA_VERSION: Final = "entroping.demo-runner.v1"


class DemoRunnerError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DemoWorkspace:
    fixture_id: str
    root: Path
    copied_files: tuple[Path, ...]

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


@dataclass(frozen=True, slots=True)
class DemoCommandStep:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    description: str


@dataclass(frozen=True, slots=True)
class DemoRunnerPlan:
    status: DemoPlanStatus
    message: str
    fixture_id: str
    workspace: Path
    commands: tuple[DemoCommandStep, ...]


@dataclass(frozen=True, slots=True)
class DemoCommandResult:
    name: str
    status: DemoCommandStatus
    exit_code: int | None
    duration_ms: int


@dataclass(frozen=True, slots=True)
class DemoResultSummary:
    total_commands: int
    passed: int
    failed: int
    not_run: int
    blocked: int
    errors: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class DemoRunnerResult:
    status: DemoRunStatus
    plan: DemoRunnerPlan
    command_results: tuple[DemoCommandResult, ...]
    summary: DemoResultSummary


DemoCommandExecutor = Callable[[DemoCommandStep], DemoCommandResult]


def provision_demo_workspace(
    *,
    fixture_id: str = DEMO_DEFAULT_FIXTURE,
    source_examples_root: Path | None = None,
    package_root: Path | None = None,
) -> DemoWorkspace:
    temp_root = Path(tempfile.mkdtemp(prefix="entroping-demo-runner-")).resolve()
    try:
        copied = copy_demo_fixture(
            fixture_id,
            temp_root,
            source_examples_root=source_examples_root,
            package_root=package_root,
        )
    except DemoFixtureError as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise DemoRunnerError(str(exc)) from exc

    return DemoWorkspace(
        fixture_id=fixture_id,
        root=copied.root,
        copied_files=copied.files,
    )


def build_demo_command_plan(
    *,
    workspace: DemoWorkspace,
    include_smoke_run: bool = False,
    report_formats: Sequence[str] | None = None,
) -> DemoRunnerPlan:
    formats = tuple(report_formats or DEMO_DEFAULT_REPORT_FORMATS)
    command_list = (
        _architect_build_step(workspace),
        *_smoke_run_steps(
            workspace=workspace,
            include_smoke_run=include_smoke_run,
            formats=tuple(_validate_report_format(item) for item in formats),
        ),
    )
    return DemoRunnerPlan(
        status="ready",
        message="Demo plan built; ready for execution or dry-run.",
        fixture_id=workspace.fixture_id,
        workspace=workspace.root,
        commands=tuple(command_list),
    )


def run_demo_plan(
    *,
    plan: DemoRunnerPlan,
    dry_run: bool = True,
    executor: DemoCommandExecutor | None = None,
) -> DemoRunnerResult:
    if plan.status != "ready":
        blocked_results = tuple(
            DemoCommandResult(
                name=command.name,
                status="blocked",
                exit_code=1,
                duration_ms=0,
            )
            for command in plan.commands
        )
        return DemoRunnerResult(
            status="blocked",
            plan=plan,
            command_results=blocked_results,
            summary=_plan_summary(blocked_results),
        )

    active_executor = executor or _default_command_executor
    started = time.perf_counter()
    results: list[DemoCommandResult] = []

    if dry_run:
        for command in plan.commands:
            results.append(
                DemoCommandResult(
                    name=command.name,
                    status="not_run",
                    exit_code=None,
                    duration_ms=0,
                )
            )
    else:
        for command in plan.commands:
            results.append(active_executor(command))

    summary = _plan_summary(tuple(results))
    if any(result.status in {"error", "failed", "blocked"} for result in results):
        status: DemoRunStatus = "failed"
    elif all(result.status == "not_run" for result in results):
        status = "ready"
    else:
        status = "passed"

    if not results:
        status = "ready"

    result_duration_ms = int((time.perf_counter() - started) * 1000)
    if summary.duration_ms == 0:
        summary = DemoResultSummary(
            total_commands=summary.total_commands,
            passed=summary.passed,
            failed=summary.failed,
            not_run=summary.not_run,
            blocked=summary.blocked,
            errors=summary.errors,
            duration_ms=result_duration_ms,
        )

    return DemoRunnerResult(
        status=status,
        plan=plan,
        command_results=tuple(results),
        summary=summary,
    )


def demo_plan_to_dict(plan: DemoRunnerPlan) -> dict[str, object]:
    return {
        "schema_version": DEMO_RUNNER_SCHEMA_VERSION,
        "status": plan.status,
        "message": plan.message,
        "fixture_id": plan.fixture_id,
        "workspace": str(plan.workspace),
        "command_count": len(plan.commands),
        "commands": [
            {
                "name": command.name,
                "cwd": str(command.cwd),
                "argv": list(command.argv),
                "description": command.description,
            }
            for command in plan.commands
        ],
    }


def demo_result_to_dict(result: DemoRunnerResult) -> dict[str, object]:
    return {
        "schema_version": DEMO_RUNNER_SCHEMA_VERSION,
        "status": result.status,
        "plan": demo_plan_to_dict(result.plan),
        "commands": [
            {
                "name": command_result.name,
                "status": command_result.status,
                "exit_code": command_result.exit_code,
                "duration_ms": command_result.duration_ms,
            }
            for command_result in result.command_results
        ],
        "summary": {
            "total_commands": result.summary.total_commands,
            "passed": result.summary.passed,
            "failed": result.summary.failed,
            "not_run": result.summary.not_run,
            "blocked": result.summary.blocked,
            "errors": result.summary.errors,
            "duration_ms": result.summary.duration_ms,
        },
    }


def _architect_build_step(workspace: DemoWorkspace) -> DemoCommandStep:
    return DemoCommandStep(
        name="architect-build",
        argv=(
            "uv",
            "run",
            "--project",
            str(workspace.root),
            "entroping",
            "architect",
            "build",
            "--new",
            "--tag",
            "smoke",
        ),
        cwd=workspace.root,
        description="Build example API contract state for the demo fixture.",
    )


def _smoke_run_steps(
    *,
    workspace: DemoWorkspace,
    include_smoke_run: bool,
    formats: tuple[str, ...],
) -> tuple[DemoCommandStep, ...]:
    if not include_smoke_run:
        return ()

    report_args = tuple(item for fmt in formats for item in ("--report", fmt))
    if not report_args:
        return ()

    return (
        DemoCommandStep(
            name="demo-run",
            argv=(
                "uv",
                "run",
                "--project",
                str(workspace.root),
                "entroping",
                "run",
                "--env",
                "local",
                "--tag",
                "smoke",
                *report_args,
            ),
            cwd=workspace.root,
            description="Run demo smoke tests through entroping.",
        ),
    )


def _default_command_executor(command: DemoCommandStep) -> DemoCommandResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # nosec B603
            list(command.argv),
            cwd=str(command.cwd),
            check=False,
            shell=False,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        duration_ms = int((time.perf_counter() - started) * 1000)
        return DemoCommandResult(
            name=command.name,
            status="error",
            exit_code=None,
            duration_ms=duration_ms,
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    status: DemoCommandStatus = "passed" if completed.returncode == 0 else "failed"
    return DemoCommandResult(
        name=command.name,
        status=status,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
    )


def _plan_summary(results: tuple[DemoCommandResult, ...]) -> DemoResultSummary:
    passed = sum(1 for result in results if result.status == "passed")
    failed = sum(1 for result in results if result.status == "failed")
    not_run = sum(1 for result in results if result.status == "not_run")
    blocked = sum(1 for result in results if result.status == "blocked")
    errors = sum(1 for result in results if result.status == "error")
    duration_ms = sum(result.duration_ms for result in results)
    return DemoResultSummary(
        total_commands=len(results),
        passed=passed,
        failed=failed,
        not_run=not_run,
        blocked=blocked,
        errors=errors,
        duration_ms=duration_ms,
    )


def _validate_report_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"json", "junit", "html"}:
        msg = f"Unsupported demo report format: {value}"
        raise DemoRunnerError(msg)
    return normalized


__all__ = [
    "DEMO_DEFAULT_FIXTURE",
    "DEMO_RUNNER_SCHEMA_VERSION",
    "DemoCommandExecutor",
    "DemoCommandResult",
    "DemoCommandStep",
    "DemoRunnerError",
    "DemoRunnerPlan",
    "DemoRunnerResult",
    "DemoResultSummary",
    "DemoWorkspace",
    "build_demo_command_plan",
    "demo_plan_to_dict",
    "demo_result_to_dict",
    "provision_demo_workspace",
    "run_demo_plan",
]
