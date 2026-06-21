"""Versioned report schema contract tests."""

import json
from pathlib import Path
from typing import cast

from entroping.bridge.capture_summary import (
    CAPTURE_SUMMARY_SCHEMA_VERSION,
    capture_summary_report_to_dict,
    compile_capture_summary,
)
from entroping.bridge.effective_policy import (
    EffectivePolicyGateReport,
    EffectivePolicyReport,
    EffectivePolicySourceReport,
)
from entroping.bridge.effective_policy_diff import (
    EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION,
    build_effective_policy_diff_report,
    effective_policy_diff_report_to_dict,
)
from entroping.bridge.gate_coverage import (
    GATE_COVERAGE_REPORT_SCHEMA_VERSION,
    GateCoverageExchangeReport,
    GateCoverageGateReport,
    GateCoverageReport,
    GateCoverageSummary,
    GateCoverageTestReport,
)
from entroping.bridge.gate_injection_explain import (
    GATE_INJECTION_REPORT_SCHEMA_VERSION,
    GateInjectionGateReport,
    GateInjectionReport,
    GateInjectionSummary,
    GateInjectionTargetReport,
)
from entroping.bridge.openapi_audit import (
    OPENAPI_AUDIT_SCHEMA_VERSION,
    audit_openapi_coverage,
    audit_report_to_dict,
)
from entroping.bridge.story_traceability import (
    compile_story_traceability,
    story_traceability_report_to_dict,
)
from entroping.bridge.test_pyramid import (
    TEST_PYRAMID_REPORT_SCHEMA_VERSION,
)
from entroping.bridge.test_pyramid import (
    TestPyramidArtifactEvidence as PyramidArtifactEvidenceModel,
)
from entroping.bridge.test_pyramid import (
    TestPyramidFinding as PyramidFindingModel,
)
from entroping.bridge.test_pyramid import (
    TestPyramidLayer as PyramidLayerModel,
)
from entroping.bridge.test_pyramid import (
    TestPyramidReport as PyramidReportModel,
)
from entroping.bridge.test_pyramid import (
    TestPyramidSummary as PyramidSummaryModel,
)
from entroping.bridge.test_quality import (
    TEST_QUALITY_REPORT_SCHEMA_VERSION,
)
from entroping.bridge.test_quality import (
    TestQualityFinding as QualityFindingModel,
)
from entroping.bridge.test_quality import (
    TestQualityReport as QualityReportModel,
)
from entroping.bridge.test_quality import (
    TestQualitySummary as QualitySummaryModel,
)
from entroping.bridge.test_quality import (
    TestQualityTestReport as QualityTestReportModel,
)
from entroping.core.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.agent_manifest import AGENT_RUN_MANIFEST_SCHEMA_VERSION
from entroping.core.api_inventory import (
    API_INVENTORY_SCHEMA_VERSION,
    ApiInventoryPacket,
    ApiInventorySource,
    ApiInventoryStyleSummary,
    ApiInventorySummary,
)
from entroping.core.connector_intent import (
    CONNECTOR_INTENT_SCHEMA_VERSION,
    ConnectorIntentNextAction,
    ConnectorIntentPacket,
    ConnectorIntentRecord,
    ConnectorIntentSource,
    ConnectorIntentSummary,
)
from entroping.core.devex_readiness import (
    DEVEX_READINESS_SCHEMA_VERSION,
    DevexReadinessFamily,
    DevexReadinessNextAction,
    DevexReadinessPacket,
    DevexReadinessSource,
    DevexReadinessSummary,
)
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    drift_baseline_to_dict,
    drift_report_to_dict,
)
from entroping.core.evidence_action_plan import (
    EVIDENCE_ACTION_PLAN_SCHEMA_VERSION,
    EvidenceActionPlanItem,
    EvidenceActionPlanPacket,
    EvidenceActionPlanSource,
    EvidenceActionPlanSummary,
)
from entroping.core.evidence_bundle import (
    EVIDENCE_BUNDLE_SCHEMA_VERSION,
    EvidenceBundleArtifact,
    EvidenceBundleDiagnostic,
    EvidenceBundleManifestAudit,
    EvidenceBundleMissingArtifact,
    EvidenceBundleReport,
    EvidenceBundleSummary,
)
from entroping.core.evidence_cloud_dashboard import (
    EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION,
    EvidenceCloudDashboardPacket,
    EvidenceCloudDashboardRepository,
    EvidenceCloudDashboardSummary,
)
from entroping.core.evidence_cloud_export import (
    EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION,
    EvidenceCloudExportBoundaryControl,
    EvidenceCloudExportItem,
    EvidenceCloudExportNextAction,
    EvidenceCloudExportPacket,
    EvidenceCloudExportSource,
    EvidenceCloudExportSummary,
)
from entroping.core.evidence_cloud_readiness import (
    EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION,
    EvidenceCloudBoundary,
    EvidenceCloudNextAction,
    EvidenceCloudReadinessArea,
    EvidenceCloudReadinessPacket,
    EvidenceCloudSource,
    EvidenceCloudSummary,
    EvidenceCloudUploadCandidate,
)
from entroping.core.evidence_cloud_workspace import (
    EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION,
    EvidenceCloudWorkspaceBoundaryControl,
    EvidenceCloudWorkspaceManifest,
    EvidenceCloudWorkspaceNextAction,
    EvidenceCloudWorkspacePacket,
    EvidenceCloudWorkspaceRepository,
    EvidenceCloudWorkspaceSummary,
)
from entroping.core.evidence_index_report import (
    EVIDENCE_INDEX_SCHEMA_VERSION,
    EvidenceIndexArtifact,
    EvidenceIndexPacket,
    EvidenceIndexSummary,
)
from entroping.core.evidence_links import (
    EVIDENCE_LINKS_SCHEMA_VERSION,
    EvidenceLinksNextAction,
    EvidenceLinksPacket,
    EvidenceLinksSource,
    EvidenceLinksSummary,
    EvidenceLinkTarget,
)
from entroping.core.evidence_portal import (
    EVIDENCE_PORTAL_SCHEMA_VERSION,
    EvidencePortalCard,
    EvidencePortalNextAction,
    EvidencePortalPacket,
    EvidencePortalSource,
    EvidencePortalSummary,
)
from entroping.core.external_test_evidence import (
    EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
    ExternalTestEvidenceLayer,
    ExternalTestEvidenceNextAction,
    ExternalTestEvidencePacket,
    ExternalTestEvidenceSource,
    ExternalTestEvidenceSummary,
)
from entroping.core.handoff_packet import (
    HANDOFF_SCHEMA_VERSION,
    HandoffArtifact,
    HandoffGit,
    HandoffPacket,
    HandoffRuntimeSummary,
    HandoffSummary,
    HandoffTarget,
)
from entroping.core.integration_readiness import (
    INTEGRATION_READINESS_SCHEMA_VERSION,
    IntegrationReadinessFamily,
    IntegrationReadinessNextAction,
    IntegrationReadinessPacket,
    IntegrationReadinessSource,
    IntegrationReadinessSummary,
)
from entroping.core.mutation_readiness import (
    MUTATION_READINESS_SCHEMA_VERSION,
    MutationReadinessCandidate,
    MutationReadinessPacket,
    MutationReadinessSource,
    MutationReadinessSummary,
)
from entroping.core.notification_packet import (
    NOTIFICATION_PACKET_SCHEMA_VERSION,
    NotificationMessage,
    NotificationPacket,
    NotificationRuntimeSummary,
    NotificationSource,
    NotificationSummary,
)
from entroping.core.observability_adapter_readiness import (
    OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION,
    ObservabilityAdapterBoundaryControl,
    ObservabilityAdapterNextAction,
    ObservabilityAdapterReadinessPacket,
    ObservabilityAdapterReadinessRow,
    ObservabilityAdapterReadinessSource,
    ObservabilityAdapterReadinessSummary,
)
from entroping.core.observability_packet import (
    OBSERVABILITY_PACKET_SCHEMA_VERSION,
    ObservabilityComponentSummary,
    ObservabilityEventSummary,
    ObservabilityMessage,
    ObservabilityPacket,
    ObservabilityRuntimeSummary,
    ObservabilitySource,
    ObservabilitySummary,
)
from entroping.core.otel_mapping import (
    OTEL_MAPPING_SCHEMA_VERSION,
    OtelAttributeMapping,
    OtelBoundaryControl,
    OtelMappingNextAction,
    OtelMappingPacket,
    OtelMappingSource,
    OtelMappingSummary,
)
from entroping.core.pilot_cohort import (
    PILOT_COHORT_SCHEMA_VERSION,
    PilotCohortAction,
    PilotCohortMonetizationSignal,
    PilotCohortOutcome,
    PilotCohortPacket,
    PilotCohortReadinessSignal,
    PilotCohortSummary,
)
from entroping.core.pilot_metrics import (
    PILOT_METRICS_SCHEMA_VERSION,
    PilotEvidenceSource,
    PilotMetric,
    PilotMetricsReport,
    PilotMetricsSummary,
)
from entroping.core.pilot_outcome import (
    PILOT_OUTCOME_SCHEMA_VERSION,
    PilotOutcomeAction,
    PilotOutcomeMonetizationSignal,
    PilotOutcomePacket,
    PilotOutcomeReadiness,
    PilotOutcomeSource,
    PilotOutcomeSummary,
)
from entroping.core.pr_evidence_card import (
    PR_EVIDENCE_CARD_SCHEMA_VERSION,
    PrEvidenceCardChecklistItem,
    PrEvidenceCardNextAction,
    PrEvidenceCardPacket,
    PrEvidenceCardSource,
    PrEvidenceCardSummary,
)
from entroping.core.qa_brain_eval_plan import (
    QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
    QaBrainEvalCase,
    QaBrainEvalPlanNextAction,
    QaBrainEvalPlanPacket,
    QaBrainEvalPlanSummary,
)
from entroping.core.qa_brain_fine_tune_readiness import (
    QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
    QaBrainFineTuneReadinessNextAction,
    QaBrainFineTuneReadinessPacket,
    QaBrainFineTuneReadinessRow,
    QaBrainFineTuneReadinessSummary,
)
from entroping.core.qa_brain_model_packaging_plan import (
    QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION,
    QaBrainModelPackagingPlanNextAction,
    QaBrainModelPackagingPlanPacket,
    QaBrainModelPackagingPlanRow,
    QaBrainModelPackagingPlanSummary,
)
from entroping.core.qa_brain_prompt_plan import (
    QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
    QaBrainPromptPlanNextAction,
    QaBrainPromptPlanPacket,
    QaBrainPromptPlanRow,
    QaBrainPromptPlanSummary,
)
from entroping.core.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalPlanNextAction,
    QaBrainRetrievalPlanPacket,
    QaBrainRetrievalPlanRow,
    QaBrainRetrievalPlanSummary,
)
from entroping.core.qa_brain_routing_plan import (
    QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
    QaBrainRoutingPlanNextAction,
    QaBrainRoutingPlanPacket,
    QaBrainRoutingPlanRow,
    QaBrainRoutingPlanSummary,
)
from entroping.core.qa_brain_seed import (
    QA_BRAIN_SEED_SCHEMA_VERSION,
    QaBrainEvalSlice,
    QaBrainNextAction,
    QaBrainSeedPacket,
    QaBrainSeedSource,
    QaBrainSeedSummary,
)
from entroping.core.report_artifact_manifest import (
    REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ReportArtifactAuditCommand,
    ReportArtifactAuditEvent,
    ReportArtifactAuditEvidence,
    ReportArtifactAuditVerification,
    ReportArtifactEntry,
    ReportArtifactManifest,
    ReportArtifactManifestSummary,
    ReportArtifactMissing,
)
from entroping.core.report_writer import run_report_to_dict
from entroping.core.run_delta import (
    RUN_DELTA_REPORT_SCHEMA_VERSION,
    build_run_delta_report,
    run_delta_report_to_dict,
)
from entroping.core.run_workflow import (
    RUN_PLAN_SCHEMA_VERSION,
    RunExecutionPlan,
    RunPlanTest,
    RunPlanVariableGap,
    run_execution_plan_to_dict,
)
from entroping.core.runtime_card import (
    RUNTIME_CARD_SCHEMA_VERSION,
    RuntimeCardAgentProvenance,
    RuntimeCardArtifact,
    RuntimeCardDriftEvidence,
    RuntimeCardFinding,
    RuntimeCardPilotReadiness,
    RuntimeCardRedactionEvidence,
    RuntimeCardReleaseEvidence,
    RuntimeCardReport,
    RuntimeCardRunEvidence,
    RuntimeCardSummary,
    RuntimeCardTestPyramidEvidence,
)
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    StructuredDiagnosticAttribute,
    StructuredDiagnosticEvent,
)
from entroping.core.team_access_control_plan import (
    TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
    TeamAccessControlAuditEvent,
    TeamAccessControlBoundary,
    TeamAccessControlNextAction,
    TeamAccessControlPlanPacket,
    TeamAccessControlPlanSummary,
    TeamAccessControlRolePlan,
    TeamAccessControlSource,
)
from entroping.core.team_evidence_readiness import (
    TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
    TeamEvidenceCloudBoundary,
    TeamEvidenceNextAction,
    TeamEvidenceReadinessArea,
    TeamEvidenceReadinessPacket,
    TeamEvidenceReadinessSummary,
    TeamEvidenceSource,
)
from entroping.core.traffic_artifact_manifest import TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION
from entroping.core.work_item_draft import (
    WORK_ITEM_DRAFT_SCHEMA_VERSION,
    WorkItemDraftItem,
    WorkItemDraftPacket,
    WorkItemDraftSource,
    WorkItemDraftSummary,
)
from entroping.core.work_item_import_bundle import (
    WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION,
    WorkItemImportAction,
    WorkItemImportBundle,
    WorkItemImportRow,
    WorkItemImportSource,
    WorkItemImportSummary,
)
from entroping.models.drift import (
    DriftBaseline,
    DriftBaselineTest,
    DriftFinding,
    DriftReport,
    DriftReportSummary,
)
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest
from entroping.models.report import (
    KnownFailureEvidence,
    RunAttemptEvidence,
    RunReport,
    RunReportSummary,
    RunRetryEvidence,
    RunSafetyEvidence,
    RunTestReport,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "docs" / "technical" / "report-schemas"


def test_run_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = RunReport(
        project="checkout-api",
        environment="ci",
        generated_at="2026-05-31T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run-1/health.hurl",
                status="passed",
                exit_code=0,
                duration_ms=12,
                timeout_ms=2500,
                operation_id="createCheckout",
                source="openapi",
                negative_category="boundary-values",
                severity="medium",
                rule_ids=("global_latency",),
                stdout='HTTP 200\n\n{"ok":true}\n',
                stderr="",
                response_status_code=200,
                response_headers=(("content-type", "application/json"),),
                response_body_shape=("$:object", "$.ok:boolean"),
                known_failures=(
                    KnownFailureEvidence(
                        test="tests/health.hurl",
                        rule_id="global_latency",
                        issue_id="GH-123",
                        expires="2026-06-30",
                        reason="Temporary upstream latency regression.",
                    ),
                ),
                safety=RunSafetyEvidence(
                    protected_environment=True,
                    safety="idempotent",
                    safety_source="test metadata",
                    methods=("POST",),
                    blocked_reason=None,
                ),
                retry=RunRetryEvidence(
                    retry_count=1,
                    unstable=True,
                    attempts=(
                        RunAttemptEvidence(
                            attempt=1,
                            status="failed",
                            exit_code=42,
                            duration_ms=20,
                            stdout_truncated=False,
                            stderr_truncated=True,
                        ),
                        RunAttemptEvidence(
                            attempt=2,
                            status="passed",
                            exit_code=0,
                            duration_ms=12,
                            stdout_truncated=False,
                            stderr_truncated=False,
                        ),
                    ),
                ),
            ),
        ),
    )

    payload = run_report_to_dict(report)

    assert payload == {
        "schema_version": "entroping.run-report.v1",
        "project": "checkout-api",
        "environment": "ci",
        "generated_at": "2026-05-31T00:00:00+00:00",
        "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
        "tests": [
            {
                "path": "tests/health.hurl",
                "execution_path": ".entroping/run-1/health.hurl",
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 12,
                "timeout_ms": 2500,
                "operation_id": "createCheckout",
                "source": "openapi",
                "negative_category": "boundary-values",
                "severity": "medium",
                "rule_ids": ["global_latency"],
                "stdout": 'HTTP 200\n\n{"ok":true}\n',
                "stderr": "",
                "known_failures": [
                    {
                        "test": "tests/health.hurl",
                        "rule_id": "global_latency",
                        "issue_id": "GH-123",
                        "expires": "2026-06-30",
                        "reason": "Temporary upstream latency regression.",
                    }
                ],
                "safety": {
                    "protected_environment": True,
                    "safety": "idempotent",
                    "safety_source": "test metadata",
                    "methods": ["POST"],
                    "blocked_reason": None,
                },
                "retry": {
                    "retry_count": 1,
                    "unstable": True,
                    "attempts": [
                        {
                            "attempt": 1,
                            "status": "failed",
                            "exit_code": 42,
                            "duration_ms": 20,
                            "stdout_truncated": False,
                            "stderr_truncated": True,
                        },
                        {
                            "attempt": 2,
                            "status": "passed",
                            "exit_code": 0,
                            "duration_ms": 12,
                            "stdout_truncated": False,
                            "stderr_truncated": False,
                        },
                    ],
                },
                "response": {
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body_shape": ["$:object", "$.ok:boolean"],
                },
            }
        ],
    }


def test_run_report_v1_schema_contract_includes_fail_fast_summary_evidence() -> None:
    schema = json.loads((SCHEMA_DIR / "run-report.v1.schema.json").read_text())
    summary_properties = schema["properties"]["summary"]["properties"]
    report = RunReport(
        project="checkout-api",
        environment="ci",
        generated_at="2026-06-05T00:00:00+00:00",
        summary=RunReportSummary(
            total=2,
            passed=1,
            failed=1,
            exit_code=1,
            selected=3,
            executed=2,
            not_scheduled=1,
            fail_fast=True,
        ),
        tests=(),
    )

    payload = run_report_to_dict(report)

    assert payload["summary"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "exit_code": 1,
        "selected": 3,
        "executed": 2,
        "not_scheduled": 1,
        "fail_fast": True,
    }
    assert summary_properties["selected"] == {"type": "integer", "minimum": 0}
    assert summary_properties["executed"] == {"type": "integer", "minimum": 0}
    assert summary_properties["not_scheduled"] == {"type": "integer", "minimum": 0}
    assert summary_properties["fail_fast"] == {"type": "boolean"}


