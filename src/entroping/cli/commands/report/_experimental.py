"""Experimental design-partner evidence report commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    AGENT_BUNDLE_ROLES,
    AgentBundleError,
    AgentBundleOutput,
    ApiInventoryError,
    ApiInventoryOutput,
    ConnectorIntentError,
    ConnectorIntentOutput,
    DesignPartnerFeedbackError,
    DevexReadinessError,
    DevexReadinessOutput,
    EvidenceActionPlanError,
    EvidenceActionPlanOutput,
    EvidenceBundleError,
    EvidenceCloudDashboardError,
    EvidenceCloudDashboardOutput,
    EvidenceCloudExportError,
    EvidenceCloudExportOutput,
    EvidenceCloudReadinessError,
    EvidenceCloudReadinessOutput,
    EvidenceCloudWorkspaceError,
    EvidenceCloudWorkspaceOutput,
    EvidenceIndexError,
    EvidenceIndexOutput,
    EvidenceLinksError,
    EvidenceLinksOutput,
    EvidencePortalError,
    EvidencePortalOutput,
    ExternalTestEvidenceError,
    ExternalTestEvidenceOutput,
    HandoffError,
    HandoffOutput,
    IntegrationReadinessError,
    IntegrationReadinessOutput,
    MutationReadinessError,
    MutationReadinessOutput,
    NotificationOutput,
    NotificationPacketError,
    ObservabilityAdapterReadinessError,
    ObservabilityAdapterReadinessOutput,
    ObservabilityOutput,
    ObservabilityPacketError,
    OtelMappingError,
    OtelMappingOutput,
    PilotCohortError,
    PilotCohortOutput,
    PilotMetricsError,
    PilotMetricsOutput,
    PilotOutcomeError,
    PilotOutcomeOutput,
    PrEvidenceCardError,
    PrEvidenceCardOutput,
    QaBrainEvalPlanError,
    QaBrainEvalPlanOutput,
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessOutput,
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanOutput,
    QaBrainPromptPlanError,
    QaBrainPromptPlanOutput,
    QaBrainRepairPlanError,
    QaBrainRepairPlanOutput,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanOutput,
    QaBrainRoutingPlanError,
    QaBrainRoutingPlanOutput,
    QaBrainSeedError,
    QaBrainSeedOutput,
    TeamAccessControlPlanError,
    TeamAccessControlPlanOutput,
    TeamEvidenceReadinessError,
    TeamEvidenceReadinessOutput,
    WorkItemDraftError,
    WorkItemDraftOutput,
    WorkItemImportBundleError,
    WorkItemImportBundleOutput,
    report_dependency,
    run_agent_bundle_report,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_api_inventory_report = report_dependency("run_api_inventory_report")
run_connector_intent_report = report_dependency("run_connector_intent_report")
run_design_partner_feedback_report = report_dependency("run_design_partner_feedback_report")
run_devex_readiness_report = report_dependency("run_devex_readiness_report")
run_evidence_action_plan_report = report_dependency("run_evidence_action_plan_report")
run_evidence_bundle_report = report_dependency("run_evidence_bundle_report")
run_evidence_cloud_dashboard_report = report_dependency("run_evidence_cloud_dashboard_report")
run_evidence_cloud_export_report = report_dependency("run_evidence_cloud_export_report")
run_evidence_cloud_readiness_report = report_dependency("run_evidence_cloud_readiness_report")
run_evidence_cloud_workspace_report = report_dependency("run_evidence_cloud_workspace_report")
run_evidence_index_report = report_dependency("run_evidence_index_report")
run_evidence_links_report = report_dependency("run_evidence_links_report")
run_evidence_portal_report = report_dependency("run_evidence_portal_report")
run_external_test_evidence_report = report_dependency("run_external_test_evidence_report")
run_handoff_report = report_dependency("run_handoff_report")
run_integration_readiness_report = report_dependency("run_integration_readiness_report")
run_mutation_readiness_report = report_dependency("run_mutation_readiness_report")
run_notification_packet_report = report_dependency("run_notification_packet_report")
run_observability_adapter_readiness_report = report_dependency(
    "run_observability_adapter_readiness_report"
)
run_observability_packet_report = report_dependency("run_observability_packet_report")
run_otel_mapping_report = report_dependency("run_otel_mapping_report")
run_pilot_cohort_report = report_dependency("run_pilot_cohort_report")
run_pilot_metrics_report = report_dependency("run_pilot_metrics_report")
run_pilot_outcome_report = report_dependency("run_pilot_outcome_report")
run_pr_evidence_card_report = report_dependency("run_pr_evidence_card_report")
run_qa_brain_eval_plan_report = report_dependency("run_qa_brain_eval_plan_report")
run_qa_brain_fine_tune_readiness_report = report_dependency(
    "run_qa_brain_fine_tune_readiness_report"
)
run_qa_brain_model_packaging_plan_report = report_dependency(
    "run_qa_brain_model_packaging_plan_report"
)
run_qa_brain_prompt_plan_report = report_dependency("run_qa_brain_prompt_plan_report")
run_qa_brain_repair_plan_report = report_dependency("run_qa_brain_repair_plan_report")
run_qa_brain_retrieval_plan_report = report_dependency("run_qa_brain_retrieval_plan_report")
run_qa_brain_routing_plan_report = report_dependency("run_qa_brain_routing_plan_report")
run_qa_brain_seed_report = report_dependency("run_qa_brain_seed_report")
run_team_access_control_plan_report = report_dependency("run_team_access_control_plan_report")
run_team_evidence_readiness_report = report_dependency("run_team_evidence_readiness_report")
run_work_item_draft_report = report_dependency("run_work_item_draft_report")
run_work_item_import_bundle_report = report_dependency("run_work_item_import_bundle_report")


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
