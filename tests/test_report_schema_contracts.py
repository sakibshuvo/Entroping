"""Versioned report schema contract tests."""

import json
from pathlib import Path

from entroping.bridge.effective_policy import EffectivePolicyGateReport, EffectivePolicyReport
from entroping.bridge.openapi_audit import (
    OPENAPI_AUDIT_SCHEMA_VERSION,
    audit_openapi_coverage,
    audit_report_to_dict,
)
from entroping.bridge.story_traceability import (
    compile_story_traceability,
    story_traceability_report_to_dict,
)
from entroping.core.agent_manifest import AGENT_RUN_MANIFEST_SCHEMA_VERSION
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    drift_baseline_to_dict,
    drift_report_to_dict,
)
from entroping.core.report_writer import run_report_to_dict
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
                rule_ids=("global_latency",),
                stdout="HTTP 200\n\n{\"ok\":true}\n",
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
                "rule_ids": ["global_latency"],
                "stdout": "HTTP 200\n\n{\"ok\":true}\n",
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


def test_agent_run_manifest_v1_schema_declares_versioned_value_free_fields() -> None:
    schema = json.loads((SCHEMA_DIR / "agent-run-manifest.v1.schema.json").read_text())

    assert schema["properties"]["schema_version"]["const"] == AGENT_RUN_MANIFEST_SCHEMA_VERSION
    assert "intent_sha256" in schema["properties"]["prompt"]["properties"]
    assert "package_sha256" in schema["properties"]["prompt"]["properties"]
    assert "raw_prompt" not in json.dumps(schema)
    assert "api_key" not in json.dumps(schema)


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
                "description": "Require request IDs",
            }
        ],
    }


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
                exchanges=(
                    HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),
                ),
            ),
            HurlTest(
                path=Path("tests/generated/stale_checkout.hurl"),
                metadata=HurlMetadata(
                    meta={"source": "openapi", "operation_id": "staleCheckout"}
                ),
                exchanges=(
                    HurlExchange(method="GET", url="{{base_url}}/stale", path="/stale"),
                ),
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
            },
            {
                "operation_id": "createCheckout",
                "method": "POST",
                "path": "/checkout",
                "status": "uncovered",
                "tests": [],
            },
        ],
        "findings": [
            {
                "code": "OPENAPI_COVERAGE_MISSING",
                "severity": "error",
                "operation_id": "createCheckout",
                "method": "POST",
                "path": "/checkout",
                "message": (
                    "OpenAPI operation 'createCheckout' has no committed Hurl coverage."
                ),
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
        "entroping.drift-report.v1": SCHEMA_DIR / "drift-report.v1.schema.json",
        "entroping.traceability-report.v1": (
            SCHEMA_DIR / "traceability-report.v1.schema.json"
        ),
        "entroping.effective-policy-report.v1": (
            SCHEMA_DIR / "effective-policy-report.v1.schema.json"
        ),
    }
    schema_doc = (REPO_ROOT / "docs" / "technical" / "REPORT_SCHEMAS.md").read_text(
        encoding="utf-8"
    )

    for schema_version, path in versions.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"]["const"] == schema_version
        assert schema_version in schema_doc