def test_run_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "run-plan.v1.schema.json").read_text())
    plan = RunExecutionPlan(
        status="blocked",
        message="Run plan blocked by unresolved Hurl variables",
        project="checkout-api",
        environment="local",
        tag_filters=("smoke",),
        tag_expression=None,
        operation_ids=(),
        changed_from="origin/main",
        selection_label=None,
        report_formats=("json",),
        would_write_reports=("reports/run-latest.json",),
        parallel=False,
        fail_fast=True,
        drift_check=False,
        worker_count=1,
        timeout_ms=2500,
        retry=1,
        discovered_count=2,
        selected_count=1,
        skipped_count=1,
        effective_rule_ids=("global_latency",),
        injected_rule_ids=("global_latency",),
        provided_variable_count=0,
        missing_variables=(RunPlanVariableGap(name="base_url", paths=("tests/health.hurl",)),),
        tests=(
            RunPlanTest(
                path="tests/health.hurl",
                tags=("smoke",),
                operation_id="health",
                injected_rule_ids=("global_latency",),
                missing_variables=("base_url",),
                safety=RunSafetyEvidence(
                    protected_environment=True,
                    safety=None,
                    safety_source=None,
                    methods=("PATCH",),
                    blocked_reason=(
                        "mutating method PATCH requires safety metadata in protected environments"
                    ),
                ),
            ),
        ),
    )

    payload = run_execution_plan_to_dict(plan)

    assert schema["properties"]["schema_version"]["const"] == RUN_PLAN_SCHEMA_VERSION
    assert payload == {
        "schema_version": "entroping.run-plan.v1",
        "status": "blocked",
        "message": "Run plan blocked by unresolved Hurl variables",
        "project": "checkout-api",
        "environment": "local",
        "filters": {
            "tag_filters": ["smoke"],
            "tag_expression": None,
            "operation_ids": [],
            "changed_from": "origin/main",
            "selection_label": None,
        },
        "reports": {
            "requested_formats": ["json"],
            "would_write": ["reports/run-latest.json"],
        },
        "execution": {
            "parallel": False,
            "fail_fast": True,
            "drift_check": False,
            "worker_count": 1,
            "timeout_ms": 2500,
            "retry": 1,
        },
        "selection": {
            "discovered_count": 2,
            "selected_count": 1,
            "skipped_count": 1,
        },
        "gates": {
            "effective_rule_ids": ["global_latency"],
            "injected_rule_ids": ["global_latency"],
            "injected_count": 1,
        },
        "variables": {
            "provided_count": 0,
            "missing": [{"name": "base_url", "paths": ["tests/health.hurl"]}],
        },
        "tests": [
            {
                "path": "tests/health.hurl",
                "tags": ["smoke"],
                "operation_id": "health",
                "injected_rule_ids": ["global_latency"],
                "missing_variables": ["base_url"],
                "safety": {
                    "protected_environment": True,
                    "safety": None,
                    "safety_source": None,
                    "methods": ["PATCH"],
                    "blocked_reason": (
                        "mutating method PATCH requires safety metadata in protected environments"
                    ),
                },
            }
        ],
    }


def test_run_delta_report_v1_schema_contract_is_versioned_and_stable() -> None:
    base = RunReport(
        project="checkout-api",
        environment="ci",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=2, passed=1, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="Authorization: Bearer hidden",
                stderr="token=hidden",
            ),
            RunTestReport(
                path="tests/refund.hurl",
                execution_path=".entroping/run/refund.hurl",
                status="failed",
                exit_code=1,
                duration_ms=12,
                rule_ids=("old_gate",),
                stdout="",
                stderr="assert failed",
            ),
        ),
    )
    current = RunReport(
        project="checkout-api",
        environment="ci",
        generated_at="2026-06-04T00:01:00+00:00",
        summary=RunReportSummary(total=2, passed=0, failed=2, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="failed",
                exit_code=1,
                duration_ms=18,
                rule_ids=("global_latency",),
                stdout="Authorization: Bearer hidden",
                stderr="token=hidden",
            ),
            RunTestReport(
                path="tests/refund.hurl",
                execution_path=".entroping/run/refund.hurl",
                status="timeout",
                exit_code=124,
                duration_ms=12,
                rule_ids=("old_gate",),
                stdout="",
                stderr="timeout",
            ),
        ),
    )

    payload = run_delta_report_to_dict(build_run_delta_report(base=base, current=current))

    assert payload == {
        "schema_version": RUN_DELTA_REPORT_SCHEMA_VERSION,
        "status": "fail",
        "base": {
            "project": "checkout-api",
            "environment": "ci",
            "generated_at": "2026-06-04T00:00:00+00:00",
            "total": 2,
        },
        "current": {
            "project": "checkout-api",
            "environment": "ci",
            "generated_at": "2026-06-04T00:01:00+00:00",
            "total": 2,
        },
        "summary": {
            "base_total": 2,
            "current_total": 2,
            "added_failures": 1,
            "resolved_failures": 0,
            "changed_failures": 1,
            "unchanged_failures": 0,
            "latency_deltas": 1,
            "policy_gate_deltas": 1,
        },
        "added_failures": [
            {
                "path": "tests/health.hurl",
                "base_status": "passed",
                "current_status": "failed",
                "base_exit_code": 0,
                "current_exit_code": 1,
                "base_rule_ids": [],
                "current_rule_ids": ["global_latency"],
            }
        ],
        "resolved_failures": [],
        "changed_failures": [
            {
                "path": "tests/refund.hurl",
                "base_status": "failed",
                "current_status": "timeout",
                "base_exit_code": 1,
                "current_exit_code": 124,
                "base_rule_ids": ["old_gate"],
                "current_rule_ids": ["old_gate"],
            }
        ],
        "unchanged_failures": [],
        "latency_deltas": [
            {
                "path": "tests/health.hurl",
                "base_duration_ms": 10,
                "current_duration_ms": 18,
                "delta_ms": 8,
            }
        ],
        "policy_gate_deltas": [
            {
                "path": "tests/health.hurl",
                "added_rule_ids": ["global_latency"],
                "resolved_rule_ids": [],
            }
        ],
    }


def test_agent_run_manifest_v1_schema_declares_versioned_value_free_fields() -> None:
    schema = json.loads((SCHEMA_DIR / "agent-run-manifest.v1.schema.json").read_text())

    assert schema["properties"]["schema_version"]["const"] == AGENT_RUN_MANIFEST_SCHEMA_VERSION
    assert "provider" in schema["properties"]
    assert "cost" in schema["properties"]
    assert "estimated_usd" in schema["properties"]["cost"]["properties"]
    assert "intent_sha256" in schema["properties"]["prompt"]["properties"]
    assert "package_sha256" in schema["properties"]["prompt"]["properties"]
    assert "raw_prompt" not in json.dumps(schema)
    assert "api_key" not in json.dumps(schema)


def test_agent_review_bundle_v1_schema_declares_versioned_value_free_fields() -> None:
    schema = json.loads((SCHEMA_DIR / "agent-review-bundle.v1.schema.json").read_text())

    assert schema["properties"]["schema_version"]["const"] == AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
    assert "roles" in schema["properties"]
    manifest_schema = schema["$defs"]["manifest"]["properties"]
    assert "manifest_path" in manifest_schema
    assert "persona_source_path" in manifest_schema
    assert "validation_status" in manifest_schema
    assert "estimated_cost_usd" in manifest_schema
    serialized = json.dumps(schema)
    assert "raw_prompt" not in serialized
    assert "provider_response" not in serialized
    assert "api_key" not in serialized
    assert "cookie" not in serialized


def test_traffic_artifact_approval_v1_schema_declares_value_free_fields() -> None:
    schema = json.loads((SCHEMA_DIR / "traffic-artifact-approval.v1.schema.json").read_text())

    assert (
        schema["properties"]["schema_version"]["const"] == TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION
    )
    assert "record_fingerprints" in schema["properties"]["source"]["properties"]
    assert "sha256" in schema["properties"]["artifacts"]["items"]["properties"]
    serialized = json.dumps(schema)
    assert "raw_url" not in serialized
    assert "headers" not in serialized
    assert "body_text" not in serialized


def test_drift_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = DriftReport(
        project="checkout-api",
        environment="ci",
        generated_at="2026-05-31T00:00:00+00:00",
        baseline_path=".entroping/drift-baseline.json",
        summary=DriftReportSummary(
            baseline_tests=1,
            current_tests=1,
            findings=1,
            drifted=1,
            missing_baseline=False,
        ),
        findings=(
            DriftFinding(
                kind="assertions_changed",
                severity="warning",
                path="tests/health.hurl",
                message="Injected QAnstitution rule IDs differ from the drift baseline.",
                baseline={"rule_ids": ["global_latency"]},
                current={"rule_ids": ["global_latency", "request_id_header"]},
            ),
        ),
    )

    payload = drift_report_to_dict(report)

    assert payload == {
        "schema_version": "entroping.drift-report.v1",
        "project": "checkout-api",
        "environment": "ci",
        "generated_at": "2026-05-31T00:00:00+00:00",
        "baseline_path": ".entroping/drift-baseline.json",
        "summary": {
            "baseline_tests": 1,
            "current_tests": 1,
            "findings": 1,
            "drifted": 1,
            "missing_baseline": False,
        },
        "findings": [
            {
                "kind": "assertions_changed",
                "severity": "warning",
                "path": "tests/health.hurl",
                "message": "Injected QAnstitution rule IDs differ from the drift baseline.",
                "baseline": {"rule_ids": ["global_latency"]},
                "current": {"rule_ids": ["global_latency", "request_id_header"]},
            }
        ],
    }


def test_drift_baseline_v1_schema_contract_is_versioned_and_stable() -> None:
    baseline = DriftBaseline(
        project="checkout-api",
        environment="ci",
        tests=(
            DriftBaselineTest(
                path="tests/health.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                duration_ms=12,
                response_status_code=200,
                response_headers=(("content-type", "application/json"),),
                response_body_shape=("$:object", "$.ok:boolean"),
            ),
        ),
    )

    payload = drift_baseline_to_dict(baseline)

    assert payload == {
        "schema_version": DRIFT_BASELINE_SCHEMA_VERSION,
        "project": "checkout-api",
        "environment": "ci",
        "tests": [
            {
                "path": "tests/health.hurl",
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 12,
                "rule_ids": ["global_latency"],
                "response": {
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body_shape": ["$:object", "$.ok:boolean"],
                },
            }
        ],
    }


def test_traceability_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = compile_story_traceability(
        [
            HurlTest(
                path=Path("tests/checkout.hurl"),
                metadata=HurlMetadata(
                    tags=frozenset({"smoke"}),
                    meta={
                        "story_id": "CHK-001",
                        "owner": "payments",
                        "doc_url": "https://jira.example.com/browse/CHK-001",
                    },
                ),
            ),
            HurlTest(
                path=Path("tests/unlinked.hurl"),
                metadata=HurlMetadata(),
            ),
        ]
    )

    payload = story_traceability_report_to_dict(report)

    assert payload == {
        "schema_version": "entroping.traceability-report.v1",
        "summary": {"stories": 1, "findings": 1, "passed": False},
        "stories": [
            {
                "story_id": "CHK-001",
                "test_paths": ["tests/checkout.hurl"],
                "story_paths": [],
                "titles": [],
                "owners": ["payments"],
                "doc_urls": ["https://jira.example.com/browse/CHK-001"],
                "tags": ["smoke"],
            }
        ],
        "findings": [
            {
                "kind": "missing_story_id",
                "message": "tests/unlinked.hurl has no # entroping: story_id metadata.",
                "test_path": "tests/unlinked.hurl",
                "story_path": None,
                "doc_url": None,
                "story_ids": [],
            }
        ],
    }


