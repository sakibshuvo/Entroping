"""Read-only local evidence artifact index for Studio and future viewers."""

from __future__ import annotations

import errno
import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.bridge.capture_summary import CAPTURE_SUMMARY_SCHEMA_VERSION
from entroping.bridge.effective_policy import EFFECTIVE_POLICY_SCHEMA_VERSION
from entroping.bridge.gate_coverage import GATE_COVERAGE_REPORT_SCHEMA_VERSION
from entroping.bridge.gate_injection_explain import GATE_INJECTION_REPORT_SCHEMA_VERSION
from entroping.bridge.test_pyramid import TEST_PYRAMID_REPORT_SCHEMA_VERSION
from entroping.bridge.test_quality import TEST_QUALITY_REPORT_SCHEMA_VERSION
from entroping.core import report_schema_versions as _report_schema_versions
from entroping.core.drift_report import DRIFT_REPORT_SCHEMA_VERSION
from entroping.core.evidence.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence.api_inventory import API_INVENTORY_SCHEMA_VERSION
from entroping.core.evidence.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence.external_test_evidence import EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
from entroping.core.evidence.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.evidence.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.evidence.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    register_local_evidence_descriptor,
)
from entroping.core.failure_bundle import FAILURE_BUNDLE_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.readiness.mutation_readiness import MUTATION_READINESS_SCHEMA_VERSION
from entroping.core.report_artifact_manifest import REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION
from entroping.core.run_workflow import RUN_PLAN_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION

EvidenceArtifactState = Literal["present", "missing", "invalid", "unsafe"]
_ArtifactKind = Literal["json", "markdown", "xml", "html", "sarif", "csv"]
_SummaryBuilder = Callable[[dict[str, object]], str]
_MAX_JSON_ARTIFACT_BYTES: Final = 10 * 1024 * 1024
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_HAS_O_DIRECTORY: Final = hasattr(os, "O_DIRECTORY")
_HAS_O_NOFOLLOW: Final = hasattr(os, "O_NOFOLLOW")
_SUPPORTS_DIR_FD_OPEN: Final = os.open in os.supports_dir_fd
EVIDENCE_INDEX_SCHEMA_VERSION: Final = _report_schema_versions.EVIDENCE_INDEX_SCHEMA_VERSION
OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION: Final = (
    _report_schema_versions.OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION
)
OTEL_MAPPING_SCHEMA_VERSION: Final = _report_schema_versions.OTEL_MAPPING_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class LocalEvidenceArtifact:
    """Value-free status for one canonical local evidence artifact."""

    id: str
    label: str
    path: str
    state: EvidenceArtifactState
    schema_version: str | None
    summary: str


@dataclass(frozen=True, slots=True)
class _EvidenceArtifactDefinition:
    id: str
    label: str
    path: Path
    kind: _ArtifactKind
    schema_version: str | None
    summary_builder: _SummaryBuilder | None = None
    reject_secret_like: bool = False


def build_local_evidence_index(*, project_root: Path) -> tuple[LocalEvidenceArtifact, ...]:
    """Return value-free status rows for canonical local report artifacts."""

    root = project_root.expanduser().resolve()
    return tuple(_artifact_status(definition, root=root) for definition in _artifact_definitions())


def read_local_evidence_json_artifact_bytes(
    path: Path,
    *,
    root: Path,
) -> tuple[bytes | None, str]:
    """Read one bounded local evidence JSON artifact through the index safety path."""

    return _read_json_artifact_bytes(path, root=root)


