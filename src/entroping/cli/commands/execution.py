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
from entroping.core.run_suite_manifest import RunSuiteManifestError, load_run_suite_manifest
from entroping.core.run_workflow import (
    NoHurlTestsMatchedError,
    RunWorkflowError,
    execute_run_workflow,
)
from entroping.core.tag_expression import TagExpressionSyntaxError, compile_tag_expression
from entroping.core.traffic_filters import TrafficCaptureFilters, TrafficFilterError
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
    include_host: Annotated[
        list[str] | None,
        typer.Option("--include-host", help="Include only this captured request host."),
    ] = None,
    exclude_host: Annotated[
        list[str] | None,
        typer.Option("--exclude-host", help="Exclude this captured request host."),
    ] = None,
    include_method: Annotated[
        list[str] | None,
        typer.Option("--include-method", help="Include only this HTTP method."),
    ] = None,
    exclude_method: Annotated[
        list[str] | None,
        typer.Option("--exclude-method", help="Exclude this HTTP method."),
    ] = None,
    include_path: Annotated[
        list[str] | None,
        typer.Option("--include-path", help="Include only this request path prefix or glob."),
    ] = None,
    exclude_path: Annotated[
        list[str] | None,
        typer.Option("--exclude-path", help="Exclude this request path prefix or glob."),
    ] = None,
) -> None:
    """Convert captured traffic into Hurl tests and mocks."""

    try:
        capture_filters = _capture_filters(
            include_host=include_host,
            exclude_host=exclude_host,
            include_method=include_method,
            exclude_method=exclude_method,
            include_path=include_path,
            exclude_path=exclude_path,
        )
    except TrafficFilterError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    if mock is not None:
        try:
            mock_result = run_freeze_mock(
                project_root=Path.cwd(),
                name=name,
                service=mock,
                capture_filters=capture_filters,
            )
        except (FreezeError, ValueError) as exc:
            print_cli_error(exc)
            raise typer.Exit(1) from exc

        noun = "mapping" if mock_result.record_count == 1 else "mappings"
        console.print(
            f"[green]Froze {mock_result.record_count} traffic {noun} into WireMock.[/green]"
        )
        for output_path in mock_result.output_paths:
            console.print(f"Wrote WireMock mapping: {display_cli_path(output_path)}")
        console.print(f"Wrote approval manifest: {display_cli_path(mock_result.manifest_path)}")
        return

    try:
        freeze_result = run_freeze(
            project_root=Path.cwd(),
            name=name,
            golden=golden,
            capture_filters=capture_filters,
        )
    except (FreezeError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "record" if freeze_result.record_count == 1 else "records"
    console.print(f"[green]Froze {freeze_result.record_count} traffic {noun} into Hurl.[/green]")
    console.print(f"Wrote Hurl test: {display_cli_path(freeze_result.output_path)}")
    console.print(f"Wrote approval manifest: {display_cli_path(freeze_result.manifest_path)}")


def map(
    export: Annotated[
        str | None,
        typer.Option("--export", help="mermaid, dot, md, or png."),
    ] = None,
    include_host: Annotated[
        list[str] | None,
        typer.Option("--include-host", help="Include only this captured request host."),
    ] = None,
    exclude_host: Annotated[
        list[str] | None,
        typer.Option("--exclude-host", help="Exclude this captured request host."),
    ] = None,
    include_method: Annotated[
        list[str] | None,
        typer.Option("--include-method", help="Include only this HTTP method."),
    ] = None,
    exclude_method: Annotated[
        list[str] | None,
        typer.Option("--exclude-method", help="Exclude this HTTP method."),
    ] = None,
    include_path: Annotated[
        list[str] | None,
        typer.Option("--include-path", help="Include only this request path prefix or glob."),
    ] = None,
    exclude_path: Annotated[
        list[str] | None,
        typer.Option("--exclude-path", help="Exclude this request path prefix or glob."),
    ] = None,
) -> None:
    """Export observed dependency maps."""

    try:
        capture_filters = _capture_filters(
            include_host=include_host,
            exclude_host=exclude_host,
            include_method=include_method,
            exclude_method=exclude_method,
            include_path=include_path,
            exclude_path=exclude_path,
        )
        result = run_dependency_map(
            project_root=Path.cwd(),
            export_format=export,
            capture_filters=capture_filters,
        )
    except (DependencyMapError, TrafficFilterError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    if result.output_path is not None:
        console.print(f"Wrote dependency map: {display_cli_path(result.output_path)}")
        if result.manifest_path is not None:
            console.print(f"Wrote approval manifest: {display_cli_path(result.manifest_path)}")
        return

    console.print(result.content, markup=False, end="")


def _capture_filters(
    *,
    include_host: list[str] | None,
    exclude_host: list[str] | None,
    include_method: list[str] | None,
    exclude_method: list[str] | None,
    include_path: list[str] | None,
    exclude_path: list[str] | None,
) -> TrafficCaptureFilters:
    return TrafficCaptureFilters(
        include_hosts=tuple(include_host or ()),
        exclude_hosts=tuple(exclude_host or ()),
        include_methods=tuple(include_method or ()),
        exclude_methods=tuple(exclude_method or ()),
        include_paths=tuple(include_path or ()),
        exclude_paths=tuple(exclude_path or ()),
    )


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
    suite: Annotated[
        str | None,
        typer.Option("--suite", help="Committed suite manifest name from suites/<name>.yaml."),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag filter; repeat for multiple tags."),
    ] = None,
    tag_expression: Annotated[
        str | None,
        typer.Option(
            "--tag-expression",
            help="Boolean tag expression using and/or/not, for example: smoke and not slow.",
        ),
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

    if suite is None:
        if tag and tag_expression is not None:
            raise typer.BadParameter(
                "--tag cannot be combined with --tag-expression",
                param_hint="--tag-expression",
            )
        try:
            tag_filters = tuple(normalize_tag_filters(tag))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--tag") from exc
        if tag_expression is not None:
            try:
                compile_tag_expression(tag_expression)
            except TagExpressionSyntaxError as exc:
                raise typer.BadParameter(
                    f"Invalid tag expression: {exc}",
                    param_hint="--tag-expression",
                ) from exc

        try:
            report_formats = _normalize_report_formats(report)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--report") from exc
        run_environment = env
        run_parallel = parallel
        run_drift_check = drift_check
        run_changed_from = changed_from
        discovery_roots = None
        selection_label = None
    else:
        _reject_suite_conflicts(
            env=env,
            tag=tag,
            tag_expression=tag_expression,
            report=report,
            parallel=parallel,
            drift_check=drift_check,
            changed_from=changed_from,
        )
        try:
            loaded_suite = load_run_suite_manifest(project_root=Path.cwd(), suite_name=suite)
        except RunSuiteManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        tag_filters = loaded_suite.tag_filters
        report_formats = loaded_suite.report_formats
        run_environment = loaded_suite.environment
        run_parallel = loaded_suite.parallel
        run_drift_check = loaded_suite.drift_check
        run_changed_from = None
        discovery_roots = loaded_suite.discovery_roots
        selection_label = f"suite {loaded_suite.name!r}"

    try:
        workflow_result = execute_run_workflow(
            project_root=Path.cwd(),
            environment=run_environment,
            tag_filters=tag_filters,
            tag_expression=tag_expression,
            report_formats=report_formats,
            parallel=run_parallel,
            drift_check=run_drift_check,
            changed_from=run_changed_from,
            discovery_roots=discovery_roots,
            selection_label=selection_label,
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

    hurl_suite = workflow_result.suite
    drift_report = workflow_result.drift_report
    selection = getattr(workflow_result, "selection", None)
    if selection is not None and (tag_expression is not None or selection.skipped_count > 0):
        reason = " by tag expression" if tag_expression is not None else " by tag filters"
        console.print(
            (
                f"Hurl selection: {selection.selected_count} selected, "
                f"{selection.skipped_count} skipped{reason}"
            ),
            markup=False,
        )
    console.print(f"Hurl run: {hurl_suite.passed} passed, {hurl_suite.failed} failed")
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
    for result in hurl_suite.results:
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


def _reject_suite_conflicts(
    *,
    env: str | None,
    tag: list[str] | None,
    tag_expression: str | None,
    report: list[str] | None,
    parallel: bool,
    drift_check: bool,
    changed_from: str | None,
) -> None:
    conflicts: list[str] = []
    if env is not None:
        conflicts.append("--env")
    if tag:
        conflicts.append("--tag")
    if tag_expression is not None:
        conflicts.append("--tag-expression")
    if report:
        conflicts.append("--report")
    if parallel:
        conflicts.append("--parallel")
    if drift_check:
        conflicts.append("--drift-check")
    if changed_from is not None:
        conflicts.append("--changed-from")
    if conflicts:
        joined = ", ".join(conflicts)
        raise typer.BadParameter(f"{joined} cannot be combined with --suite", param_hint="--suite")
