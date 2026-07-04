from pathlib import Path

from entroping.core.demo_runner import (
    DemoCommandResult,
    DemoCommandStep,
    DemoRunnerPlan,
    build_demo_command_plan,
    provision_demo_workspace,
    run_demo_plan,
)


def test_provision_demo_workspace_copies_demo_fixture_and_can_be_cleaned() -> None:
    workspace = provision_demo_workspace()
    try:
        assert workspace.root.is_dir()
        assert workspace.fixture_id == "checkout-api"
        assert (workspace.root / "README.md").is_file()
        assert (workspace.root / "demo_server.py").is_file()
        assert (workspace.root / "tests" / "checkout_smoke.hurl").is_file()
        assert len(workspace.copied_files) == 5
        assert not (workspace.root / "reports").exists()
    finally:
        workspace.cleanup()
        assert not workspace.root.exists()


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
        assert str(workspace.root) in " ".join(plan.commands[0].argv)
        assert plan.commands[0].argv[:6] == (
            "uv",
            "run",
            "--project",
            str(workspace.root),
            "entroping",
            "architect",
        )
        assert plan.commands[1].argv[:9] == (
            "uv",
            "run",
            "--project",
            str(workspace.root),
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
