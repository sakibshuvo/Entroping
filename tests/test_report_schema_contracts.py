"""Versioned report schema contract tests."""

import json
from pathlib import Path

from entroping.bridge.effective_policy import EffectivePolicyGateReport, EffectivePolicyReport
from entroping.bridge.story_traceability import (
    compile_story_traceability,
    story_traceability_report_to_dict,
)
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
from entroping.models.hurl import HurlMetadata, HurlTest
from entroping.models.report import (
    KnownFailureEvidence,
    RunReport,
    RunReportSummary,
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
                "response": {
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body_shape": ["$:object", "$.ok:boolean"],
                },
            }
        ],
    }


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
