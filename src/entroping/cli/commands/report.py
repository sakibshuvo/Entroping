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
from entroping.core.api_inventory import (
    ApiInventoryError,
    ApiInventoryOutput,
    run_api_inventory_report,
)
from entroping.core.capture_summary_report import (
    CaptureSummaryError,
    CaptureSummaryOutput,
    run_capture_summary_report,
)
from entroping.core.connector_intent import (
    ConnectorIntentError,
    ConnectorIntentOutput,
    run_connector_intent_report,
)
from entroping.core.coverage_badges import BadgeReportError, write_coverage_badges
from entroping.core.design_partner_feedback import (
    DesignPartnerFeedbackError,
    run_design_partner_feedback_report,
)
from entroping.core.devex_readiness import (
    DevexReadinessError,
    DevexReadinessOutput,
    run_devex_readiness_report,
)
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
from entroping.core.evidence_action_plan import (
    EvidenceActionPlanError,
    EvidenceActionPlanOutput,
    run_evidence_action_plan_report,
)
from entroping.core.evidence_bundle import (
    EvidenceBundleError,
    run_evidence_bundle_report,
)
from entroping.core.evidence_cloud_dashboard import (
    EvidenceCloudDashboardError,
    EvidenceCloudDashboardOutput,
    run_evidence_cloud_dashboard_report,
)
from entroping.core.evidence_cloud_export import (
    EvidenceCloudExportError,
    EvidenceCloudExportOutput,
    run_evidence_cloud_export_report,
)
from entroping.core.evidence_cloud_readiness import (
    EvidenceCloudReadinessError,
    EvidenceCloudReadinessOutput,
    run_evidence_cloud_readiness_report,
)
from entroping.core.evidence_cloud_workspace import (
    EvidenceCloudWorkspaceError,
    EvidenceCloudWorkspaceOutput,
    run_evidence_cloud_workspace_report,
)
from entroping.core.evidence_index_report import (
    EvidenceIndexError,
    EvidenceIndexOutput,
    run_evidence_index_report,
)
from entroping.core.evidence_links import (
    EvidenceLinksError,
    EvidenceLinksOutput,
    run_evidence_links_report,
)
from entroping.core.evidence_portal import (
    EvidencePortalError,
    EvidencePortalOutput,
    run_evidence_portal_report,
)
from entroping.core.external_test_evidence import (
    ExternalTestEvidenceError,
    ExternalTestEvidenceOutput,
    run_external_test_evidence_report,
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
from entroping.core.handoff_packet import (
    HandoffError,
    HandoffOutput,
    run_handoff_report,
)
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.integration_readiness import (
    IntegrationReadinessError,
    IntegrationReadinessOutput,
    run_integration_readiness_report,
)
from entroping.core.mutation_readiness import (
    MutationReadinessError,
    MutationReadinessOutput,
    run_mutation_readiness_report,
)
from entroping.core.notification_packet import (
    NotificationOutput,
    NotificationPacketError,
    run_notification_packet_report,
)
from entroping.core.observability_adapter_readiness import (
    ObservabilityAdapterReadinessError,
    ObservabilityAdapterReadinessOutput,
    run_observability_adapter_readiness_report,
)
from entroping.core.observability_packet import (
    ObservabilityOutput,
    ObservabilityPacketError,
    run_observability_packet_report,
)
from entroping.core.otel_mapping import (
    OtelMappingError,
    OtelMappingOutput,
    run_otel_mapping_report,
)
from entroping.core.pilot_cohort import (
    PilotCohortError,
    PilotCohortOutput,
    run_pilot_cohort_report,
)
from entroping.core.pilot_metrics import (
    PilotMetricsError,
    PilotMetricsOutput,
    run_pilot_metrics_report,
)
from entroping.core.pilot_outcome import (
    PilotOutcomeError,
    PilotOutcomeOutput,
    run_pilot_outcome_report,
)
from entroping.core.pr_evidence_card import (
    PrEvidenceCardError,
    PrEvidenceCardOutput,
    run_pr_evidence_card_report,
)
from entroping.core.qa_brain_eval_plan import (
    QaBrainEvalPlanError,
    QaBrainEvalPlanOutput,
    run_qa_brain_eval_plan_report,
)
from entroping.core.qa_brain_fine_tune_readiness import (
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessOutput,
    run_qa_brain_fine_tune_readiness_report,
)
from entroping.core.qa_brain_model_packaging_plan import (
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanOutput,
    run_qa_brain_model_packaging_plan_report,
)
from entroping.core.qa_brain_prompt_plan import (
    QaBrainPromptPlanError,
    QaBrainPromptPlanOutput,
    run_qa_brain_prompt_plan_report,
)
from entroping.core.qa_brain_repair_plan import (
    QaBrainRepairPlanError,
    QaBrainRepairPlanOutput,
    run_qa_brain_repair_plan_report,
)
from entroping.core.qa_brain_retrieval_plan import (
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanOutput,
    run_qa_brain_retrieval_plan_report,
)
from entroping.core.qa_brain_routing_plan import (
    QaBrainRoutingPlanError,
    QaBrainRoutingPlanOutput,
    run_qa_brain_routing_plan_report,
)
from entroping.core.qa_brain_seed import (
    QaBrainSeedError,
    QaBrainSeedOutput,
    run_qa_brain_seed_report,
)
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
from entroping.core.team_access_control_plan import (
    TeamAccessControlPlanError,
    TeamAccessControlPlanOutput,
    run_team_access_control_plan_report,
)
from entroping.core.team_evidence_readiness import (
    TeamEvidenceReadinessError,
    TeamEvidenceReadinessOutput,
    run_team_evidence_readiness_report,
)
from entroping.core.test_pyramid_report import (
    TestPyramidOutput,
    TestPyramidReportError,
    run_test_pyramid_report,
)
from entroping.core.test_quality_report import (
    TestQualityOutput,
    TestQualityReportError,
    run_test_quality_report,
)
from entroping.core.work_item_draft import (
    WorkItemDraftError,
    WorkItemDraftOutput,
    run_work_item_draft_report,
)
from entroping.core.work_item_import_bundle import (
    WorkItemImportBundleError,
    WorkItemImportBundleOutput,
    run_work_item_import_bundle_report,
)
from entroping.models.hurl import HurlMetadataSyntaxError

app = typer.Typer(help="Generate human handoff artifacts.")

LAUNCH_REPORT_PANEL = "Launch-Critical Reports"
STABLE_REPORT_PANEL = "Stable Public Reports"
MAINTAINER_REPORT_PANEL = "Maintainer And Baseline Tools"
EXPERIMENTAL_REPORT_PANEL = "Experimental Design-Partner Evidence"


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


def _gate_coverage_percent(*, matched_gates: int, total_gates: int) -> float:
    if total_gates <= 0:
        return 0.0
    return (matched_gates / total_gates) * 100


def _format_percent(value: float) -> str:
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"


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


@app.command("qa-brain-seed", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_seed(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain seed packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-seed output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_seed_report(
            project_root=Path.cwd(),
            output=cast(QaBrainSeedOutput, normalized_output),
        )
    except QaBrainSeedError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain seed: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-eval-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_eval_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain eval-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-eval-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_eval_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainEvalPlanOutput, normalized_output),
        )
    except QaBrainEvalPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain eval plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-retrieval-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_retrieval_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain retrieval-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-retrieval-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_retrieval_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRetrievalPlanOutput, normalized_output),
        )
    except QaBrainRetrievalPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain retrieval plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-prompt-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_prompt_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain prompt-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-prompt-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_prompt_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainPromptPlanOutput, normalized_output),
        )
    except QaBrainPromptPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain prompt plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-fine-tune-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_fine_tune_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain fine-tune readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-fine-tune-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_fine_tune_readiness_report(
            project_root=Path.cwd(),
            output=cast(QaBrainFineTuneReadinessOutput, normalized_output),
        )
    except QaBrainFineTuneReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain fine-tune readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-model-packaging-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_model_packaging_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain model-packaging plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(
            f"[yellow]Unsupported qa-brain-model-packaging-plan output: {output}[/yellow]"
        )
        raise typer.Exit(2)

    try:
        result = run_qa_brain_model_packaging_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainModelPackagingPlanOutput, normalized_output),
        )
    except QaBrainModelPackagingPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain model packaging plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-routing-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_routing_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain routing-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-routing-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_routing_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRoutingPlanOutput, normalized_output),
        )
    except QaBrainRoutingPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain routing plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-repair-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_repair_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain repair-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-repair-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_repair_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRepairPlanOutput, normalized_output),
        )
    except QaBrainRepairPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain repair plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("agent-bundle", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
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
        selected_role for selected_role in selected_roles if selected_role not in AGENT_BUNDLE_ROLES
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
