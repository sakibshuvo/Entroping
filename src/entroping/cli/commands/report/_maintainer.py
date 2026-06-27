"""Maintainer and baseline tool report commands.

Core and bridge functions are resolved through the parent package via
``__getattr__`` so that test monkeypatching remains effective.
"""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._helpers import _format_percent
from ._panels import MAINTAINER_REPORT_PANEL


@app.command("badges", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_badges(
    output: Annotated[
        Path,
        typer.Option("--output", help="Coverage badge output directory."),
    ] = Path("reports") / "badges",
    run_json: Annotated[
        Path,
        typer.Option("--run-json", help="JSON run report path."),
    ] = Path("reports") / "run-latest.json",
    policy_json: Annotated[
        Path,
        typer.Option("--policy-json", help="Effective policy JSON report path."),
    ] = Path("reports") / "effective-policy.json",
    openapi_json: Annotated[
        Path,
        typer.Option("--openapi-json", help="OpenAPI audit JSON report path."),
    ] = Path("reports") / "openapi-audit.json",
    traceability_json: Annotated[
        Path,
        typer.Option("--traceability-json", help="Traceability JSON report path."),
    ] = Path("reports") / "traceability.json",
) -> None:
    """Write local shields-compatible coverage badge JSON files."""

    try:
        result = write_coverage_badges(
            run_json_path=run_json,
            policy_json_path=policy_json,
            openapi_json_path=openapi_json,
            traceability_json_path=traceability_json,
            output_dir=output,
            project_root=Path.cwd(),
        )
    except BadgeReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    for artifact in result.artifacts:
        console.print(f"Wrote coverage badge: {display_cli_path(artifact)}")
    raise typer.Exit(0)


@app.command("gate-injection", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_gate_injection(
    target: Annotated[
        list[Path],
        typer.Option("--target", help="Selected .hurl file to explain; repeatable."),
    ],
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Explain effective QAnstitution gates for selected Hurl files."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported gate-injection output: {output}[/yellow]")
        raise typer.Exit(2)
    gate_output = cast(GateInjectionOutput, normalized_output)

    try:
        result = run_gate_injection_report(
            project_root=Path.cwd(),
            targets=tuple(target),
            output=gate_output,
        )
    except GateInjectionReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "target" if result.report.summary.total_targets == 1 else "targets"
    console.print(
        f"[green]Explained gate injection for {result.report.summary.total_targets} {noun}.[/green]"
    )
    console.print(f"Wrote gate injection report: {display_cli_path(result.output_path)}")


@app.command("test-quality", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_test_quality(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    fail_under: Annotated[
        int | None,
        typer.Option(
            "--fail-under",
            min=0,
            max=100,
            help=("Exit 1 when the generated-test quality score is below this 0-100 threshold."),
        ),
    ] = None,
) -> None:
    """Write a static quality score for generated Hurl tests."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported test-quality output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_test_quality_report(
            project_root=Path.cwd(),
            output=cast(TestQualityOutput, normalized_output),
        )
    except TestQualityReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote generated-test quality report: "
        f"{display_cli_path(result.output_path)} "
        f"({result.report.summary.status}, score {result.report.summary.score}, "
        f"{result.report.summary.generated_tests} generated)"
    )
    if fail_under is not None and result.report.summary.score < fail_under:
        console.print(
            "[yellow]Generated-test quality score "
            f"{result.report.summary.score} is below required threshold "
            f"{fail_under}.[/yellow]"
        )
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("test-pyramid", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_test_pyramid(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local test-pyramid evidence summary."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported test-pyramid output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_test_pyramid_report(
            project_root=Path.cwd(),
            output=cast(TestPyramidOutput, normalized_output),
        )
    except TestPyramidReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote test pyramid report: "
        f"{display_cli_path(result.output_path)} "
        f"({result.report.summary.runtime_governance_status}, "
        f"{result.report.summary.present_layers}/"
        f"{result.report.summary.total_layers} layers present)"
    )
    raise typer.Exit(0)


@app.command("artifact-manifest", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_artifact_manifest(
    output: Annotated[
        Path,
        typer.Option("--output", help="Artifact manifest output path."),
    ] = Path("reports") / "artifact-manifest.json",
    fail_on_incomplete: Annotated[
        bool,
        typer.Option(
            "--fail-on-incomplete",
            help=(
                "Write the manifest, then exit 1 when artifacts are missing or "
                "audit verification is broken."
            ),
        ),
    ] = False,
) -> None:
    """Write checksum evidence for local report artifacts."""

    try:
        result = write_report_artifact_manifest(
            project_root=Path.cwd(),
            output_path=output,
        )
    except ReportArtifactManifestError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(
        "Wrote artifact manifest: "
        f"{display_cli_path(result.output_path)} "
        f"({result.manifest.summary.total_present} present, "
        f"{result.manifest.summary.total_missing} missing, "
        f"audit {result.manifest.audit.verification.status})"
    )
    missing_count = result.manifest.summary.total_missing
    audit_status = result.manifest.audit.verification.status
    if fail_on_incomplete and (missing_count > 0 or audit_status != "verified"):
        console.print(
            "[yellow]Artifact manifest incomplete: "
            f"missing={missing_count}, audit={audit_status}.[/yellow]"
        )
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("promote-drift-baseline", rich_help_panel=MAINTAINER_REPORT_PANEL)
def report_promote_drift_baseline(
    candidate: Annotated[
        Path,
        typer.Option("--candidate", help="Reviewed drift baseline candidate path."),
    ] = Path("reports") / "drift-baseline.candidate.json",
    output: Annotated[
        Path,
        typer.Option("--output", help="Active drift baseline output path."),
    ] = Path(".entroping") / "drift-baseline.json",
) -> None:
    """Promote a reviewed drift baseline candidate into active local state."""

    try:
        result = promote_reviewed_drift_baseline_candidate(
            project_root=Path.cwd(),
            candidate_path=candidate,
            output_path=output,
        )
    except DriftReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "test" if result.test_count == 1 else "tests"
    console.print(
        f"Promoted drift baseline: {display_cli_path(result.output_path)} "
        f"({result.test_count} {noun})"
    )
    raise typer.Exit(0)
