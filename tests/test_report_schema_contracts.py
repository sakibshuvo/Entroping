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
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    drift_baseline_to_dict,
    drift_report_to_dict,
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
from entroping.core.pilot_metrics import (
    PILOT_METRICS_SCHEMA_VERSION,
    PilotEvidenceSource,
    PilotMetric,
    PilotMetricsReport,
    PilotMetricsSummary,
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
)
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    StructuredDiagnosticAttribute,
    StructuredDiagnosticEvent,
)
from entroping.core.traffic_artifact_manifest import TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION
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
    assert schema["$defs"]["source"]["properties"]["sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )
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
    assert schema["$defs"]["artifact"]["properties"]["sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )
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
    assert schema["properties"]["schema_version"]["const"] == RUNTIME_CARD_SCHEMA_VERSION
    assert schema["properties"]["pilot_readiness"]["$ref"] == "#/$defs/pilot_readiness"
    assert "pilot_readiness" not in schema["required"]
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
    schema = json.loads(
        (SCHEMA_DIR / "design-partner-feedback.v1.schema.json").read_text()
    )
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
    assert schema["properties"]["evidence"]["properties"]["pilot_metrics_status"][
        "enum"
    ] == [
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
