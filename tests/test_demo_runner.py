import socket
import subprocess
import sys
from pathlib import Path

import pytest

import entroping.core.demo_runner as demo_runner
from entroping.core.safe_write import SafeWriteError


def test_provision_demo_workspace_copies_demo_fixture_and_can_be_cleaned() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        assert workspace.root.is_dir()
        assert workspace.fixture_id == "checkout-api"
        assert workspace.temporary is True
        assert (workspace.root / "README.md").is_file()
        assert (workspace.root / "demo_server.py").is_file()
        assert (workspace.root / "tests" / "checkout_smoke.hurl").is_file()
        assert len(workspace.copied_files) == 5
        assert not (workspace.root / "reports").exists()
    finally:
        workspace.cleanup()
        assert not workspace.root.exists()


def test_provision_demo_workspace_can_use_empty_selected_project(tmp_path: Path) -> None:
    project = tmp_path / "my-demo-project"

    workspace = demo_runner.provision_demo_workspace(destination=project)

    assert workspace.root == project.resolve()
    assert workspace.temporary is False
    assert (project / "README.md").is_file()
    workspace.cleanup()
    assert project.exists()


def test_provision_demo_workspace_rejects_non_empty_selected_project(tmp_path: Path) -> None:
    project = tmp_path / "existing-project"
    project.mkdir()
    (project / "README.md").write_text("real project\n", encoding="utf-8")

    try:
        _ = demo_runner.provision_demo_workspace(destination=project)
    except demo_runner.DemoRunnerError as exc:
        assert "must be empty" in str(exc)
    else:
        raise AssertionError("expected non-empty demo project destination to fail")


def test_provision_demo_workspace_rejects_file_destination(tmp_path: Path) -> None:
    destination = tmp_path / "demo-file"
    destination.write_text("not a directory\n", encoding="utf-8")

    try:
        _ = demo_runner.provision_demo_workspace(destination=destination)
    except demo_runner.DemoRunnerError as exc:
        assert "must be a directory" in str(exc)
    else:
        raise AssertionError("expected file demo project destination to fail")


def test_build_demo_command_plan_includes_architect_and_optional_smoke_run() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        plan = demo_runner.build_demo_command_plan(
            workspace=workspace,
            include_smoke_run=True,
            report_formats=("json", "junit"),
        )
        assert plan.status == "ready"
        assert plan.fixture_id == "checkout-api"
        assert [step.name for step in plan.commands] == [
            "architect-build",
            "demo-run",
        ]
        assert plan.commands[0].cwd == workspace.root
        assert plan.commands[0].argv[:4] == (
            "entroping",
            "architect",
            "build",
            "--new",
        )
        assert plan.commands[1].cwd == workspace.root
        assert plan.commands[1].argv[:5] == (
            "entroping",
            "run",
            "--env",
            "local",
            "--tag",
        )
        assert "--report" in plan.commands[1].argv
        assert "json" in plan.commands[1].argv
        assert "junit" in plan.commands[1].argv
    finally:
        workspace.cleanup()


def test_build_demo_command_plan_accepts_explicit_command_prefix() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        plan = demo_runner.build_demo_command_plan(
            workspace=workspace,
            include_smoke_run=True,
            command_prefix=(sys.executable, "-m", "entroping.cli.main"),
        )

        assert plan.commands[0].argv[:5] == (
            sys.executable,
            "-m",
            "entroping.cli.main",
            "architect",
            "build",
        )
        assert plan.commands[1].argv[:4] == (
            sys.executable,
            "-m",
            "entroping.cli.main",
            "run",
        )
    finally:
        workspace.cleanup()


def test_build_demo_command_plan_rejects_empty_command_prefix() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        try:
            _ = demo_runner.build_demo_command_plan(workspace=workspace, command_prefix=("", " "))
        except demo_runner.DemoRunnerError as exc:
            assert "command prefix must not be empty" in str(exc)
        else:
            raise AssertionError("expected empty command prefix to fail")
    finally:
        workspace.cleanup()


def test_run_demo_plan_dry_run_and_fake_executor_return_summary() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        plan = demo_runner.build_demo_command_plan(workspace=workspace, include_smoke_run=True)

        dry_run_result = demo_runner.run_demo_plan(plan=plan, dry_run=True)
        assert dry_run_result.status == "ready"
        assert dry_run_result.summary.total_commands == 2
        assert dry_run_result.summary.not_run == 2
        assert all(item.status == "not_run" for item in dry_run_result.command_results)

        def fake_executor(_: demo_runner.DemoCommandStep) -> demo_runner.DemoCommandResult:
            return demo_runner.DemoCommandResult(
                name="fake-command",
                status="passed",
                exit_code=0,
                duration_ms=5,
            )

        live_result = demo_runner.run_demo_plan(
            plan=plan,
            dry_run=False,
            executor=fake_executor,
        )
        assert live_result.status == "passed"
        assert live_result.summary.passed == 2
        assert live_result.summary.failed == 0
    finally:
        workspace.cleanup()


