"""Report command adapter."""

import json
import sys
from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.bridge.effective_policy_diff import (
    EffectivePolicyDiffError,
    build_effective_policy_diff_report,
    effective_policy_diff_report_to_dict,
    render_effective_policy_diff_markdown,
)
from entroping.bridge.story_traceability import (
    compile_story_traceability,
    render_story_traceability_markdown,
    story_traceability_report_to_dict,
)
from entroping.cli.shared import console, display_cli_path, print_cli_error
from entroping.core.agent_bundle import (
    AGENT_BUNDLE_ROLES,
    AgentBundleError,
    AgentBundleOutput,
    run_agent_bundle_report,
)
from entroping.core.capture_summary_report import (
    CaptureSummaryError,
    CaptureSummaryOutput,
    run_capture_summary_report,
)
from entroping.core.coverage_badges import BadgeReportError, write_coverage_badges
from entroping.core.drift_report import (
    DriftReportError,
    promote_reviewed_drift_baseline_candidate,
)
from entroping.core.effective_policy_diff_report import (
    EffectivePolicyDiffOutput,
    EffectivePolicyDiffReportError,
    load_effective_policy_report,
)
from entroping.core.effective_policy_report import (
    EffectivePolicyOutput,
    EffectivePolicyReportError,
    run_effective_policy_report,
)
from entroping.core.evidence_bundle import (
    EvidenceBundleError,
    run_evidence_bundle_report,
)
from entroping.core.failure_bundle import FailureBundleError, create_failure_bundle
from entroping.core.gate_coverage_report import (
    GateCoverageOutput,
    GateCoverageReportError,
    run_gate_coverage_report,
)
from entroping.core.gate_injection_report import (
    GateInjectionOutput,
    GateInjectionReportError,
    run_gate_injection_report,
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
from entroping.core.report_artifact_manifest import (
    ReportArtifactManifestError,
    write_report_artifact_manifest,
)
from entroping.core.report_writer import (
    ReportWriterError,
    load_run_report,
    write_bug_report,
)
from entroping.core.review_summary import ReviewSummaryError, run_review_summary
from entroping.core.run_delta import (
    RunDeltaError,
    build_run_delta_report,
    render_run_delta_markdown,
    run_delta_report_to_dict,
)
from entroping.core.runtime_card import (
    RuntimeCardError,
    RuntimeCardOutput,
    run_runtime_card_report,
)
from entroping.core.sarif_report import SarifReportError, run_sarif_report
from entroping.core.story_documents import discover_story_documents
from entroping.core.test_quality_report import (
    TestQualityOutput,
    TestQualityReportError,
    run_test_quality_report,
)
from entroping.models.hurl import HurlMetadataSyntaxError

app = typer.Typer(help="Generate human handoff artifacts.")

CORE_REPORT_PANEL = "Core CI And Review"
ADVANCED_REPORT_PANEL = "Advanced Evidence"


@app.command("bug", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("delta", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("policy-diff", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("badges", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("failure-bundle", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("redaction", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("capture-summary", rich_help_panel=ADVANCED_REPORT_PANEL)
def report_capture_summary(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
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


@app.command("policy", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("gate-coverage", rich_help_panel=ADVANCED_REPORT_PANEL)
def report_gate_coverage(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
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
    console.print(
        f"[green]Mapped coverage for {result.report.summary.total_gates} "
        f"{noun}.[/green]"
    )
    console.print(f"Wrote gate coverage report: {display_cli_path(result.output_path)}")


@app.command("gate-injection", rich_help_panel=ADVANCED_REPORT_PANEL)
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
        f"[green]Explained gate injection for {result.report.summary.total_targets} "
        f"{noun}.[/green]"
    )
    console.print(f"Wrote gate injection report: {display_cli_path(result.output_path)}")


@app.command("test-quality", rich_help_panel=ADVANCED_REPORT_PANEL)
def report_test_quality(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
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
    raise typer.Exit(0)


@app.command("artifact-manifest", rich_help_panel=ADVANCED_REPORT_PANEL)
def report_artifact_manifest(
    output: Annotated[
        Path,
        typer.Option("--output", help="Artifact manifest output path."),
    ] = Path("reports") / "artifact-manifest.json",
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


@app.command("evidence-bundle", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("runtime-card", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("agent-bundle", rich_help_panel=ADVANCED_REPORT_PANEL)
def report_agent_bundle(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="Agent role to include; repeatable."),
    ] = None,
    scope: Annotated[
        Path,
        typer.Option("--scope", help="Project-relative output path scope."),
    ] = Path("."),
) -> None:
    """Write a local multi-agent review bundle from sanitized manifests."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported agent-bundle output: {output}[/yellow]")
        raise typer.Exit(2)
    selected_roles = tuple(role or ())
    unsupported_roles = sorted(
        selected_role
        for selected_role in selected_roles
        if selected_role not in AGENT_BUNDLE_ROLES
    )
    if unsupported_roles:
        joined = ", ".join(unsupported_roles)
        console.print(
            "[yellow]Unsupported agent-bundle role "
            f"{joined}; expected builder, breaker, or auditor.[/yellow]"
        )
        raise typer.Exit(2)

    try:
        result = run_agent_bundle_report(
            project_root=Path.cwd(),
            output=cast(AgentBundleOutput, normalized_output),
            roles=selected_roles,
            scope=scope,
        )
    except AgentBundleError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote agent review bundle: {display_cli_path(result.output_path)}")
    raise typer.Exit(0 if result.report.summary.status != "fail" else 1)


@app.command("github-annotations", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("sarif", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("promote-drift-baseline", rich_help_panel=ADVANCED_REPORT_PANEL)
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


@app.command("review-summary", rich_help_panel=CORE_REPORT_PANEL)
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


@app.command("traceability", rich_help_panel=ADVANCED_REPORT_PANEL)
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
