"""Launch-critical report commands."""

import json
from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    FailureBundleError,
    HurlMetadataSyntaxError,
    ReportWriterError,
    ReviewSummaryError,
    RuntimeCardError,
    RuntimeCardOutput,
    create_failure_bundle,
    load_run_report,
    report_dependency,
    run_review_summary,
)
from ._panels import LAUNCH_REPORT_PANEL

run_runtime_card_report = report_dependency("run_runtime_card_report")
write_bug_report = report_dependency("write_bug_report")
run_first_run_checklist = report_dependency("run_first_run_checklist")


@app.command("bug", rich_help_panel=LAUNCH_REPORT_PANEL)
def report_bug() -> None:
    """Generate a Markdown bug report from the latest failure."""

    latest_state = Path(".entroping") / "latest-run.json"
    if not latest_state.exists():
        console.print("[yellow]No latest run found. Run entroping run before report bug.[/yellow]")
        raise typer.Exit(1)

    try:
        report = load_run_report(latest_state)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print_cli_error(RuntimeError(f"Could not load latest run report: {exc}"))
        raise typer.Exit(1) from exc

    if report.summary.failed == 0:
        console.print("[yellow]Latest Entroping run has no failures to report.[/yellow]")
        raise typer.Exit(1)

    try:
        output_path = write_bug_report(report, Path("reports") / "bug.md")
    except ReportWriterError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"Wrote bug report: {display_cli_path(output_path)}")


@app.command("failure-bundle", rich_help_panel=LAUNCH_REPORT_PANEL)
def report_failure_bundle(
    output: Annotated[
        Path,
        typer.Option("--output", help="Failure bundle output directory."),
    ] = Path("reports") / "failure-bundle",
) -> None:
    """Generate a sanitized local failure bundle for issue tracker handoff."""

    try:
        result = create_failure_bundle(project_root=Path.cwd(), output_dir=output)
    except FailureBundleError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "artifact" if len(result.artifacts) == 1 else "artifacts"
    console.print(
        f"Wrote failure bundle: {display_cli_path(result.manifest_path)} "
        f"({len(result.artifacts)} {noun})"
    )


@app.command("first-run-checklist", rich_help_panel=LAUNCH_REPORT_PANEL)
def report_first_run_checklist() -> None:
    result = run_first_run_checklist(project_root=Path.cwd())
    for item in result.items:
        color = {
            "present": "green",
            "missing": "yellow",
            "optional-missing": "yellow",
            "error": "red",
        }[item.state]
        console.print(f"{item.label}: [{color}]{item.state}[/{color}]")
        for path in item.paths:
            console.print(f"  - path: {display_cli_path(path)}")
        for hint in item.hints:
            console.print(f"  - hint: {hint}")
    if result.has_errors:
        raise typer.Exit(1)


@app.command("runtime-card", rich_help_panel=LAUNCH_REPORT_PANEL)
def report_runtime_card(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a concise PR/runtime evidence card from sanitized local reports."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported runtime card output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_runtime_card_report(
            project_root=Path.cwd(),
            output=cast(RuntimeCardOutput, normalized_output),
        )
    except RuntimeCardError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote runtime evidence card: {display_cli_path(result.output_path)}")
    raise typer.Exit(0 if result.card.summary.status == "pass" else 1)


@app.command("review-summary", rich_help_panel=LAUNCH_REPORT_PANEL)
def report_review_summary(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format. Currently: md."),
    ] = "md",
    junit: Annotated[
        Path,
        typer.Option("--junit", help="JUnit XML report path."),
    ] = Path("reports") / "junit.xml",
    run_json: Annotated[
        Path,
        typer.Option("--run-json", help="JSON run report path."),
    ] = Path("reports") / "run-latest.json",
    drift: Annotated[
        Path,
        typer.Option("--drift", help="Drift JSON report path."),
    ] = Path("reports") / "drift.json",
    traceability: Annotated[
        bool,
        typer.Option("--traceability", help="Include local story traceability findings."),
    ] = False,
) -> None:
    """Write a provider-neutral Markdown review summary from local artifacts."""

    normalized_output = output.strip().lower()
    if normalized_output != "md":
        console.print(f"[yellow]Unsupported review summary output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_review_summary(
            project_root=Path.cwd(),
            run_json_path=run_json,
            junit_path=junit,
            drift_path=drift,
            include_traceability=traceability,
        )
    except (ReviewSummaryError, HurlMetadataSyntaxError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote review summary: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)
