from __future__ import annotations

import importlib
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from factory_orchestration_test_support import git, repository

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

gates = importlib.import_module("scripts.factory_orchestration_gates")
tools = importlib.import_module("scripts.factory_orchestration_tools")
from scripts.factory_orchestration_gates import GateCommand  # noqa: E402


@pytest.fixture
def _trusted_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = shutil.which("uv")
    assert source is not None
    tool_dir = tmp_path / "private-tools"
    tool_dir.mkdir(mode=0o700)
    executable = tool_dir / "uv"
    shutil.copy2(source, executable)
    executable.chmod(0o700)
    real_which = shutil.which

    def resolve_uv(
        name: str,
        mode: int = os.F_OK | os.X_OK,
        path: str | None = None,
    ) -> str | None:
        if name == "uv" and path is None:
            return str(executable)
        return real_which(name, mode=mode, path=path)

    monkeypatch.setattr(tools.shutil, "which", resolve_uv)
    return executable


def _command(code: str, *, timeout: float = 2, limit: int = 1024) -> GateCommand:
    return GateCommand(
        name="focused-tests",
        command_id="test-command-v1",
        argv=(sys.executable, "-c", code),
        timeout_seconds=timeout,
        max_output_bytes=limit,
    )


def test_gate_runner_records_value_free_output_digests(
    tmp_path: Path, _trusted_uv: Path
) -> None:
    # Given: one successful bounded gate with raw output.
    commands = (_command("print('secret-like-output-not-receipted')"),)

    # When: the gate runs and repository truth remains stable.
    results = gates.run_gate_commands(
        commands,
        cwd=tmp_path,
        cancelled=lambda: False,
        integrity_check=lambda: True,
    )

    # Then: only exit identity and output digests leave the boundary.
    assert results[0].state == "passed"
    assert results[0].exit_code == 0
    assert len(results[0].stdout_sha256) == 64
    assert "secret-like" not in results[0].model_dump_json()


@pytest.mark.parametrize(
    ("command", "reason", "state"),
    [
        (_command("raise SystemExit(3)"), "gate-failed", "failed"),
        (_command("import time; time.sleep(60)", timeout=0.05), "gate-timeout", "timed-out"),
        (_command("print('x' * 10000)", limit=64), "gate-output-exceeded", "output-exceeded"),
    ],
)
def test_gate_runner_fails_closed_on_exit_timeout_and_output(
    tmp_path: Path,
    _trusted_uv: Path,
    command: GateCommand,
    reason: str,
    state: str,
) -> None:
    # Given/When: a bounded gate reaches one explicit failure state.
    with pytest.raises(gates.GateRunError) as exc_info:
        gates.run_gate_commands(
            (command,),
            cwd=tmp_path,
            cancelled=lambda: False,
            integrity_check=lambda: True,
        )

    # Then: the error exposes only the fixed reason and normalized exit state.
    assert exc_info.value.code == reason
    assert exc_info.value.results[0].state == state


def test_gate_runner_rejects_cancellation_and_gate_created_drift(
    tmp_path: Path, _trusted_uv: Path
) -> None:
    # Given: cancellation before a gate.
    with pytest.raises(gates.GateRunError) as cancelled:
        gates.run_gate_commands(
            (_command("raise SystemExit(99)"),),
            cwd=tmp_path,
            cancelled=lambda: True,
            integrity_check=lambda: True,
        )
    assert cancelled.value.code == "cancelled"
    assert cancelled.value.results == ()

    # Given: a passing gate that mutates the bound Git truth.
    with pytest.raises(gates.GateRunError) as drift:
        gates.run_gate_commands(
            (_command("pass"),),
            cwd=tmp_path,
            cancelled=lambda: False,
            integrity_check=lambda: False,
        )
    assert drift.value.code == "gate-drift"


