"""Shared dependencies for report command modules."""

from __future__ import annotations

from importlib import import_module
from typing import Any

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
from entroping.core.capture_summary_report import (
    CaptureSummaryError,
    CaptureSummaryOutput,
    run_capture_summary_report,
)
from entroping.core.coverage_badges import BadgeReportError, write_coverage_badges
from entroping.core.design_partner_feedback import (
    DesignPartnerFeedbackError,
    run_design_partner_feedback_report,
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
from entroping.core.evidence.agent_bundle import (
    AGENT_BUNDLE_ROLES,
    AgentBundleError,
    AgentBundleOutput,
    run_agent_bundle_report,
)
from entroping.core.evidence.api_inventory import (
    ApiInventoryError,
    ApiInventoryOutput,
    run_api_inventory_report,
)
from entroping.core.evidence.connector_intent import (
    ConnectorIntentError,
    ConnectorIntentOutput,
    run_connector_intent_report,
)
from entroping.core.evidence.evidence_bundle import (
    EvidenceBundleError,
    run_evidence_bundle_report,
)
from entroping.core.evidence.evidence_cloud_dashboard import (
    EvidenceCloudDashboardError,
    EvidenceCloudDashboardOutput,
    run_evidence_cloud_dashboard_report,
)
from entroping.core.evidence.evidence_index_report import (
    EvidenceIndexError,
    EvidenceIndexOutput,
    run_evidence_index_report,
)
from entroping.core.evidence.evidence_links import (
    EvidenceLinksError,
    EvidenceLinksOutput,
    run_evidence_links_report,
)
from entroping.core.evidence.evidence_portal import (
    EvidencePortalError,
    EvidencePortalOutput,
    run_evidence_portal_report,
)
from entroping.core.evidence.external_test_evidence import (
    ExternalTestEvidenceError,
    ExternalTestEvidenceOutput,
    run_external_test_evidence_report,
)
from entroping.core.evidence.handoff_packet import (
    HandoffError,
    HandoffOutput,
    run_handoff_report,
)
from entroping.core.evidence.notification_packet import (
    NotificationOutput,
    NotificationPacketError,
    run_notification_packet_report,
)
from entroping.core.evidence.observability_packet import (
    ObservabilityOutput,
    ObservabilityPacketError,
    run_observability_packet_report,
)
from entroping.core.evidence.otel_mapping import (
    OtelMappingError,
    OtelMappingOutput,
    run_otel_mapping_report,
)
from entroping.core.evidence.pilot_cohort import (
    PilotCohortError,
    PilotCohortOutput,
    run_pilot_cohort_report,
)
from entroping.core.evidence.pilot_metrics import (
    PilotMetricsError,
    PilotMetricsOutput,
    run_pilot_metrics_report,
)
from entroping.core.evidence.pilot_outcome import (
    PilotOutcomeError,
    PilotOutcomeOutput,
    run_pilot_outcome_report,
)
from entroping.core.evidence.pr_evidence_card import (
    PrEvidenceCardError,
    PrEvidenceCardOutput,
    run_pr_evidence_card_report,
)
from entroping.core.evidence.test_pyramid_report import (
    TestPyramidOutput,
    TestPyramidReportError,
    run_test_pyramid_report,
)
from entroping.core.export.evidence_cloud_export import (
    EvidenceCloudExportError,
    EvidenceCloudExportOutput,
    run_evidence_cloud_export_report,
)
from entroping.core.export.evidence_cloud_workspace import (
    EvidenceCloudWorkspaceError,
    EvidenceCloudWorkspaceOutput,
    run_evidence_cloud_workspace_report,
)
from entroping.core.export.work_item_draft import (
    WorkItemDraftError,
    WorkItemDraftOutput,
    run_work_item_draft_report,
)
from entroping.core.export.work_item_import_bundle import (
    WorkItemImportBundleError,
    WorkItemImportBundleOutput,
    run_work_item_import_bundle_report,
)
from entroping.core.failure_bundle import FailureBundleError, create_failure_bundle
from entroping.core.first_run_checklist import (
    FirstRunChecklist,
    FirstRunChecklistItem,
    run_first_run_checklist,
)
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
from entroping.core.plan.evidence_action_plan import (
    EvidenceActionPlanError,
    EvidenceActionPlanOutput,
    run_evidence_action_plan_report,
)
from entroping.core.plan.qa_brain_eval_plan import (
    QaBrainEvalPlanError,
    QaBrainEvalPlanOutput,
    run_qa_brain_eval_plan_report,
)
from entroping.core.plan.qa_brain_fine_tune_readiness import (
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessOutput,
    run_qa_brain_fine_tune_readiness_report,
)
from entroping.core.plan.qa_brain_model_packaging_plan import (
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanOutput,
    run_qa_brain_model_packaging_plan_report,
)
from entroping.core.plan.qa_brain_prompt_plan import (
    QaBrainPromptPlanError,
    QaBrainPromptPlanOutput,
    run_qa_brain_prompt_plan_report,
)
from entroping.core.plan.qa_brain_repair_plan import (
    QaBrainRepairPlanError,
    QaBrainRepairPlanOutput,
    run_qa_brain_repair_plan_report,
)
from entroping.core.plan.qa_brain_retrieval_plan import (
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanOutput,
    run_qa_brain_retrieval_plan_report,
)
from entroping.core.plan.qa_brain_routing_plan import (
    QaBrainRoutingPlanError,
    QaBrainRoutingPlanOutput,
    run_qa_brain_routing_plan_report,
)
from entroping.core.plan.qa_brain_seed import (
    QaBrainSeedError,
    QaBrainSeedOutput,
    run_qa_brain_seed_report,
)
from entroping.core.plan.team_access_control_plan import (
    TeamAccessControlPlanError,
    TeamAccessControlPlanOutput,
    run_team_access_control_plan_report,
)
from entroping.core.readiness.devex_readiness import (
    DevexReadinessError,
    DevexReadinessOutput,
    run_devex_readiness_report,
)
from entroping.core.readiness.evidence_cloud_readiness import (
    EvidenceCloudReadinessError,
    EvidenceCloudReadinessOutput,
    run_evidence_cloud_readiness_report,
)
from entroping.core.readiness.integration_readiness import (
    IntegrationReadinessError,
    IntegrationReadinessOutput,
    run_integration_readiness_report,
)
from entroping.core.readiness.mutation_readiness import (
    MutationReadinessError,
    MutationReadinessOutput,
    run_mutation_readiness_report,
)
from entroping.core.readiness.observability_adapter_readiness import (
    ObservabilityAdapterReadinessError,
    ObservabilityAdapterReadinessOutput,
    run_observability_adapter_readiness_report,
)
from entroping.core.readiness.team_evidence_readiness import (
    TeamEvidenceReadinessError,
    TeamEvidenceReadinessOutput,
    run_team_evidence_readiness_report,
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
from entroping.core.test_quality_report import (
    TestQualityOutput,
    TestQualityReportError,
    run_test_quality_report,
)
from entroping.models.hurl import HurlMetadataSyntaxError

__all__ = [
    "AGENT_BUNDLE_ROLES",
    "AgentBundleError",
    "AgentBundleOutput",
    "ApiInventoryError",
    "ApiInventoryOutput",
    "BadgeReportError",
    "CaptureSummaryError",
    "CaptureSummaryOutput",
    "ConnectorIntentError",
    "ConnectorIntentOutput",
    "DesignPartnerFeedbackError",
    "DevexReadinessError",
    "DevexReadinessOutput",
    "DriftReportError",
    "EffectivePolicyDiffError",
    "EffectivePolicyDiffOutput",
    "EffectivePolicyDiffReportError",
    "EffectivePolicyOutput",
    "EffectivePolicyReportError",
    "EvidenceActionPlanError",
    "EvidenceActionPlanOutput",
    "EvidenceBundleError",
    "EvidenceCloudDashboardError",
    "EvidenceCloudDashboardOutput",
    "EvidenceCloudExportError",
    "EvidenceCloudExportOutput",
    "EvidenceCloudReadinessError",
    "EvidenceCloudReadinessOutput",
    "EvidenceCloudWorkspaceError",
    "EvidenceCloudWorkspaceOutput",
    "EvidenceIndexError",
    "EvidenceIndexOutput",
    "EvidenceLinksError",
    "EvidenceLinksOutput",
    "EvidencePortalError",
    "EvidencePortalOutput",
    "ExternalTestEvidenceError",
    "ExternalTestEvidenceOutput",
    "FailureBundleError",
    "FirstRunChecklist",
    "FirstRunChecklistItem",
    "GateCoverageOutput",
    "GateCoverageReportError",
    "GateInjectionOutput",
    "GateInjectionReportError",
    "GitHubAnnotation",
    "GitHubAnnotationError",
    "HandoffError",
    "HandoffOutput",
    "HurlMetadataSyntaxError",
    "IntegrationReadinessError",
    "IntegrationReadinessOutput",
    "MutationReadinessError",
    "MutationReadinessOutput",
    "NotificationOutput",
    "NotificationPacketError",
    "ObservabilityAdapterReadinessError",
    "ObservabilityAdapterReadinessOutput",
    "ObservabilityOutput",
    "ObservabilityPacketError",
    "OtelMappingError",
    "OtelMappingOutput",
    "PilotCohortError",
    "PilotCohortOutput",
    "PilotMetricsError",
    "PilotMetricsOutput",
    "PilotOutcomeError",
    "PilotOutcomeOutput",
    "PrEvidenceCardError",
    "PrEvidenceCardOutput",
    "QaBrainEvalPlanError",
    "QaBrainEvalPlanOutput",
    "QaBrainFineTuneReadinessError",
    "QaBrainFineTuneReadinessOutput",
    "QaBrainModelPackagingPlanError",
    "QaBrainModelPackagingPlanOutput",
    "QaBrainPromptPlanError",
    "QaBrainPromptPlanOutput",
    "QaBrainRepairPlanError",
    "QaBrainRepairPlanOutput",
    "QaBrainRetrievalPlanError",
    "QaBrainRetrievalPlanOutput",
    "QaBrainRoutingPlanError",
    "QaBrainRoutingPlanOutput",
    "QaBrainSeedError",
    "QaBrainSeedOutput",
    "RedactionReviewError",
    "RedactionReviewOutput",
    "ReportArtifactManifestError",
    "ReportWriterError",
    "ReviewSummaryError",
    "RunDeltaError",
    "RuntimeCardError",
    "RuntimeCardOutput",
    "SarifReportError",
    "TeamAccessControlPlanError",
    "TeamAccessControlPlanOutput",
    "TeamEvidenceReadinessError",
    "TeamEvidenceReadinessOutput",
    "TestPyramidOutput",
    "TestPyramidReportError",
    "TestQualityOutput",
    "TestQualityReportError",
    "WorkItemDraftError",
    "WorkItemDraftOutput",
    "WorkItemImportBundleError",
    "WorkItemImportBundleOutput",
    "build_effective_policy_diff_report",
    "build_run_delta_report",
    "collect_github_annotations",
    "compile_story_traceability",
    "console",
    "create_failure_bundle",
    "discover_hurl_tests",
    "discover_story_documents",
    "display_cli_path",
    "effective_policy_diff_report_to_dict",
    "load_effective_policy_report",
    "load_run_report",
    "print_cli_error",
    "promote_reviewed_drift_baseline_candidate",
    "render_effective_policy_diff_markdown",
    "render_github_annotation",
    "render_run_delta_markdown",
    "render_story_traceability_markdown",
    "report_dependency",
    "run_agent_bundle_report",
    "run_api_inventory_report",
    "run_capture_summary_report",
    "run_connector_intent_report",
    "run_first_run_checklist",
    "run_delta_report_to_dict",
    "run_design_partner_feedback_report",
    "run_devex_readiness_report",
    "run_effective_policy_report",
    "run_evidence_action_plan_report",
    "run_evidence_bundle_report",
    "run_evidence_cloud_dashboard_report",
    "run_evidence_cloud_export_report",
    "run_evidence_cloud_readiness_report",
    "run_evidence_cloud_workspace_report",
    "run_evidence_index_report",
    "run_evidence_links_report",
    "run_evidence_portal_report",
    "run_external_test_evidence_report",
    "run_gate_coverage_report",
    "run_gate_injection_report",
    "run_handoff_report",
    "run_integration_readiness_report",
    "run_mutation_readiness_report",
    "run_notification_packet_report",
    "run_observability_adapter_readiness_report",
    "run_observability_packet_report",
    "run_otel_mapping_report",
    "run_pilot_cohort_report",
    "run_pilot_metrics_report",
    "run_pilot_outcome_report",
    "run_pr_evidence_card_report",
    "run_qa_brain_eval_plan_report",
    "run_qa_brain_fine_tune_readiness_report",
    "run_qa_brain_model_packaging_plan_report",
    "run_qa_brain_prompt_plan_report",
    "run_qa_brain_repair_plan_report",
    "run_qa_brain_retrieval_plan_report",
    "run_qa_brain_routing_plan_report",
    "run_qa_brain_seed_report",
    "run_redaction_review",
    "run_review_summary",
    "run_runtime_card_report",
    "run_sarif_report",
    "run_team_access_control_plan_report",
    "run_team_evidence_readiness_report",
    "run_test_pyramid_report",
    "run_test_quality_report",
    "run_work_item_draft_report",
    "run_work_item_import_bundle_report",
    "story_traceability_report_to_dict",
    "write_bug_report",
    "write_coverage_badges",
    "write_report_artifact_manifest",
]


def report_dependency(name: str) -> Any:
    """Resolve a report dependency through the package for monkeypatch compatibility."""

    def _call(*args: Any, **kwargs: Any) -> Any:
        report_module = import_module("entroping.cli.commands.report")
        return getattr(report_module, name)(*args, **kwargs)

    return _call