def test_run_demo_plan_reports_blocked_and_empty_plans(tmp_path: Path) -> None:
    blocked_plan = demo_runner.DemoRunnerPlan(
        status="blocked",
        message="missing fixture",
        fixture_id="checkout-api",
        workspace=tmp_path,
        commands=(
            demo_runner.DemoCommandStep(
                name="blocked-command",
                argv=("uv", "--version"),
                cwd=tmp_path,
                description="Blocked command should not run.",
            ),
        ),
    )

    blocked_result = demo_runner.run_demo_plan(plan=blocked_plan, dry_run=False)
    assert blocked_result.status == "blocked"
    assert blocked_result.summary.blocked == 1
    assert blocked_result.command_results[0].status == "blocked"

    empty_plan = demo_runner.DemoRunnerPlan(
        status="ready",
        message="empty",
        fixture_id="checkout-api",
        workspace=tmp_path,
        commands=(),
    )

    empty_result = demo_runner.run_demo_plan(plan=empty_plan, dry_run=False)
    assert empty_result.status == "ready"
    assert empty_result.summary.total_commands == 0


def test_demo_runner_serializes_plan_and_result() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        plan = demo_runner.build_demo_command_plan(workspace=workspace)
        result = demo_runner.run_demo_plan(plan=plan, dry_run=True)

        plan_payload = demo_runner.demo_plan_to_dict(plan)
        result_payload = demo_runner.demo_result_to_dict(result)

        assert plan_payload["schema_version"] == "entroping.demo-runner.v1"
        assert plan_payload["command_count"] == 1
        assert result_payload["status"] == "ready"
        assert result_payload["summary"] == {
            "total_commands": 1,
            "passed": 0,
            "failed": 0,
            "not_run": 1,
            "blocked": 0,
            "errors": 0,
            "duration_ms": 0,
        }
    finally:
        workspace.cleanup()


def test_demo_plan_rejects_invalid_report_format_and_allows_empty_formats() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        empty_format_plan = demo_runner.build_demo_command_plan(
            workspace=workspace,
            include_smoke_run=True,
            report_formats=(),
        )
        assert [step.name for step in empty_format_plan.commands] == [
            "architect-build",
        ]

        try:
            _ = demo_runner.build_demo_command_plan(
                workspace=workspace,
                include_smoke_run=True,
                report_formats=("xml",),
            )
        except demo_runner.DemoRunnerError as exc:
            assert str(exc) == "Unsupported demo report format: xml"
        else:
            raise AssertionError("expected invalid demo report format to fail")
    finally:
        workspace.cleanup()


def test_provision_demo_workspace_wraps_fixture_errors() -> None:
    try:
        _ = demo_runner.provision_demo_workspace(fixture_id="missing-demo-fixture")
    except demo_runner.DemoRunnerError as exc:
        assert "Unknown demo fixture" in str(exc)
    else:
        raise AssertionError("expected missing demo fixture to fail")


def test_default_executor_reports_subprocess_exit_codes(tmp_path: Path) -> None:
    passed_command = demo_runner.DemoCommandStep(
        name="python-pass",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        cwd=tmp_path,
        description="Successful command should pass.",
    )
    failed_command = demo_runner.DemoCommandStep(
        name="python-fail",
        argv=(sys.executable, "-c", "raise SystemExit(7)"),
        cwd=tmp_path,
        description="Non-zero command should fail.",
    )

    result = demo_runner.run_demo_plan(
        plan=demo_runner.DemoRunnerPlan(
            status="ready",
            message="ready",
            fixture_id="checkout-api",
            workspace=tmp_path,
            commands=(passed_command, failed_command),
        ),
        dry_run=False,
    )

    assert result.status == "failed"
    assert [item.status for item in result.command_results] == ["passed", "failed"]
    assert [item.exit_code for item in result.command_results] == [0, 7]


def test_default_executor_returns_error_for_missing_command(tmp_path: Path) -> None:
    command = demo_runner.DemoCommandStep(
        name="missing-command",
        argv=("entroping-demo-missing-command",),
        cwd=tmp_path,
        description="Missing command should become value-free error metadata.",
    )

    result = demo_runner.run_demo_plan(
        plan=demo_runner.DemoRunnerPlan(
            status="ready",
            message="ready",
            fixture_id="checkout-api",
            workspace=tmp_path,
            commands=(command,),
        ),
        dry_run=False,
    )

    assert result.status == "failed"
    assert result.command_results[0].status == "error"
    assert result.command_results[0].exit_code is None