def test_gate_runner_cancels_running_process(tmp_path: Path, _trusted_uv: Path) -> None:
    # Given: cancellation becomes true while a gate process is still running.
    started = time.monotonic()

    # When: the bounded gate observes cancellation.
    with pytest.raises(gates.GateRunError) as exc_info:
        gates.run_gate_commands(
            (_command("import time; time.sleep(60)", timeout=10),),
            cwd=tmp_path,
            cancelled=lambda: time.monotonic() - started >= 0.05,
            integrity_check=lambda: True,
        )

    # Then: cancellation is terminal and cannot be reported as acceptance.
    assert exc_info.value.code == "cancelled"
    assert exc_info.value.results[0].state == "cancelled"


@pytest.mark.parametrize(
    ("lane", "command_ids"),
    (
        ("tiny-docs", ("doc-governance-v1",)),
        ("docs-guardrail", ("agent-workflow-docs-v1", "doc-governance-v1")),
    ),
)
def test_lane_commands_are_exact_target_worktree_allowlists(
    tmp_path: Path,
    lane: str,
    command_ids: tuple[str, ...],
) -> None:
    commands = gates.commands_for_lane(lane, repo_root=tmp_path)

    assert tuple(command.command_id for command in commands) == command_ids
    assert commands[-1].argv == (
        "/bin/bash",
        str(tmp_path / "scripts" / "doc_governance_check.sh"),
    )


def test_non_documentation_lane_has_no_executable_fallback(tmp_path: Path) -> None:
    with pytest.raises(gates.GateRunError) as exc_info:
        gates.commands_for_lane("normal-code", repo_root=tmp_path)

    assert exc_info.value.code == "scope-denied"


def test_fixture_gate_executes_target_worktree_script_and_isolates_main(
    tmp_path: Path,
    _trusted_uv: Path,
) -> None:
    main, target, _base = repository(tmp_path)
    script = main / "scripts" / "doc_governance_check.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/bin/bash\n! grep -q BROKEN docs/user/guide.md\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    git(main, "add", "scripts/doc_governance_check.sh")
    git(main, "commit", "-m", "add docs gate")
    git(target, "reset", "--hard", git(main, "rev-parse", "HEAD"))
    control = main / ".entroping" / "control-state"
    control.parent.mkdir(parents=True)
    control.write_bytes(b"scheduler-state")
    main_status = git(main, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    (target / "docs/user/guide.md").write_text("BROKEN\n", encoding="utf-8")

    main_results = gates.run_gate_commands(
        gates.commands_for_lane("tiny-docs", repo_root=main),
        cwd=main,
        cancelled=lambda: False,
        integrity_check=lambda: True,
    )
    assert main_results[0].state == "passed"

    commands = gates.commands_for_lane("tiny-docs", repo_root=target)
    with pytest.raises(gates.GateRunError) as exc_info:
        gates.run_gate_commands(
            commands,
            cwd=target,
            cancelled=lambda: False,
            integrity_check=lambda: True,
        )

    assert exc_info.value.code == "gate-failed"
    assert exc_info.value.results[0].exit_code == 1
    assert commands[0].argv[1] == str(target / "scripts" / "doc_governance_check.sh")
    assert git(main, "status", "--porcelain=v1", "-z", "--untracked-files=all") == main_status
    assert control.read_bytes() == b"scheduler-state"


def test_production_tiny_docs_command_runs_real_governance_chain(
    _trusted_uv: Path,
) -> None:
    command = gates.commands_for_lane("tiny-docs", repo_root=REPO_ROOT)

    results = gates.run_gate_commands(
        command,
        cwd=REPO_ROOT,
        cancelled=lambda: False,
        integrity_check=lambda: True,
    )

    assert len(results) == 1
    assert results[0].command_id == "doc-governance-v1"
    assert results[0].state == "passed"
    assert command[0].argv == (
        "/bin/bash",
        str(REPO_ROOT / "scripts/doc_governance_check.sh"),
    )