def _artifact_definitions() -> tuple[_EvidenceArtifactDefinition, ...]:
    return (
        _EvidenceArtifactDefinition(
            id="run-json",
            label="Run JSON",
            path=Path("reports") / "run-latest.json",
            kind="json",
            schema_version=RUN_REPORT_SCHEMA_VERSION,
            summary_builder=_run_summary,
        ),
        _EvidenceArtifactDefinition(
            id="run-plan-json",
            label="Run Plan",
            path=Path("reports") / "run-plan.json",
            kind="json",
            schema_version=RUN_PLAN_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="junit-xml",
            label="JUnit XML",
            path=Path("reports") / "junit.xml",
            kind="xml",
            schema_version="junit.xml",
        ),
        _EvidenceArtifactDefinition(
            id="run-html",
            label="Run HTML",
            path=Path("reports") / "run-latest.html",
            kind="html",
            schema_version="entroping.run-report.html",
        ),
        _EvidenceArtifactDefinition(
            id="drift-json",
            label="Drift JSON",
            path=Path("reports") / "drift.json",
            kind="json",
            schema_version=DRIFT_REPORT_SCHEMA_VERSION,
            summary_builder=_drift_summary,
        ),
        _EvidenceArtifactDefinition(
            id="bug-md",
            label="Bug Markdown",
            path=Path("reports") / "bug.md",
            kind="markdown",
            schema_version="entroping.bug.md",
        ),
        _EvidenceArtifactDefinition(
            id="failure-bundle-manifest-json",
            label="Failure Bundle Manifest",
            path=Path("reports") / "failure-bundle" / "manifest.json",
            kind="json",
            schema_version=FAILURE_BUNDLE_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="capture-summary-json",
            label="Capture Summary JSON",
            path=Path("reports") / "capture-summary.json",
            kind="json",
            schema_version=CAPTURE_SUMMARY_SCHEMA_VERSION,
            summary_builder=_capture_summary,
        ),
        _EvidenceArtifactDefinition(
            id="capture-summary-md",
            label="Capture Summary Markdown",
            path=Path("reports") / "capture-summary.md",
            kind="markdown",
            schema_version="entroping.capture-summary.md",
        ),
        _EvidenceArtifactDefinition(
            id="effective-policy-json",
            label="Effective Policy JSON",
            path=Path("reports") / "effective-policy.json",
            kind="json",
            schema_version=EFFECTIVE_POLICY_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="effective-policy-md",
            label="Effective Policy Markdown",
            path=Path("reports") / "effective-policy.md",
            kind="markdown",
            schema_version="entroping.effective-policy.md",
        ),
        _EvidenceArtifactDefinition(
            id="gate-coverage-json",
            label="Gate Coverage JSON",
            path=Path("reports") / "gate-coverage.json",
            kind="json",
            schema_version=GATE_COVERAGE_REPORT_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="gate-coverage-md",
            label="Gate Coverage Markdown",
            path=Path("reports") / "gate-coverage.md",
            kind="markdown",
            schema_version="entroping.gate-coverage.md",
        ),
        _EvidenceArtifactDefinition(
            id="gate-injection-json",
            label="Gate Injection JSON",
            path=Path("reports") / "gate-injection.json",
            kind="json",
            schema_version=GATE_INJECTION_REPORT_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="gate-injection-md",
            label="Gate Injection Markdown",
            path=Path("reports") / "gate-injection.md",
            kind="markdown",
            schema_version="entroping.gate-injection.md",
        ),
        _EvidenceArtifactDefinition(
            id="test-quality-json",
            label="Generated-Test Quality JSON",
            path=Path("reports") / "test-quality.json",
            kind="json",
            schema_version=TEST_QUALITY_REPORT_SCHEMA_VERSION,
            summary_builder=_test_quality_summary,
        ),
        _EvidenceArtifactDefinition(
            id="test-quality-md",
            label="Generated-Test Quality Markdown",
            path=Path("reports") / "test-quality.md",
            kind="markdown",
            schema_version="entroping.test-quality.md",
        ),
        _EvidenceArtifactDefinition(
            id="test-pyramid-json",
            label="Test Pyramid JSON",
            path=Path("reports") / "test-pyramid.json",
            kind="json",
            schema_version=TEST_PYRAMID_REPORT_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="test-pyramid-md",
            label="Test Pyramid Markdown",
            path=Path("reports") / "test-pyramid.md",
            kind="markdown",
            schema_version="entroping.test-pyramid.md",
        ),
        _EvidenceArtifactDefinition(
            id="external-test-evidence-json",
            label="External Test Evidence JSON",
            path=Path("reports") / "external-test-evidence.json",
            kind="json",
            schema_version=EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
            summary_builder=_external_test_evidence_summary,
            reject_secret_like=True,
        ),
        _EvidenceArtifactDefinition(
            id="external-test-evidence-md",
            label="External Test Evidence Markdown",
            path=Path("reports") / "external-test-evidence.md",
            kind="markdown",
            schema_version="entroping.external-test-evidence.md",
        ),
        _EvidenceArtifactDefinition(
            id="artifact-manifest-json",
            label="Artifact Manifest",
            path=Path("reports") / "artifact-manifest.json",
            kind="json",
            schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
            summary_builder=_artifact_manifest_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-bundle-json",
            label="Evidence Bundle",
            path=Path("reports") / "evidence-bundle.json",
            kind="json",
            schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="runtime-card-md",
            label="Runtime Card Markdown",
            path=Path("reports") / "runtime-card.md",
            kind="markdown",
            schema_version="entroping.runtime-card.md",
        ),
        _EvidenceArtifactDefinition(
            id="runtime-card-json",
            label="Runtime Card JSON",
            path=Path("reports") / "runtime-card.json",
            kind="json",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="handoff-md",
            label="Handoff Markdown",
            path=Path("reports") / "handoff.md",
            kind="markdown",
            schema_version="entroping.handoff.md",
        ),
        _EvidenceArtifactDefinition(
            id="handoff-json",
            label="Handoff JSON",
            path=Path("reports") / "handoff.json",
            kind="json",
            schema_version=HANDOFF_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="notification-packet-md",
            label="Notification Packet Markdown",
            path=Path("reports") / "notification-packet.md",
            kind="markdown",
            schema_version="entroping.notification-packet.md",
        ),
        _EvidenceArtifactDefinition(
            id="notification-packet-json",
            label="Notification Packet JSON",
            path=Path("reports") / "notification-packet.json",
            kind="json",
            schema_version=NOTIFICATION_PACKET_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="team-evidence-readiness-md",
            label="Team Evidence Readiness Markdown",
            path=Path("reports") / "team-evidence-readiness.md",
            kind="markdown",
            schema_version="entroping.team-evidence-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="team-evidence-readiness-json",
            label="Team Evidence Readiness JSON",
            path=Path("reports") / "team-evidence-readiness.json",
            kind="json",
            schema_version="entroping.team-evidence-readiness.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="team-access-control-plan-md",
            label="Team Access-Control Plan Markdown",
            path=Path("reports") / "team-access-control-plan.md",
            kind="markdown",
            schema_version="entroping.team-access-control-plan.md",
        ),
        _EvidenceArtifactDefinition(
            id="team-access-control-plan-json",
            label="Team Access-Control Plan JSON",
            path=Path("reports") / "team-access-control-plan.json",
            kind="json",
            schema_version="entroping.team-access-control-plan.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="integration-readiness-md",
            label="Integration Readiness Markdown",
            path=Path("reports") / "integration-readiness.md",
            kind="markdown",
            schema_version="entroping.integration-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="integration-readiness-json",
            label="Integration Readiness JSON",
            path=Path("reports") / "integration-readiness.json",
            kind="json",
            schema_version="entroping.integration-readiness.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="devex-readiness-md",
            label="Developer Experience Readiness Markdown",
            path=Path("reports") / "devex-readiness.md",
            kind="markdown",
            schema_version="entroping.devex-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="devex-readiness-json",
            label="Developer Experience Readiness JSON",
            path=Path("reports") / "devex-readiness.json",
            kind="json",
            schema_version="entroping.devex-readiness.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="connector-intent-md",
            label="Connector Intent Markdown",
            path=Path("reports") / "connector-intent.md",
            kind="markdown",
            schema_version="entroping.connector-intent.md",
        ),
        _EvidenceArtifactDefinition(
            id="connector-intent-json",
            label="Connector Intent JSON",
            path=Path("reports") / "connector-intent.json",
            kind="json",
            schema_version="entroping.connector-intent.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-readiness-md",
            label="Evidence Cloud Readiness Markdown",
            path=Path("reports") / "evidence-cloud-readiness.md",
            kind="markdown",
            schema_version="entroping.evidence-cloud-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-readiness-json",
            label="Evidence Cloud Readiness JSON",
            path=Path("reports") / "evidence-cloud-readiness.json",
            kind="json",
            schema_version="entroping.evidence-cloud-readiness.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-export-md",
            label="Evidence Cloud Export Markdown",
            path=Path("reports") / "evidence-cloud-export.md",
            kind="markdown",
            schema_version="entroping.evidence-cloud-export.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-export-json",
            label="Evidence Cloud Export JSON",
            path=Path("reports") / "evidence-cloud-export.json",
            kind="json",
            schema_version="entroping.evidence-cloud-export.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-workspace-md",
            label="Evidence Cloud Workspace Markdown",
            path=Path("reports") / "evidence-cloud-workspace.md",
            kind="markdown",
            schema_version="entroping.evidence-cloud-workspace.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-workspace-json",
            label="Evidence Cloud Workspace JSON",
            path=Path("reports") / "evidence-cloud-workspace.json",
            kind="json",
            schema_version="entroping.evidence-cloud-workspace.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-dashboard-html",
            label="Evidence Cloud Dashboard HTML",
            path=Path("reports") / "evidence-cloud-dashboard.html",
            kind="html",
            schema_version="entroping.evidence-cloud-dashboard.html",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-cloud-dashboard-json",
            label="Evidence Cloud Dashboard JSON",
            path=Path("reports") / "evidence-cloud-dashboard.json",
            kind="json",
            schema_version="entroping.evidence-cloud-dashboard.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-links-md",
            label="Evidence Links Markdown",
            path=Path("reports") / "evidence-links.md",
            kind="markdown",
            schema_version="entroping.evidence-links.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-links-json",
            label="Evidence Links JSON",
            path=Path("reports") / "evidence-links.json",
            kind="json",
            schema_version="entroping.evidence-links.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-portal-html",
            label="Evidence Portal HTML",
            path=Path("reports") / "evidence-portal.html",
            kind="html",
            schema_version="entroping.evidence-portal.html",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-portal-json",
            label="Evidence Portal JSON",
            path=Path("reports") / "evidence-portal.json",
            kind="json",
            schema_version="entroping.evidence-portal.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="pr-evidence-card-md",
            label="PR Evidence Card Markdown",
            path=Path("reports") / "pr-evidence-card.md",
            kind="markdown",
            schema_version="entroping.pr-evidence-card.md",
        ),
        _EvidenceArtifactDefinition(
            id="pr-evidence-card-json",
            label="PR Evidence Card JSON",
            path=Path("reports") / "pr-evidence-card.json",
            kind="json",
            schema_version="entroping.pr-evidence-card.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-action-plan-md",
            label="Evidence Action Plan Markdown",
            path=Path("reports") / "evidence-action-plan.md",
            kind="markdown",
            schema_version="entroping.evidence-action-plan.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-action-plan-json",
            label="Evidence Action Plan JSON",
            path=Path("reports") / "evidence-action-plan.json",
            kind="json",
            schema_version="entroping.evidence-action-plan.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="work-item-draft-md",
            label="Work Item Draft Markdown",
            path=Path("reports") / "work-item-draft.md",
            kind="markdown",
            schema_version="entroping.work-item-draft.md",
        ),
        _EvidenceArtifactDefinition(
            id="work-item-draft-json",
            label="Work Item Draft JSON",
            path=Path("reports") / "work-item-draft.json",
            kind="json",
            schema_version="entroping.work-item-draft.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="work-item-import-bundle-json",
            label="Work Item Import Bundle JSON",
            path=Path("reports") / "work-item-import-bundle.json",
            kind="json",
            schema_version="entroping.work-item-import-bundle.v1",
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="work-item-import-bundle-csv",
            label="Work Item Import Bundle CSV",
            path=Path("reports") / "work-item-import-bundle.csv",
            kind="csv",
            schema_version="entroping.work-item-import-bundle.csv",
        ),
        _EvidenceArtifactDefinition(
            id="pilot-outcome-md",
            label="Pilot Outcome Markdown",
            path=Path("reports") / "pilot-outcome.md",
            kind="markdown",
            schema_version="entroping.pilot-outcome.md",
        ),
        _EvidenceArtifactDefinition(
            id="pilot-outcome-json",
            label="Pilot Outcome JSON",
            path=Path("reports") / "pilot-outcome.json",
            kind="json",
            schema_version="entroping.pilot-outcome.v1",
            summary_builder=_status_summary,
            reject_secret_like=True,
        ),
        _EvidenceArtifactDefinition(
            id="pilot-cohort-md",
            label="Pilot Cohort Markdown",
            path=Path("reports") / "pilot-cohort.md",
            kind="markdown",
            schema_version="entroping.pilot-cohort.md",
        ),
        _EvidenceArtifactDefinition(
            id="pilot-cohort-json",
            label="Pilot Cohort JSON",
            path=Path("reports") / "pilot-cohort.json",
            kind="json",
            schema_version="entroping.pilot-cohort.v1",
            summary_builder=_status_summary,
            reject_secret_like=True,
        ),
        _EvidenceArtifactDefinition(
            id="observability-packet-md",
            label="Observability Packet Markdown",
            path=Path("reports") / "observability-packet.md",
            kind="markdown",
            schema_version="entroping.observability-packet.md",
        ),
        _EvidenceArtifactDefinition(
            id="observability-packet-json",
            label="Observability Packet JSON",
            path=Path("reports") / "observability-packet.json",
            kind="json",
            schema_version=OBSERVABILITY_PACKET_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="otel-mapping-md",
            label="OpenTelemetry Mapping Markdown",
            path=Path("reports") / "otel-mapping.md",
            kind="markdown",
            schema_version="entroping.otel-mapping.md",
        ),
        _EvidenceArtifactDefinition(
            id="otel-mapping-json",
            label="OpenTelemetry Mapping JSON",
            path=Path("reports") / "otel-mapping.json",
            kind="json",
            schema_version=OTEL_MAPPING_SCHEMA_VERSION,
            summary_builder=_status_summary,
            reject_secret_like=True,
        ),
        _EvidenceArtifactDefinition(
            id="observability-adapter-readiness-md",
            label="Observability Adapter Readiness Markdown",
            path=Path("reports") / "observability-adapter-readiness.md",
            kind="markdown",
            schema_version="entroping.observability-adapter-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="observability-adapter-readiness-json",
            label="Observability Adapter Readiness JSON",
            path=Path("reports") / "observability-adapter-readiness.json",
            kind="json",
            schema_version=OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION,
            summary_builder=_status_summary,
            reject_secret_like=True,
        ),
        _EvidenceArtifactDefinition(
            id="api-inventory-md",
            label="API Inventory Markdown",
            path=Path("reports") / "api-inventory.md",
            kind="markdown",
            schema_version="entroping.api-inventory.md",
        ),
        _EvidenceArtifactDefinition(
            id="api-inventory-json",
            label="API Inventory JSON",
            path=Path("reports") / "api-inventory.json",
            kind="json",
            schema_version=API_INVENTORY_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="mutation-readiness-md",
            label="Mutation Readiness Markdown",
            path=Path("reports") / "mutation-readiness.md",
            kind="markdown",
            schema_version="entroping.mutation-readiness.md",
        ),
        _EvidenceArtifactDefinition(
            id="mutation-readiness-json",
            label="Mutation Readiness JSON",
            path=Path("reports") / "mutation-readiness.json",
            kind="json",
            schema_version=MUTATION_READINESS_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-index-md",
            label="Evidence Index Markdown",
            path=Path("reports") / "evidence-index.md",
            kind="markdown",
            schema_version="entroping.evidence-index.md",
        ),
        _EvidenceArtifactDefinition(
            id="evidence-index-json",
            label="Evidence Index JSON",
            path=Path("reports") / "evidence-index.json",
            kind="json",
            schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="agent-bundle-md",
            label="Agent Bundle Markdown",
            path=Path("reports") / "agent-bundle.md",
            kind="markdown",
            schema_version="entroping.agent-review-bundle.md",
        ),
        _EvidenceArtifactDefinition(
            id="agent-bundle-json",
            label="Agent Bundle JSON",
            path=Path("reports") / "agent-bundle.json",
            kind="json",
            schema_version=AGENT_REVIEW_BUNDLE_SCHEMA_VERSION,
            summary_builder=_agent_bundle_summary,
        ),
        _EvidenceArtifactDefinition(
            id="sarif",
            label="SARIF",
            path=Path("reports") / "entroping.sarif",
            kind="sarif",
            schema_version="SARIF 2.1.0",
        ),
        _EvidenceArtifactDefinition(
            id="review-summary-md",
            label="Review Summary",
            path=Path("reports") / "review-summary.md",
            kind="markdown",
            schema_version="entroping.review-summary.md",
        ),
    )


