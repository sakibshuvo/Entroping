"""Allowlisted verification-lane execution with value-free results."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_orchestration_models import GateExitState, GateState, VerificationLane
from scripts.factory_orchestration_tools import trusted_tool_path


@dataclass(frozen=True, slots=True)
class GateCommand:
    name: str
    command_id: str
    argv: tuple[str, ...]
    timeout_seconds: float
    max_output_bytes: int


class GateRunError(RuntimeError):
    def __init__(self, code: str, results: tuple[GateExitState, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.results = results


def commands_for_lane(
    lane: VerificationLane,
    *,
    repo_root: Path,
) -> tuple[GateCommand, ...]:
    """Derive the exact static-documentation gates from the target worktree."""

    script = repo_root / "scripts"
    match lane:
        case "tiny-docs":
            return (_script("doc-governance-v1", script / "doc_governance_check.sh"),)
        case "docs-guardrail":
            return (
                GateCommand(
                    "docs-tests",
                    "agent-workflow-docs-v1",
                    (
                        "uv",
                        "run",
                        "pytest",
                        "tests/test_agent_workflow_prompt_library.py",
                        "tests/test_agent_workflow_control_plane.py",
                        "tests/test_agent_workflow_issue_lifecycle.py",
                        "tests/test_agent_workflow_factory_artifacts.py",
                        "-q",
                    ),
                    300,
                    1_048_576,
                ),
                _script("doc-governance-v1", script / "doc_governance_check.sh"),
            )
        case _:
            raise GateRunError("scope-denied")


def run_gate_commands(
    commands: tuple[GateCommand, ...],
    *,
    cwd: Path,
    cancelled: Callable[[], bool],
    integrity_check: Callable[[], bool],
) -> tuple[GateExitState, ...]:
    """Run commands sequentially and verify Git truth after every gate."""

    results: list[GateExitState] = []
    for command in commands:
        if cancelled():
            raise GateRunError("cancelled", tuple(results))
        stdout = hashlib.sha256()
        stderr = hashlib.sha256()
        started = datetime.now(UTC)
        try:
            process = run_bounded_process(
                command.argv,
                cwd=cwd,
                timeout_seconds=command.timeout_seconds,
                max_output_bytes=command.max_output_bytes,
                env={
                    "PATH": trusted_tool_path(("uv",)),
                    "LC_ALL": "C",
                    "LANG": "C",
                },
                stdout_consumer=stdout.update,
                stderr_consumer=stderr.update,
                capture_stdout=False,
                cancelled=cancelled,
            )
        except BoundedProcessError as exc:
            raise GateRunError("gate-failed", tuple(results)) from exc
        finished = datetime.now(UTC)
        state, code = _process_state(
            process.returncode,
            process.timed_out,
            process.output_limit_exceeded,
            process.cancelled,
        )
        exit_code = process.returncode if process.returncode >= 0 else None
        signal_number = -process.returncode if process.returncode < 0 else None
        result = GateExitState(
            name=command.name,
            command_id=command.command_id,
            exit_code=exit_code,
            signal_number=signal_number,
            state=state,
            stdout_sha256=stdout.hexdigest(),
            stderr_sha256=stderr.hexdigest(),
            started_at=started,
            finished_at=finished,
        )
        results.append(result)
        if code is not None:
            raise GateRunError(code, tuple(results))
        if not integrity_check():
            raise GateRunError("gate-drift", tuple(results))
    return tuple(results)


def _script(command_id: str, path: Path, *args: str) -> GateCommand:
    return GateCommand(
        command_id.removesuffix("-v1"),
        command_id,
        ("/bin/bash", str(path), *args),
        1800,
        1_048_576,
    )


def _process_state(
    returncode: int,
    timed_out: bool,
    output_exceeded: bool,
    cancelled: bool,
) -> tuple[GateState, str | None]:
    if cancelled:
        return "cancelled", "cancelled"
    if output_exceeded:
        return "output-exceeded", "gate-output-exceeded"
    if timed_out:
        return "timed-out", "gate-timeout"
    if returncode != 0:
        return "failed", "gate-failed"
    return "passed", None
