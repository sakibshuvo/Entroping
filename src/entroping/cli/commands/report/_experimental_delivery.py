"""Experimental delivery surface report commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    EvidenceActionPlanError,
    EvidenceActionPlanOutput,
    EvidenceCloudDashboardError,
    EvidenceCloudDashboardOutput,
    EvidenceCloudExportError,
    EvidenceCloudExportOutput,
    EvidenceCloudReadinessError,
    EvidenceCloudReadinessOutput,
    EvidenceCloudWorkspaceError,
    EvidenceCloudWorkspaceOutput,
    EvidenceLinksError,
    EvidenceLinksOutput,
    EvidencePortalError,
    EvidencePortalOutput,
    NotificationOutput,
    NotificationPacketError,
    PrEvidenceCardError,
    PrEvidenceCardOutput,
    TeamEvidenceReadinessError,
    TeamEvidenceReadinessOutput,
    report_dependency,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_evidence_cloud_dashboard_report = report_dependency("run_evidence_cloud_dashboard_report")
run_evidence_cloud_export_report = report_dependency("run_evidence_cloud_export_report")
run_evidence_cloud_readiness_report = report_dependency("run_evidence_cloud_readiness_report")
run_evidence_cloud_workspace_report = report_dependency("run_evidence_cloud_workspace_report")
run_evidence_links_report = report_dependency("run_evidence_links_report")
run_evidence_portal_report = report_dependency("run_evidence_portal_report")
run_evidence_action_plan_report = report_dependency("run_evidence_action_plan_report")
run_handoff_report = report_dependency("run_handoff_report")
run_notification_packet_report = report_dependency("run_notification_packet_report")
run_pr_evidence_card_report = report_dependency("run_pr_evidence_card_report")
run_team_evidence_readiness_report = report_dependency("run_team_evidence_readiness_report")


@app.command("notification-packet", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_notification_packet(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local notification packet for work-management and chat surfaces."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported notification-packet output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_notification_packet_report(
            project_root=Path.cwd(),
            output=cast(NotificationOutput, normalized_output),
        )
    except NotificationPacketError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote notification packet: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("team-evidence-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_team_evidence_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local team evidence cloud readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported team-evidence-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_team_evidence_readiness_report(
            project_root=Path.cwd(),
            output=cast(TeamEvidenceReadinessOutput, normalized_output),
        )
    except TeamEvidenceReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote team evidence readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-cloud-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_cloud_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local Evidence Cloud readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-cloud-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_cloud_readiness_report(
            project_root=Path.cwd(),
            output=cast(EvidenceCloudReadinessOutput, normalized_output),
        )
    except EvidenceCloudReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote Evidence Cloud readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-cloud-export", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_cloud_export(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local Evidence Cloud export manifest."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-cloud-export output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_cloud_export_report(
            project_root=Path.cwd(),
            output=cast(EvidenceCloudExportOutput, normalized_output),
        )
    except EvidenceCloudExportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote Evidence Cloud export: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-cloud-workspace", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_cloud_workspace(
    manifest: Annotated[
        list[Path],
        typer.Option(
            "--manifest",
            help="Evidence Cloud export JSON manifest path; repeatable.",
        ),
    ],
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local Evidence Cloud workspace dashboard packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-cloud-workspace output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_cloud_workspace_report(
            project_root=Path.cwd(),
            manifests=tuple(manifest),
            output=cast(EvidenceCloudWorkspaceOutput, normalized_output),
        )
    except EvidenceCloudWorkspaceError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote Evidence Cloud workspace: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-cloud-dashboard", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_cloud_dashboard(
    manifest: Annotated[
        list[Path],
        typer.Option(
            "--manifest",
            help="Evidence Cloud export JSON manifest path; repeatable.",
        ),
    ],
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: html or json."),
    ] = "html",
) -> None:
    """Write a static local Evidence Cloud workspace dashboard."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"html", "json"}:
        console.print(f"[yellow]Unsupported evidence-cloud-dashboard output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_cloud_dashboard_report(
            project_root=Path.cwd(),
            manifests=tuple(manifest),
            output=cast(EvidenceCloudDashboardOutput, normalized_output),
        )
    except EvidenceCloudDashboardError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote Evidence Cloud dashboard: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-links", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_links(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local cross-surface evidence links packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-links output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_links_report(
            project_root=Path.cwd(),
            output=cast(EvidenceLinksOutput, normalized_output),
        )
    except EvidenceLinksError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote evidence links: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-portal", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_portal(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: html or json."),
    ] = "html",
) -> None:
    """Write a static local evidence portal dashboard."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"html", "json"}:
        console.print(f"[yellow]Unsupported evidence-portal output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_portal_report(
            project_root=Path.cwd(),
            output=cast(EvidencePortalOutput, normalized_output),
        )
    except EvidencePortalError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote evidence portal: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("pr-evidence-card", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_pr_evidence_card(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local PR evidence review card."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported pr-evidence-card output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_pr_evidence_card_report(
            project_root=Path.cwd(),
            output=cast(PrEvidenceCardOutput, normalized_output),
        )
    except PrEvidenceCardError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote PR evidence card: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-action-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_action_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local evidence action plan."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-action-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_action_plan_report(
            project_root=Path.cwd(),
            output=cast(EvidenceActionPlanOutput, normalized_output),
        )
    except EvidenceActionPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote evidence action plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)