def _artifact_status(
    definition: _EvidenceArtifactDefinition,
    *,
    root: Path,
) -> LocalEvidenceArtifact:
    candidate = root / definition.path
    unsafe_summary = _unsafe_summary(candidate, root=root)
    if unsafe_summary is not None:
        return _status(definition, "unsafe", None, unsafe_summary)
    if not candidate.exists():
        return _status(definition, "missing", None, "missing")
    if not candidate.is_file():
        return _status(definition, "unsafe", None, "not a file")
    if definition.kind == "json":
        return _json_status(definition, candidate, root=root)
    if definition.kind == "sarif":
        return _sarif_status(definition, candidate, root=root)
    return _status(definition, "present", definition.schema_version, f"{definition.label} present")


def _unsafe_summary(path: Path, *, root: Path) -> str | None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return "path outside project"
    if symlink_path is not None:
        return "symlinked path component"
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return "path outside project"
    return None


def _json_status(
    definition: _EvidenceArtifactDefinition,
    path: Path,
    *,
    root: Path,
) -> LocalEvidenceArtifact:
    raw_text, load_error = _read_json_artifact_text(path, root=root)
    if raw_text is None:
        return _status(definition, _load_failure_state(load_error), None, load_error)
    if definition.reject_secret_like and contains_unredacted_evidence_secret(
        _SHA256_HEX_RE.sub("[SHA256]", raw_text)
    ):
        return _status(definition, "unsafe", None, "secret-like content")
    document, load_error = _parse_json_object(raw_text)
    if document is None:
        return _status(definition, "invalid", None, load_error)
    if document.get("schema_version") != definition.schema_version:
        return _status(definition, "invalid", None, "schema mismatch")
    summary = _metadata_summary(definition, document)
    return _status(definition, "present", definition.schema_version, summary)


