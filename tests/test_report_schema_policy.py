"""Versioned report schema contract tests."""

import json
from pathlib import Path
from typing import cast

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
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "docs" / "technical" / "report-schemas"


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
            "happy_path_covered_operations": 1,
            "auth_negative_covered_operations": 0,
            "validation_negative_covered_operations": 0,
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
                "auth_negative_tests": [],
                "validation_negative_tests": [],
            },
            {
                "operation_id": "createCheckout",
                "method": "POST",
                "path": "/checkout",
                "status": "uncovered",
                "tests": [],
                "negative_tests": [],
                "auth_negative_tests": [],
                "validation_negative_tests": [],
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
        "entroping.otlp-preview.v1": SCHEMA_DIR / "otlp-preview.v1.schema.json",
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
        "entroping.qa-brain-repair-plan.v1": (SCHEMA_DIR / "qa-brain-repair-plan.v1.schema.json"),
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
