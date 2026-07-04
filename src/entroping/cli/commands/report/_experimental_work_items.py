"""Experimental work-item and integration readiness report commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    ConnectorIntentError,
    ConnectorIntentOutput,
    DevexReadinessError,
    DevexReadinessOutput,
    ExternalTestEvidenceError,
    ExternalTestEvidenceOutput,
    IntegrationReadinessError,
    IntegrationReadinessOutput,
    TeamAccessControlPlanError,
    TeamAccessControlPlanOutput,
    WorkItemDraftError,
    WorkItemDraftOutput,
    WorkItemImportBundleError,
    WorkItemImportBundleOutput,
    report_dependency,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_connector_intent_report = report_dependency("run_connector_intent_report")
run_devex_readiness_report = report_dependency("run_devex_readiness_report")
run_external_test_evidence_report = report_dependency("run_external_test_evidence_report")
run_integration_readiness_report = report_dependency("run_integration_readiness_report")
run_team_access_control_plan_report = report_dependency("run_team_access_control_plan_report")
run_work_item_draft_report = report_dependency("run_work_item_draft_report")
run_work_item_import_bundle_report = report_dependency("run_work_item_import_bundle_report")


@app.command("work-item-draft", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_work_item_draft(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write local tracker work item draft rows."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported work-item-draft output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_work_item_draft_report(
            project_root=Path.cwd(),
            output=cast(WorkItemDraftOutput, normalized_output),
        )
    except WorkItemDraftError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote work item draft: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("work-item-import-bundle", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_work_item_import_bundle(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: json or csv."),
    ] = "json",
) -> None:
    """Write local tracker import bundle rows."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"json", "csv"}:
        console.print(
            f"[yellow]Unsupported work-item-import-bundle output: {output}[/yellow]"
        )
        raise typer.Exit(2)

    try:
        result = run_work_item_import_bundle_report(
            project_root=Path.cwd(),
            output=cast(WorkItemImportBundleOutput, normalized_output),
        )
    except WorkItemImportBundleError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote work item import bundle: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("team-access-control-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_team_access_control_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local team access-control and audit planning packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported team-access-control-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_team_access_control_plan_report(
            project_root=Path.cwd(),
            output=cast(TeamAccessControlPlanOutput, normalized_output),
        )
    except TeamAccessControlPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote team access-control plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("integration-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_integration_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local integration-readiness packet for team surfaces."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported integration-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_integration_readiness_report(
            project_root=Path.cwd(),
            output=cast(IntegrationReadinessOutput, normalized_output),
        )
    except IntegrationReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote integration readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("devex-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_devex_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local developer-experience readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported devex-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_devex_readiness_report(
            project_root=Path.cwd(),
            output=cast(DevexReadinessOutput, normalized_output),
        )
    except DevexReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote developer experience readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("connector-intent", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_connector_intent(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local connector intent packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported connector-intent output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_connector_intent_report(
            project_root=Path.cwd(),
            output=cast(ConnectorIntentOutput, normalized_output),
        )
    except ConnectorIntentError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote connector intent: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("external-test-evidence", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_external_test_evidence(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local external test evidence packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported external-test-evidence output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_external_test_evidence_report(
            project_root=Path.cwd(),
            output=cast(ExternalTestEvidenceOutput, normalized_output),
        )
    except ExternalTestEvidenceError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote external test evidence: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)