def _sarif_status(
    definition: _EvidenceArtifactDefinition,
    path: Path,
    *,
    root: Path,
) -> LocalEvidenceArtifact:
    document, load_error = _load_json_object(path, root=root)
    if document is None:
        return _status(definition, _load_failure_state(load_error), None, load_error)
    if document.get("version") != "2.1.0":
        return _status(definition, "invalid", None, "schema mismatch")
    return _status(definition, "present", definition.schema_version, "SARIF 2.1.0")


def _load_json_object(path: Path, *, root: Path) -> tuple[dict[str, object] | None, str]:
    raw_text, load_error = _read_json_artifact_text(path, root=root)
    if raw_text is None:
        return None, load_error
    return _parse_json_object(raw_text)


def _load_failure_state(load_error: str) -> EvidenceArtifactState:
    if load_error in {"not a file", "path outside project", "symlinked path component"}:
        return "unsafe"
    return "invalid"


def _read_json_artifact_text(path: Path, *, root: Path) -> tuple[str | None, str]:
    raw_bytes, load_error = _read_json_artifact_bytes(path, root=root)
    if raw_bytes is None:
        return None, load_error
    try:
        return raw_bytes.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "invalid JSON"


def _read_json_artifact_bytes(path: Path, *, root: Path) -> tuple[bytes | None, str]:
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return None, "path outside project"
    if _supports_no_follow_tree_open():
        return _read_json_artifact_bytes_no_follow(root=root, relative_path=relative_path)
    return _read_json_artifact_bytes_best_effort(path)


