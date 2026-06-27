"""Report command package.

Splits the monolithic report CLI adapter into focused submodules
by rich help panel while preserving the single ``app`` Typer instance
and a single module namespace for test monkeypatch compatibility.

Each submodule is executed in this package's namespace via ``exec()``
so that all command functions, core imports, and panel constants
share a single ``__globals__`` dict.
"""

import json
import sys
from pathlib import Path
from typing import Annotated, cast

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

# Shared app and panel constants.
from entroping.cli.commands.report._app import app
from entroping.cli.commands.report._panels import (  # noqa: F401
    EXPERIMENTAL_REPORT_PANEL,
    LAUNCH_REPORT_PANEL,
    MAINTAINER_REPORT_PANEL,
    STABLE_REPORT_PANEL,
)

# Shared helpers.
from entroping.cli.commands.report._helpers import (  # noqa: F401
    _format_percent,
    _gate_coverage_percent,
)

# Execute submodule command code in this package's namespace so that all
# functions share a single ``__globals__`` and test monkeypatching of
# ``entroping.cli.commands.report`` remains effective.
_module_dir = Path(__file__).resolve().parent

for _sub_name in ("_launch", "_stable", "_maintainer", "_experimental"):
    _src = (_module_dir / f"{_sub_name}.py").read_text(encoding="utf-8")
    _code_lines = _src.split("\n")
    _in_docstring = False
    _kept: list[str] = []
    for _line in _code_lines:
        # Strip trailing globals-injection block.
        if _line.strip().startswith("# Inject report-package names"):
            break
        # Strip the _report import used for __getattr__ delegation.
        if _line.strip() == "import entroping.cli.commands.report as _report":
            continue
        # Skip module docstring.
        if not _kept and _line.strip().startswith('"""') and not _in_docstring:
            _in_docstring = True
            # Check if docstring opens and closes on same line.
            if _line.strip().count('"""') >= 2:
                _in_docstring = False
            continue
        if _in_docstring:
            if '"""' in _line:
                _in_docstring = False
            continue
        # Skip leading blank lines and comments.
        if not _kept and (not _line.strip() or _line.strip().startswith("#")):
            continue
        _kept.append(_line)
    _body = "\n".join(_kept)
    exec(compile(_body, f"<report/{_sub_name}>", "exec"), globals())

__all__ = ["app"]
