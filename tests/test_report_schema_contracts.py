"""Versioned report schema contract tests."""

import json
from pathlib import Path
from typing import cast

from entroping.bridge.capture_summary import (
    CAPTURE_SUMMARY_SCHEMA_VERSION,
    capture_summary_report_to_dict,
    compile_capture_summary,
)
from entroping.bridge.effective_policy import EffectivePolicyGateReport, EffectivePolicyReport
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
from entroping.core.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.agent_manifest import AGENT_RUN_MANIFEST_SCHEMA_VERSION
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    drift_baseline_to_dict,
    drift_report_to_dict,
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
    report = EffectivePolicyReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        imports=("rules/security.yaml",),
        gates=(
            EffectivePolicyGateReport(
                id="request_id_header",
                source_path="rules/security.yaml",
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
        "gates": [
            {
                "id": "request_id_header",
                "source_path": "rules/security.yaml",
                "condition": "true",
                "gate": 'header "X-Request-Id" exists',
                "enforcement": "block",
                "final": True,
                "group": None,
                "description": "Require request IDs",
            }
        ],
    }


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
        "entroping.report-artifact-manifest.v1": (
            SCHEMA_DIR / "report-artifact-manifest.v1.schema.json"
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