def _supports_no_follow_tree_open() -> bool:
    return _HAS_O_DIRECTORY and _HAS_O_NOFOLLOW and _SUPPORTS_DIR_FD_OPEN


def _read_json_artifact_bytes_no_follow(
    *,
    root: Path,
    relative_path: Path,
) -> tuple[bytes | None, str]:
    if any(part in {"", ".", ".."} for part in relative_path.parts):
        return None, "path outside project"
    try:
        with ExitStack() as descriptor_stack:
            directory_descriptor = register_local_evidence_descriptor(
                descriptor_stack,
                os.open(root, os.O_RDONLY | os.O_DIRECTORY),
            )
            for component in relative_path.parts[:-1]:
                directory_descriptor = register_local_evidence_descriptor(
                    descriptor_stack,
                    os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_descriptor,
                    ),
                )
            file_descriptor = register_local_evidence_descriptor(
                descriptor_stack,
                os.open(
                    relative_path.name,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory_descriptor,
                ),
            )
            return _read_bounded_bytes_from_descriptor(file_descriptor)
    except OSError as exc:
        return None, _os_read_error_summary(exc)


def _read_json_artifact_bytes_best_effort(path: Path) -> tuple[bytes | None, str]:
    file_descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(path, flags)
        path_stat = path.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(path_stat.st_mode) or not stat.S_ISREG(descriptor_stat.st_mode):
            return None, "not a file"
        if (path_stat.st_dev, path_stat.st_ino) != (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ):
            return None, "unreadable"
        return _read_bounded_bytes_from_descriptor(file_descriptor)
    except OSError as exc:
        return None, _os_read_error_summary(exc)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _read_bounded_bytes_from_descriptor(file_descriptor: int) -> tuple[bytes | None, str]:
    descriptor_stat = os.fstat(file_descriptor)
    if not stat.S_ISREG(descriptor_stat.st_mode):
        return None, "not a file"
    if descriptor_stat.st_size > _MAX_JSON_ARTIFACT_BYTES:
        return None, "artifact too large"
    chunks: list[bytes] = []
    bytes_read = 0
    while bytes_read <= _MAX_JSON_ARTIFACT_BYTES:
        chunk = os.read(
            file_descriptor,
            min(65536, _MAX_JSON_ARTIFACT_BYTES + 1 - bytes_read),
        )
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)
    if bytes_read > _MAX_JSON_ARTIFACT_BYTES:
        return None, "artifact too large"
    return b"".join(chunks), ""


