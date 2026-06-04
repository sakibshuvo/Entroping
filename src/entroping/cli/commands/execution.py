"""Runtime and observation command adapters."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error, safe_cli_text
from entroping.core.config_loader import QanstitutionLoadError
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.drift_report import DriftReportError
from entroping.core.freeze import FreezeError, run_freeze, run_freeze_mock
from entroping.core.gate_injector import GateInjectionError
from entroping.core.hurl_discovery import normalize_tag_filters
from entroping.core.hurl_runner import HurlBinaryNotFoundError
from entroping.core.report_writer import ReportWriterError
from entroping.core.run_workflow import (
    NoHurlTestsMatchedError,
    RunWorkflowError,
    execute_run_workflow,
)
from entroping.core.traffic_proxy import (
    DEFAULT_WATCH_PORT,
    TrafficProxyError,
    WatchConfig,
    run_watch,
)
from entroping.studio.app import run_studio_app
from entroping.studio.status import (
    StudioDependencyError,
    collect_studio_status,
    ensure_studio_available,
)


def register_execution_commands(root_app: typer.Typer) -> None:
    root_app.command()(watch)
    root_app.command()(freeze)
    root_app.command()(map)
    root_app.command()(studio)
    root_app.command()(run)


def watch(
    port: Annotated[int | None, typer.Option("--port", help="Local proxy port.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target upstream URL.")] = None,
) -> None:
    """Start traffic observation."""

    try:
        config = WatchConfig(
            project_root=Path.cwd(),
            listen_port=port or DEFAULT_WATCH_PORT,
            target_url=target,
        )
        console.print(f"Capturing traffic on 127.0.0.1:{config.listen_port}")
        if config.target_url is not None:
            console.print(f"Target scope: {safe_cli_text(config.target_url)}", markup=False)
        console.print("Persisting redacted traffic to .entroping/state.db")
        asyncio.run(run_watch(config))
    except KeyboardInterrupt:
        console.print("Stopped traffic capture.")
    except (TrafficProxyError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc


def freeze(
    name: Annotated[str, typer.Option("--name", help="Captured flow name.")],
    golden: Annotated[bool, typer.Option("--golden", help="Add golden assertions.")] = False,
    mock: Annotated[str | None, typer.Option("--mock", help="Dependency to mock.")] = None,
) -> None:
    """Convert captured traffic into Hurl tests and mocks."""

    if mock is not None:
        try:
            mock_result = run_freeze_mock(project_root=Path.cwd(), name=name, service=mock)
        except (FreezeError, ValueError) as exc:
            print_cli_error(exc)
            raise typer.Exit(1) from exc

        noun = "mapping" if mock_result.record_count == 1 else "mappings"
        console.print(
            f"[green]Froze {mock_result.record_count} traffic {noun} into WireMock.[/green]"
        )
        for output_path in mock_result.output_paths:
            console.print(f"Wrote WireMock mapping: {display_cli_path(output_path)}")
        return

    try:
        freeze_result = run_freeze(project_root=Path.cwd(), name=name, golden=golden)
    except (FreezeError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "record" if freeze_result.record_count == 1 else "records"
    console.print(f"[green]Froze {freeze_result.record_count} traffic {noun} into Hurl.[/green]")
    console.print(f"Wrote Hurl test: {display_cli_path(freeze_result.output_path)}")


def map(
    export: Annotated[
        str | None,
        typer.Option("--export", help="mermaid, dot, md, or png."),
    ] = None,
) -> None:
    """Export observed dependency maps."""

    try:
        result = run_dependency_map(project_root=Path.cwd(), export_format=export)
    except (DependencyMapError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    if result.output_path is not None:
        console.print(f"Wrote dependency map: {display_cli_path(result.output_path)}")
        return

    console.print(result.content, markup=False, end="")


def studio(
    env: Annotated[str | None, typer.Option("--env", help="Environment name.")] = None,
) -> None:
    """Open the local Studio interface."""

    try:
        ensure_studio_available()
        status = collect_studio_status(project_root=Path.cwd(), environment=env)
    except StudioDependencyError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1) from exc

    run_studio_app(status)


def run(
    env: Annotated[str | None, typer.Option("--env", help="Environment name.")] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag filter; repeat for multiple tags."),
    ] = None,
    ci: Annotated[bool, typer.Option("--ci", help="Strict CI mode.")] = False,
    parallel: Annotated[
        bool,
        typer.Option("--parallel", help="Bounded parallel execution."),
    ] = False,
    report: Annotated[
        list[str] | None,
        typer.Option("--report", help="Report format; repeat for multiple formats."),
    ] = None,
    drift_check: Annotated[
        bool,
        typer.Option("--drift-check", help="Compare against baseline."),
    ] = False,
    changed_from: Annotated[
        str | None,
        typer.Option(
            "--changed-from",
            help="Run existing changed .hurl files from a Git base ref.",
        ),
    ] = None,
) -> None:
    """Run Hurl suites with QAnstitution gates."""

    try:
        tag_filters = normalize_tag_filters(tag)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--tag") from exc

    try:
        report_formats = _normalize_report_formats(report)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--report") from exc

    try:
        workflow_result = execute_run_workflow(
            project_root=Path.cwd(),
            environment=env,
            tag_filters=tuple(tag_filters),
            report_formats=report_formats,
            parallel=parallel,
            drift_check=drift_check,
            changed_from=changed_from,
        )
    except NoHurlTestsMatchedError as exc:
        console.print(safe_cli_text(exc), style="yellow", markup=False)
        raise typer.Exit(1 if ci else 0) from exc
    except (
        DriftReportError,
        FileNotFoundError,
        GateInjectionError,
        HurlBinaryNotFoundError,
        QanstitutionLoadError,
        ReportWriterError,
        RunWorkflowError,
        ValueError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    suite = workflow_result.suite
    drift_report = workflow_result.drift_report
    console.print(f"Hurl run: {suite.passed} passed, {suite.failed} failed")
    if drift_report is not None:
        if drift_report.summary.missing_baseline:
            console.print(
                "[yellow]Drift baseline not found: .entroping/drift-baseline.json. "
                "Run with --report drift to review reports/drift-baseline.candidate.json "
                "before running entroping report promote-drift-baseline.[/yellow]"
            )
        else:
            noun = "finding" if drift_report.summary.drifted == 1 else "findings"
            console.print(f"Drift check: {drift_report.summary.drifted} {noun}")
    console.print(f"Wrote latest run state: {display_cli_path(workflow_result.latest_state_path)}")
    for artifact in workflow_result.artifacts:
        console.print(f"Wrote report: {display_cli_path(artifact)}")
    for result in suite.results:
        if result.passed:
            continue
        console.print(f"[red]{result.path.name}: {result.status}[/red]")
        if result.stdout:
            console.print(result.stdout, markup=False)
        if result.stderr:
            console.print(result.stderr, markup=False)

    raise typer.Exit(workflow_result.exit_code)


def _normalize_report_formats(report: list[str] | None) -> tuple[str, ...]:
    if not report:
        return ()

    normalized: list[str] = []
    for raw_format in report:
        report_format = raw_format.strip().lower()
        if report_format not in {"drift", "html", "json", "junit"}:
            msg = (
                f"Unsupported report format {raw_format!r}; "
                "supported formats: drift, html, json, junit"
            )
            raise ValueError(msg)
        if report_format not in normalized:
            normalized.append(report_format)
    return tuple(normalized)
