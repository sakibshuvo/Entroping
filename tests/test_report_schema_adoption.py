"""Versioned report schema contract tests."""

import json
from pathlib import Path

from entroping.core.evidence.connector_intent import (
    CONNECTOR_INTENT_SCHEMA_VERSION,
    ConnectorIntentNextAction,
    ConnectorIntentPacket,
    ConnectorIntentRecord,
    ConnectorIntentSource,
    ConnectorIntentSummary,
)
from entroping.core.evidence.evidence_cloud_dashboard import (
    EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION,
    EvidenceCloudDashboardManifest,
    EvidenceCloudDashboardPacket,
    EvidenceCloudDashboardRepository,
    EvidenceCloudDashboardSummary,
)
from entroping.core.evidence.evidence_links import (
    EVIDENCE_LINKS_SCHEMA_VERSION,
    EvidenceLinksNextAction,
    EvidenceLinksPacket,
    EvidenceLinksSource,
    EvidenceLinksSummary,
    EvidenceLinkTarget,
)
from entroping.core.evidence.evidence_portal import (
    EVIDENCE_PORTAL_SCHEMA_VERSION,
    EvidencePortalCard,
    EvidencePortalNextAction,
    EvidencePortalPacket,
    EvidencePortalSource,
    EvidencePortalSummary,
)
from entroping.core.evidence.external_test_evidence import (
    EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
    ExternalTestEvidenceLayer,
    ExternalTestEvidenceNextAction,
    ExternalTestEvidencePacket,
    ExternalTestEvidenceSource,
    ExternalTestEvidenceSummary,
)
from entroping.core.evidence.handoff_packet import (
    HANDOFF_SCHEMA_VERSION,
    HandoffArtifact,
    HandoffGit,
    HandoffPacket,
    HandoffRuntimeSummary,
    HandoffSummary,
    HandoffTarget,
)
from entroping.core.evidence.notification_packet import (
    NOTIFICATION_PACKET_SCHEMA_VERSION,
    NotificationMessage,
    NotificationPacket,
    NotificationPreview,
    NotificationRuntimeSummary,
    NotificationSource,
    NotificationSummary,
)
from entroping.core.evidence.pilot_cohort import (
    PILOT_COHORT_SCHEMA_VERSION,
    PilotCohortAction,
    PilotCohortMonetizationSignal,
    PilotCohortOutcome,
    PilotCohortPacket,
    PilotCohortReadinessSignal,
    PilotCohortSummary,
)
from entroping.core.evidence.pilot_metrics import (
    PILOT_METRICS_SCHEMA_VERSION,
    PilotEvidenceSource,
    PilotMetric,
    PilotMetricsReport,
    PilotMetricsSummary,
)
from entroping.core.evidence.pilot_outcome import (
    PILOT_OUTCOME_SCHEMA_VERSION,
    PilotOutcomeAction,
    PilotOutcomeMonetizationSignal,
    PilotOutcomePacket,
    PilotOutcomeReadiness,
    PilotOutcomeSource,
    PilotOutcomeSummary,
)
from entroping.core.evidence.pr_evidence_card import (
    PR_EVIDENCE_CARD_SCHEMA_VERSION,
    PrEvidenceCardChecklistItem,
    PrEvidenceCardNextAction,
    PrEvidenceCardPacket,
    PrEvidenceCardSource,
    PrEvidenceCardSummary,
)
from entroping.core.export.evidence_cloud_export import (
    EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION,
    EvidenceCloudExportBoundaryControl,
    EvidenceCloudExportItem,
    EvidenceCloudExportNextAction,
    EvidenceCloudExportPacket,
    EvidenceCloudExportSource,
    EvidenceCloudExportSummary,
)
from entroping.core.export.evidence_cloud_workspace import (
    EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION,
    EvidenceCloudWorkspaceBoundaryControl,
    EvidenceCloudWorkspaceManifest,
    EvidenceCloudWorkspaceNextAction,
    EvidenceCloudWorkspacePacket,
    EvidenceCloudWorkspaceRepository,
    EvidenceCloudWorkspaceSummary,
)
from entroping.core.export.work_item_draft import (
    WORK_ITEM_DRAFT_SCHEMA_VERSION,
    WorkItemDraftItem,
    WorkItemDraftPacket,
    WorkItemDraftSource,
    WorkItemDraftSummary,
)
from entroping.core.export.work_item_import_bundle import (
    WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION,
    WORK_ITEM_IMPORT_CSV_COLUMNS,
    WORK_ITEM_IMPORT_CSV_CONTRACT_VERSION,
    WorkItemImportAction,
    WorkItemImportBundle,
    WorkItemImportRow,
    WorkItemImportSource,
    WorkItemImportSummary,
)
from entroping.core.plan.evidence_action_plan import (
    EVIDENCE_ACTION_PLAN_SCHEMA_VERSION,
    EvidenceActionPlanItem,
    EvidenceActionPlanPacket,
    EvidenceActionPlanSource,
    EvidenceActionPlanSummary,
)
from entroping.core.plan.team_access_control_plan import (
    TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
    TeamAccessControlAuditEvent,
    TeamAccessControlBoundary,
    TeamAccessControlNextAction,
    TeamAccessControlPlanPacket,
    TeamAccessControlPlanSummary,
    TeamAccessControlRolePlan,
    TeamAccessControlSource,
)
from entroping.core.readiness.devex_readiness import (
    DEVEX_READINESS_SCHEMA_VERSION,
    DevexReadinessFamily,
    DevexReadinessNextAction,
    DevexReadinessPacket,
    DevexReadinessSource,
    DevexReadinessSummary,
)
from entroping.core.readiness.evidence_cloud_readiness import (
    EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION,
    EvidenceCloudBoundary,
    EvidenceCloudNextAction,
    EvidenceCloudReadinessArea,
    EvidenceCloudReadinessPacket,
    EvidenceCloudSource,
    EvidenceCloudSummary,
    EvidenceCloudUploadCandidate,
)
from entroping.core.readiness.integration_readiness import (
    INTEGRATION_READINESS_SCHEMA_VERSION,
    IntegrationReadinessFamily,
    IntegrationReadinessNextAction,
    IntegrationReadinessPacket,
    IntegrationReadinessSource,
    IntegrationReadinessSummary,
    IntegrationReadinessSurfaceBlockerTotal,
)
from entroping.core.readiness.team_evidence_readiness import (
    TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
    TeamEvidenceCloudBoundary,
    TeamEvidenceNextAction,
    TeamEvidenceReadinessArea,
    TeamEvidenceReadinessPacket,
    TeamEvidenceReadinessSummary,
    TeamEvidenceSource,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "docs" / "technical" / "report-schemas"


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
        previews=(
            NotificationPreview(
                family="issue_tracker",
                surface="jira",
                label="Jira",
                readiness="ready",
                local_evidence_refs=("reports/notification-packet.json", "reports/handoff.json"),
                next_action="Attach this packet as read-only issue evidence.",
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
        "previews": [
            {
                "family": "issue_tracker",
                "surface": "jira",
                "label": "Jira",
                "readiness": "ready",
                "local_evidence_refs": [
                    "reports/notification-packet.json",
                    "reports/handoff.json",
                ],
                "next_action": "Attach this packet as read-only issue evidence.",
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
    assert schema["properties"]["previews"]["$ref"] == "#/$defs/previews"
    assert schema["$defs"]["preview"]["properties"]["family"]["enum"] == [
        "issue_tracker",
        "chat",
        "automation",
        "agent",
    ]
    assert schema["$defs"]["preview"]["properties"]["readiness"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
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
            first_five_minutes_score=100,
            first_five_minutes_readiness_band="ready",
            missing_source_count=0,
            top_next_action="Generate evidence-index evidence before editor surfaces.",
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
            EvidenceCloudDashboardManifest(
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
    assert schema["properties"]["capability_matrix"]["items"]["$ref"] == "#/$defs/capability"
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
            surface_blocker_totals=(
                IntegrationReadinessSurfaceBlockerTotal(
                    surface="tracker",
                    label="Tracker",
                    family_ids=("issue_trackers",),
                    surface_ids=("jira", "linear", "monday"),
                    families_blocked=0,
                    families_attention=0,
                    blockers_total=0,
                ),
            ),
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
    assert payload["summary"]["surface_blocker_totals"] == [
        {
            "surface": "tracker",
            "label": "Tracker",
            "family_ids": ["issue_trackers"],
            "surface_ids": ["jira", "linear", "monday"],
            "families_blocked": 0,
            "families_attention": 0,
            "blockers_total": 0,
        }
    ]
    assert schema["properties"]["schema_version"]["const"] == ("entroping.integration-readiness.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert "surface_blocker_totals" not in schema["$defs"]["summary"]["required"]
    assert schema["$defs"]["summary"]["properties"]["surface_blocker_totals"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/surface_blocker_total"},
    }
    assert schema["$defs"]["surface_group_id"]["enum"] == [
        "tracker",
        "chat",
        "automation",
        "evidence_surface",
        "observability_surface",
    ]
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
                artifact_uri="entroping://evidence/runtime-card-json",
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
                artifact_uri="entroping://evidence/evidence-index-json",
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
    assert payload["targets"][0]["artifact_uri"] == "entroping://evidence/runtime-card-json"
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
    assert payload["csv_contract_version"] == WORK_ITEM_IMPORT_CSV_CONTRACT_VERSION
    assert payload["csv_columns"] == list(WORK_ITEM_IMPORT_CSV_COLUMNS)
    assert payload["summary"]["source_item_count"] == 1
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.work-item-import-bundle.v1"
    )
    assert schema["properties"]["csv_contract_version"]["const"] == (
        "entroping.work-item-import-csv.v1"
    )
    assert schema["properties"]["csv_columns"]["prefixItems"] == [
        {"const": column} for column in WORK_ITEM_IMPORT_CSV_COLUMNS
    ]
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
