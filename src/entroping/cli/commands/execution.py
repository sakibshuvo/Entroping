"""Runtime and observation command adapters."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error, safe_cli_text
from entroping.core.config_loader import QanstitutionLoadError
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.drift_report import DriftReportError
from entroping.core.freeze import (
    FreezeError,
    FreezePreviewResult,
    preview_freeze,
    preview_freeze_mock,
    run_freeze,
    run_freeze_mock,
)
from entroping.core.gate_injector import GateInjectionError
from entroping.core.hurl_runner import HurlBinaryNotFoundError
from entroping.core.report_writer import ReportWriterError
from entroping.core.rerun_failures import (
    RerunFailureSelection,
    RerunFailuresError,
    select_latest_failed_hurl_tests,
)
from entroping.core.run_option_validation import (
    RunOptionValidationError,
    normalize_run_report_formats,
    prepare_ad_hoc_run_selectors,
    validate_rerun_failure_options,
    validate_run_suite_options,
)
from entroping.core.run_suite_manifest import RunSuiteManifestError, load_run_suite_manifest
from entroping.core.run_workflow import (
    NoHurlTestsMatchedError,
    RunExecutionPlan,
    RunWorkflowError,
    execute_run_workflow,
    plan_run_workflow,
    write_run_execution_plan,
)
from entroping.core.traffic_filters import TrafficCaptureFilters, TrafficFilterError
from entroping.core.traffic_proxy import (
    DEFAULT_WATCH_PORT,
    TrafficProxyError,
    WatchConfig,
    WatchRunSummary,
    run_watch,
)
from entroping.studio.app import run_studio_app
from entroping.studio.status import (
    StudioDependencyError,
    collect_studio_status,
    ensure_studio_available,
)


def register_execution_commands(root_app: typer.Typer) -> None:
    root_app.command(rich_help_panel="Traffic Observation")(watch)
    root_app.command(rich_help_panel="Traffic Observation")(freeze)
    root_app.command(rich_help_panel="Traffic Observation")(map)
    root_app.command(rich_help_panel="Advanced And Evidence")(studio)
    root_app.command(rich_help_panel="Core Workflow")(run)


def watch(
    port: Annotated[int | None, typer.Option("--port", help="Local proxy port.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target upstream URL.")] = None,
    scope_host: Annotated[
        list[str] | None,
        typer.Option("--scope-host", help="Capture only this host; repeat for more hosts."),
    ] = None,
    scope_url_prefix: Annotated[
        list[str] | None,
        typer.Option(
            "--scope-url-prefix",
            help="Capture only this absolute URL prefix; repeat for more prefixes.",
        ),
    ] = None,
) -> None:
    """Start traffic observation."""

    try:
        config = WatchConfig(
            project_root=Path.cwd(),
            listen_port=port or DEFAULT_WATCH_PORT,
            target_url=target,
            scope_hosts=tuple(scope_host or ()),
            scope_url_prefixes=tuple(scope_url_prefix or ()),
        )
        console.print(f"Capturing traffic on 127.0.0.1:{config.listen_port}")
        console.print(_watch_scope_summary(config), markup=False)
        console.print("Persisting redacted traffic to .entroping/state.db")
        console.print(
            "Review redaction coverage with `entroping report redaction`.",
            markup=False,
        )
        console.print(
            "Check before freeze, freeze --mock, map --export, or sharing artifacts.",
            markup=False,
        )
        summary = asyncio.run(run_watch(config))
        if summary is not None:
            _print_watch_summary(summary)
    except KeyboardInterrupt:
        console.print("Stopped traffic capture.")
    except (TrafficProxyError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc


def freeze(
    name: Annotated[str, typer.Option("--name", help="Captured flow name.")],
    golden: Annotated[bool, typer.Option("--golden", help="Add golden assertions.")] = False,
    mock: Annotated[str | None, typer.Option("--mock", help="Dependency to mock.")] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview generated artifacts without writing files."),
    ] = False,
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
            if dry_run:
                mock_preview = preview_freeze_mock(
                    project_root=Path.cwd(),
                    name=name,
                    service=mock,
                    capture_filters=capture_filters,
                )
                _print_freeze_preview(mock_preview)
                return
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
        if dry_run:
            freeze_preview = preview_freeze(
                project_root=Path.cwd(),
                name=name,
                golden=golden,
                capture_filters=capture_filters,
            )
            _print_freeze_preview(freeze_preview)
            return
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


def _print_freeze_preview(preview: FreezePreviewResult) -> None:
    console.print("Dry run: no files were written.")
    console.print(f"Selected traffic records: {preview.record_count}")
    if preview.workflow == "freeze-hurl":
        console.print(f"Golden assertions: {'yes' if preview.golden else 'no'}")

    for artifact in preview.artifacts:
        if artifact.kind == "hurl":
            console.print(f"Would write Hurl test: {display_cli_path(artifact.path)}")
        elif artifact.kind == "wiremock":
            console.print(f"Would write WireMock mapping: {display_cli_path(artifact.path)}")

    for record in preview.records:
        status = record.status_code if record.status_code is not None else "no response"
        console.print(
            f"{safe_cli_text(record.method)} {safe_cli_text(record.path)} -> {status}",
            markup=False,
        )

    if preview.redaction_categories:
        console.print("Redaction categories:")
        for category in preview.redaction_categories:
            console.print(f"- {safe_cli_text(category.category)}: {category.count}", markup=False)


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


def _watch_scope_summary(config: WatchConfig) -> str:
    scopes: list[str] = []
    if config.target_url is not None:
        scopes.append("1 target origin")
    if config.scope_hosts:
        scopes.append(_plural_noun(len(config.scope_hosts), "host", "hosts"))
    if config.scope_url_prefixes:
        scopes.append(_plural_noun(len(config.scope_url_prefixes), "URL prefix", "URL prefixes"))
    return f"Capture scope: {', '.join(scopes)}"


def _print_watch_summary(summary: WatchRunSummary) -> None:
    console.print(
        _plural_sentence(
            summary.recorded_count,
            "Recorded {count} in-scope traffic flow",
            "Recorded {count} in-scope traffic flows",
        )
    )
    if summary.ignored_count:
        console.print(
            _plural_sentence(
                summary.ignored_count,
                "Ignored {count} out-of-scope traffic flow",
                "Ignored {count} out-of-scope traffic flows",
            )
        )
    if summary.malformed_count:
        console.print(
            _plural_sentence(
                summary.malformed_count,
                "Ignored {count} malformed traffic flow",
                "Ignored {count} malformed traffic flows",
            )
        )


def _plural_noun(count: int, singular: str, plural: str) -> str:
    noun = singular if count == 1 else plural
    return f"{count} {noun}"


def _plural_sentence(count: int, singular: str, plural: str) -> str:
    template = singular if count == 1 else plural
    return template.format(count=count)


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
    operation_id: Annotated[
        list[str] | None,
        typer.Option(
            "--operation-id",
            help="OpenAPI operation_id metadata filter; repeat for multiple operations.",
        ),
    ] = None,
    ci: Annotated[bool, typer.Option("--ci", help="Strict CI mode.")] = False,
    parallel: Annotated[
        bool,
        typer.Option("--parallel", help="Bounded parallel execution."),
    ] = False,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop scheduling tests after the first failure."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the execution plan without running Hurl."),
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
    rerun_failures: Annotated[
        bool,
        typer.Option(
            "--rerun-failures",
            help="Run failed Hurl files from the latest local run report.",
        ),
    ] = False,
) -> None:
    """Run Hurl suites with QAnstitution gates."""

    rerun_selection: RerunFailureSelection | None = None
    if suite is None:
        try:
            if rerun_failures:
                validate_rerun_failure_options(
                    tag=tag,
                    tag_expression=tag_expression,
                    operation_id=operation_id,
                    changed_from=changed_from,
                )
            selectors = prepare_ad_hoc_run_selectors(
                tag=tag,
                tag_expression=tag_expression,
                operation_id=operation_id,
                changed_from=changed_from,
            )
            report_formats = normalize_run_report_formats(report)
        except RunOptionValidationError as exc:
            raise typer.BadParameter(str(exc), param_hint=exc.param_hint) from exc
        tag_filters = selectors.tag_filters
        operation_filters = selectors.operation_filters
        run_environment = env
        run_parallel = parallel
        run_fail_fast = fail_fast
        run_drift_check = drift_check
        run_changed_from = changed_from
        if rerun_failures:
            try:
                rerun_selection = select_latest_failed_hurl_tests(project_root=Path.cwd())
            except RerunFailuresError as exc:
                print_cli_error(exc)
                raise typer.Exit(1) from exc
            run_environment = env if env is not None else rerun_selection.environment
            discovery_roots = rerun_selection.failed_paths
            selection_label = (
                f"failed tests from {display_cli_path(rerun_selection.report_path)}"
            )
        else:
            discovery_roots = None
            selection_label = None
    else:
        try:
            validate_run_suite_options(
                env=env,
                tag=tag,
                tag_expression=tag_expression,
                operation_id=operation_id,
                report=report,
                parallel=parallel,
                fail_fast=fail_fast,
                drift_check=drift_check,
                changed_from=changed_from,
                rerun_failures=rerun_failures,
            )
        except RunOptionValidationError as exc:
            raise typer.BadParameter(str(exc), param_hint=exc.param_hint) from exc
        try:
            loaded_suite = load_run_suite_manifest(project_root=Path.cwd(), suite_name=suite)
        except RunSuiteManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        tag_filters = loaded_suite.tag_filters
        operation_filters = ()
        report_formats = loaded_suite.report_formats
        run_environment = loaded_suite.environment
        run_parallel = loaded_suite.parallel
        run_fail_fast = loaded_suite.fail_fast
        run_drift_check = loaded_suite.drift_check
        run_changed_from = None
        discovery_roots = loaded_suite.discovery_roots
        selection_label = f"suite {loaded_suite.name!r}"

    if dry_run:
        _execute_run_dry_run(
            run_environment=run_environment,
            tag_filters=tag_filters,
            tag_expression=tag_expression,
            operation_filters=operation_filters,
            report_formats=report_formats,
            run_parallel=run_parallel,
            run_fail_fast=run_fail_fast,
            run_drift_check=run_drift_check,
            run_changed_from=run_changed_from,
            discovery_roots=discovery_roots,
            selection_label=selection_label,
            ci=ci,
        )

    try:
        workflow_result = execute_run_workflow(
            project_root=Path.cwd(),
            environment=run_environment,
            tag_filters=tag_filters,
            tag_expression=tag_expression,
            operation_ids=operation_filters,
            report_formats=report_formats,
            parallel=run_parallel,
            fail_fast=run_fail_fast,
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
    if rerun_selection is not None:
        console.print(
            (
                f"Rerun failures: {len(rerun_selection.failed_paths)} selected from "
                f"{display_cli_path(rerun_selection.report_path)}"
            ),
            markup=False,
        )
    if selection is not None and (tag_expression is not None or selection.skipped_count > 0):
        if operation_filters:
            reason = " by operation ID"
        elif tag_expression is not None:
            reason = " by tag expression"
        else:
            reason = " by tag filters"
        console.print(
            (
                f"Hurl selection: {selection.selected_count} selected, "
                f"{selection.skipped_count} skipped{reason}"
            ),
            markup=False,
        )
    console.print(f"Hurl run: {hurl_suite.passed} passed, {hurl_suite.failed} failed")
    if hurl_suite.fail_fast and hurl_suite.not_scheduled:
        console.print(
            (
                f"Fail-fast: executed {hurl_suite.total} of "
                f"{hurl_suite.selected_count} selected tests; "
                f"{hurl_suite.not_scheduled} not scheduled"
            ),
            markup=False,
        )
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
    event_log_path = getattr(workflow_result, "event_log_path", None)
    if isinstance(event_log_path, Path):
        console.print(f"Wrote execution events: {display_cli_path(event_log_path)}")
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


def _execute_run_dry_run(
    *,
    run_environment: str | None,
    tag_filters: tuple[str, ...],
    tag_expression: str | None,
    operation_filters: tuple[str, ...],
    report_formats: tuple[str, ...],
    run_parallel: bool,
    run_fail_fast: bool,
    run_drift_check: bool,
    run_changed_from: str | None,
    discovery_roots: tuple[Path, ...] | None,
    selection_label: str | None,
    ci: bool,
) -> None:
    try:
        plan = plan_run_workflow(
            project_root=Path.cwd(),
            environment=run_environment,
            tag_filters=tag_filters,
            tag_expression=tag_expression,
            operation_ids=operation_filters,
            report_formats=report_formats,
            parallel=run_parallel,
            fail_fast=run_fail_fast,
            drift_check=run_drift_check,
            changed_from=run_changed_from,
            discovery_roots=discovery_roots,
            selection_label=selection_label,
        )
        _print_run_plan(plan)
        if "json" in report_formats:
            plan_path = write_run_execution_plan(
                plan,
                Path("reports") / "run-plan.json",
                project_root=Path.cwd(),
            )
            console.print(f"Wrote execution plan: {display_cli_path(plan_path)}")
    except (
        FileNotFoundError,
        GateInjectionError,
        QanstitutionLoadError,
        ReportWriterError,
        RunWorkflowError,
        ValueError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if plan.status == "blocked" or (ci and plan.status == "no_match"):
        raise typer.Exit(1)
    raise typer.Exit(0)


def _print_run_plan(plan: RunExecutionPlan) -> None:
    console.print("Dry run: no Hurl execution performed.")
    if plan.status == "no_match":
        console.print(safe_cli_text(plan.message), style="yellow", markup=False)
    elif plan.status == "blocked":
        console.print("[yellow]Run plan blocked before Hurl execution.[/yellow]")
    else:
        console.print("[green]Run plan ready.[/green]")
    console.print(
        (
            f"Selection: {plan.selected_count} selected, {plan.skipped_count} skipped "
            f"from {plan.discovered_count} discovered"
        ),
        markup=False,
    )
    console.print(f"Environment: {plan.environment}", markup=False)
    if plan.tag_filters:
        console.print(f"Tags: {', '.join(plan.tag_filters)}", markup=False)
    if plan.tag_expression is not None:
        console.print(f"Tag expression: {plan.tag_expression}", markup=False)
    if plan.operation_ids:
        console.print(f"Operation IDs: {', '.join(plan.operation_ids)}", markup=False)
    if plan.changed_from is not None:
        console.print(f"Changed from: {plan.changed_from}", markup=False)
    console.print(
        (
            f"Execution: workers={plan.worker_count}, timeout_ms={plan.timeout_ms}, "
            f"retry={plan.retry}, parallel={'yes' if plan.parallel else 'no'}, "
            f"fail_fast={'yes' if plan.fail_fast else 'no'}"
        ),
        markup=False,
    )
    console.print(
        (
            f"Gates: {len(plan.effective_rule_ids)} effective, "
            f"{sum(len(test.injected_rule_ids) for test in plan.tests)} injected"
        ),
        markup=False,
    )
    if plan.injected_rule_ids:
        console.print(f"Injected rules: {', '.join(plan.injected_rule_ids)}", markup=False)
    missing_count = sum(len(item.paths) for item in plan.missing_variables)
    console.print(
        f"Variables: {plan.provided_variable_count} provided, {missing_count} missing",
        markup=False,
    )
    for item in plan.missing_variables:
        console.print(
            f"Missing variable {item.name}: {', '.join(item.paths)}",
            style="yellow",
            markup=False,
        )
    if plan.report_formats:
        console.print(f"Requested reports: {', '.join(plan.report_formats)}", markup=False)
    for path in plan.would_write_reports:
        console.print(f"Would write report: {path}", markup=False)
    if plan.tests:
        console.print("Selected tests:")
    for test in plan.tests:
        tags = f" tags={','.join(test.tags)}" if test.tags else ""
        rules = f" gates={','.join(test.injected_rule_ids)}" if test.injected_rule_ids else ""
        console.print(f"- {test.path}{tags}{rules}", markup=False)
