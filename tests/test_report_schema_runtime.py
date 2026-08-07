"""Versioned report schema contract tests."""

import json
from pathlib import Path
from typing import cast

from entroping.bridge.capture_summary import (
    CAPTURE_SUMMARY_SCHEMA_VERSION,
    capture_summary_report_to_dict,
    compile_capture_summary,
)
from entroping.core.agent_manifest import AGENT_RUN_MANIFEST_SCHEMA_VERSION
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    drift_baseline_to_dict,
    drift_report_to_dict,
)
from entroping.core.evidence.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence.evidence_bundle import (
    EVIDENCE_BUNDLE_SCHEMA_VERSION,
    EvidenceBundleArtifact,
    EvidenceBundleDiagnostic,
    EvidenceBundleManifestAudit,
    EvidenceBundleMissingArtifact,
    EvidenceBundleReport,
    EvidenceBundleSummary,
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
from entroping.core.traffic_artifact_manifest import TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION
from entroping.models.drift import (
    DriftBaseline,
    DriftBaselineTest,
    DriftFinding,
    DriftReport,
    DriftReportSummary,
)
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
    gate_properties = schema["properties"]["tests"]["items"]["properties"]["gate_results"][
        "items"
    ]["properties"]
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
    assert gate_properties["enforcement"] == {"enum": ["block", "warn", "audit_only"]}
    assert gate_properties["result"] == {
        "enum": ["passed", "failed", "timeout", "error", "blocked"]
    }


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