def _os_read_error_summary(exc: OSError) -> str:
    if exc.errno == errno.ELOOP:
        return "symlinked path component"
    return "unreadable"


def _parse_json_object(raw_text: str) -> tuple[dict[str, object] | None, str]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    return (document, "") if isinstance(document, dict) else (None, "invalid JSON")


def _metadata_summary(
    definition: _EvidenceArtifactDefinition,
    document: dict[str, object],
) -> str:
    if definition.summary_builder is None:
        return f"{definition.label} present"
    return definition.summary_builder(document)


def _run_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    total = _int_field(summary, "total")
    passed = _int_field(summary, "passed")
    failed = _int_field(summary, "failed")
    if total is None or passed is None or failed is None:
        return "run summary available"
    return f"{total} total, {passed} passed, {failed} failed"


def _drift_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    findings = _int_field(summary, "findings")
    drifted = _int_field(summary, "drifted")
    if findings is None or drifted is None:
        return "drift summary available"
    return f"{findings} findings, {drifted} drifted"


def _capture_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    total = _int_field(summary, "total_records")
    redacted = _int_field(summary, "redacted_records")
    unredacted = _int_field(summary, "unredacted_records")
    if total is None or redacted is None or unredacted is None:
        return "capture summary available"
    return f"{redacted}/{total} records redacted, {unredacted} unredacted"


