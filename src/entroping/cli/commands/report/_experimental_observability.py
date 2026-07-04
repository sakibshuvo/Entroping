"""Experimental observability and API readiness report commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    ApiInventoryError,
    ApiInventoryOutput,
    EvidenceIndexError,
    EvidenceIndexOutput,
    MutationReadinessError,
    MutationReadinessOutput,
    ObservabilityAdapterReadinessError,
    ObservabilityAdapterReadinessOutput,
    ObservabilityOutput,
    ObservabilityPacketError,
    OtelMappingError,
    OtelMappingOutput,
    report_dependency,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_api_inventory_report = report_dependency("run_api_inventory_report")
run_evidence_index_report = report_dependency("run_evidence_index_report")
run_mutation_readiness_report = report_dependency("run_mutation_readiness_report")
run_observability_adapter_readiness_report = report_dependency(
    "run_observability_adapter_readiness_report"
)
run_observability_packet_report = report_dependency("run_observability_packet_report")
run_otel_mapping_report = report_dependency("run_otel_mapping_report")


@app.command("observability-packet", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_observability_packet(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local observability packet for telemetry and dashboard surfaces."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported observability-packet output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_observability_packet_report(
            project_root=Path.cwd(),
            output=cast(ObservabilityOutput, normalized_output),
        )
    except ObservabilityPacketError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote observability packet: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("otel-mapping", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_otel_mapping(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local OpenTelemetry evidence mapping packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported otel-mapping output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_otel_mapping_report(
            project_root=Path.cwd(),
            output=cast(OtelMappingOutput, normalized_output),
        )
    except OtelMappingError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote OpenTelemetry mapping packet: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("observability-adapter-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_observability_adapter_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local observability adapter readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(
            f"[yellow]Unsupported observability-adapter-readiness output: {output}[/yellow]"
        )
        raise typer.Exit(2)

    try:
        result = run_observability_adapter_readiness_report(
            project_root=Path.cwd(),
            output=cast(ObservabilityAdapterReadinessOutput, normalized_output),
        )
    except ObservabilityAdapterReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        f"Wrote observability adapter readiness: {display_cli_path(result.output_path)}"
    )
    raise typer.Exit(0)


@app.command("api-inventory", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_api_inventory(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local API surface inventory packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported api-inventory output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_api_inventory_report(
            project_root=Path.cwd(),
            output=cast(ApiInventoryOutput, normalized_output),
        )
    except ApiInventoryError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote API inventory: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("mutation-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_mutation_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local mutation and fuzz readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported mutation-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_mutation_readiness_report(
            project_root=Path.cwd(),
            output=cast(MutationReadinessOutput, normalized_output),
        )
    except MutationReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote mutation readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("evidence-index", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_evidence_index(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local evidence artifact index packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported evidence-index output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_evidence_index_report(
            project_root=Path.cwd(),
            output=cast(EvidenceIndexOutput, normalized_output),
        )
    except EvidenceIndexError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote evidence index: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)