def test_effective_policy_report_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "effective-policy-report.v1.schema.json").read_text())
    report = EffectivePolicyReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        imports=("rules/security.yaml",),
        sources=(
            EffectivePolicySourceReport(
                path="qanstitution.yaml",
                sha256="0" * 64,
                import_chain=("qanstitution.yaml",),
            ),
            EffectivePolicySourceReport(
                path="rules/security.yaml",
                sha256="1" * 64,
                import_chain=("qanstitution.yaml", "rules/security.yaml"),
            ),
        ),
        gates=(
            EffectivePolicyGateReport(
                id="request_id_header",
                source_path="rules/security.yaml",
                import_chain=("qanstitution.yaml", "rules/security.yaml"),
                condition="true",
                gate='header "X-Request-Id" exists',
                enforcement="block",
                final=True,
                description="Require request IDs",
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload == {
        "schema_version": "entroping.effective-policy-report.v1",
        "project": "checkout-api",
        "config_path": "qanstitution.yaml",
        "imports": ["rules/security.yaml"],
        "sources": [
            {
                "path": "qanstitution.yaml",
                "sha256": "0" * 64,
                "import_chain": ["qanstitution.yaml"],
            },
            {
                "path": "rules/security.yaml",
                "sha256": "1" * 64,
                "import_chain": ["qanstitution.yaml", "rules/security.yaml"],
            },
        ],
        "gates": [
            {
                "id": "request_id_header",
                "source_path": "rules/security.yaml",
                "import_chain": ["qanstitution.yaml", "rules/security.yaml"],
                "condition": "true",
                "gate": 'header "X-Request-Id" exists',
                "enforcement": "block",
                "final": True,
                "group": None,
                "description": "Require request IDs",
            }
        ],
    }
    assert schema["properties"]["sources"]["items"]["$ref"] == "#/$defs/source"
    assert schema["$defs"]["source"]["required"] == [
        "path",
        "sha256",
        "import_chain",
    ]
    assert schema["$defs"]["source"]["properties"]["sha256"]["pattern"] == ("^[0-9a-f]{64}$")
    assert "sources" not in schema["required"]
    assert "import_chain" not in schema["$defs"]["gate"]["required"]


def test_effective_policy_report_v1_accepts_legacy_payload_without_additive_provenance() -> None:
    report = EffectivePolicyReport.model_validate(
        {
            "schema_version": "entroping.effective-policy-report.v1",
            "project": "checkout-api",
            "config_path": "qanstitution.yaml",
            "imports": ["rules/security.yaml"],
            "gates": [
                {
                    "id": "request_id_header",
                    "source_path": "rules/security.yaml",
                    "condition": "true",
                    "gate": 'header "X-Request-Id" exists',
                    "enforcement": "block",
                    "final": True,
                    "description": "Require request IDs",
                }
            ],
        }
    )

    assert report.sources == ()
    assert report.gates[0].import_chain == ()


def test_gate_injection_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = GateInjectionReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        summary=GateInjectionSummary(
            total_targets=1,
            total_would_inject=1,
            total_known_failures=1,
        ),
        targets=(
            GateInjectionTargetReport(
                path="tests/health.hurl",
                tags=("smoke",),
                operation_id="getHealth",
                gates=(
                    GateInjectionGateReport(
                        id="global_latency",
                        source_path="qanstitution.yaml",
                        condition="true",
                        gate="duration < 2000",
                        enforcement="block",
                        final=False,
                        status="would_inject",
                    ),
                    GateInjectionGateReport(
                        id="temporary_latency",
                        source_path="rules/security.yaml",
                        condition="tags contains 'smoke'",
                        gate="duration < 500",
                        enforcement="warn",
                        final=True,
                        status="known_failure",
                        group="api_baseline",
                        description="Temporary override",
                        issue_id="GH-123",
                        expires="2999-01-01",
                        reason="Known upstream latency.",
                    ),
                ),
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload == {
        "schema_version": GATE_INJECTION_REPORT_SCHEMA_VERSION,
        "project": "checkout-api",
        "config_path": "qanstitution.yaml",
        "summary": {
            "total_targets": 1,
            "total_would_inject": 1,
            "total_known_failures": 1,
        },
        "targets": [
            {
                "path": "tests/health.hurl",
                "tags": ["smoke"],
                "operation_id": "getHealth",
                "gates": [
                    {
                        "id": "global_latency",
                        "source_path": "qanstitution.yaml",
                        "condition": "true",
                        "gate": "duration < 2000",
                        "enforcement": "block",
                        "final": False,
                        "status": "would_inject",
                        "group": None,
                        "description": None,
                        "issue_id": None,
                        "expires": None,
                        "reason": None,
                    },
                    {
                        "id": "temporary_latency",
                        "source_path": "rules/security.yaml",
                        "condition": "tags contains 'smoke'",
                        "gate": "duration < 500",
                        "enforcement": "warn",
                        "final": True,
                        "status": "known_failure",
                        "group": "api_baseline",
                        "description": "Temporary override",
                        "issue_id": "GH-123",
                        "expires": "2999-01-01",
                        "reason": "Known upstream latency.",
                    },
                ],
            }
        ],
    }


def test_gate_coverage_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = GateCoverageReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        summary=GateCoverageSummary(
            total_gates=2,
            matched_gates=1,
            unmatched_gates=1,
            total_tests=1,
            total_test_matches=1,
        ),
        gates=(
            GateCoverageGateReport(
                id="global_latency",
                source_path="qanstitution.yaml",
                condition="true",
                gate="duration < 2000",
                enforcement="block",
                final=False,
                matched=True,
                tests=(
                    GateCoverageTestReport(
                        path="tests/health.hurl",
                        tags=("smoke",),
                        operation_id="getHealth",
                        exchanges=(GateCoverageExchangeReport(method="GET", path="/health"),),
                    ),
                ),
            ),
            GateCoverageGateReport(
                id="billing_latency",
                source_path="rules/security.yaml",
                condition="path contains 'billing'",
                gate="duration < 500",
                enforcement="warn",
                final=True,
                group="api_baseline",
                description="Billing-specific latency",
                matched=False,
                tests=(),
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload == {
        "schema_version": GATE_COVERAGE_REPORT_SCHEMA_VERSION,
        "project": "checkout-api",
        "config_path": "qanstitution.yaml",
        "summary": {
            "total_gates": 2,
            "matched_gates": 1,
            "unmatched_gates": 1,
            "total_tests": 1,
            "total_test_matches": 1,
        },
        "gates": [
            {
                "id": "global_latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 2000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
                "matched": True,
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "tags": ["smoke"],
                        "operation_id": "getHealth",
                        "exchanges": [
                            {
                                "method": "GET",
                                "path": "/health",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "billing_latency",
                "source_path": "rules/security.yaml",
                "condition": "path contains 'billing'",
                "gate": "duration < 500",
                "enforcement": "warn",
                "final": True,
                "group": "api_baseline",
                "description": "Billing-specific latency",
                "matched": False,
                "tests": [],
            },
        ],
    }


def test_test_quality_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = QualityReportModel(
        project="checkout-api",
        summary=QualitySummaryModel(
            total_tests=2,
            generated_tests=1,
            manual_tests=1,
            score=72,
            status="warn",
            findings=2,
        ),
        findings=(
            QualityFindingModel(
                category="missing-negative-path",
                severity="medium",
                path=None,
                message="Generated-test corpus has no negative-path metadata.",
                evidence="corpus metadata",
                deduction=10,
            ),
        ),
        tests=(
            QualityTestReportModel(
                path="tests/generated/checkout.hurl",
                source="openapi",
                operation_id="createCheckout",
                tags=("generated", "smoke"),
                score=72,
                findings=(
                    QualityFindingModel(
                        category="assertion-strength",
                        severity="medium",
                        path="tests/generated/checkout.hurl",
                        message="Generated test has fewer than two response assertions.",
                        evidence="assertion count",
                        deduction=15,
                    ),
                ),
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload == {
        "schema_version": TEST_QUALITY_REPORT_SCHEMA_VERSION,
        "project": "checkout-api",
        "summary": {
            "total_tests": 2,
            "generated_tests": 1,
            "manual_tests": 1,
            "score": 72,
            "status": "warn",
            "findings": 2,
        },
        "findings": [
            {
                "category": "missing-negative-path",
                "severity": "medium",
                "path": None,
                "message": "Generated-test corpus has no negative-path metadata.",
                "evidence": "corpus metadata",
                "deduction": 10,
            }
        ],
        "tests": [
            {
                "path": "tests/generated/checkout.hurl",
                "source": "openapi",
                "operation_id": "createCheckout",
                "negative_category": None,
                "security": None,
                "tags": ["generated", "smoke"],
                "score": 72,
                "findings": [
                    {
                        "category": "assertion-strength",
                        "severity": "medium",
                        "path": "tests/generated/checkout.hurl",
                        "message": "Generated test has fewer than two response assertions.",
                        "evidence": "assertion count",
                        "deduction": 15,
                    }
                ],
            }
        ],
    }
    schema = json.loads((SCHEMA_DIR / "test-quality-report.v1.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == TEST_QUALITY_REPORT_SCHEMA_VERSION


def test_test_pyramid_report_v1_schema_contract_is_versioned_and_stable() -> None:
    report = PyramidReportModel(
        project="checkout-api",
        summary=PyramidSummaryModel(
            total_layers=2,
            present_layers=1,
            attention_layers=1,
            findings=1,
            runtime_governance_status="incomplete",
        ),
        layers=(
            PyramidLayerModel(
                id="runtime-api-proof",
                label="Runtime API Proof",
                status="incomplete",
                summary="some required evidence missing",
                artifacts=(
                    PyramidArtifactEvidenceModel(
                        id="run-json",
                        label="Run JSON",
                        path="reports/run-latest.json",
                        state="present",
                        schema_version="entroping.run-report.v1",
                        summary="Run JSON present",
                    ),
                    PyramidArtifactEvidenceModel(
                        id="junit-xml",
                        label="JUnit XML",
                        path="reports/junit.xml",
                        state="missing",
                        schema_version="junit.xml",
                        summary="missing",
                    ),
                ),
            ),
            PyramidLayerModel(
                id="policy-governance",
                label="Policy Governance",
                status="present",
                summary="all required evidence present",
                artifacts=(
                    PyramidArtifactEvidenceModel(
                        id="gate-coverage-json",
                        label="Gate Coverage JSON",
                        path="reports/gate-coverage.json",
                        state="present",
                        schema_version="entroping.gate-coverage-report.v1",
                        summary="Gate Coverage JSON present",
                    ),
                ),
            ),
        ),
        findings=(
            PyramidFindingModel(
                severity="high",
                layer_id="runtime-api-proof",
                artifact_id="junit-xml",
                state="missing",
                message="Runtime governance proof is missing for JUnit XML evidence.",
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload == {
        "schema_version": TEST_PYRAMID_REPORT_SCHEMA_VERSION,
        "project": "checkout-api",
        "summary": {
            "total_layers": 2,
            "present_layers": 1,
            "attention_layers": 1,
            "findings": 1,
            "runtime_governance_status": "incomplete",
        },
        "layers": [
            {
                "id": "runtime-api-proof",
                "label": "Runtime API Proof",
                "status": "incomplete",
                "summary": "some required evidence missing",
                "artifacts": [
                    {
                        "id": "run-json",
                        "label": "Run JSON",
                        "path": "reports/run-latest.json",
                        "state": "present",
                        "schema_version": "entroping.run-report.v1",
                        "summary": "Run JSON present",
                    },
                    {
                        "id": "junit-xml",
                        "label": "JUnit XML",
                        "path": "reports/junit.xml",
                        "state": "missing",
                        "schema_version": "junit.xml",
                        "summary": "missing",
                    },
                ],
            },
            {
                "id": "policy-governance",
                "label": "Policy Governance",
                "status": "present",
                "summary": "all required evidence present",
                "artifacts": [
                    {
                        "id": "gate-coverage-json",
                        "label": "Gate Coverage JSON",
                        "path": "reports/gate-coverage.json",
                        "state": "present",
                        "schema_version": "entroping.gate-coverage-report.v1",
                        "summary": "Gate Coverage JSON present",
                    },
                ],
            },
        ],
        "findings": [
            {
                "severity": "high",
                "layer_id": "runtime-api-proof",
                "artifact_id": "junit-xml",
                "state": "missing",
                "message": "Runtime governance proof is missing for JUnit XML evidence.",
            }
        ],
    }
    schema = json.loads((SCHEMA_DIR / "test-pyramid-report.v1.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == TEST_PYRAMID_REPORT_SCHEMA_VERSION


def test_report_artifact_manifest_v1_schema_contract_is_versioned_and_stable() -> None:
    manifest = ReportArtifactManifest(
        summary=ReportArtifactManifestSummary(
            total_expected=2,
            total_present=1,
            total_missing=1,
        ),
        artifacts=(
            ReportArtifactEntry(
                kind="run_json",
                path="reports/run-latest.json",
                schema_version="entroping.run-report.v1",
                size_bytes=17,
                sha256="0" * 64,
            ),
        ),
        missing_artifacts=(
            ReportArtifactMissing(
                kind="junit",
                path="reports/junit.xml",
            ),
        ),
        audit=ReportArtifactAuditEvidence(
            chain_path=".entroping/report-audit-chain.jsonl",
            verification=ReportArtifactAuditVerification(
                status="verified",
                checked_events=1,
                latest_event_hash="1" * 64,
                diagnostics=(),
            ),
            event=ReportArtifactAuditEvent(
                schema_version="entroping.report-audit-event.v1",
                event_type="report_artifact_manifest",
                sequence=1,
                generated_at="2026-06-12T00:00:00+00:00",
                previous_event_hash=None,
                command=ReportArtifactAuditCommand(
                    name="entroping report artifact-manifest",
                    output_path="reports/artifact-manifest.json",
                ),
                summary=ReportArtifactManifestSummary(
                    total_expected=2,
                    total_present=1,
                    total_missing=1,
                ),
                artifacts=(
                    ReportArtifactEntry(
                        kind="run_json",
                        path="reports/run-latest.json",
                        schema_version="entroping.run-report.v1",
                        size_bytes=17,
                        sha256="0" * 64,
                    ),
                ),
                event_hash="1" * 64,
            ),
        ),
    )

    payload = manifest.model_dump(mode="json")

    assert payload == {
        "schema_version": REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "summary": {
            "total_expected": 2,
            "total_present": 1,
            "total_missing": 1,
        },
        "artifacts": [
            {
                "kind": "run_json",
                "path": "reports/run-latest.json",
                "schema_version": "entroping.run-report.v1",
                "size_bytes": 17,
                "sha256": "0" * 64,
            }
        ],
        "missing_artifacts": [
            {
                "kind": "junit",
                "path": "reports/junit.xml",
            }
        ],
        "audit": {
            "chain_path": ".entroping/report-audit-chain.jsonl",
            "verification": {
                "status": "verified",
                "checked_events": 1,
                "latest_event_hash": "1" * 64,
                "diagnostics": [],
            },
            "event": {
                "schema_version": "entroping.report-audit-event.v1",
                "event_type": "report_artifact_manifest",
                "sequence": 1,
                "generated_at": "2026-06-12T00:00:00+00:00",
                "previous_event_hash": None,
                "command": {
                    "name": "entroping report artifact-manifest",
                    "output_path": "reports/artifact-manifest.json",
                },
                "summary": {
                    "total_expected": 2,
                    "total_present": 1,
                    "total_missing": 1,
                },
                "artifacts": [
                    {
                        "kind": "run_json",
                        "path": "reports/run-latest.json",
                        "schema_version": "entroping.run-report.v1",
                        "size_bytes": 17,
                        "sha256": "0" * 64,
                    }
                ],
                "event_hash": "1" * 64,
            },
        },
    }


def test_evidence_bundle_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-bundle.v1.schema.json").read_text())
    bundle = EvidenceBundleReport(
        generated_at="2026-06-18T00:00:00+00:00",
        purpose="design-partner-upload-readiness",
        project="checkout-api",
        summary=EvidenceBundleSummary(
            status="not_ready",
            required_total=3,
            required_present=2,
            required_missing=1,
            required_invalid=1,
            artifacts_total=2,
            diagnostics_total=2,
        ),
        artifacts=(
            EvidenceBundleArtifact(
                kind="run_json",
                path="reports/run-latest.json",
                required=True,
                schema_version="entroping.run-report.v1",
                size_bytes=17,
                sha256="0" * 64,
            ),
        ),
        missing_artifacts=(
            EvidenceBundleMissingArtifact(
                kind="effective_policy",
                path="reports/effective-policy.json",
                required=True,
            ),
        ),
        diagnostics=(
            EvidenceBundleDiagnostic(
                severity="error",
                code="missing_required_artifact",
                path="reports/effective-policy.json",
                message="Required evidence artifact is missing.",
                remediation_hint="entroping report policy --output json",
            ),
        ),
        manifest_audit=EvidenceBundleManifestAudit(
            path="reports/artifact-manifest.json",
            status="verified",
            chain_path=".entroping/report-audit-chain.jsonl",
            checked_events=1,
            latest_event_hash="1" * 64,
            diagnostics=(),
        ),
    )

    payload = bundle.model_dump(mode="json")

    assert EVIDENCE_BUNDLE_SCHEMA_VERSION == "entroping.evidence-bundle.v1"
    assert payload == {
        "schema_version": "entroping.evidence-bundle.v1",
        "generated_at": "2026-06-18T00:00:00+00:00",
        "purpose": "design-partner-upload-readiness",
        "project": "checkout-api",
        "summary": {
            "status": "not_ready",
            "required_total": 3,
            "required_present": 2,
            "required_missing": 1,
            "required_invalid": 1,
            "artifacts_total": 2,
            "diagnostics_total": 2,
        },
        "artifacts": [
            {
                "kind": "run_json",
                "path": "reports/run-latest.json",
                "required": True,
                "schema_version": "entroping.run-report.v1",
                "size_bytes": 17,
                "sha256": "0" * 64,
            }
        ],
        "missing_artifacts": [
            {
                "kind": "effective_policy",
                "path": "reports/effective-policy.json",
                "required": True,
            }
        ],
        "diagnostics": [
            {
                "severity": "error",
                "code": "missing_required_artifact",
                "path": "reports/effective-policy.json",
                "message": "Required evidence artifact is missing.",
                "remediation_hint": "entroping report policy --output json",
            }
        ],
        "manifest_audit": {
            "path": "reports/artifact-manifest.json",
            "status": "verified",
            "chain_path": ".entroping/report-audit-chain.jsonl",
            "checked_events": 1,
            "latest_event_hash": "1" * 64,
            "diagnostics": [],
        },
    }
    assert schema["properties"]["schema_version"]["const"] == EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert schema["$defs"]["artifact"]["properties"]["sha256"]["pattern"] == ("^[0-9a-f]{64}$")
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "not_ready",
    ]
    assert schema["$defs"]["diagnostic"]["properties"]["remediation_hint"] == {
        "type": [
            "string",
            "null",
        ]
    }
    assert "remediation_hint" not in schema["$defs"]["diagnostic"]["required"]


def test_structured_diagnostics_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "diagnostics.v1.schema.json").read_text())
    event = StructuredDiagnosticEvent(
        timestamp="2026-06-19T00:00:00+00:00",
        component="run",
        operation="hurl.timeout",
        severity="warning",
        code="hurl_timeout",
        summary="Hurl subprocess timed out.",
        attributes=(
            StructuredDiagnosticAttribute(name="duration_ms", value=125),
            StructuredDiagnosticAttribute(name="artifact_path", value="reports/run-latest.json"),
        ),
    )

    payload = event.model_dump(mode="json")

    assert payload == {
        "schema_version": "entroping.diagnostics.v1",
        "timestamp": "2026-06-19T00:00:00+00:00",
        "component": "run",
        "operation": "hurl.timeout",
        "severity": "warning",
        "code": "hurl_timeout",
        "summary": "Hurl subprocess timed out.",
        "attributes": [
            {"name": "duration_ms", "value": 125},
            {"name": "artifact_path", "value": "reports/run-latest.json"},
        ],
    }
    assert STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION == "entroping.diagnostics.v1"
    assert schema["properties"]["schema_version"]["const"] == (
        STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION
    )
    assert schema["properties"]["severity"]["enum"] == [
        "debug",
        "info",
        "warning",
        "error",
    ]
    assert schema["$defs"]["attribute"]["properties"]["value"]["type"] == [
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    ]


def test_runtime_card_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "runtime-card.v1.schema.json").read_text())
    card = RuntimeCardReport(
        summary=RuntimeCardSummary(status="fail", findings=1, evidence_links=2),
        run=RuntimeCardRunEvidence(
            project="checkout-api",
            environment="ci",
            total=2,
            passed=1,
            failed=1,
            exit_code=1,
            failed_tests=1,
            failed_gate_ids=("global_latency",),
        ),
        drift=RuntimeCardDriftEvidence(
            status="drift",
            findings=1,
            drifted=1,
            missing_baseline=False,
        ),
        redaction=RuntimeCardRedactionEvidence(
            status="attention",
            total_records=3,
            redacted_records=2,
            unredacted_records=1,
            low_confidence_categories=("low-confidence-body",),
        ),
        release=RuntimeCardReleaseEvidence(
            artifact_manifest_audit_status="verified",
            evidence_bundle_status="ready",
            evidence_links=("reports/evidence-bundle.json", "reports/run-latest.json"),
        ),
        pilot_readiness=RuntimeCardPilotReadiness(
            status="ready",
            path="reports/evidence-bundle.json",
            missing_artifacts=0,
            invalid_artifacts=0,
            checksum_mismatches=0,
            diagnostics=0,
            manifest_audit_status="verified",
        ),
        test_pyramid=RuntimeCardTestPyramidEvidence(
            status="incomplete",
            path="reports/test-pyramid.json",
            total_layers=6,
            present_layers=4,
            attention_layers=2,
            findings=2,
        ),
        agent_provenance=RuntimeCardAgentProvenance(
            status="attention",
            configured_roles=2,
            manifests=2,
            findings=1,
        ),
        artifacts=(
            RuntimeCardArtifact(
                name="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
            ),
        ),
        findings=(
            RuntimeCardFinding(
                severity="warning",
                code="drift_attention",
                path="reports/drift.json",
                message="Drift evidence requires reviewer attention.",
            ),
        ),
    )

    payload = card.model_dump(mode="json")

    assert RUNTIME_CARD_SCHEMA_VERSION == "entroping.runtime-card.v1"
    assert payload["schema_version"] == "entroping.runtime-card.v1"
    assert payload["summary"] == {"status": "fail", "findings": 1, "evidence_links": 2}
    assert payload["run"]["failed_gate_ids"] == ["global_latency"]
    assert payload["pilot_readiness"] == {
        "status": "ready",
        "path": "reports/evidence-bundle.json",
        "missing_artifacts": 0,
        "invalid_artifacts": 0,
        "checksum_mismatches": 0,
        "diagnostics": 0,
        "manifest_audit_status": "verified",
    }
    assert payload["test_pyramid"] == {
        "status": "incomplete",
        "path": "reports/test-pyramid.json",
        "total_layers": 6,
        "present_layers": 4,
        "attention_layers": 2,
        "findings": 2,
    }
    assert schema["properties"]["schema_version"]["const"] == RUNTIME_CARD_SCHEMA_VERSION
    assert schema["properties"]["pilot_readiness"]["$ref"] == "#/$defs/pilot_readiness"
    assert schema["properties"]["test_pyramid"]["$ref"] == "#/$defs/test_pyramid"
    assert "pilot_readiness" not in schema["required"]
    assert "test_pyramid" not in schema["required"]
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "pass",
        "attention",
        "fail",
    ]
    assert schema["$defs"]["pilot_readiness"]["properties"]["status"]["enum"] == [
        "ready",
        "not_ready",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["test_pyramid"]["properties"]["status"]["enum"] == [
        "complete",
        "incomplete",
        "missing",
    ]


def test_pilot_metrics_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "pilot-metrics.v1.schema.json").read_text())
    report = PilotMetricsReport(
        generated_at="2026-06-19T00:00:00+00:00",
        project="checkout-api",
        summary=PilotMetricsSummary(
            status="partial",
            metrics_total=6,
            metrics_known=2,
            metrics_unknown=0,
            metrics_manual_input_required=4,
            sources_total=5,
            sources_present=2,
            sources_missing=3,
            sources_invalid=0,
            sources_unsafe=0,
        ),
        metrics=(
            PilotMetric(
                id="evidence_bundle_ready_rate",
                label="Evidence bundle ready rate",
                state="known",
                value=1.0,
                unit="ratio",
                numerator=1,
                denominator=1,
                summary="One local evidence bundle is ready.",
                source_paths=("reports/evidence-bundle.json",),
            ),
            PilotMetric(
                id="setup_time_minutes",
                label="Setup time",
                state="manual_input_required",
                value=None,
                unit="minutes",
                numerator=None,
                denominator=None,
                summary="Requires design-partner timing input.",
                source_paths=(),
            ),
        ),
        sources=(
            PilotEvidenceSource(
                id="evidence_bundle",
                label="Evidence bundle",
                path="reports/evidence-bundle.json",
                state="present",
                schema_version="entroping.evidence-bundle.v1",
                summary="ready",
            ),
            PilotEvidenceSource(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="missing",
                schema_version=None,
                summary="Artifact is missing.",
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert PILOT_METRICS_SCHEMA_VERSION == "entroping.pilot-metrics.v1"
    assert payload == {
        "schema_version": "entroping.pilot-metrics.v1",
        "generated_at": "2026-06-19T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "metrics_total": 6,
            "metrics_known": 2,
            "metrics_unknown": 0,
            "metrics_manual_input_required": 4,
            "sources_total": 5,
            "sources_present": 2,
            "sources_missing": 3,
            "sources_invalid": 0,
            "sources_unsafe": 0,
        },
        "metrics": [
            {
                "id": "evidence_bundle_ready_rate",
                "label": "Evidence bundle ready rate",
                "state": "known",
                "value": 1.0,
                "unit": "ratio",
                "numerator": 1,
                "denominator": 1,
                "summary": "One local evidence bundle is ready.",
                "source_paths": ["reports/evidence-bundle.json"],
            },
            {
                "id": "setup_time_minutes",
                "label": "Setup time",
                "state": "manual_input_required",
                "value": None,
                "unit": "minutes",
                "numerator": None,
                "denominator": None,
                "summary": "Requires design-partner timing input.",
                "source_paths": [],
            },
        ],
        "sources": [
            {
                "id": "evidence_bundle",
                "label": "Evidence bundle",
                "path": "reports/evidence-bundle.json",
                "state": "present",
                "schema_version": "entroping.evidence-bundle.v1",
                "summary": "ready",
            },
            {
                "id": "runtime_card",
                "label": "Runtime card",
                "path": "reports/runtime-card.json",
                "state": "missing",
                "schema_version": None,
                "summary": "Artifact is missing.",
            },
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == PILOT_METRICS_SCHEMA_VERSION
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["metric"]["properties"]["state"]["enum"] == [
        "known",
        "unknown",
        "manual_input_required",
    ]
    assert schema["$defs"]["source"]["properties"]["state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]


def test_handoff_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "handoff.v1.schema.json").read_text())
    packet = HandoffPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        git=HandoffGit(branch="main", commit="1" * 40),
        summary=HandoffSummary(
            status="ready",
            artifacts_total=5,
            artifacts_present=5,
            artifacts_missing=0,
            artifacts_invalid=0,
            artifacts_unsafe=0,
        ),
        runtime=HandoffRuntimeSummary(
            status="attention",
            findings=2,
            evidence_links=3,
            failed_gate_ids=1,
            pilot_readiness_status="ready",
            test_pyramid_status="complete",
        ),
        artifacts=(
            HandoffArtifact(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="attention; 2 findings",
            ),
        ),
        targets=(
            HandoffTarget(
                id="cli",
                label="CLI",
                next_action="Open the local handoff packet.",
                artifact_paths=("reports/handoff.json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert HANDOFF_SCHEMA_VERSION == "entroping.handoff.v1"
    assert payload == {
        "schema_version": "entroping.handoff.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "git": {"branch": "main", "commit": "1" * 40},
        "summary": {
            "status": "ready",
            "artifacts_total": 5,
            "artifacts_present": 5,
            "artifacts_missing": 0,
            "artifacts_invalid": 0,
            "artifacts_unsafe": 0,
        },
        "runtime": {
            "status": "attention",
            "findings": 2,
            "evidence_links": 3,
            "failed_gate_ids": 1,
            "pilot_readiness_status": "ready",
            "test_pyramid_status": "complete",
        },
        "artifacts": [
            {
                "id": "runtime_card",
                "label": "Runtime card",
                "path": "reports/runtime-card.json",
                "state": "present",
                "schema_version": "entroping.runtime-card.v1",
                "sha256": "a" * 64,
                "summary": "attention; 2 findings",
            }
        ],
        "targets": [
            {
                "id": "cli",
                "label": "CLI",
                "next_action": "Open the local handoff packet.",
                "artifact_paths": ["reports/handoff.json"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == HANDOFF_SCHEMA_VERSION
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["artifact"]["properties"]["state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["artifact"]["properties"]["sha256"]["pattern"] == ("^[0-9a-f]{64}$")
    assert schema["$defs"]["target"]["properties"]["id"]["enum"] == [
        "cli",
        "pr",
        "desktop",
        "cloud",
        "mobile",
        "agent",
    ]


def test_notification_packet_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "notification-packet.v1.schema.json").read_text())
    packet = NotificationPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=NotificationSummary(
            status="ready",
            severity="blocker",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
        ),
        runtime=NotificationRuntimeSummary(
            status="attention",
            findings=2,
            evidence_links=3,
            failed_gate_ids=1,
        ),
        sources=(
            NotificationSource(
                id="handoff",
                label="Cross-surface handoff",
                path="reports/handoff.json",
                state="present",
                schema_version="entroping.handoff.v1",
                sha256="a" * 64,
                summary="ready handoff evidence",
            ),
        ),
        messages=(
            NotificationMessage(
                surface="jira",
                label="Jira",
                severity="blocker",
                title="Entroping runtime governance needs attention",
                body="Runtime status attention; 1 failed gates; 1/1 sources present.",
                next_action="Attach this packet as read-only issue evidence.",
                artifact_paths=("reports/notification-packet.json", "reports/handoff.json"),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert NOTIFICATION_PACKET_SCHEMA_VERSION == "entroping.notification-packet.v1"
    assert payload == {
        "schema_version": "entroping.notification-packet.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "blocker",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
        },
        "runtime": {
            "status": "attention",
            "findings": 2,
            "evidence_links": 3,
            "failed_gate_ids": 1,
        },
        "sources": [
            {
                "id": "handoff",
                "label": "Cross-surface handoff",
                "path": "reports/handoff.json",
                "state": "present",
                "schema_version": "entroping.handoff.v1",
                "sha256": "a" * 64,
                "summary": "ready handoff evidence",
            }
        ],
        "messages": [
            {
                "surface": "jira",
                "label": "Jira",
                "severity": "blocker",
                "title": "Entroping runtime governance needs attention",
                "body": "Runtime status attention; 1 failed gates; 1/1 sources present.",
                "next_action": "Attach this packet as read-only issue evidence.",
                "artifact_paths": [
                    "reports/notification-packet.json",
                    "reports/handoff.json",
                ],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.notification-packet.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["summary"]["properties"]["severity"]["enum"] == [
        "info",
        "attention",
        "blocker",
    ]
    assert schema["$defs"]["message"]["properties"]["surface"]["enum"] == [
        "jira",
        "linear",
        "monday",
        "slack",
        "discord",
        "workato",
        "agent",
    ]


def test_team_evidence_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "team-evidence-readiness.v1.schema.json").read_text())
    packet = TeamEvidenceReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=TeamEvidenceReadinessSummary(
            status="partial",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            areas_total=1,
            areas_ready=0,
            areas_attention=1,
            areas_blocked=0,
            blockers_total=1,
            next_actions_total=1,
        ),
        cloud_boundary=TeamEvidenceCloudBoundary(
            explicit_user_intent_required=True,
            upload_implemented=False,
            access_control_audit_required=True,
            forbidden_data_classes=(
                "raw_traffic",
                "secrets",
                "source_hurl",
                "env_values",
                "prompts",
                "provider_outputs",
                "full_report_contents",
            ),
            boundary_summary="Local readiness view only.",
        ),
        sources=(
            TeamEvidenceSource(
                id="evidence_bundle",
                label="Evidence bundle",
                path="reports/evidence-bundle.json",
                state="present",
                schema_version="entroping.evidence-bundle.v1",
                sha256="a" * 64,
                summary="ready; 3/3 required present",
            ),
        ),
        readiness_areas=(
            TeamEvidenceReadinessArea(
                id="upload_boundary",
                label="Upload boundary",
                status="attention",
                source_ids=("evidence_bundle",),
                boundary="Existing evidence bundle must be reviewed before upload.",
                blockers=("Manual cloud approval is missing.",),
                next_action="Review sanitized evidence before team evidence promotion.",
            ),
        ),
        next_actions=(
            TeamEvidenceNextAction(
                priority="medium",
                action="Review sanitized evidence before team evidence promotion.",
                source_ids=("evidence_bundle",),
                area_ids=("upload_boundary",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert TEAM_EVIDENCE_READINESS_SCHEMA_VERSION == "entroping.team-evidence-readiness.v1"
    assert payload == {
        "schema_version": "entroping.team-evidence-readiness.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "areas_total": 1,
            "areas_ready": 0,
            "areas_attention": 1,
            "areas_blocked": 0,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "cloud_boundary": {
            "explicit_user_intent_required": True,
            "upload_implemented": False,
            "access_control_audit_required": True,
            "forbidden_data_classes": [
                "raw_traffic",
                "secrets",
                "source_hurl",
                "env_values",
                "prompts",
                "provider_outputs",
                "full_report_contents",
            ],
            "boundary_summary": "Local readiness view only.",
        },
        "sources": [
            {
                "id": "evidence_bundle",
                "label": "Evidence bundle",
                "path": "reports/evidence-bundle.json",
                "state": "present",
                "schema_version": "entroping.evidence-bundle.v1",
                "sha256": "a" * 64,
                "summary": "ready; 3/3 required present",
            }
        ],
        "readiness_areas": [
            {
                "id": "upload_boundary",
                "label": "Upload boundary",
                "status": "attention",
                "source_ids": ["evidence_bundle"],
                "boundary": "Existing evidence bundle must be reviewed before upload.",
                "blockers": ["Manual cloud approval is missing."],
                "next_action": "Review sanitized evidence before team evidence promotion.",
            }
        ],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Review sanitized evidence before team evidence promotion.",
                "source_ids": ["evidence_bundle"],
                "area_ids": ["upload_boundary"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.team-evidence-readiness.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["area_id"]["enum"] == [
        "upload_boundary",
        "runtime_visibility",
        "design_partner_pilot",
        "cross_surface_continuity",
        "notification_linkout",
        "cloud_boundary_controls",
    ]
    assert schema["$defs"]["forbidden_data_class"]["enum"] == [
        "raw_traffic",
        "secrets",
        "source_hurl",
        "env_values",
        "prompts",
        "provider_outputs",
        "full_report_contents",
    ]


def test_team_access_control_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "team-access-control-plan.v1.schema.json").read_text())
    packet = TeamAccessControlPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=TeamAccessControlPlanSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            roles_total=1,
            roles_ready=1,
            roles_attention=0,
            roles_blocked=0,
            audit_events_total=1,
            blockers_total=0,
            next_actions_total=1,
        ),
        boundary=TeamAccessControlBoundary(
            explicit_user_intent_required=True,
            upload_implemented=False,
            access_control_enforced=False,
            write_back_implemented=False,
            pass_fail_override_allowed=False,
            forbidden_data_classes=(
                "raw_traffic",
                "secrets",
                "source_hurl",
                "env_values",
                "prompts",
                "provider_outputs",
                "full_report_contents",
            ),
            boundary_summary="Local access-control plan only.",
        ),
        sources=(
            TeamAccessControlSource(
                id="team_evidence_readiness",
                label="Team evidence readiness",
                path="reports/team-evidence-readiness.json",
                state="present",
                schema_version="entroping.team-evidence-readiness.v1",
                sha256="a" * 64,
                summary="ready; 1/1 sources present; 1/1 areas ready",
            ),
        ),
        roles=(
            TeamAccessControlRolePlan(
                id="owner",
                label="Owner",
                status="ready",
                allowed_actions=("view_value_free_evidence", "acknowledge_status"),
                forbidden_actions=(
                    "override_hurl_qanstitution_result",
                    "view_raw_traffic",
                    "silent_upload",
                ),
                evidence_scope="Can review sanitized evidence references.",
                audit_event_ids=("evidence_viewed", "status_acknowledged"),
                blockers=(),
                next_action="Owner access-control plan is ready for local review.",
            ),
        ),
        audit_events=(
            TeamAccessControlAuditEvent(
                id="evidence_viewed",
                label="Evidence viewed",
                trigger="A future team surface renders sanitized evidence.",
                required_fields=("actor_role", "artifact_id", "timestamp"),
                forbidden_fields=("raw_traffic", "secrets"),
            ),
        ),
        next_actions=(
            TeamAccessControlNextAction(
                priority="medium",
                action="Review team access-control plan before hosted evidence.",
                source_ids=("team_evidence_readiness",),
                role_ids=("owner",),
                audit_event_ids=("evidence_viewed",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION == "entroping.team-access-control-plan.v1"
    assert payload["schema_version"] == "entroping.team-access-control-plan.v1"
    assert payload["boundary"]["upload_implemented"] is False
    assert payload["boundary"]["access_control_enforced"] is False
    assert payload["roles"][0]["forbidden_actions"] == [
        "override_hurl_qanstitution_result",
        "view_raw_traffic",
        "silent_upload",
    ]
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.team-access-control-plan.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["boundary"]["$ref"] == "#/$defs/boundary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "team_evidence_readiness",
        "handoff",
        "notification_packet",
        "runtime_card",
    ]
    assert schema["$defs"]["role_id"]["enum"] == [
        "owner",
        "maintainer",
        "reviewer",
        "observer",
        "external_design_partner",
    ]
    assert schema["$defs"]["allowed_action"]["enum"] == [
        "view_value_free_evidence",
        "share_evidence_link",
        "acknowledge_status",
        "plan_follow_up_assignment",
    ]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "override_hurl_qanstitution_result",
        "view_raw_traffic",
        "view_source_hurl",
        "view_provider_transcripts",
        "view_secrets_or_env",
        "silent_upload",
        "mutate_tickets_or_chat",
    ]
    assert schema["$defs"]["forbidden_data_class"]["enum"] == [
        "raw_traffic",
        "secrets",
        "source_hurl",
        "env_values",
        "prompts",
        "provider_outputs",
        "full_report_contents",
    ]
    assert schema["$defs"]["audit_event_id"]["enum"] == [
        "evidence_viewed",
        "evidence_link_shared",
        "status_acknowledged",
        "follow_up_assignment_planned",
        "access_policy_reviewed",
        "upload_intent_recorded",
    ]


def test_devex_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "devex-readiness.v1.schema.json").read_text())
    packet = DevexReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=DevexReadinessSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            families_total=1,
            families_ready=1,
            families_attention=0,
            families_blocked=0,
            blockers_total=0,
            next_actions_total=1,
        ),
        sources=(
            DevexReadinessSource(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass; 0 findings",
            ),
        ),
        families=(
            DevexReadinessFamily(
                id="editor",
                label="Editor",
                status="ready",
                surface_ids=("vscode", "editor"),
                required_source_ids=("runtime_card", "evidence_index"),
                present_source_ids=("runtime_card",),
                missing_source_ids=("evidence_index",),
                blockers=(),
                link_requirements=("artifact_id", "source_sha256"),
                action_requirements=("actor_role", "explicit_user_action"),
                forbidden_actions=("execute_hurl", "implement_app_surface"),
                next_action="Expose value-free run status and problem-matchable evidence.",
            ),
        ),
        next_actions=(
            DevexReadinessNextAction(
                priority="medium",
                action="Generate evidence-index evidence before editor surfaces.",
                source_ids=("evidence_index",),
                family_ids=("editor",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert DEVEX_READINESS_SCHEMA_VERSION == "entroping.devex-readiness.v1"
    assert payload["schema_version"] == "entroping.devex-readiness.v1"
    assert payload["families"][0]["surface_ids"] == ["vscode", "editor"]
    assert payload["families"][0]["forbidden_actions"] == [
        "execute_hurl",
        "implement_app_surface",
    ]
    assert schema["properties"]["schema_version"]["const"] == "entroping.devex-readiness.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "runtime_card",
        "handoff",
        "evidence_index",
        "integration_readiness",
        "notification_packet",
        "team_access_control_plan",
    ]
    assert schema["$defs"]["family_id"]["enum"] == [
        "cli",
        "editor",
        "local_workbench",
        "pr_runtime_card",
        "desktop",
        "cloud",
        "mobile",
    ]
    assert schema["$defs"]["surface_id"]["enum"] == [
        "cli",
        "vscode",
        "editor",
        "local_workbench",
        "pr_runtime_card",
        "desktop",
        "cloud",
        "mobile",
    ]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "execute_hurl",
        "run_tests",
        "call_external_api",
        "invoke_model_provider",
        "upload_artifacts",
        "mutate_external_system",
        "read_provider_keys",
        "override_hurl_qanstitution_result",
        "sync_raw_repo_or_vault",
        "render_raw_artifact_contents",
        "implement_app_surface",
    ]


def test_evidence_cloud_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-cloud-readiness.v1.schema.json").read_text())
    packet = EvidenceCloudReadinessPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceCloudSummary(
            status="ready",
            sources_total=2,
            sources_present=2,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            areas_total=1,
            areas_ready=1,
            areas_attention=0,
            areas_blocked=0,
            upload_candidates_total=1,
            upload_candidates_ready=1,
            upload_candidates_blocked=0,
            blockers_total=0,
            next_actions_total=1,
        ),
        cloud_boundary=EvidenceCloudBoundary(
            explicit_user_intent_required=True,
            upload_implemented=False,
            hosted_sync_implemented=False,
            access_control_audit_required=True,
            forbidden_data_classes=("raw_traffic", "secrets", "full_report_contents"),
            boundary_summary="local-only readiness packet",
        ),
        sources=(
            EvidenceCloudSource(
                id="team_evidence_readiness",
                label="Team evidence readiness",
                path="reports/team-evidence-readiness.json",
                state="present",
                schema_version="entroping.team-evidence-readiness.v1",
                sha256="a" * 64,
                summary="ready; 6/6 sources present",
            ),
            EvidenceCloudSource(
                id="evidence_bundle",
                label="Evidence bundle",
                path="reports/evidence-bundle.json",
                state="present",
                schema_version="entroping.evidence-bundle.v1",
                sha256="b" * 64,
                summary="ready",
            ),
        ),
        readiness_areas=(
            EvidenceCloudReadinessArea(
                id="team_upload_boundary",
                label="Team upload boundary",
                status="ready",
                source_ids=("team_evidence_readiness", "evidence_bundle"),
                boundary="Future cloud surfaces may reference sanitized metadata only.",
                upload_candidate=True,
                blockers=(),
                next_action="Review local Evidence Cloud pilot metadata.",
            ),
        ),
        upload_candidates=(
            EvidenceCloudUploadCandidate(
                id="team_evidence_bundle",
                label="Team evidence bundle",
                state="ready",
                source_ids=("team_evidence_readiness", "evidence_bundle"),
                description="Sanitized team evidence metadata.",
                blockers=(),
            ),
        ),
        next_actions=(
            EvidenceCloudNextAction(
                priority="low",
                action="Keep upload intent explicit and audited.",
                source_ids=("team_evidence_readiness",),
                area_ids=("team_upload_boundary",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION == "entroping.evidence-cloud-readiness.v1"
    assert payload["schema_version"] == "entroping.evidence-cloud-readiness.v1"
    assert payload["cloud_boundary"]["upload_implemented"] is False
    assert payload["cloud_boundary"]["hosted_sync_implemented"] is False
    assert payload["upload_candidates"][0]["id"] == "team_evidence_bundle"
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.evidence-cloud-readiness.v1"
    )
    assert schema["properties"]["cloud_boundary"]["$ref"] == "#/$defs/cloud_boundary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "team_evidence_readiness",
        "evidence_bundle",
        "runtime_card",
        "artifact_manifest",
        "design_partner_feedback",
        "pilot_metrics",
        "integration_readiness",
        "devex_readiness",
        "connector_intent",
        "evidence_index",
    ]
    assert schema["$defs"]["upload_candidate_id"]["enum"] == [
        "team_evidence_bundle",
        "runtime_governance_card",
        "integration_surface_packet",
        "developer_experience_packet",
    ]
    assert "design_partner_free_form_text" in schema["$defs"]["forbidden_data_class"]["enum"]


def test_evidence_cloud_export_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-cloud-export.v1.schema.json").read_text())
    packet = EvidenceCloudExportPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceCloudExportSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            export_items_total=2,
            export_items_ready=1,
            export_items_blocked=1,
            boundary_controls_total=2,
            next_actions_total=1,
        ),
        sources=(
            EvidenceCloudExportSource(
                id="evidence-portal-json",
                label="Evidence Portal JSON",
                path="reports/evidence-portal.json",
                state="present",
                schema_version="entroping.evidence-portal.v1",
                sha256="a" * 64,
                summary="ready",
            ),
            EvidenceCloudExportSource(
                id="evidence-links-json",
                label="Evidence Links JSON",
                path="reports/evidence-links.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        export_items=(
            EvidenceCloudExportItem(
                id="evidence-portal-json",
                label="Evidence Portal JSON",
                source_id="evidence-portal-json",
                path="reports/evidence-portal.json",
                state="ready",
                local_reference="entroping://evidence-cloud-export/evidence-portal-json",
                schema_version="entroping.evidence-portal.v1",
                sha256="a" * 64,
                summary="ready",
                required_user_action="Review artifact metadata before explicit upload.",
            ),
            EvidenceCloudExportItem(
                id="evidence-links-json",
                label="Evidence Links JSON",
                source_id="evidence-links-json",
                path="reports/evidence-links.json",
                state="blocked",
                local_reference="entroping://evidence-cloud-export/evidence-links-json",
                schema_version=None,
                sha256=None,
                summary="missing",
                required_user_action="Generate Evidence Links JSON before Evidence Cloud export.",
            ),
        ),
        boundary_controls=(
            EvidenceCloudExportBoundaryControl(
                id="explicit_upload_only",
                label="Explicit upload only",
                enforced=True,
                summary="This manifest never uploads artifacts.",
            ),
            EvidenceCloudExportBoundaryControl(
                id="no_remote_api",
                label="No remote API",
                enforced=True,
                summary="The report does not call hosted Evidence Cloud APIs.",
            ),
        ),
        next_actions=(
            EvidenceCloudExportNextAction(
                priority="medium",
                action="Generate Evidence Links JSON before Evidence Cloud export.",
                source_ids=("evidence-links-json",),
                export_item_ids=("evidence-links-json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION == "entroping.evidence-cloud-export.v1"
    assert payload["schema_version"] == "entroping.evidence-cloud-export.v1"
    assert payload["export_items"][0]["local_reference"] == (
        "entroping://evidence-cloud-export/evidence-portal-json"
    )
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.evidence-cloud-export.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "evidence-portal-json",
        "evidence-links-json",
        "evidence-cloud-readiness-json",
        "team-evidence-readiness-json",
        "evidence-bundle-json",
        "artifact-manifest-json",
        "runtime-card-json",
        "handoff-json",
        "integration-readiness-json",
        "devex-readiness-json",
        "connector-intent-json",
        "observability-packet-json",
        "evidence-index-json",
    ]
    assert schema["$defs"]["boundary_control_id"]["enum"] == [
        "explicit_upload_only",
        "no_remote_api",
        "no_raw_traffic",
        "no_secrets",
        "no_prompts_or_provider_outputs",
        "no_source_hurl",
        "no_env_values",
        "no_full_report_payloads",
    ]


def test_evidence_cloud_workspace_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-cloud-workspace.v1.schema.json").read_text())
    packet = EvidenceCloudWorkspacePacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="tmp-workspace",
        summary=EvidenceCloudWorkspaceSummary(
            status="partial",
            manifests_total=2,
            manifests_present=2,
            manifests_missing=0,
            manifests_invalid=0,
            manifests_unsafe=0,
            repositories_total=2,
            repositories_ready=1,
            repositories_partial=1,
            repositories_insufficient=0,
            export_items_total=4,
            export_items_ready=3,
            export_items_blocked=1,
            boundary_controls_total=2,
            next_actions_total=1,
        ),
        manifests=(
            EvidenceCloudWorkspaceManifest(
                id="manifest-1",
                path="reports/repo-a-export.json",
                state="present",
                schema_version="entroping.evidence-cloud-export.v1",
                sha256="a" * 64,
                project="checkout-api",
                export_status="ready",
                summary="ready",
            ),
            EvidenceCloudWorkspaceManifest(
                id="manifest-2",
                path="reports/repo-b-export.json",
                state="present",
                schema_version="entroping.evidence-cloud-export.v1",
                sha256="b" * 64,
                project="billing-api",
                export_status="partial",
                summary="partial",
            ),
        ),
        repositories=(
            EvidenceCloudWorkspaceRepository(
                id="repository-1",
                manifest_id="manifest-1",
                project="checkout-api",
                status="ready",
                sources_present=2,
                sources_total=2,
                export_items_ready=2,
                export_items_total=2,
                export_items_blocked=0,
                boundary_controls_total=2,
                local_reference="entroping://evidence-cloud-workspace/repository-1",
                summary="ready",
            ),
            EvidenceCloudWorkspaceRepository(
                id="repository-2",
                manifest_id="manifest-2",
                project="billing-api",
                status="partial",
                sources_present=1,
                sources_total=2,
                export_items_ready=1,
                export_items_total=2,
                export_items_blocked=1,
                boundary_controls_total=2,
                local_reference="entroping://evidence-cloud-workspace/repository-2",
                summary="partial",
            ),
        ),
        boundary_controls=(
            EvidenceCloudWorkspaceBoundaryControl(
                id="explicit_upload_only",
                label="Explicit upload only",
                total_manifests=2,
                enforced_manifests=2,
                summary="Both manifests preserve explicit upload only.",
            ),
            EvidenceCloudWorkspaceBoundaryControl(
                id="no_remote_api",
                label="No remote API",
                total_manifests=2,
                enforced_manifests=2,
                summary="Both manifests avoid remote APIs.",
            ),
        ),
        next_actions=(
            EvidenceCloudWorkspaceNextAction(
                priority="medium",
                action="Review partial Evidence Cloud export manifests before workspace promotion.",
                manifest_ids=("manifest-2",),
                repository_ids=("repository-2",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION == "entroping.evidence-cloud-workspace.v1"
    assert payload["schema_version"] == "entroping.evidence-cloud-workspace.v1"
    assert payload["repositories"][0]["local_reference"] == (
        "entroping://evidence-cloud-workspace/repository-1"
    )
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.evidence-cloud-workspace.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["manifest_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["repository_status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["boundary_control_id"]["enum"] == [
        "explicit_upload_only",
        "no_remote_api",
        "no_raw_traffic",
        "no_secrets",
        "no_prompts_or_provider_outputs",
        "no_source_hurl",
        "no_env_values",
        "no_full_report_payloads",
    ]


def test_evidence_cloud_dashboard_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-cloud-dashboard.v1.schema.json").read_text())
    packet = EvidenceCloudDashboardPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="tmp-workspace",
        summary=EvidenceCloudDashboardSummary(
            status="partial",
            manifests_total=2,
            manifests_present=2,
            repositories_total=2,
            repositories_ready=1,
            repositories_attention=1,
            export_items_total=4,
            export_items_ready=3,
            export_items_blocked=1,
            boundary_controls_total=2,
            next_actions_total=1,
        ),
        manifests=(
            EvidenceCloudWorkspaceManifest(
                id="manifest-1",
                path="reports/repo-a-export.json",
                state="present",
                schema_version="entroping.evidence-cloud-export.v1",
                sha256="a" * 64,
                project="checkout-api",
                export_status="ready",
                summary="ready",
            ),
        ),
        repositories=(
            EvidenceCloudDashboardRepository(
                id="repository-1",
                manifest_id="manifest-1",
                project="checkout-api",
                status="ready",
                dashboard_state="ready",
                sources_present=2,
                sources_total=2,
                export_items_ready=2,
                export_items_total=2,
                export_items_blocked=0,
                boundary_controls_total=2,
                local_reference="entroping://evidence-cloud-workspace/repository-1",
                summary="ready",
            ),
            EvidenceCloudDashboardRepository(
                id="repository-2",
                manifest_id="manifest-2",
                project="billing-api",
                status="partial",
                dashboard_state="attention",
                sources_present=1,
                sources_total=2,
                export_items_ready=1,
                export_items_total=2,
                export_items_blocked=1,
                boundary_controls_total=2,
                local_reference="entroping://evidence-cloud-workspace/repository-2",
                summary="partial",
            ),
        ),
        boundary_controls=(
            EvidenceCloudWorkspaceBoundaryControl(
                id="explicit_upload_only",
                label="Explicit upload only",
                total_manifests=2,
                enforced_manifests=2,
                summary="Both manifests preserve explicit upload only.",
            ),
        ),
        next_actions=(
            EvidenceCloudWorkspaceNextAction(
                priority="medium",
                action="Review partial Evidence Cloud export manifests before dashboard review.",
                manifest_ids=("manifest-2",),
                repository_ids=("repository-2",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION == "entroping.evidence-cloud-dashboard.v1"
    assert payload["schema_version"] == "entroping.evidence-cloud-dashboard.v1"
    assert payload["workspace_schema_version"] == "entroping.evidence-cloud-workspace.v1"
    assert payload["repositories"][1]["dashboard_state"] == "attention"
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.evidence-cloud-dashboard.v1"
    )
    assert schema["properties"]["workspace_schema_version"]["const"] == (
        "entroping.evidence-cloud-workspace.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["dashboard_state"]["enum"] == ["ready", "attention"]


def test_connector_intent_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "connector-intent.v1.schema.json").read_text())
    packet = ConnectorIntentPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=ConnectorIntentSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            intents_total=1,
            intents_ready=1,
            intents_attention=0,
            intents_blocked=0,
            blockers_total=0,
            next_actions_total=1,
        ),
        sources=(
            ConnectorIntentSource(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass; 0 findings",
            ),
        ),
        intents=(
            ConnectorIntentRecord(
                id="issue_tracker",
                label="Issue tracker",
                target_family="issue_tracker",
                target_systems=("jira", "linear"),
                status="ready",
                intent_kind="issue_link",
                required_source_ids=("runtime_card", "notification_packet"),
                present_source_ids=("runtime_card",),
                missing_source_ids=("notification_packet",),
                minimum_payload_fields=("artifact_id", "source_sha256"),
                required_user_action="explicit_user_approval",
                audit_fields=("actor_role", "approval_id"),
                forbidden_actions=("call_external_api", "mutate_issue_tracker"),
                blockers=(),
                next_action="Prepare read-only evidence links.",
            ),
        ),
        next_actions=(
            ConnectorIntentNextAction(
                priority="medium",
                action="Generate notification evidence before issue tracker intents.",
                source_ids=("notification_packet",),
                intent_ids=("issue_tracker",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert CONNECTOR_INTENT_SCHEMA_VERSION == "entroping.connector-intent.v1"
    assert payload["schema_version"] == "entroping.connector-intent.v1"
    assert payload["intents"][0]["target_systems"] == ["jira", "linear"]
    assert payload["intents"][0]["required_user_action"] == "explicit_user_approval"
    assert schema["properties"]["schema_version"]["const"] == "entroping.connector-intent.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "runtime_card",
        "handoff",
        "notification_packet",
        "integration_readiness",
        "devex_readiness",
        "observability_packet",
        "evidence_index",
    ]
    assert schema["$defs"]["intent_id"]["enum"] == [
        "issue_tracker",
        "chat",
        "enterprise_automation",
        "enterprise_ai",
        "observability",
        "devex_surface",
    ]
    assert schema["$defs"]["target_system"]["enum"] == [
        "jira",
        "linear",
        "monday",
        "github_issues",
        "generic_tracker",
        "slack",
        "discord",
        "teams",
        "generic_chat",
        "workato",
        "zapier",
        "generic_workflow",
        "claude",
        "codex",
        "openai_compatible_agent",
        "generic_ai_assistant",
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic_observability",
        "vscode",
        "editor",
        "local_workbench",
        "desktop",
        "cloud",
        "mobile",
        "pr_card",
    ]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "call_external_api",
        "invoke_model_provider",
        "upload_artifacts",
        "mutate_issue_tracker",
        "post_chat_message",
        "execute_chat_command",
        "mutate_dashboard_or_monitor",
        "mutate_workflow",
        "sync_raw_repo_or_vault",
        "read_provider_keys",
        "override_hurl_qanstitution_result",
        "render_raw_artifact_contents",
        "implement_app_surface",
        "execute_hurl",
        "run_tests",
    ]


def test_external_test_evidence_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "external-test-evidence.v1.schema.json").read_text())
    packet = ExternalTestEvidencePacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=ExternalTestEvidenceSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            layers_total=1,
            layers_with_evidence=1,
            layers_missing=0,
            layers_blocked=0,
            total_tests=5,
            total_failures=0,
            total_errors=0,
            total_skipped=1,
            line_coverage_percent=87.5,
            branch_coverage_percent=50.0,
            sarif_results_total=3,
            sarif_error_results=1,
            next_actions_total=1,
        ),
        sources=(
            ExternalTestEvidenceSource(
                id="unit_junit",
                label="unit JUnit",
                path="reports/external-tests/unit-junit.xml",
                kind="junit",
                layer="unit",
                state="present",
                sha256="a" * 64,
                summary="5 tests; 0 failures; 0 errors; 1 skipped",
                suites=1,
                tests=5,
                failures=0,
                errors=0,
                skipped=1,
            ),
        ),
        layers=(
            ExternalTestEvidenceLayer(
                id="unit",
                label="Unit",
                status="covered",
                source_ids=("unit_junit",),
                tests=5,
                failures=0,
                errors=0,
                skipped=1,
                next_action="Review counts-only evidence.",
            ),
        ),
        next_actions=(
            ExternalTestEvidenceNextAction(
                priority="medium",
                action="Generate integration JUnit evidence.",
                source_ids=("integration_junit",),
                layer_ids=("integration",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION == ("entroping.external-test-evidence.v1")
    assert payload["schema_version"] == "entroping.external-test-evidence.v1"
    assert payload["sources"][0]["id"] == "unit_junit"
    assert payload["layers"][0]["status"] == "covered"
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.external-test-evidence.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "unit_junit",
        "integration_junit",
        "component_junit",
        "contract_junit",
        "e2e_junit",
        "coverage_xml",
        "lcov_info",
        "sarif_json",
    ]
    assert schema["$defs"]["layer_id"]["enum"] == [
        "unit",
        "integration",
        "component",
        "contract",
        "e2e",
    ]
    assert schema["$defs"]["source_kind"]["enum"] == [
        "junit",
        "coverage_xml",
        "lcov",
        "sarif",
    ]


def test_integration_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "integration-readiness.v1.schema.json").read_text())
    packet = IntegrationReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=IntegrationReadinessSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            families_total=1,
            families_ready=1,
            families_attention=0,
            families_blocked=0,
            blockers_total=0,
            next_actions_total=1,
        ),
        sources=(
            IntegrationReadinessSource(
                id="team_access_control_plan",
                label="Team access-control plan",
                path="reports/team-access-control-plan.json",
                state="present",
                schema_version="entroping.team-access-control-plan.v1",
                sha256="a" * 64,
                summary="ready; 1/1 roles ready; 0 blockers",
            ),
        ),
        families=(
            IntegrationReadinessFamily(
                id="issue_trackers",
                label="Issue trackers",
                status="ready",
                surface_ids=("jira", "linear", "monday"),
                required_source_ids=("team_access_control_plan", "notification_packet"),
                present_source_ids=("team_access_control_plan",),
                missing_source_ids=("notification_packet",),
                blockers=(),
                link_requirements=("artifact_id", "source_sha256"),
                event_requirements=("actor_role", "target_surface", "artifact_id"),
                forbidden_actions=("call_external_api", "override_hurl_qanstitution_result"),
                next_action="Attach read-only Entroping evidence links.",
            ),
        ),
        next_actions=(
            IntegrationReadinessNextAction(
                priority="medium",
                action="Generate notification evidence before issue tracker links.",
                source_ids=("notification_packet",),
                family_ids=("issue_trackers",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert INTEGRATION_READINESS_SCHEMA_VERSION == "entroping.integration-readiness.v1"
    assert payload["schema_version"] == "entroping.integration-readiness.v1"
    assert payload["families"][0]["surface_ids"] == ["jira", "linear", "monday"]
    assert payload["families"][0]["forbidden_actions"] == [
        "call_external_api",
        "override_hurl_qanstitution_result",
    ]
    assert schema["properties"]["schema_version"]["const"] == ("entroping.integration-readiness.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["source_id"]["enum"] == [
        "team_access_control_plan",
        "notification_packet",
        "handoff",
        "observability_packet",
        "api_inventory",
        "runtime_card",
    ]
    assert schema["$defs"]["family_id"]["enum"] == [
        "issue_trackers",
        "chat",
        "enterprise_automation",
        "cross_surface_continuity",
        "observability",
        "api_governance",
    ]
    assert schema["$defs"]["surface_id"]["enum"] == [
        "jira",
        "linear",
        "monday",
        "slack",
        "discord",
        "workato",
        "claude",
        "codex",
        "cli",
        "desktop",
        "cloud",
        "mobile",
        "opentelemetry",
        "datadog",
        "splunk",
        "openapi",
        "graphql",
        "soap_xml",
        "grpc",
        "webhooks",
        "asyncapi",
        "websocket",
    ]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "call_external_api",
        "upload_artifacts",
        "mutate_issue_tracker",
        "post_chat_message",
        "execute_chat_command",
        "read_provider_keys",
        "override_hurl_qanstitution_result",
        "sync_raw_repo_or_vault",
        "render_raw_artifact_contents",
    ]


def test_observability_packet_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "observability-packet.v1.schema.json").read_text())
    packet = ObservabilityPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=ObservabilitySummary(
            status="ready",
            severity="blocker",
            sources_total=2,
            sources_present=2,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            events_total=1,
            debug_events=0,
            info_events=0,
            warning_events=0,
            error_events=1,
        ),
        runtime=ObservabilityRuntimeSummary(
            status="attention",
            findings=2,
            evidence_links=3,
            failed_gate_ids=1,
        ),
        sources=(
            ObservabilitySource(
                id="diagnostics",
                label="Structured diagnostics",
                path=".entroping/latest-diagnostics.jsonl",
                state="present",
                schema_version="entroping.diagnostics.v1",
                sha256="a" * 64,
                summary="1 diagnostic events.",
            ),
            ObservabilitySource(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="b" * 64,
                summary="attention runtime evidence",
            ),
        ),
        events=(
            ObservabilityEventSummary(
                component="run",
                operation="execute",
                severity="error",
                code="hurl.timeout",
                summary="Hurl timeout recorded.",
            ),
        ),
        components=(
            ObservabilityComponentSummary(
                component="run",
                events_total=1,
                debug_events=0,
                info_events=0,
                warning_events=0,
                error_events=1,
                operations=("execute",),
                codes=("hurl.timeout",),
            ),
        ),
        messages=(
            ObservabilityMessage(
                surface="opentelemetry",
                label="OpenTelemetry",
                severity="blocker",
                title="Entroping observability signals need attention",
                body=(
                    "Runtime status attention; 1 diagnostic events; "
                    "1 errors; 0 warnings; 2/2 sources present."
                ),
                next_action="Use this packet as value-free OTLP adapter input.",
                artifact_paths=(
                    "reports/observability-packet.json",
                    ".entroping/latest-diagnostics.jsonl",
                    "reports/runtime-card.json",
                ),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OBSERVABILITY_PACKET_SCHEMA_VERSION == "entroping.observability-packet.v1"
    assert payload == {
        "schema_version": "entroping.observability-packet.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "blocker",
            "sources_total": 2,
            "sources_present": 2,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "events_total": 1,
            "debug_events": 0,
            "info_events": 0,
            "warning_events": 0,
            "error_events": 1,
        },
        "runtime": {
            "status": "attention",
            "findings": 2,
            "evidence_links": 3,
            "failed_gate_ids": 1,
        },
        "sources": [
            {
                "id": "diagnostics",
                "label": "Structured diagnostics",
                "path": ".entroping/latest-diagnostics.jsonl",
                "state": "present",
                "schema_version": "entroping.diagnostics.v1",
                "sha256": "a" * 64,
                "summary": "1 diagnostic events.",
            },
            {
                "id": "runtime_card",
                "label": "Runtime card",
                "path": "reports/runtime-card.json",
                "state": "present",
                "schema_version": "entroping.runtime-card.v1",
                "sha256": "b" * 64,
                "summary": "attention runtime evidence",
            },
        ],
        "events": [
            {
                "component": "run",
                "operation": "execute",
                "severity": "error",
                "code": "hurl.timeout",
                "summary": "Hurl timeout recorded.",
            }
        ],
        "components": [
            {
                "component": "run",
                "events_total": 1,
                "debug_events": 0,
                "info_events": 0,
                "warning_events": 0,
                "error_events": 1,
                "operations": ["execute"],
                "codes": ["hurl.timeout"],
            }
        ],
        "messages": [
            {
                "surface": "opentelemetry",
                "label": "OpenTelemetry",
                "severity": "blocker",
                "title": "Entroping observability signals need attention",
                "body": (
                    "Runtime status attention; 1 diagnostic events; "
                    "1 errors; 0 warnings; 2/2 sources present."
                ),
                "next_action": "Use this packet as value-free OTLP adapter input.",
                "artifact_paths": [
                    "reports/observability-packet.json",
                    ".entroping/latest-diagnostics.jsonl",
                    "reports/runtime-card.json",
                ],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.observability-packet.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["summary"]["properties"]["severity"]["enum"] == [
        "info",
        "attention",
        "blocker",
    ]
    assert schema["$defs"]["message"]["properties"]["surface"]["enum"] == [
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    ]


def test_otel_mapping_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "otel-mapping.v1.schema.json").read_text())
    packet = OtelMappingPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=OtelMappingSummary(
            status="ready",
            severity="attention",
            sources_total=4,
            sources_present=4,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            mappings_total=1,
            resource_mappings=1,
            log_mappings=0,
            metric_mappings=0,
            trace_mappings=0,
            boundary_controls=1,
        ),
        sources=(
            OtelMappingSource(
                id="observability_packet",
                label="Observability packet",
                path="reports/observability-packet.json",
                state="present",
                schema_version="entroping.observability-packet.v1",
                sha256="a" * 64,
                summary="ready observability, attention severity, 3 events",
            ),
        ),
        mappings=(
            OtelAttributeMapping(
                signal="resource",
                attribute="service.name",
                requirement="required",
                value_kind="identifier",
                source_ids=("observability_packet", "runtime_card"),
                summary="Future OTLP resources can identify the sanitized project/service name.",
                forbidden_fields=("raw_urls", "headers"),
            ),
        ),
        boundary_controls=(
            OtelBoundaryControl(
                id="no_otlp_export",
                state="active",
                summary="This command writes local mapping evidence only; it does not export OTLP.",
            ),
        ),
        next_actions=(
            OtelMappingNextAction(
                priority="low",
                action="Use this packet as the value-free contract for a future OTLP adapter.",
                source_ids=("observability_packet", "runtime_card"),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OTEL_MAPPING_SCHEMA_VERSION == "entroping.otel-mapping.v1"
    assert payload == {
        "schema_version": "entroping.otel-mapping.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "attention",
            "sources_total": 4,
            "sources_present": 4,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "mappings_total": 1,
            "resource_mappings": 1,
            "log_mappings": 0,
            "metric_mappings": 0,
            "trace_mappings": 0,
            "boundary_controls": 1,
        },
        "sources": [
            {
                "id": "observability_packet",
                "label": "Observability packet",
                "path": "reports/observability-packet.json",
                "state": "present",
                "schema_version": "entroping.observability-packet.v1",
                "sha256": "a" * 64,
                "summary": "ready observability, attention severity, 3 events",
            }
        ],
        "mappings": [
            {
                "signal": "resource",
                "attribute": "service.name",
                "requirement": "required",
                "value_kind": "identifier",
                "source_ids": ["observability_packet", "runtime_card"],
                "summary": (
                    "Future OTLP resources can identify the sanitized project/service name."
                ),
                "forbidden_fields": ["raw_urls", "headers"],
            }
        ],
        "boundary_controls": [
            {
                "id": "no_otlp_export",
                "state": "active",
                "summary": (
                    "This command writes local mapping evidence only; it does not export OTLP."
                ),
            }
        ],
        "next_actions": [
            {
                "priority": "low",
                "action": (
                    "Use this packet as the value-free contract for a future OTLP adapter."
                ),
                "source_ids": ["observability_packet", "runtime_card"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.otel-mapping.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "observability_packet",
        "runtime_card",
        "test_pyramid",
        "external_test_evidence",
    ]
    assert schema["$defs"]["signal"]["enum"] == ["resource", "log", "metric", "trace"]


def test_observability_adapter_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads(
        (SCHEMA_DIR / "observability-adapter-readiness.v1.schema.json").read_text()
    )
    packet = ObservabilityAdapterReadinessPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=ObservabilityAdapterReadinessSummary(
            status="ready",
            severity="attention",
            sources_total=4,
            sources_present=4,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            adapters_total=1,
            adapters_ready=1,
            adapters_attention=0,
            adapters_blocked=0,
            boundary_controls=1,
        ),
        sources=(
            ObservabilityAdapterReadinessSource(
                id="observability_packet",
                label="Observability packet",
                path="reports/observability-packet.json",
                state="present",
                schema_version="entroping.observability-packet.v1",
                sha256="a" * 64,
                summary="ready observability, attention severity, 3 events",
            ),
        ),
        adapters=(
            ObservabilityAdapterReadinessRow(
                id="opentelemetry",
                label="OpenTelemetry",
                status="ready",
                required_source_ids=("observability_packet", "otel_mapping"),
                optional_source_ids=("evidence_index", "runtime_card"),
                summary="Required value-free evidence is present for adapter design.",
                next_action=(
                    "Use the mapping packet as the value-free contract for an OTLP adapter."
                ),
                forbidden_fields=("raw_urls", "dashboard_payloads"),
            ),
        ),
        boundary_controls=(
            ObservabilityAdapterBoundaryControl(
                id="no_vendor_api",
                state="active",
                summary="This command does not call vendor APIs.",
            ),
        ),
        next_actions=(
            ObservabilityAdapterNextAction(
                priority="low",
                action="Use this packet as the local value-free adapter readiness contract.",
                source_ids=("observability_packet", "otel_mapping"),
                adapter_ids=("opentelemetry",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION == (
        "entroping.observability-adapter-readiness.v1"
    )
    assert payload == {
        "schema_version": "entroping.observability-adapter-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "attention",
            "sources_total": 4,
            "sources_present": 4,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "adapters_total": 1,
            "adapters_ready": 1,
            "adapters_attention": 0,
            "adapters_blocked": 0,
            "boundary_controls": 1,
        },
        "sources": [
            {
                "id": "observability_packet",
                "label": "Observability packet",
                "path": "reports/observability-packet.json",
                "state": "present",
                "schema_version": "entroping.observability-packet.v1",
                "sha256": "a" * 64,
                "summary": "ready observability, attention severity, 3 events",
            }
        ],
        "adapters": [
            {
                "id": "opentelemetry",
                "label": "OpenTelemetry",
                "status": "ready",
                "required_source_ids": ["observability_packet", "otel_mapping"],
                "optional_source_ids": ["evidence_index", "runtime_card"],
                "summary": "Required value-free evidence is present for adapter design.",
                "next_action": (
                    "Use the mapping packet as the value-free contract for an OTLP adapter."
                ),
                "forbidden_fields": ["raw_urls", "dashboard_payloads"],
            }
        ],
        "boundary_controls": [
            {
                "id": "no_vendor_api",
                "state": "active",
                "summary": "This command does not call vendor APIs.",
            }
        ],
        "next_actions": [
            {
                "priority": "low",
                "action": (
                    "Use this packet as the local value-free adapter readiness contract."
                ),
                "source_ids": ["observability_packet", "otel_mapping"],
                "adapter_ids": ["opentelemetry"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.observability-adapter-readiness.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "observability_packet",
        "otel_mapping",
        "evidence_index",
        "runtime_card",
    ]
    assert schema["$defs"]["adapter_id"]["enum"] == [
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    ]


def test_api_inventory_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "api-inventory.v1.schema.json").read_text())
    packet = ApiInventoryPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=ApiInventorySummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            styles_total=1,
            hurl_tests_total=0,
            operations_total=2,
        ),
        sources=(
            ApiInventorySource(
                kind="configured_openapi",
                style="rest_openapi",
                path="openapi.yaml",
                state="present",
                sha256="a" * 64,
                tags=(),
                operations=2,
                summary="2 OpenAPI operations.",
            ),
        ),
        styles=(
            ApiInventoryStyleSummary(
                style="rest_openapi",
                label="REST/OpenAPI",
                sources=1,
                hurl_tests=0,
                operations=2,
                tags=(),
                source_paths=("openapi.yaml",),
                next_action="Use Architect OpenAPI generation and audit reports.",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert API_INVENTORY_SCHEMA_VERSION == "entroping.api-inventory.v1"
    assert payload == {
        "schema_version": "entroping.api-inventory.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "styles_total": 1,
            "hurl_tests_total": 0,
            "operations_total": 2,
        },
        "sources": [
            {
                "kind": "configured_openapi",
                "style": "rest_openapi",
                "path": "openapi.yaml",
                "state": "present",
                "sha256": "a" * 64,
                "tags": [],
                "operations": 2,
                "summary": "2 OpenAPI operations.",
            }
        ],
        "styles": [
            {
                "style": "rest_openapi",
                "label": "REST/OpenAPI",
                "sources": 1,
                "hurl_tests": 0,
                "operations": 2,
                "tags": [],
                "source_paths": ["openapi.yaml"],
                "next_action": "Use Architect OpenAPI generation and audit reports.",
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.api-inventory.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["api_style"]["enum"] == [
        "rest_openapi",
        "graphql",
        "soap_xml",
        "grpc_proto",
        "unknown_http",
    ]


def test_mutation_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "mutation-readiness.v1.schema.json").read_text())
    packet = MutationReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=MutationReadinessSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            generated_tests=1,
            negative_tests=1,
            security_tests=1,
            assertions_total=2,
            seed_metadata_tests=1,
            candidate_categories_total=1,
            optional_reports_present=0,
            optional_reports_invalid=0,
            optional_reports_unsafe=0,
        ),
        sources=(
            MutationReadinessSource(
                kind="generated_hurl",
                path="tests/generated/security/auth.hurl",
                state="present",
                schema_version=None,
                tags=("generated", "security"),
                candidate_categories=("auth",),
                assertions=2,
                seed_metadata=True,
                summary="1 generated Hurl exchanges.",
            ),
        ),
        candidates=(
            MutationReadinessCandidate(
                category="auth",
                label="Auth/security mutation",
                tests=1,
                source_paths=("tests/generated/security/auth.hurl",),
                next_action="Keep auth/security cases explicit before future mutation execution.",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert MUTATION_READINESS_SCHEMA_VERSION == "entroping.mutation-readiness.v1"
    assert payload == {
        "schema_version": "entroping.mutation-readiness.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "generated_tests": 1,
            "negative_tests": 1,
            "security_tests": 1,
            "assertions_total": 2,
            "seed_metadata_tests": 1,
            "candidate_categories_total": 1,
            "optional_reports_present": 0,
            "optional_reports_invalid": 0,
            "optional_reports_unsafe": 0,
        },
        "sources": [
            {
                "kind": "generated_hurl",
                "path": "tests/generated/security/auth.hurl",
                "state": "present",
                "schema_version": None,
                "tags": ["generated", "security"],
                "candidate_categories": ["auth"],
                "assertions": 2,
                "seed_metadata": True,
                "summary": "1 generated Hurl exchanges.",
            }
        ],
        "candidates": [
            {
                "category": "auth",
                "label": "Auth/security mutation",
                "tests": 1,
                "source_paths": ["tests/generated/security/auth.hurl"],
                "next_action": (
                    "Keep auth/security cases explicit before future mutation execution."
                ),
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.mutation-readiness.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["candidate_category"]["enum"] == [
        "status_code",
        "schema",
        "auth",
        "latency",
        "request_shape",
        "response_shape",
    ]


def test_evidence_index_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-index.v1.schema.json").read_text())
    packet = EvidenceIndexPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceIndexSummary(
            status="partial",
            artifacts_total=2,
            artifacts_present=1,
            artifacts_missing=0,
            artifacts_invalid=1,
            artifacts_unsafe=0,
        ),
        artifacts=(
            EvidenceIndexArtifact(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                summary="1 total, 1 passed, 0 failed",
            ),
            EvidenceIndexArtifact(
                id="drift-json",
                label="Drift JSON",
                path="reports/drift.json",
                state="invalid",
                schema_version=None,
                summary="invalid JSON",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_INDEX_SCHEMA_VERSION == "entroping.evidence-index.v1"
    assert payload == {
        "schema_version": "entroping.evidence-index.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "artifacts_total": 2,
            "artifacts_present": 1,
            "artifacts_missing": 0,
            "artifacts_invalid": 1,
            "artifacts_unsafe": 0,
        },
        "artifacts": [
            {
                "id": "run-json",
                "label": "Run JSON",
                "path": "reports/run-latest.json",
                "state": "present",
                "schema_version": "entroping.run-report.v1",
                "summary": "1 total, 1 passed, 0 failed",
            },
            {
                "id": "drift-json",
                "label": "Drift JSON",
                "path": "reports/drift.json",
                "state": "invalid",
                "schema_version": None,
                "summary": "invalid JSON",
            },
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.evidence-index.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["artifact_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]


def test_evidence_links_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-links.v1.schema.json").read_text())
    packet = EvidenceLinksPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceLinksSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            targets_total=2,
            targets_ready=1,
            targets_blocked=1,
            surfaces_total=6,
            next_actions_total=1,
        ),
        sources=(
            EvidenceLinksSource(
                id="runtime-card-json",
                label="Runtime Card JSON",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass",
            ),
            EvidenceLinksSource(
                id="evidence-index-json",
                label="Evidence Index JSON",
                path="reports/evidence-index.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        targets=(
            EvidenceLinkTarget(
                id="runtime-card-json",
                label="Runtime Card JSON",
                source_id="runtime-card-json",
                link_token="entroping://evidence/runtime-card-json",
                path="reports/runtime-card.json",
                state="ready",
                surfaces=("cli", "pr", "desktop", "cloud", "mobile", "agent"),
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass",
            ),
            EvidenceLinkTarget(
                id="evidence-index-json",
                label="Evidence Index JSON",
                source_id="evidence-index-json",
                link_token="entroping://evidence/evidence-index-json",
                path="reports/evidence-index.json",
                state="blocked",
                surfaces=("cli", "desktop", "cloud", "mobile", "agent"),
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        next_actions=(
            EvidenceLinksNextAction(
                priority="medium",
                action="Generate Evidence Index JSON local evidence.",
                source_ids=("evidence-index-json",),
                target_ids=("evidence-index-json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_LINKS_SCHEMA_VERSION == "entroping.evidence-links.v1"
    assert payload["schema_version"] == "entroping.evidence-links.v1"
    assert payload["summary"]["surfaces_total"] == 6
    assert payload["targets"][0]["link_token"] == "entroping://evidence/runtime-card-json"
    assert schema["properties"]["schema_version"]["const"] == "entroping.evidence-links.v1"
    assert schema["$defs"]["source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["surface"]["enum"] == [
        "cli",
        "pr",
        "desktop",
        "cloud",
        "mobile",
        "agent",
    ]


def test_evidence_portal_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-portal.v1.schema.json").read_text())
    packet = EvidencePortalPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidencePortalSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            cards_total=2,
            cards_ready=1,
            cards_blocked=1,
            surfaces_total=6,
            next_actions_total=1,
        ),
        sources=(
            EvidencePortalSource(
                id="evidence-links-json",
                label="Evidence Links JSON",
                path="reports/evidence-links.json",
                state="present",
                schema_version="entroping.evidence-links.v1",
                sha256="a" * 64,
                summary="ready",
            ),
            EvidencePortalSource(
                id="evidence-index-json",
                label="Evidence Index JSON",
                path="reports/evidence-index.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        cards=(
            EvidencePortalCard(
                id="evidence-links-json",
                label="Evidence Links JSON",
                source_id="evidence-links-json",
                path="reports/evidence-links.json",
                state="ready",
                schema_version="entroping.evidence-links.v1",
                sha256="a" * 64,
                summary="ready",
                ready_targets=9,
                blocked_targets=0,
                surface_count=6,
                next_actions_count=0,
            ),
            EvidencePortalCard(
                id="evidence-index-json",
                label="Evidence Index JSON",
                source_id="evidence-index-json",
                path="reports/evidence-index.json",
                state="blocked",
                schema_version=None,
                sha256=None,
                summary="missing",
                ready_targets=None,
                blocked_targets=None,
                surface_count=None,
                next_actions_count=None,
            ),
        ),
        next_actions=(
            EvidencePortalNextAction(
                priority="medium",
                action="Generate Evidence Index JSON local evidence.",
                source_ids=("evidence-index-json",),
                card_ids=("evidence-index-json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_PORTAL_SCHEMA_VERSION == "entroping.evidence-portal.v1"
    assert payload["schema_version"] == "entroping.evidence-portal.v1"
    assert payload["summary"]["cards_blocked"] == 1
    assert payload["cards"][0]["surface_count"] == 6
    assert schema["properties"]["schema_version"]["const"] == "entroping.evidence-portal.v1"
    assert schema["$defs"]["source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "evidence-links-json",
        "evidence-index-json",
        "runtime-card-json",
        "handoff-json",
        "evidence-cloud-readiness-json",
        "devex-readiness-json",
        "connector-intent-json",
        "observability-packet-json",
        "test-pyramid-json",
    ]


def test_pr_evidence_card_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "pr-evidence-card.v1.schema.json").read_text())
    packet = PrEvidenceCardPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=PrEvidenceCardSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            checklist_total=2,
            checklist_ready=1,
            checklist_attention=0,
            checklist_blocked=1,
            next_actions_total=1,
        ),
        sources=(
            PrEvidenceCardSource(
                id="runtime-card-json",
                label="Runtime Card JSON",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass",
            ),
            PrEvidenceCardSource(
                id="test-pyramid-json",
                label="Test Pyramid JSON",
                path="reports/test-pyramid.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        checklist=(
            PrEvidenceCardChecklistItem(
                id="runtime-governance",
                label="Runtime governance",
                source_id="runtime-card-json",
                state="ready",
                path="reports/runtime-card.json",
                schema_version="entroping.runtime-card.v1",
                sha256="a" * 64,
                summary="pass",
            ),
            PrEvidenceCardChecklistItem(
                id="test-pyramid",
                label="Test pyramid",
                source_id="test-pyramid-json",
                state="blocked",
                path="reports/test-pyramid.json",
                schema_version=None,
                sha256=None,
                summary="missing",
            ),
        ),
        next_actions=(
            PrEvidenceCardNextAction(
                priority="medium",
                action="Generate Test Pyramid JSON before using the PR evidence card.",
                source_ids=("test-pyramid-json",),
                checklist_ids=("test-pyramid",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert PR_EVIDENCE_CARD_SCHEMA_VERSION == "entroping.pr-evidence-card.v1"
    assert payload["schema_version"] == "entroping.pr-evidence-card.v1"
    assert payload["summary"]["checklist_blocked"] == 1
    assert schema["properties"]["schema_version"]["const"] == "entroping.pr-evidence-card.v1"
    assert schema["$defs"]["checklist_state"]["enum"] == [
        "ready",
        "attention",
        "blocked",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "runtime-card-json",
        "evidence-bundle-json",
        "test-pyramid-json",
        "mutation-readiness-json",
        "observability-packet-json",
        "integration-readiness-json",
        "devex-readiness-json",
        "connector-intent-json",
        "handoff-json",
        "evidence-cloud-dashboard-json",
        "evidence-index-json",
    ]


def test_evidence_action_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-action-plan.v1.schema.json").read_text())
    packet = EvidenceActionPlanPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceActionPlanSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            sources_blocked=0,
            sources_attention=1,
            actions_total=1,
            actions_high=0,
            actions_medium=1,
            actions_low=0,
        ),
        sources=(
            EvidenceActionPlanSource(
                id="pr-evidence-card-json",
                label="PR Evidence Card",
                path="reports/pr-evidence-card.json",
                state="present",
                schema_version="entroping.pr-evidence-card.v1",
                sha256="a" * 64,
                summary="partial",
                status="partial",
            ),
            EvidenceActionPlanSource(
                id="evidence-portal-json",
                label="Evidence Portal",
                path="reports/evidence-portal.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
                status=None,
            ),
        ),
        actions=(
            EvidenceActionPlanItem(
                priority="medium",
                category="generate",
                action="Generate Evidence Portal before using the evidence action plan.",
                source_ids=("evidence-portal-json",),
                status="missing",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_ACTION_PLAN_SCHEMA_VERSION == "entroping.evidence-action-plan.v1"
    assert payload["schema_version"] == "entroping.evidence-action-plan.v1"
    assert payload["summary"]["sources_attention"] == 1
    assert schema["properties"]["schema_version"]["const"] == "entroping.evidence-action-plan.v1"
    assert schema["$defs"]["priority"]["enum"] == ["high", "medium", "low"]
    assert schema["$defs"]["category"]["enum"] == ["generate", "repair", "review"]
    assert schema["$defs"]["source_id"]["enum"] == [
        "pr-evidence-card-json",
        "evidence-portal-json",
        "evidence-links-json",
        "evidence-cloud-dashboard-json",
        "devex-readiness-json",
        "integration-readiness-json",
        "connector-intent-json",
        "observability-packet-json",
        "mutation-readiness-json",
        "test-pyramid-json",
    ]


def test_work_item_draft_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "work-item-draft.v1.schema.json").read_text())
    packet = WorkItemDraftPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=WorkItemDraftSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=1,
            sources_invalid=0,
            sources_unsafe=0,
            items_total=1,
            items_high=0,
            items_medium=1,
            items_low=0,
            source_action_count=1,
        ),
        sources=(
            WorkItemDraftSource(
                id="evidence-action-plan-json",
                label="Evidence Action Plan",
                path="reports/evidence-action-plan.json",
                state="present",
                schema_version="entroping.evidence-action-plan.v1",
                sha256="a" * 64,
                summary="partial",
                status="partial",
            ),
            WorkItemDraftSource(
                id="connector-intent-json",
                label="Connector Intent",
                path="reports/connector-intent.json",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="missing",
                status=None,
            ),
        ),
        items=(
            WorkItemDraftItem(
                id="work-item-draft:001",
                category="draft",
                priority="medium",
                title="Prepare safe tracker draft.",
                summary="Draft tracker row for review evidence action with unknown status.",
                source_ids=("evidence-action-plan-json",),
                source_action_ids=("evidence-action-plan:001",),
                source_action_count=1,
                status="partial",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert WORK_ITEM_DRAFT_SCHEMA_VERSION == "entroping.work-item-draft.v1"
    assert payload["schema_version"] == "entroping.work-item-draft.v1"
    assert payload["summary"]["source_action_count"] == 1
    assert schema["properties"]["schema_version"]["const"] == "entroping.work-item-draft.v1"
    assert schema["$defs"]["category"]["enum"] == ["draft", "generate", "repair"]
    assert schema["$defs"]["target_system"]["enum"] == [
        "jira",
        "linear",
        "monday",
        "github_issues",
        "generic_tracker",
    ]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "call_external_api",
        "mutate_issue_tracker",
        "post_chat_message",
        "execute_chat_command",
        "upload_artifacts",
        "invoke_model_provider",
        "execute_hurl",
        "run_tests",
        "read_provider_keys",
        "parse_raw_traffic",
        "render_raw_artifact_contents",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "evidence-action-plan-json",
        "connector-intent-json",
        "integration-readiness-json",
        "evidence-links-json",
        "notification-packet-json",
    ]


def test_work_item_import_bundle_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads(
        (SCHEMA_DIR / "work-item-import-bundle.v1.schema.json").read_text()
    )
    packet = WorkItemImportBundle(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=WorkItemImportSummary(
            status="partial",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            rows_total=1,
            rows_high=1,
            rows_medium=0,
            rows_low=0,
            actions_total=0,
            actions_high=0,
            actions_medium=0,
            actions_low=0,
            source_item_count=1,
            source_action_count=1,
        ),
        sources=(
            WorkItemImportSource(
                id="work-item-draft-json",
                label="Work Item Draft",
                path="reports/work-item-draft.json",
                state="present",
                schema_version="entroping.work-item-draft.v1",
                sha256="a" * 64,
                summary="partial",
                status="partial",
            ),
        ),
        rows=(
            WorkItemImportRow(
                id="entroping-work-item-draft-001-jira:import-row",
                tracker_family="jira",
                external_id="entroping-work-item-draft-001-jira",
                title="Review blocked evidence before merge.",
                body="Draft row from Entroping evidence.",
                priority="high",
                labels=("entroping", "runtime-governance", "priority-high"),
                source_item_ids=("work-item-draft:001",),
                source_action_ids=("evidence-action-plan:001",),
                source_action_count=1,
                status="partial",
            ),
        ),
        actions=(
            WorkItemImportAction(
                priority="medium",
                category="generate",
                action="Generate Work Item Draft before building tracker import bundle.",
                source_ids=("work-item-draft-json",),
                status="missing",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION == (
        "entroping.work-item-import-bundle.v1"
    )
    assert payload["schema_version"] == "entroping.work-item-import-bundle.v1"
    assert payload["summary"]["source_item_count"] == 1
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.work-item-import-bundle.v1"
    )
    assert schema["$defs"]["tracker_family"]["enum"] == [
        "jira",
        "linear",
        "monday",
        "github_issues",
        "generic_tracker",
    ]
    assert schema["$defs"]["source_id"]["enum"] == ["work-item-draft-json"]
    assert schema["$defs"]["forbidden_action"]["enum"] == [
        "call_external_api",
        "mutate_issue_tracker",
        "post_chat_message",
        "execute_chat_command",
        "upload_artifacts",
        "invoke_model_provider",
        "execute_hurl",
        "run_tests",
        "read_provider_keys",
        "parse_raw_traffic",
        "render_raw_artifact_contents",
    ]


def test_pilot_outcome_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "pilot-outcome.v1.schema.json").read_text())
    packet = PilotOutcomePacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=PilotOutcomeSummary(
            status="partial",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            manual_input_gaps=1,
            monetization_yes=1,
            monetization_no=0,
            monetization_unclear=1,
            actions_total=1,
            actions_high=0,
            actions_medium=1,
            actions_low=0,
        ),
        sources=(
            PilotOutcomeSource(
                id="design-partner-feedback-json",
                label="Design-partner feedback",
                path="reports/design-partner-feedback.json",
                state="present",
                schema_version="entroping.design-partner-feedback.v1",
                sha256="a" * 64,
                summary="partial",
                status="partial",
            ),
        ),
        pilot_evidence_readiness=PilotOutcomeReadiness(
            design_partner_feedback_status="partial",
            pilot_metrics_status="missing",
            runtime_card_status="pass",
            evidence_cloud_status="ready",
            work_item_import_status="partial",
        ),
        manual_input_gaps=("feedback.missing_evidence",),
        monetization_signals=(
            PilotOutcomeMonetizationSignal(
                id="hosted_aggregation",
                answer="yes",
                manual_reason_required=True,
            ),
            PilotOutcomeMonetizationSignal(
                id="premium_policy_packs",
                answer="unclear",
                manual_reason_required=True,
            ),
        ),
        actions=(
            PilotOutcomeAction(
                priority="medium",
                category="collect",
                action="Collect sanitized manual design-partner pilot inputs.",
                field_paths=("feedback.missing_evidence",),
                status="manual_input_required",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert PILOT_OUTCOME_SCHEMA_VERSION == "entroping.pilot-outcome.v1"
    assert payload["schema_version"] == "entroping.pilot-outcome.v1"
    assert payload["summary"]["manual_input_gaps"] == 1
    assert schema["properties"]["schema_version"]["const"] == "entroping.pilot-outcome.v1"
    assert schema["$defs"]["source_id"]["enum"] == [
        "design-partner-feedback-json",
        "pilot-metrics-json",
        "runtime-card-json",
        "evidence-cloud-dashboard-json",
        "work-item-import-bundle-json",
    ]
    assert schema["$defs"]["category"]["enum"] == [
        "generate",
        "repair",
        "collect",
        "review",
    ]
    assert schema["$defs"]["signal_id"]["enum"] == [
        "hosted_aggregation",
        "premium_policy_packs",
    ]


def test_pilot_cohort_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "pilot-cohort.v1.schema.json").read_text())
    packet = PilotCohortPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        manifest_path="reports/pilot-cohort-manifest.json",
        summary=PilotCohortSummary(
            status="partial",
            outcomes_total=2,
            outcomes_present=1,
            outcomes_missing=1,
            outcomes_invalid=0,
            outcomes_unsafe=0,
            pilots_ready=1,
            pilots_partial=0,
            pilots_insufficient=0,
            manual_input_gaps_total=1,
            actions_total=2,
            actions_high=0,
            actions_medium=1,
            actions_low=1,
        ),
        outcomes=(
            PilotCohortOutcome(
                id="pilot-a",
                path="reports/pilot-a.json",
                state="present",
                schema_version="entroping.pilot-outcome.v1",
                sha256="a" * 64,
                project="checkout-api",
                status="ready",
                manual_input_gaps=1,
                summary="ready",
            ),
            PilotCohortOutcome(
                id="pilot-b",
                path="reports/pilot-b.json",
                state="missing",
                summary="missing",
            ),
        ),
        monetization_signals=(
            PilotCohortMonetizationSignal(
                id="hosted_aggregation",
                yes=1,
                no=0,
                unclear=0,
            ),
            PilotCohortMonetizationSignal(
                id="premium_policy_packs",
                yes=0,
                no=0,
                unclear=1,
            ),
        ),
        readiness_signals=(
            PilotCohortReadinessSignal(
                id="design_partner_feedback",
                ready=1,
                pass_count=0,
                partial=0,
                insufficient=0,
                missing=0,
                invalid=0,
                unsafe=0,
                other=0,
            ),
        ),
        actions=(
            PilotCohortAction(
                priority="medium",
                category="generate",
                action="Generate missing pilot outcome packets before cohort review.",
                outcome_ids=("pilot-b",),
                status="missing",
            ),
            PilotCohortAction(
                priority="low",
                category="review",
                action="Review unclear monetization signals before commercial follow-up.",
                status="unclear",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert PILOT_COHORT_SCHEMA_VERSION == "entroping.pilot-cohort.v1"
    assert payload["schema_version"] == "entroping.pilot-cohort.v1"
    assert payload["summary"]["outcomes_total"] == 2
    assert schema["properties"]["schema_version"]["const"] == "entroping.pilot-cohort.v1"
    assert schema["$defs"]["source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["signal_id"]["enum"] == [
        "hosted_aggregation",
        "premium_policy_packs",
    ]
    assert schema["$defs"]["readiness_id"]["enum"] == [
        "design_partner_feedback",
        "pilot_metrics",
        "runtime_card",
        "evidence_cloud",
        "work_item_import",
    ]


def test_qa_brain_seed_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-seed.v1.schema.json").read_text())
    packet = QaBrainSeedPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=QaBrainSeedSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=0,
            sources_invalid=1,
            sources_unsafe=0,
            eval_slices_total=1,
            eval_slices_ready=0,
            next_actions_total=1,
        ),
        sources=(
            QaBrainSeedSource(
                id="test-quality-json",
                label="Generated-Test Quality JSON",
                path="reports/test-quality.json",
                state="present",
                schema_version="entroping.test-quality-report.v1",
                category="generated_test_quality",
                eval_slices=("weak_test_detection", "unsafe_generated_hurl"),
                summary="warn, score 80, 2 generated, 1 findings",
            ),
            QaBrainSeedSource(
                id="drift-json",
                label="Drift JSON",
                path="reports/drift.json",
                state="invalid",
                schema_version=None,
                category="api_inventory",
                eval_slices=("api_drift_reasoning", "bogus_evidence"),
                summary="invalid JSON",
            ),
        ),
        eval_slices=(
            QaBrainEvalSlice(
                id="weak_test_detection",
                label="Weak-test detection",
                status="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                next_action="Review generated-test quality evidence before QA-brain evals.",
            ),
        ),
        next_actions=(
            QaBrainNextAction(
                priority="medium",
                action="Add or repair value-free local evidence for weak-test detection.",
                source_ids=("test-quality-json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_SEED_SCHEMA_VERSION == "entroping.qa-brain-seed.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-seed.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "sources_total": 2,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 1,
            "sources_unsafe": 0,
            "eval_slices_total": 1,
            "eval_slices_ready": 0,
            "next_actions_total": 1,
        },
        "sources": [
            {
                "id": "test-quality-json",
                "label": "Generated-Test Quality JSON",
                "path": "reports/test-quality.json",
                "state": "present",
                "schema_version": "entroping.test-quality-report.v1",
                "category": "generated_test_quality",
                "eval_slices": ["weak_test_detection", "unsafe_generated_hurl"],
                "summary": "warn, score 80, 2 generated, 1 findings",
            },
            {
                "id": "drift-json",
                "label": "Drift JSON",
                "path": "reports/drift.json",
                "state": "invalid",
                "schema_version": None,
                "category": "api_inventory",
                "eval_slices": ["api_drift_reasoning", "bogus_evidence"],
                "summary": "invalid JSON",
            },
        ],
        "eval_slices": [
            {
                "id": "weak_test_detection",
                "label": "Weak-test detection",
                "status": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "next_action": "Review generated-test quality evidence before QA-brain evals.",
            }
        ],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Add or repair value-free local evidence for weak-test detection.",
                "source_ids": ["test-quality-json"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.qa-brain-seed.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["seed_category"]["enum"] == [
        "runtime_governance",
        "policy_governance",
        "generated_test_quality",
        "test_pyramid",
        "api_inventory",
        "mutation_fuzz",
        "redaction_safety",
        "cross_surface_handoff",
        "agent_review",
        "review_signal",
        "generic_evidence",
    ]
    assert schema["$defs"]["eval_slice_id"]["enum"] == [
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    ]


def test_qa_brain_eval_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-eval-plan.v1.schema.json").read_text())
    packet = QaBrainEvalPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        seed_schema_version="entroping.qa-brain-seed.v1",
        summary=QaBrainEvalPlanSummary(
            status="partial",
            cases_total=1,
            cases_ready=0,
            cases_missing=0,
            cases_attention=1,
            next_actions_total=1,
        ),
        cases=(
            QaBrainEvalCase(
                id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                input_contract="Value-free generated-test quality evidence rows.",
                output_contract="schema-valid QA critique result",
                acceptance_signal="Detect weak tests without using raw report contents.",
                negative_controls=("Do not reward generic confidence.",),
                next_action="Review invalid evidence before eval execution.",
            ),
        ),
        next_actions=(
            QaBrainEvalPlanNextAction(
                priority="high",
                action="Repair evidence before weak-test detection evals.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION == "entroping.qa-brain-eval-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-eval-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "seed_schema_version": "entroping.qa-brain-seed.v1",
        "summary": {
            "status": "partial",
            "cases_total": 1,
            "cases_ready": 0,
            "cases_missing": 0,
            "cases_attention": 1,
            "next_actions_total": 1,
        },
        "cases": [
            {
                "id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "input_contract": "Value-free generated-test quality evidence rows.",
                "output_contract": "schema-valid QA critique result",
                "acceptance_signal": "Detect weak tests without using raw report contents.",
                "negative_controls": ["Do not reward generic confidence."],
                "next_action": "Review invalid evidence before eval execution.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair evidence before weak-test detection evals.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-eval-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]
    assert schema["$defs"]["eval_slice_id"]["enum"] == [
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    ]


def test_qa_brain_retrieval_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-retrieval-plan.v1.schema.json").read_text())
    packet = QaBrainRetrievalPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
        summary=QaBrainRetrievalPlanSummary(
            status="partial",
            plans_total=1,
            plans_ready=0,
            plans_missing=0,
            plans_attention=1,
            next_actions_total=1,
        ),
        retrieval_plans=(
            QaBrainRetrievalPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                retrieval_category="test_quality",
                retrieval_intent="Find weak generated-test evidence by stable IDs.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body"),
                query_hints=("Find weak-test evidence using test-quality-json.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Repair local evidence before retrieval indexing.",
            ),
        ),
        next_actions=(
            QaBrainRetrievalPlanNextAction(
                priority="high",
                action="Repair retrieval evidence before weak-test detection indexing.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION == "entroping.qa-brain-retrieval-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-retrieval-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "eval_plan_schema_version": "entroping.qa-brain-eval-plan.v1",
        "summary": {
            "status": "partial",
            "plans_total": 1,
            "plans_ready": 0,
            "plans_missing": 0,
            "plans_attention": 1,
            "next_actions_total": 1,
        },
        "retrieval_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "retrieval_category": "test_quality",
                "retrieval_intent": "Find weak generated-test evidence by stable IDs.",
                "allowed_fields": ["schema_version", "artifact_id"],
                "forbidden_fields": ["request_body", "response_body"],
                "query_hints": ["Find weak-test evidence using test-quality-json."],
                "safety_notes": ["Use value-free local metadata only."],
                "next_action": "Repair local evidence before retrieval indexing.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair retrieval evidence before weak-test detection indexing.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-retrieval-plan.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["retrieval_category"]["enum"] == [
        "test_quality",
        "policy_governance",
        "generated_hurl_safety",
        "evidence_integrity",
        "redaction_safety",
        "api_drift",
        "mutation_fuzz",
        "cross_surface_handoff",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_prompt_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-prompt-plan.v1.schema.json").read_text())
    packet = QaBrainPromptPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        retrieval_plan_schema_version="entroping.qa-brain-retrieval-plan.v1",
        summary=QaBrainPromptPlanSummary(
            status="partial",
            prompts_total=1,
            prompts_ready=0,
            prompts_missing=0,
            prompts_attention=1,
            next_actions_total=1,
        ),
        prompt_plans=(
            QaBrainPromptPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                retrieval_category="test_quality",
                prompt_objective="Critique generated-test quality using stable IDs.",
                prompt_inputs_allowed=("case_id", "artifact_id"),
                prompt_inputs_forbidden=("request_body", "response_body"),
                expected_output_fields=("case_id", "risk_level"),
                deterministic_acceptance_signals=("Evidence IDs are present.",),
                negative_controls=("Do not reward generic confidence.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Repair local evidence before prompt design.",
            ),
        ),
        next_actions=(
            QaBrainPromptPlanNextAction(
                priority="high",
                action="Repair prompt-plan evidence before weak-test detection prompts.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION == "entroping.qa-brain-prompt-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-prompt-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "retrieval_plan_schema_version": "entroping.qa-brain-retrieval-plan.v1",
        "summary": {
            "status": "partial",
            "prompts_total": 1,
            "prompts_ready": 0,
            "prompts_missing": 0,
            "prompts_attention": 1,
            "next_actions_total": 1,
        },
        "prompt_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "retrieval_category": "test_quality",
                "prompt_objective": "Critique generated-test quality using stable IDs.",
                "prompt_inputs_allowed": ["case_id", "artifact_id"],
                "prompt_inputs_forbidden": ["request_body", "response_body"],
                "expected_output_fields": ["case_id", "risk_level"],
                "deterministic_acceptance_signals": ["Evidence IDs are present."],
                "negative_controls": ["Do not reward generic confidence."],
                "safety_notes": ["Use value-free local metadata only."],
                "next_action": "Repair local evidence before prompt design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair prompt-plan evidence before weak-test detection prompts.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-prompt-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["retrieval_category"]["enum"] == [
        "test_quality",
        "policy_governance",
        "generated_hurl_safety",
        "evidence_integrity",
        "redaction_safety",
        "api_drift",
        "mutation_fuzz",
        "cross_surface_handoff",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_fine_tune_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-fine-tune-readiness.v1.schema.json").read_text())
    packet = QaBrainFineTuneReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        prompt_plan_schema_version="entroping.qa-brain-prompt-plan.v1",
        summary=QaBrainFineTuneReadinessSummary(
            status="partial",
            readiness_total=1,
            readiness_ready=0,
            readiness_missing=0,
            readiness_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        readiness_rows=(
            QaBrainFineTuneReadinessRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                readiness_stage="needs_repair",
                evidence_coverage="Repair source evidence before dataset design.",
                prompt_plan_completeness="Prompt-plan metadata is complete.",
                safety_boundary="Provider-free metadata only.",
                eval_case_coverage="Covers weak-test detection.",
                redaction_boundary="No secrets, headers, cookies, tokens, or bodies.",
                deterministic_acceptance="Evidence IDs are present.",
                blockers=("Repair invalid or unsafe prompt-plan evidence.",),
                next_action="Repair prompt-plan evidence before fine-tune design.",
            ),
        ),
        next_actions=(
            QaBrainFineTuneReadinessNextAction(
                priority="high",
                action="Repair fine-tune readiness evidence before weak-test detection.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert (
        QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION == "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert payload == {
        "schema_version": "entroping.qa-brain-fine-tune-readiness.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "prompt_plan_schema_version": "entroping.qa-brain-prompt-plan.v1",
        "summary": {
            "status": "partial",
            "readiness_total": 1,
            "readiness_ready": 0,
            "readiness_missing": 0,
            "readiness_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "readiness_rows": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "readiness_stage": "needs_repair",
                "evidence_coverage": "Repair source evidence before dataset design.",
                "prompt_plan_completeness": "Prompt-plan metadata is complete.",
                "safety_boundary": "Provider-free metadata only.",
                "eval_case_coverage": "Covers weak-test detection.",
                "redaction_boundary": "No secrets, headers, cookies, tokens, or bodies.",
                "deterministic_acceptance": "Evidence IDs are present.",
                "blockers": ["Repair invalid or unsafe prompt-plan evidence."],
                "next_action": "Repair prompt-plan evidence before fine-tune design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair fine-tune readiness evidence before weak-test detection.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["prompt_plan_schema_version"]["const"] == (
        "entroping.qa-brain-prompt-plan.v1"
    )
    assert schema["$defs"]["readiness_stage"]["enum"] == [
        "metadata_ready",
        "needs_evidence",
        "needs_repair",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_model_packaging_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-model-packaging-plan.v1.schema.json").read_text())
    packet = QaBrainModelPackagingPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        fine_tune_readiness_schema_version=("entroping.qa-brain-fine-tune-readiness.v1"),
        summary=QaBrainModelPackagingPlanSummary(
            status="partial",
            plans_total=1,
            plans_ready=0,
            plans_missing=0,
            plans_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        packaging_plans=(
            QaBrainModelPackagingPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                packaging_stage="needs_boundary_repair",
                endpoint_boundary="OpenAI-compatible endpoint planning only.",
                litellm_routing_boundary="Route through LiteLLM later.",
                deployment_modes=("hosted", "local", "enterprise"),
                artifact_boundary="No model artifacts are produced.",
                access_control_audit="Access control design is required.",
                blockers=("Repair readiness evidence before packaging design.",),
                next_action="Repair readiness evidence before model packaging design.",
            ),
        ),
        next_actions=(
            QaBrainModelPackagingPlanNextAction(
                priority="high",
                action="Repair model packaging readiness evidence.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert (
        QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION == "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert payload == {
        "schema_version": "entroping.qa-brain-model-packaging-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "fine_tune_readiness_schema_version": ("entroping.qa-brain-fine-tune-readiness.v1"),
        "summary": {
            "status": "partial",
            "plans_total": 1,
            "plans_ready": 0,
            "plans_missing": 0,
            "plans_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "packaging_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "packaging_stage": "needs_boundary_repair",
                "endpoint_boundary": "OpenAI-compatible endpoint planning only.",
                "litellm_routing_boundary": "Route through LiteLLM later.",
                "deployment_modes": ["hosted", "local", "enterprise"],
                "artifact_boundary": "No model artifacts are produced.",
                "access_control_audit": "Access control design is required.",
                "blockers": ["Repair readiness evidence before packaging design."],
                "next_action": "Repair readiness evidence before model packaging design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair model packaging readiness evidence.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["fine_tune_readiness_schema_version"]["const"] == (
        "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert schema["$defs"]["packaging_stage"]["enum"] == [
        "packaging_ready",
        "needs_readiness_evidence",
        "needs_boundary_repair",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_routing_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-routing-plan.v1.schema.json").read_text())
    packet = QaBrainRoutingPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        model_packaging_plan_schema_version=("entroping.qa-brain-model-packaging-plan.v1"),
        summary=QaBrainRoutingPlanSummary(
            status="partial",
            routes_total=1,
            routes_ready=0,
            routes_missing=0,
            routes_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        routing_plans=(
            QaBrainRoutingPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                packaging_stage="needs_boundary_repair",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                routing_stage="needs_boundary_repair",
                litellm_boundary="Route through LiteLLM later.",
                endpoint_boundary="OpenAI-compatible endpoint planning only.",
                deployment_modes=("hosted", "local", "enterprise"),
                allowed_use_cases=(
                    "critique",
                    "generation",
                    "prioritization",
                    "repair_proposals",
                ),
                forbidden_authority="Hurl/QAnstitution remains authority.",
                access_control_audit="Access control design is required.",
                blockers=("Repair packaging boundaries before routing design.",),
                next_action="Repair routing readiness evidence.",
            ),
        ),
        next_actions=(
            QaBrainRoutingPlanNextAction(
                priority="high",
                action="Repair routing readiness evidence.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION == "entroping.qa-brain-routing-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-routing-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "model_packaging_plan_schema_version": ("entroping.qa-brain-model-packaging-plan.v1"),
        "summary": {
            "status": "partial",
            "routes_total": 1,
            "routes_ready": 0,
            "routes_missing": 0,
            "routes_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "routing_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "packaging_stage": "needs_boundary_repair",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "routing_stage": "needs_boundary_repair",
                "litellm_boundary": "Route through LiteLLM later.",
                "endpoint_boundary": "OpenAI-compatible endpoint planning only.",
                "deployment_modes": ["hosted", "local", "enterprise"],
                "allowed_use_cases": [
                    "critique",
                    "generation",
                    "prioritization",
                    "repair_proposals",
                ],
                "forbidden_authority": "Hurl/QAnstitution remains authority.",
                "access_control_audit": "Access control design is required.",
                "blockers": ["Repair packaging boundaries before routing design."],
                "next_action": "Repair routing readiness evidence.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair routing readiness evidence.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-routing-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["model_packaging_plan_schema_version"]["const"] == (
        "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert schema["$defs"]["routing_stage"]["enum"] == [
        "routing_design_ready",
        "needs_packaging_evidence",
        "needs_boundary_repair",
    ]
    assert schema["$defs"]["allowed_use_case"]["enum"] == [
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ]


def test_effective_policy_diff_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "effective-policy-diff.v1.schema.json").read_text())
    base = EffectivePolicyReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        imports=("rules/base.yaml",),
        gates=(
            EffectivePolicyGateReport(
                id="latency",
                source_path="qanstitution.yaml",
                condition="true",
                gate="duration < 2000",
                enforcement="block",
                final=False,
                group=None,
                description=None,
            ),
        ),
    )
    current = EffectivePolicyReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        imports=("rules/current.yaml",),
        gates=(
            EffectivePolicyGateReport(
                id="latency",
                source_path="qanstitution.yaml",
                condition="true",
                gate="duration < 1000",
                enforcement="block",
                final=True,
                group=None,
                description="Tighter latency.",
            ),
        ),
    )

    payload = effective_policy_diff_report_to_dict(
        build_effective_policy_diff_report(
            base=base,
            current=current,
            base_path=Path("reports/base-policy.json"),
            current_path=Path("reports/effective-policy.json"),
        )
    )

    assert schema["properties"]["schema_version"]["const"] == (EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION)
    assert payload["schema_version"] == "entroping.effective-policy-diff.v1"
    assert payload["status"] == "changed"
    assert payload["summary"] == {
        "added_imports": 1,
        "removed_imports": 1,
        "added_gates": 0,
        "removed_gates": 0,
        "changed_gates": 1,
    }
    changed_gates = cast(list[dict[str, object]], payload["changed_gates"])
    assert changed_gates[0]["changed_fields"] == [
        "description",
        "final",
        "gate",
    ]


def test_capture_summary_v1_schema_contract_is_versioned_and_stable() -> None:
    from datetime import UTC, datetime

    from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse

    schema = json.loads((SCHEMA_DIR / "capture-summary.v1.schema.json").read_text())
    report = compile_capture_summary(
        (
            TrafficExchange(
                captured_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
                duration_ms=20,
                redacted=True,
                request=TrafficRequest(
                    method="GET",
                    url="https://api.example.test/health?token=[REDACTED]",
                    headers={"Authorization": "[REDACTED]"},
                ),
                response=TrafficResponse(status_code=200, headers={}),
            ),
        )
    )
    payload = capture_summary_report_to_dict(report)

    assert schema["properties"]["schema_version"]["const"] == CAPTURE_SUMMARY_SCHEMA_VERSION
    assert payload["schema_version"] == "entroping.capture-summary.v1"
    assert payload["summary"] == {
        "total_records": 1,
        "total_sessions": 1,
        "redacted_records": 1,
        "unredacted_records": 0,
    }
    sessions = cast(list[dict[str, object]], payload["sessions"])
    assert sessions[0]["id"] == "session-001"
    assert payload["methods"] == [{"label": "GET", "count": 1}]
    assert payload["status_families"] == [{"label": "2xx", "count": 1}]


def test_openapi_audit_v1_schema_contract_is_versioned_and_stable() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {"201": {"description": "created"}},
                }
            },
        },
    }
    report = audit_openapi_coverage(
        document,
        [
            HurlTest(
                path=Path("tests/generated/get_health.hurl"),
                metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
                exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
            ),
            HurlTest(
                path=Path("tests/generated/stale_checkout.hurl"),
                metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "staleCheckout"}),
                exchanges=(HurlExchange(method="GET", url="{{base_url}}/stale", path="/stale"),),
            ),
        ],
    )

    payload = audit_report_to_dict(report)

    assert payload == {
        "schema_version": OPENAPI_AUDIT_SCHEMA_VERSION,
        "status": "fail",
        "summary": {
            "total_operations": 2,
            "covered_operations": 1,
            "missing_operations": 1,
            "ambiguous_operations": 0,
            "stale_references": 1,
        },
        "operation_matrix": [
            {
                "operation_id": "getHealth",
                "method": "GET",
                "path": "/health",
                "status": "covered",
                "tests": ["tests/generated/get_health.hurl"],
                "negative_tests": [],
            },
            {
                "operation_id": "createCheckout",
                "method": "POST",
                "path": "/checkout",
                "status": "uncovered",
                "tests": [],
                "negative_tests": [],
            },
        ],
        "findings": [
            {
                "code": "OPENAPI_COVERAGE_MISSING",
                "severity": "error",
                "operation_id": "createCheckout",
                "method": "POST",
                "path": "/checkout",
                "message": ("OpenAPI operation 'createCheckout' has no committed Hurl coverage."),
            }
        ],
        "stale_references": [
            {
                "operation_id": "staleCheckout",
                "test_path": "tests/generated/stale_checkout.hurl",
            }
        ],
        "traffic_routes": None,
    }


def test_design_partner_feedback_v1_schema_contract_is_safe_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "design-partner-feedback.v1.schema.json").read_text())
    required = set(schema["required"])

    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.design-partner-feedback.v1"
    )
    assert schema["properties"]["recorded_at"]["format"] == "date-time"
    assert schema["additionalProperties"] is False
    assert {
        "schema_version",
        "recorded_at",
        "pilot",
        "evidence",
        "feedback",
        "monetization_signals",
        "follow_up",
    } <= required
    assert schema["properties"]["pilot"]["required"] == [
        "repo_or_service",
        "ai_assisted_change_type",
    ]
    assert schema["properties"]["pilot"]["additionalProperties"] is False
    assert schema["properties"]["evidence"]["required"] == [
        "entroping_commands_run",
        "evidence_bundle_status",
        "runtime_card_status",
    ]
    assert schema["properties"]["evidence"]["additionalProperties"] is False
    assert schema["properties"]["evidence"]["properties"]["pilot_metrics_status"]["enum"] == [
        "complete",
        "partial",
        "insufficient",
        "missing",
        "invalid",
        "unsafe",
        "not_collected",
    ]
    assert schema["properties"]["feedback"]["required"] == [
        "blocked_regression_or_useful_failure",
        "false_positive_or_noisy_gate",
        "missing_evidence",
        "setup_friction",
        "security_privacy_concern",
    ]
    assert schema["properties"]["feedback"]["additionalProperties"] is False
    assert schema["$defs"]["nullable_sanitized_summary"]["type"] == ["string", "null"]
    for field in schema["properties"]["feedback"]["required"]:
        assert schema["properties"]["feedback"]["properties"][field] == {
            "$ref": "#/$defs/nullable_sanitized_summary"
        }
    assert schema["properties"]["monetization_signals"]["required"] == [
        "hosted_aggregation",
        "premium_policy_packs",
    ]
    assert schema["properties"]["monetization_signals"]["additionalProperties"] is False
    assert schema["properties"]["follow_up"]["additionalProperties"] is False
    signal = schema["$defs"]["pay_signal"]
    assert signal["required"] == ["answer", "reason"]
    assert signal["properties"]["answer"]["enum"] == ["yes", "no", "unclear"]

    serialized_schema = json.dumps(schema)
    forbidden_fields = [
        "customer_secret",
        "raw_traffic",
        "credential",
        "provider_output",
        "source_hurl",
        "conversation_dump",
        "prompt_transcript",
    ]
    for field in forbidden_fields:
        assert field not in serialized_schema


def test_report_schema_files_are_parseable_and_list_current_versions() -> None:
    versions = {
        "entroping.run-report.v1": SCHEMA_DIR / "run-report.v1.schema.json",
        "entroping.run-delta-report.v1": (SCHEMA_DIR / "run-delta-report.v1.schema.json"),
        "entroping.drift-report.v1": SCHEMA_DIR / "drift-report.v1.schema.json",
        "entroping.traceability-report.v1": (SCHEMA_DIR / "traceability-report.v1.schema.json"),
        "entroping.effective-policy-report.v1": (
            SCHEMA_DIR / "effective-policy-report.v1.schema.json"
        ),
        "entroping.effective-policy-diff.v1": (SCHEMA_DIR / "effective-policy-diff.v1.schema.json"),
        "entroping.capture-summary.v1": SCHEMA_DIR / "capture-summary.v1.schema.json",
        "entroping.gate-injection-report.v1": (SCHEMA_DIR / "gate-injection-report.v1.schema.json"),
        "entroping.gate-coverage-report.v1": (SCHEMA_DIR / "gate-coverage-report.v1.schema.json"),
        "entroping.test-quality-report.v1": (SCHEMA_DIR / "test-quality-report.v1.schema.json"),
        "entroping.test-pyramid-report.v1": (SCHEMA_DIR / "test-pyramid-report.v1.schema.json"),
        "entroping.report-artifact-manifest.v1": (
            SCHEMA_DIR / "report-artifact-manifest.v1.schema.json"
        ),
        "entroping.evidence-bundle.v1": SCHEMA_DIR / "evidence-bundle.v1.schema.json",
        "entroping.runtime-card.v1": SCHEMA_DIR / "runtime-card.v1.schema.json",
        "entroping.pilot-metrics.v1": SCHEMA_DIR / "pilot-metrics.v1.schema.json",
        "entroping.handoff.v1": SCHEMA_DIR / "handoff.v1.schema.json",
        "entroping.notification-packet.v1": (SCHEMA_DIR / "notification-packet.v1.schema.json"),
        "entroping.team-evidence-readiness.v1": (
            SCHEMA_DIR / "team-evidence-readiness.v1.schema.json"
        ),
        "entroping.team-access-control-plan.v1": (
            SCHEMA_DIR / "team-access-control-plan.v1.schema.json"
        ),
        "entroping.devex-readiness.v1": (SCHEMA_DIR / "devex-readiness.v1.schema.json"),
        "entroping.evidence-cloud-readiness.v1": (
            SCHEMA_DIR / "evidence-cloud-readiness.v1.schema.json"
        ),
        "entroping.evidence-cloud-export.v1": (
            SCHEMA_DIR / "evidence-cloud-export.v1.schema.json"
        ),
        "entroping.evidence-cloud-workspace.v1": (
            SCHEMA_DIR / "evidence-cloud-workspace.v1.schema.json"
        ),
        "entroping.evidence-cloud-dashboard.v1": (
            SCHEMA_DIR / "evidence-cloud-dashboard.v1.schema.json"
        ),
        "entroping.evidence-links.v1": (SCHEMA_DIR / "evidence-links.v1.schema.json"),
        "entroping.evidence-portal.v1": (SCHEMA_DIR / "evidence-portal.v1.schema.json"),
        "entroping.pr-evidence-card.v1": (SCHEMA_DIR / "pr-evidence-card.v1.schema.json"),
        "entroping.evidence-action-plan.v1": (
            SCHEMA_DIR / "evidence-action-plan.v1.schema.json"
        ),
        "entroping.work-item-draft.v1": (SCHEMA_DIR / "work-item-draft.v1.schema.json"),
        "entroping.work-item-import-bundle.v1": (
            SCHEMA_DIR / "work-item-import-bundle.v1.schema.json"
        ),
        "entroping.pilot-outcome.v1": SCHEMA_DIR / "pilot-outcome.v1.schema.json",
        "entroping.pilot-cohort.v1": SCHEMA_DIR / "pilot-cohort.v1.schema.json",
        "entroping.connector-intent.v1": (SCHEMA_DIR / "connector-intent.v1.schema.json"),
        "entroping.external-test-evidence.v1": (
            SCHEMA_DIR / "external-test-evidence.v1.schema.json"
        ),
        "entroping.integration-readiness.v1": (SCHEMA_DIR / "integration-readiness.v1.schema.json"),
        "entroping.observability-packet.v1": (SCHEMA_DIR / "observability-packet.v1.schema.json"),
        "entroping.otel-mapping.v1": SCHEMA_DIR / "otel-mapping.v1.schema.json",
        "entroping.observability-adapter-readiness.v1": (
            SCHEMA_DIR / "observability-adapter-readiness.v1.schema.json"
        ),
        "entroping.api-inventory.v1": SCHEMA_DIR / "api-inventory.v1.schema.json",
        "entroping.mutation-readiness.v1": (SCHEMA_DIR / "mutation-readiness.v1.schema.json"),
        "entroping.evidence-index.v1": SCHEMA_DIR / "evidence-index.v1.schema.json",
        "entroping.qa-brain-seed.v1": SCHEMA_DIR / "qa-brain-seed.v1.schema.json",
        "entroping.qa-brain-eval-plan.v1": (SCHEMA_DIR / "qa-brain-eval-plan.v1.schema.json"),
        "entroping.qa-brain-retrieval-plan.v1": (
            SCHEMA_DIR / "qa-brain-retrieval-plan.v1.schema.json"
        ),
        "entroping.qa-brain-prompt-plan.v1": (SCHEMA_DIR / "qa-brain-prompt-plan.v1.schema.json"),
        "entroping.qa-brain-fine-tune-readiness.v1": (
            SCHEMA_DIR / "qa-brain-fine-tune-readiness.v1.schema.json"
        ),
        "entroping.qa-brain-model-packaging-plan.v1": (
            SCHEMA_DIR / "qa-brain-model-packaging-plan.v1.schema.json"
        ),
        "entroping.qa-brain-routing-plan.v1": (SCHEMA_DIR / "qa-brain-routing-plan.v1.schema.json"),
        "entroping.design-partner-feedback.v1": (
            SCHEMA_DIR / "design-partner-feedback.v1.schema.json"
        ),
        "entroping.agent-review-bundle.v1": (SCHEMA_DIR / "agent-review-bundle.v1.schema.json"),
        "entroping.traffic-artifact-approval.v1": (
            SCHEMA_DIR / "traffic-artifact-approval.v1.schema.json"
        ),
    }
    schema_doc = (REPO_ROOT / "docs" / "technical" / "REPORT_SCHEMAS.md").read_text(
        encoding="utf-8"
    )

    for schema_version, path in versions.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"]["const"] == schema_version
        assert schema_version in schema_doc
