"""Experimental report commands for bundle and pilot artifacts."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    DesignPartnerFeedbackError,
    EvidenceBundleError,
    HandoffError,
    HandoffOutput,
    PilotCohortError,
    PilotCohortOutput,
    PilotMetricsError,
    PilotMetricsOutput,
    PilotOutcomeError,
    PilotOutcomeOutput,
    report_dependency,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_design_partner_feedback_report = report_dependency("run_design_partner_feedback_report")
run_evidence_bundle_report = report_dependency("run_evidence_bundle_report")
run_handoff_report = report_dependency("run_handoff_report")
run_pilot_cohort_report = report_dependency("run_pilot_cohort_report")
run_pilot_metrics_report = report_dependency("run_pilot_metrics_report")
run_pilot_outcome_report = report_dependency("run_pilot_outcome_report")


@app.command("evidence-bundle", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_bundle(
    output: Annotated[
        Path,
        typer.Option("--output", help="Evidence bundle output path."),
    ] = Path("reports") / "evidence-bundle.json",
) -> None:
    """Write a sanitized design-partner upload-readiness evidence bundle."""

    try:
        result = run_evidence_bundle_report(
            project_root=Path.cwd(),
            output_path=output,
        )
    except EvidenceBundleError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote evidence bundle: "
        f"{display_cli_path(result.output_path)} "
        f"({result.bundle.summary.status}, "
        f"{result.bundle.summary.required_present}/"
        f"{result.bundle.summary.required_total} required present, "
        f"{result.bundle.summary.required_invalid} invalid)"
    )
    raise typer.Exit(0 if result.bundle.summary.status == "ready" else 1)


@app.command("design-partner-feedback", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_design_partner_feedback(
    output: Annotated[
        Path,
        typer.Option("--output", help="Design-partner feedback artifact output path."),
    ] = Path("reports") / "design-partner-feedback.json",
) -> None:
    """Write a sanitized local design-partner feedback template artifact."""

    try:
        result = run_design_partner_feedback_report(
            project_root=Path.cwd(),
            output_path=output,
        )
    except DesignPartnerFeedbackError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote design-partner feedback artifact: "
        f"{display_cli_path(result.output_path)} "
        f"(evidence bundle {result.feedback.evidence.evidence_bundle_status}, "
        f"runtime card {result.feedback.evidence.runtime_card_status})"
    )
    raise typer.Exit(0)


@app.command("pilot-metrics", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_pilot_metrics(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write local pilot metrics inferred from sanitized report artifacts."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported pilot metrics output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_pilot_metrics_report(
            project_root=Path.cwd(),
            output=cast(PilotMetricsOutput, normalized_output),
        )
    except PilotMetricsError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote pilot metrics report: "
        f"{display_cli_path(result.output_path)} "
        f"({result.report.summary.status}, "
        f"{result.report.summary.metrics_known}/"
        f"{result.report.summary.metrics_total} known)"
    )
    raise typer.Exit(0)


@app.command("pilot-outcome", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_pilot_outcome(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local design-partner pilot outcome packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported pilot-outcome output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_pilot_outcome_report(
            project_root=Path.cwd(),
            output=cast(PilotOutcomeOutput, normalized_output),
        )
    except PilotOutcomeError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote pilot outcome packet: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("pilot-cohort", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_pilot_cohort(
    manifest: Annotated[
        Path,
        typer.Option(
            "--manifest",
            help="Pilot cohort manifest JSON path.",
        ),
    ],
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local design-partner pilot cohort rollup."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported pilot-cohort output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_pilot_cohort_report(
            project_root=Path.cwd(),
            manifest=manifest,
            output=cast(PilotCohortOutput, normalized_output),
        )
    except PilotCohortError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote pilot cohort packet: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("handoff", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_handoff(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    fail_on_insufficient: Annotated[
        bool,
        typer.Option(
            "--fail-on-insufficient",
            help="Exit 1 after writing when no source evidence artifacts are present.",
        ),
    ] = False,
) -> None:
    """Write a local cross-surface evidence handoff packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported handoff output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_handoff_report(
            project_root=Path.cwd(),
            output=cast(HandoffOutput, normalized_output),
        )
    except HandoffError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote evidence handoff packet: {display_cli_path(result.output_path)}")
    if fail_on_insufficient and result.packet.summary.status == "insufficient":
        console.print("[yellow]Handoff packet has no present evidence artifacts.[/yellow]")
        raise typer.Exit(1)
    raise typer.Exit(0)
