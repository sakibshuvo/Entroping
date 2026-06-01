"""Report command adapter."""

import sys
from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.bridge.story_traceability import (
    compile_story_traceability,
    render_story_traceability_markdown,
)
from entroping.cli.shared import console, display_cli_path, print_cli_error
from entroping.core.effective_policy_report import (
    EffectivePolicyOutput,
    EffectivePolicyReportError,
    run_effective_policy_report,
)
from entroping.core.github_annotations import (
    GitHubAnnotation,
    GitHubAnnotationError,
    collect_github_annotations,
    render_github_annotation,
)
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.redaction_review_report import (
    RedactionReviewError,
    RedactionReviewOutput,
    run_redaction_review,
)
from entroping.core.report_writer import (
    ReportWriterError,
    load_run_report,
    write_bug_report,
)
from entroping.models.hurl import HurlMetadataSyntaxError

app = typer.Typer(help="Generate human handoff artifacts.")


@app.command("bug")
def report_bug() -> None:
    """Generate a Markdown bug report from the latest failure."""

    latest_state = Path(".entroping") / "latest-run.json"
    if not latest_state.exists():
        console.print("[yellow]No latest run found. Run entroping run before report bug.[/yellow]")
        raise typer.Exit(1)

    report = load_run_report(latest_state)
    if report.summary.failed == 0:
        console.print("[yellow]Latest Entroping run has no failures to report.[/yellow]")
        raise typer.Exit(1)

    try:
        output_path = write_bug_report(report, Path("reports") / "bug.md")
    except ReportWriterError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"Wrote bug report: {display_cli_path(output_path)}")


@app.command("redaction")
def report_redaction(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or html."),
    ] = "md",
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


@app.command("policy")
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


@app.command("github-annotations")
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


@app.command("traceability")
def report_traceability(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format. Currently: md."),
    ] = "md",
) -> None:
    """Generate a local Markdown story traceability report."""

    normalized_output = output.strip().lower()
    if normalized_output != "md":
        console.print(f"[yellow]Unsupported traceability output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        report = compile_story_traceability(hurl_tests)
    except (FileNotFoundError, HurlMetadataSyntaxError, ValueError) as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    sys.stdout.write(render_story_traceability_markdown(report))
    raise typer.Exit(0 if report.passed else 1)
