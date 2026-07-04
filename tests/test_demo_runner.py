import socket
import sys
from pathlib import Path

from entroping.core.demo_runner import (
    DemoCommandResult,
    DemoCommandStep,
    DemoRunnerError,
    DemoRunnerPlan,
    build_demo_command_plan,
    demo_plan_to_dict,
    demo_result_to_dict,
    provision_demo_workspace,
    run_demo_plan,
    run_demo_workspace,
)


def test_provision_demo_workspace_copies_demo_fixture_and_can_be_cleaned() -> None:
    workspace = provision_demo_workspace()
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

    workspace = provision_demo_workspace(destination=project)

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
        _ = provision_demo_workspace(destination=project)
    except DemoRunnerError as exc:
        assert "must be empty" in str(exc)
    else:
        raise AssertionError("expected non-empty demo project destination to fail")


def test_build_demo_command_plan_includes_architect_and_optional_smoke_run() -> None:
    workspace = provision_demo_workspace()
    try:
        plan = build_demo_command_plan(
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
    workspace = provision_demo_workspace()
    try:
        plan = build_demo_command_plan(
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


def test_run_demo_plan_dry_run_and_fake_executor_return_summary() -> None:
    workspace = provision_demo_workspace()
    try:
        plan = build_demo_command_plan(workspace=workspace, include_smoke_run=True)

        dry_run_result = run_demo_plan(plan=plan, dry_run=True)
        assert dry_run_result.status == "ready"
        assert dry_run_result.summary.total_commands == 2
        assert dry_run_result.summary.not_run == 2
        assert all(item.status == "not_run" for item in dry_run_result.command_results)

        def fake_executor(_: DemoCommandStep) -> DemoCommandResult:
            return DemoCommandResult(
                name="fake-command",
                status="passed",
                exit_code=0,
                duration_ms=5,
            )

        live_result = run_demo_plan(
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
    blocked_plan = DemoRunnerPlan(
        status="blocked",
        message="missing fixture",
        fixture_id="checkout-api",
        workspace=tmp_path,
        commands=(
            DemoCommandStep(
                name="blocked-command",
                argv=("uv", "--version"),
                cwd=tmp_path,
                description="Blocked command should not run.",
            ),
        ),
    )

    blocked_result = run_demo_plan(plan=blocked_plan, dry_run=False)
    assert blocked_result.status == "blocked"
    assert blocked_result.summary.blocked == 1
    assert blocked_result.command_results[0].status == "blocked"

    empty_plan = DemoRunnerPlan(
        status="ready",
        message="empty",
        fixture_id="checkout-api",
        workspace=tmp_path,
        commands=(),
    )

    empty_result = run_demo_plan(plan=empty_plan, dry_run=False)
    assert empty_result.status == "ready"
    assert empty_result.summary.total_commands == 0


def test_demo_runner_serializes_plan_and_result() -> None:
    workspace = provision_demo_workspace()
    try:
        plan = build_demo_command_plan(workspace=workspace)
        result = run_demo_plan(plan=plan, dry_run=True)

        plan_payload = demo_plan_to_dict(plan)
        result_payload = demo_result_to_dict(result)

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
    workspace = provision_demo_workspace()
    try:
        empty_format_plan = build_demo_command_plan(
            workspace=workspace,
            include_smoke_run=True,
            report_formats=(),
        )
        assert [step.name for step in empty_format_plan.commands] == [
            "architect-build",
        ]

        try:
            _ = build_demo_command_plan(
                workspace=workspace,
                include_smoke_run=True,
                report_formats=("xml",),
            )
        except DemoRunnerError as exc:
            assert str(exc) == "Unsupported demo report format: xml"
        else:
            raise AssertionError("expected invalid demo report format to fail")
    finally:
        workspace.cleanup()


def test_provision_demo_workspace_wraps_fixture_errors() -> None:
    try:
        _ = provision_demo_workspace(fixture_id="missing-demo-fixture")
    except DemoRunnerError as exc:
        assert "Unknown demo fixture" in str(exc)
    else:
        raise AssertionError("expected missing demo fixture to fail")


def test_default_executor_reports_subprocess_exit_codes(tmp_path: Path) -> None:
    passed_command = DemoCommandStep(
        name="python-pass",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        cwd=tmp_path,
        description="Successful command should pass.",
    )
    failed_command = DemoCommandStep(
        name="python-fail",
        argv=(sys.executable, "-c", "raise SystemExit(7)"),
        cwd=tmp_path,
        description="Non-zero command should fail.",
    )

    result = run_demo_plan(
        plan=DemoRunnerPlan(
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
    command = DemoCommandStep(
        name="missing-command",
        argv=("entroping-demo-missing-command",),
        cwd=tmp_path,
        description="Missing command should become value-free error metadata.",
    )

    result = run_demo_plan(
        plan=DemoRunnerPlan(
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
    workspace = provision_demo_workspace()
    seen_commands: list[str] = []
    try:
        port = _unused_tcp_port()

        def fake_executor(command: DemoCommandStep) -> DemoCommandResult:
            seen_commands.append(command.name)
            return DemoCommandResult(
                name=command.name,
                status="passed",
                exit_code=0,
                duration_ms=5,
            )

        result = run_demo_workspace(
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


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])