def _artifact_manifest_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    present = _int_field(summary, "total_present")
    missing = _int_field(summary, "total_missing")
    audit = _object_field(document, "audit")
    verification = _object_field(audit, "verification")
    audit_status = _allowed_status(
        verification.get("status"),
        allowed=("verified", "broken"),
        fallback="unknown",
    )
    if present is None or missing is None:
        return f"audit {audit_status}"
    return f"{present} present, {missing} missing, audit {audit_status}"


def _status_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    return _allowed_status(
        summary.get("status"),
        allowed=("ready", "partial", "insufficient", "not_ready", "pass", "attention", "fail"),
        fallback="unknown",
    )


def _agent_bundle_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    status = _allowed_status(
        summary.get("status"),
        allowed=("pass", "attention", "fail"),
        fallback="unknown",
    )
    manifests = _int_field(summary, "manifests")
    findings = _int_field(summary, "findings")
    if manifests is None or findings is None:
        return status
    return f"{status}, {manifests} manifests, {findings} findings"


def _test_quality_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    status = _allowed_status(
        summary.get("status"),
        allowed=("pass", "warn", "fail", "missing"),
        fallback="unknown",
    )
    score = _int_field(summary, "score")
    generated_tests = _int_field(summary, "generated_tests")
    findings = _int_field(summary, "findings")
    if score is None or generated_tests is None or findings is None:
        return status
    return f"{status}, score {score}, {generated_tests} generated, {findings} findings"