def test_run_demo_workspace_starts_server_writes_env_and_runs_plan() -> None:
    workspace = demo_runner.provision_demo_workspace()
    seen_commands: list[str] = []
    try:
        port = _unused_tcp_port()

        def fake_executor(command: demo_runner.DemoCommandStep) -> demo_runner.DemoCommandResult:
            seen_commands.append(command.name)
            return demo_runner.DemoCommandResult(
                name=command.name,
                status="passed",
                exit_code=0,
                duration_ms=5,
            )

        result = demo_runner.run_demo_workspace(
            workspace=workspace,
            port=port,
            executor=fake_executor,
        )

        assert result.status == "passed"
        assert seen_commands == ["architect-build", "demo-run"]
        assert (workspace.root / "envs" / "local.env").read_text(encoding="utf-8") == (
            f"base_url=http://127.0.0.1:{port}\ncart_id=demo-cart-001\n"
        )
    finally:
        workspace.cleanup()


def test_run_demo_workspace_rejects_invalid_port() -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:
        try:
            _ = demo_runner.run_demo_workspace(workspace=workspace, port=0)
        except demo_runner.DemoRunnerError as exc:
            assert "between 1 and 65535" in str(exc)
        else:
            raise AssertionError("expected invalid demo port to fail")
    finally:
        workspace.cleanup()


def test_run_demo_workspace_rejects_missing_server(tmp_path: Path) -> None:
    workspace = demo_runner.DemoWorkspace(
        fixture_id="checkout-api",
        root=tmp_path,
        copied_files=(),
        temporary=False,
    )

    try:
        _ = demo_runner.run_demo_workspace(workspace=workspace)
    except demo_runner.DemoRunnerError as exc:
        assert "Demo server is missing" in str(exc)
    else:
        raise AssertionError("expected missing demo server to fail")


def test_run_demo_workspace_wraps_server_start_and_env_write_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = demo_runner.provision_demo_workspace()
    try:

        def fake_popen(*_: object, **__: object) -> subprocess.Popen[str]:
            raise OSError("blocked server")

        monkeypatch.setattr("entroping.core.demo_runner.subprocess.Popen", fake_popen)
        try:
            _ = demo_runner.run_demo_workspace(workspace=workspace)
        except demo_runner.DemoRunnerError as exc:
            assert "Could not start demo server" in str(exc)
        else:
            raise AssertionError("expected demo server start failure")
    finally:
        workspace.cleanup()
        monkeypatch.undo()

    workspace = demo_runner.provision_demo_workspace()
    try:

        def fake_safe_write_text(*_: object, **__: object) -> Path:
            raise SafeWriteError("blocked env")

        def fake_executor(command: demo_runner.DemoCommandStep) -> demo_runner.DemoCommandResult:
            return demo_runner.DemoCommandResult(
                name=command.name,
                status="passed",
                exit_code=0,
                duration_ms=1,
            )

        monkeypatch.setattr(demo_runner, "safe_write_text", fake_safe_write_text)
        try:
            _ = demo_runner.run_demo_workspace(
                workspace=workspace,
                port=_unused_tcp_port(),
                executor=fake_executor,
            )
        except demo_runner.DemoRunnerError as exc:
            assert "blocked env" in str(exc)
        else:
            raise AssertionError("expected demo env write failure")
    finally:
        workspace.cleanup()


def test_demo_server_wait_and_stop_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    exited_process = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(1)"],
        text=True,
    )
    exited_process.wait(timeout=5)
    try:
        demo_runner._wait_for_demo_server(
            exited_process,
            port=18080,
        )
    except demo_runner.DemoRunnerError as exc:
        assert "exited before readiness" in str(exc)
    else:
        raise AssertionError("expected exited demo server readiness failure")

    pending_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        text=True,
    )
    monkeypatch.setattr(demo_runner, "DEMO_SERVER_READY_TIMEOUT_SECONDS", 0.01)
    try:
        demo_runner._wait_for_demo_server(
            pending_process,
            port=_unused_tcp_port(),
        )
    except demo_runner.DemoRunnerError as exc:
        assert "did not become ready" in str(exc)
    else:
        raise AssertionError("expected demo server readiness timeout")
    finally:
        pending_process.kill()
        pending_process.wait(timeout=5)

    already_exited_process = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(0)"],
        text=True,
    )
    already_exited_process.wait(timeout=5)
    demo_runner._stop_demo_server(already_exited_process)

    slow_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        text=True,
    )
    original_kill = slow_process.kill
    original_wait = slow_process.wait
    state = {"killed": False, "terminated": False, "waits": 0}

    def fake_terminate() -> None:
        state["terminated"] = True

    def fake_kill() -> None:
        state["killed"] = True
        original_kill()

    def fake_wait(timeout: float | None = None) -> int:
        state["waits"] += 1
        if state["waits"] == 1:
            raise subprocess.TimeoutExpired("demo-server", timeout or 0.0)
        return original_wait(timeout=timeout)

    monkeypatch.setattr(slow_process, "terminate", fake_terminate)
    monkeypatch.setattr(slow_process, "kill", fake_kill)
    monkeypatch.setattr(slow_process, "wait", fake_wait)
    try:
        demo_runner._stop_demo_server(slow_process)
    finally:
        if slow_process.poll() is None:
            original_kill()
            original_wait(timeout=5)
    assert state == {"killed": True, "terminated": True, "waits": 2}


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])
