"""Stable public report commands.

Core and bridge functions are resolved through the parent package via
``__getattr__`` so that test monkeypatching remains effective.
"""

import json
import sys
from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._helpers import _format_percent, _gate_coverage_percent
from ._panels import STABLE_REPORT_PANEL


@app.command("delta", rich_help_panel=STABLE_REPORT_PANEL)
def report_delta(
    base: Annotated[
        Path,
        typer.Option("--base", help="Baseline JSON run report path."),
    ] = Path("reports") / "run-base.json",
    current: Annotated[
        Path,
        typer.Option("--current", help="Current JSON run report path."),
    ] = Path("reports") / "run-latest.json",
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Compare two local run JSON reports without executing Hurl."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported delta output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        report = build_run_delta_report(
            base=load_run_report(base),
            current=load_run_report(current),
        )
    except (OSError, KeyError, TypeError, ValueError, RunDeltaError) as exc:
        print_cli_error(RuntimeError(f"Could not compare run reports: {exc}"))
        raise typer.Exit(1) from exc

    if normalized_output == "json":
        sys.stdout.write(json.dumps(run_delta_report_to_dict(report), indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_run_delta_markdown(report))
    raise typer.Exit(0 if report.passed else 1)


@app.command("policy-diff", rich_help_panel=STABLE_REPORT_PANEL)
def report_policy_diff(
    base: Annotated[
        Path,
        typer.Option("--base", help="Baseline effective policy JSON report path."),
    ] = Path("reports") / "base-effective-policy.json",
    current: Annotated[
        Path,
        typer.Option("--current", help="Current effective policy JSON report path."),
    ] = Path("reports") / "effective-policy.json",
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    fail_on_change: Annotated[
        bool,
        typer.Option(
            "--fail-on-change",
            help="Exit 1 when the effective policy diff status is changed.",
        ),
    ] = False,
) -> None:
    """Compare two local effective policy JSON reports without loading policy files."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported policy-diff output: {output}[/yellow]")
        raise typer.Exit(2)
    policy_diff_output = cast(EffectivePolicyDiffOutput, normalized_output)

    try:
        report = build_effective_policy_diff_report(
            base=load_effective_policy_report(base),
            current=load_effective_policy_report(current),
            base_path=base,
            current_path=current,
        )
    except (EffectivePolicyDiffError, EffectivePolicyDiffReportError) as exc:
        print_cli_error(RuntimeError(f"Could not compare effective policy reports: {exc}"))
        raise typer.Exit(1) from exc

    if policy_diff_output == "json":
        sys.stdout.write(
            json.dumps(
                effective_policy_diff_report_to_dict(report),
                indent=2,
                sort_keys=True,
            )
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_effective_policy_diff_markdown(report))
    raise typer.Exit(1 if fail_on_change and report.changed else 0)


@app.command("redaction", rich_help_panel=STABLE_REPORT_PANEL)
def report_redaction(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or html."),
    ] = "md",
    fail_on_unsafe: Annotated[
        bool,
        typer.Option(
            "--fail-on-unsafe",
            help=("Write the report, then exit 1 when unredacted or low-confidence records exist."),
        ),
    ] = False,
) -> None:
    """Generate a safe counts-only redaction review report from captured traffic."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "html"}:
        console.print(f"[yellow]Unsupported redaction output: {output}[/yellow]")
        raise typer.Exit(2)
    redaction_output = cast(RedactionReviewOutput, normalized_output)

    try:
        result = run_redaction_review(
            project_root=Path.cwd(),
            output=redaction_output,
        )
    except RedactionReviewError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "record" if result.report.total_records == 1 else "records"
    console.print(
        f"[green]Reviewed redaction coverage for {result.report.total_records} traffic "
        f"{noun}.[/green]"
    )
    console.print(f"Wrote redaction review: {display_cli_path(result.output_path)}")
    unsafe_unredacted = result.report.unredacted_records
    unsafe_low_confidence = result.report.low_confidence_records
    if fail_on_unsafe and (unsafe_unredacted > 0 or unsafe_low_confidence > 0):
        console.print(
            "[yellow]Redaction review found unsafe records: "
            f"unredacted={unsafe_unredacted}, "
            f"low_confidence={unsafe_low_confidence}.[/yellow]"
        )
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("capture-summary", rich_help_panel=STABLE_REPORT_PANEL)
def report_capture_summary(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    fail_on_unredacted: Annotated[
        bool,
        typer.Option(
            "--fail-on-unredacted",
            help=(
                "Write the report, then exit 1 when the capture summary contains "
                "unredacted records."
            ),
        ),
    ] = False,
) -> None:
    """Generate a safe counts-only summary from captured traffic."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported capture-summary output: {output}[/yellow]")
        raise typer.Exit(2)
    capture_output = cast(CaptureSummaryOutput, normalized_output)

    try:
        result = run_capture_summary_report(
            project_root=Path.cwd(),
            output=capture_output,
        )
    except CaptureSummaryError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "record" if result.report.summary.total_records == 1 else "records"
    console.print(
        f"[green]Summarized {result.report.summary.total_records} traffic "
        f"{noun} across {result.report.summary.total_sessions} sessions.[/green]"
    )
    console.print(f"Wrote capture summary: {display_cli_path(result.output_path)}")
    unredacted_records = result.report.summary.unredacted_records
    if fail_on_unredacted and unredacted_records > 0:
        record_noun = "record" if unredacted_records == 1 else "records"
        console.print(
            "[yellow]Capture summary found "
            f"{unredacted_records} unredacted traffic {record_noun}.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("policy", rich_help_panel=STABLE_REPORT_PANEL)
def report_policy(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Generate local evidence for the resolved QAnstitution policy."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported policy output: {output}[/yellow]")
        raise typer.Exit(2)
    policy_output = cast(EffectivePolicyOutput, normalized_output)

    try:
        result = run_effective_policy_report(project_root=Path.cwd(), output=policy_output)
    except EffectivePolicyReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "gate" if len(result.report.gates) == 1 else "gates"
    console.print(
        f"[green]Resolved effective policy with {len(result.report.gates)} {noun}.[/green]"
    )
    console.print(f"Wrote effective policy report: {display_cli_path(result.output_path)}")


@app.command("gate-coverage", rich_help_panel=STABLE_REPORT_PANEL)
def report_gate_coverage(
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
            help=("Exit 1 when matched policy-gate coverage is below this 0-100 threshold."),
        ),
    ] = None,
) -> None:
    """Map effective QAnstitution gates to matching committed Hurl tests."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported gate-coverage output: {output}[/yellow]")
        raise typer.Exit(2)
    gate_output = cast(GateCoverageOutput, normalized_output)

    try:
        result = run_gate_coverage_report(project_root=Path.cwd(), output=gate_output)
    except GateCoverageReportError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "gate" if result.report.summary.total_gates == 1 else "gates"
    console.print(f"[green]Mapped coverage for {result.report.summary.total_gates} {noun}.[/green]")
    console.print(f"Wrote gate coverage report: {display_cli_path(result.output_path)}")
    coverage_percent = _gate_coverage_percent(
        matched_gates=result.report.summary.matched_gates,
        total_gates=result.report.summary.total_gates,
    )
    if fail_under is not None and coverage_percent < fail_under:
        console.print(
            "[yellow]Policy gate coverage "
            f"{_format_percent(coverage_percent)} is below required threshold "
            f"{fail_under}.[/yellow]"
        )
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("github-annotations", rich_help_panel=STABLE_REPORT_PANEL)
def report_github_annotations(
    junit: Annotated[
        Path,
        typer.Option("--junit", help="JUnit XML report path."),
    ] = Path("reports") / "junit.xml",
    drift: Annotated[
        Path,
        typer.Option("--drift", help="Drift JSON report path."),
    ] = Path("reports") / "drift.json",
    traceability: Annotated[
        bool,
        typer.Option("--traceability", help="Annotate local story traceability findings."),
    ] = False,
    max_annotations: Annotated[
        int,
        typer.Option("--max-annotations", min=0, help="Maximum annotations to emit."),
    ] = 50,
) -> None:
    """Emit GitHub Actions workflow-command annotations from local reports."""

    try:
        annotations = collect_github_annotations(
            junit_path=junit,
            drift_path=drift,
            include_traceability=traceability,
        )
    except (GitHubAnnotationError, HurlMetadataSyntaxError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    for annotation in annotations[:max_annotations]:
        sys.stdout.write(render_github_annotation(annotation) + "\n")
    if len(annotations) > max_annotations:
        omitted = len(annotations) - max_annotations
        sys.stdout.write(
            render_github_annotation(
                GitHubAnnotation(
                    level="notice",
                    title="Entroping annotations truncated",
                    message=f"{omitted} annotation(s) omitted by --max-annotations.",
                )
            )
            + "\n"
        )
    raise typer.Exit(0)


@app.command("sarif", rich_help_panel=STABLE_REPORT_PANEL)
def report_sarif(
    output: Annotated[
        Path,
        typer.Option("--output", help="SARIF output path."),
    ] = Path("reports") / "entroping.sarif",
    junit: Annotated[
        Path,
        typer.Option("--junit", help="JUnit XML report path."),
    ] = Path("reports") / "junit.xml",
    drift: Annotated[
        Path,
        typer.Option("--drift", help="Drift JSON report path."),
    ] = Path("reports") / "drift.json",
    traceability: Annotated[
        bool,
        typer.Option("--traceability", help="Include local story traceability findings."),
    ] = False,
) -> None:
    """Write a SARIF report from local Entroping findings."""

    try:
        result = run_sarif_report(
            project_root=Path.cwd(),
            output_path=output,
            junit_path=junit,
            drift_path=drift,
            include_traceability=traceability,
        )
    except (GitHubAnnotationError, HurlMetadataSyntaxError, SarifReportError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote SARIF report: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("traceability", rich_help_panel=STABLE_REPORT_PANEL)
def report_traceability(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Generate a local story traceability report."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported traceability output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        story_documents = discover_story_documents(project_root=Path.cwd())
        report = compile_story_traceability(
            hurl_tests,
            story_documents=story_documents.documents,
            story_findings=story_documents.findings,
            story_document_scope_present=story_documents.scope_present,
        )
    except (FileNotFoundError, HurlMetadataSyntaxError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    if normalized_output == "json":
        sys.stdout.write(json.dumps(story_traceability_report_to_dict(report), indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_story_traceability_markdown(report))
    raise typer.Exit(0 if report.passed else 1)