def _external_test_evidence_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    status = _allowed_status(
        summary.get("status"),
        allowed=("ready", "partial", "insufficient"),
        fallback="unknown",
    )
    layers_with_evidence = _int_field(summary, "layers_with_evidence")
    layers_total = _int_field(summary, "layers_total")
    total_tests = _int_field(summary, "total_tests")
    total_failures = _int_field(summary, "total_failures")
    total_errors = _int_field(summary, "total_errors")
    total_skipped = _int_field(summary, "total_skipped")
    if (
        layers_with_evidence is None
        or layers_total is None
        or total_tests is None
        or total_failures is None
        or total_errors is None
        or total_skipped is None
    ):
        return status
    return (
        f"{status}, {layers_with_evidence}/{layers_total} layers, "
        f"{total_tests} tests, {total_failures} failures, "
        f"{total_errors} errors, {total_skipped} skipped"
    )


def _object_field(document: dict[str, object], field: str) -> dict[str, object]:
    value = document.get(field)
    return value if isinstance(value, dict) else {}


def _int_field(document: dict[str, object], field: str) -> int | None:
    value = document.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _allowed_status(
    value: object,
    *,
    allowed: tuple[str, ...],
    fallback: str,
) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def _status(
    definition: _EvidenceArtifactDefinition,
    state: EvidenceArtifactState,
    schema_version: str | None,
    summary: str,
) -> LocalEvidenceArtifact:
    return LocalEvidenceArtifact(
        id=definition.id,
        label=definition.label,
        path=definition.path.as_posix(),
        state=state,
        schema_version=schema_version,
        summary=summary,
    )
