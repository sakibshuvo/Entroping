"""Safety-boundary tests for deterministic run reports."""

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import pytest
from report_writer_test_helpers import _execution_copy, _suite_result

import entroping.core.report_rendering as report_rendering
import entroping.core.report_serialization as report_serialization
import entroping.core.report_writer as report_writer
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult
from entroping.core.safe_write import SafeWriteError
from entroping.models.report import (
    RunReport,
    RunReportSummary,
    RunSafetyEvidence,
    RunTestReport,
)


def test_write_json_report_includes_ci_debug_fields_and_redacts_output(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "token=live-secret\nassert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.json"

    report_writer.write_json_report(report, output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["project"] == "checkout-api"
    assert data["environment"] == "local"
    assert data["summary"] == {"total": 1, "passed": 0, "failed": 1, "exit_code": 1}
    assert data["tests"][0]["path"] == "tests/health.hurl"
    assert data["tests"][0]["status"] == "failed"
    assert data["tests"][0]["rule_ids"] == ["global_latency"]
    assert data["tests"][0]["duration_ms"] == 123
    assert data["tests"][0]["timeout_ms"] == 2500
    assert "live-secret" not in output.read_text(encoding="utf-8")
    assert "Authorization: [REDACTED]" in data["tests"][0]["stdout"]
    assert "token=[REDACTED]" in data["tests"][0]["stderr"]

    junit_path = tmp_path / "reports" / "junit.xml"
    report_writer.write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.timeout_ms"] == "2500"

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<th>Timeout</th>" in html
    assert "<td>2500 ms</td>" in html


def test_reports_include_auth_chain_evidence_without_secret_values(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "auth_chain.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "auth_chain.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[
            _execution_copy(
                source,
                execution,
                auth_flow="oauth2-client-credentials",
                auth_requires=("access_token", "csrf_token"),
                auth_produces=("session_cookie",),
            )
        ],
        suite=_suite_result(
            execution,
            "Authorization: Bearer live-auth-secret\ncsrf_token=live-csrf-secret\n",
        ),
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["auth"] == {
        "flow": "oauth2-client-credentials",
        "requires": ["access_token", "csrf_token"],
        "produces": ["session_cookie"],
    }
    serialized = json.dumps(payload)
    assert "live-auth-secret" not in serialized
    assert "live-csrf-secret" not in serialized

    output = tmp_path / "reports" / "run-latest.json"
    report_writer.write_json_report(report, output)
    loaded = report_writer.load_run_report(output)
    assert loaded.tests[0].auth is not None
    assert loaded.tests[0].auth.flow == "oauth2-client-credentials"
    assert loaded.tests[0].auth.requires == ("access_token", "csrf_token")
    assert loaded.tests[0].auth.produces == ("session_cookie",)

    junit_path = tmp_path / "reports" / "junit.xml"
    report_writer.write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.auth.flow"] == "oauth2-client-credentials"
    assert values["entroping.auth.requires"] == "access_token,csrf_token"
    assert values["entroping.auth.produces"] == "session_cookie"

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "auth_flow=oauth2-client-credentials" in html
    assert "auth_requires=access_token,csrf_token" in html
    assert "auth_produces=session_cookie" in html
    assert "live-auth-secret" not in html
    assert "live-csrf-secret" not in html


def test_junit_failure_text_replaces_xml_illegal_control_characters(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "control-output.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "control-output.hurl"
    suite = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="failed",
                exit_code=1,
                stdout="HTTP 500\x01\n",
                stderr="assert\x0b failed\n",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=50,
            ),
        ),
    )
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"

    report_writer.write_junit_report(report, output)

    xml_text = output.read_text(encoding="utf-8")
    assert "\x01" not in xml_text
    assert "\x0b" not in xml_text
    failure = ElementTree.parse(output).getroot().find("testcase/failure")
    assert failure is not None
    assert "HTTP 500\ufffd" in (failure.text or "")
    assert "assert\ufffd failed" in (failure.text or "")


def test_junit_report_replaces_xml_illegal_control_characters_in_attributes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "metadata-control.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "metadata-control.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[
            _execution_copy(
                source,
                execution,
                operation_id="checkout\x01Create",
            )
        ],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"

    report_writer.write_junit_report(report, output)

    xml_text = output.read_text(encoding="utf-8")
    assert "\x01" not in xml_text
    properties = ElementTree.parse(output).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.operation_id"] == "checkout\ufffdCreate"


def _base_load_run_report_payload() -> dict[str, object]:
    return {
        "schema_version": "entroping.run-report.v1",
        "project": "private-report-project",
        "environment": "local",
        "generated_at": "2026-06-12T00:00:00+00:00",
        "summary": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "exit_code": 0,
        },
        "tests": [
            {
                "path": "tests/private-test.hurl",
                "execution_path": ".entroping/run/private-test.hurl",
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 5,
                "rule_ids": [],
                "stdout": "",
                "stderr": "",
                "retry": {
                    "retry_count": 1,
                    "unstable": False,
                    "attempts": [
                        {
                            "attempt": 1,
                            "status": "passed",
                            "exit_code": 0,
                            "duration_ms": 5,
                            "stdout_truncated": False,
                            "stderr_truncated": False,
                        }
                    ],
                },
            }
        ],
    }


def _payload_first_test(payload: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], payload["tests"])[0]


def _payload_summary(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["summary"])


def test_load_run_report_rejects_unknown_root_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    payload["private_root"] = "private-root-value"
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field root contains unknown fields" in str(exc_info.value)
    assert "private-root-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_summary_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    summary = _payload_summary(payload)
    summary["private_summary"] = "private-summary-value"
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field summary contains unknown fields" in str(exc_info.value)
    assert "private-summary-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_test_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["private_test"] = "private-test-value"
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0] contains unknown fields" in str(exc_info.value)
    assert "private-test-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_retry_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    retry = cast(dict[str, object], first_test["retry"])
    retry["private_retry"] = "private-retry-value"
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].retry contains unknown fields" in str(exc_info.value)
    assert "private-retry-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_retry_attempt_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    retry = cast(dict[str, object], first_test["retry"])
    attempts = cast(list[dict[str, object]], retry["attempts"])
    attempts[0]["private_attempt"] = "private-attempt-value"
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].retry.attempts[0] contains unknown fields" in str(exc_info.value)
    assert "private-attempt-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_auth_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["auth"] = {
        "flow": None,
        "requires": [],
        "produces": [],
        "private_auth": "private-auth-value",
    }
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].auth contains unknown fields" in str(exc_info.value)
    assert "private-auth-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_safety_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["safety"] = {
        "protected_environment": True,
        "safety": None,
        "safety_source": None,
        "methods": [],
        "blocked_reason": None,
        "private_safety": "private-safety-value",
    }
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].safety contains unknown fields" in str(exc_info.value)
    assert "private-safety-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_response_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["response"] = {
        "status_code": 200,
        "headers": {},
        "body_shape": ["$:object"],
        "private_response": "private-response-value",
    }
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].response contains unknown fields" in str(exc_info.value)
    assert "private-response-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_known_failure_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["known_failures"] = [
        {
            "test": "tests/private-test.hurl",
            "rule_id": "private-rule-id",
            "issue_id": "private-issue-id",
            "expires": "2026-06-30",
            "reason": "Known failure",
            "private_failure": "private-failure-value",
        }
    ]
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].known_failures[0] contains unknown fields" in str(exc_info.value)
    assert "private-failure-value" not in str(exc_info.value)


def test_load_run_report_rejects_unknown_gate_result_fields(tmp_path: Path) -> None:
    payload = _base_load_run_report_payload()
    first_test = _payload_first_test(payload)
    first_test["gate_results"] = [
        {
            "rule_id": "global_latency",
            "enforcement": "warn",
            "result": "passed",
            "exit_code": 0,
            "private_gate_result": "private-gate-result-value",
        }
    ]
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].gate_results[0] contains unknown fields" in str(exc_info.value)
    assert "private-gate-result-value" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "forbidden_error_fragment"),
    [
        (
            {
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 0, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            None,
        ),
        (
            {
                "schema_version": "entroping.run-report.v999",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 0, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            "entroping.run-report.v999",
        ),
    ],
)
def test_load_run_report_rejects_unversioned_or_unsupported_schema(
    tmp_path: Path,
    payload: dict[str, object],
    forbidden_error_fragment: str | None,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="must use schema_version entroping\\.run-report\\.v1",
    ) as exc_info:
        report_writer.load_run_report(latest)
    if forbidden_error_fragment is not None:
        assert forbidden_error_fragment not in str(exc_info.value)


def test_load_run_report_rejects_non_object_payload(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        report_writer.load_run_report(latest)


def test_load_run_report_rejects_oversize_report_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(" " * 9, encoding="utf-8")
    monkeypatch.setattr(report_serialization, "_MAX_RUN_REPORT_BYTES", 8, raising=False)

    with pytest.raises(ValueError, match="exceeds 8 bytes"):
        report_writer.load_run_report(latest)


def test_load_run_report_rejects_non_string_schema_version(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 0, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="field schema_version must be a string") as exc_info:
        report_writer.load_run_report(latest)
    assert "private-runtime-value" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "tests": [],
            },
            "required field summary",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            "required field summary.total",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": "private-summary-value",
                "tests": [],
            },
            "field summary must be a JSON object",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 0, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": {"private": "test-value"},
            },
            "field tests must be a JSON array",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": ["private-test-value"],
            },
            "field tests[0] must be a JSON object",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [{"path": "private-test-value"}],
            },
            "required field tests[0].execution_path",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": 123,
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 0, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            "field project must be a string",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {
                    "total": "private-total-value",
                    "passed": 0,
                    "failed": 0,
                    "exit_code": 0,
                },
                "tests": [],
            },
            "field summary.total must be an integer",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/private-test.hurl",
                        "execution_path": ".entroping/run/private-test.hurl",
                        "status": "failed",
                        "exit_code": "private-exit-value",
                        "duration_ms": 1,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            },
            "field tests[0].exit_code must be an integer",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/private-test.hurl",
                        "execution_path": ".entroping/run/private-test.hurl",
                        "status": 500,
                        "exit_code": 1,
                        "duration_ms": 1,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            },
            "field tests[0].status must be a string",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/private-test.hurl",
                        "execution_path": ".entroping/run/private-test.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 1,
                        "rule_ids": None,
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            },
            "field tests[0].rule_ids must be a JSON array",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/private-test.hurl",
                        "execution_path": ".entroping/run/private-test.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 1,
                        "rule_ids": ["private-rule-value", 7],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            },
            "field tests[0].rule_ids[1] must be a string",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/private-test.hurl",
                        "execution_path": ".entroping/run/private-test.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 1,
                        "rule_ids": ["private-rule-value", ""],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            },
            "field tests[0].rule_ids[1] must be a non-empty string without control characters",
        ),
    ],
)
def test_load_run_report_rejects_versioned_payload_with_invalid_required_fields(
    tmp_path: Path,
    payload: dict[str, object],
    expected_error: str,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert expected_error in str(exc_info.value)
    assert "private-runtime-value" not in str(exc_info.value)
    assert "private-summary-value" not in str(exc_info.value)
    assert "test-value" not in str(exc_info.value)
    assert "private-test-value" not in str(exc_info.value)
    assert "private-total-value" not in str(exc_info.value)
    assert "private-exit-value" not in str(exc_info.value)
    assert "private-rule-value" not in str(exc_info.value)


def test_load_run_report_round_trips_safety_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()

    def row(path: str, safety: object) -> dict[str, object]:
        return {
            "path": path,
            "execution_path": f".entroping/run/{Path(path).name}",
            "status": "blocked",
            "exit_code": 1,
            "duration_ms": 0,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "safety": safety,
        }

    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "prod",
                "generated_at": "2026-06-12T00:00:00+00:00",
                "summary": {"total": 9, "passed": 0, "failed": 9, "exit_code": 1},
                "tests": [
                    row(
                        "tests/valid.hurl",
                        {
                            "protected_environment": True,
                            "safety": " idempotent ",
                            "safety_source": " test metadata ",
                            "methods": [" POST ", ""],
                            "blocked_reason": " not blocked ",
                        },
                    ),
                    row("tests/not-mapping.hurl", "not-a-mapping"),
                    row("tests/no-bool.hurl", {"protected_environment": "true", "methods": []}),
                    row(
                        "tests/bad-safety.hurl",
                        {
                            "protected_environment": True,
                            "safety": 123,
                            "methods": [],
                        },
                    ),
                    row(
                        "tests/bad-source.hurl",
                        {
                            "protected_environment": True,
                            "safety_source": 123,
                            "methods": [],
                        },
                    ),
                    row(
                        "tests/bad-reason.hurl",
                        {
                            "protected_environment": True,
                            "blocked_reason": 123,
                            "methods": [],
                        },
                    ),
                    row(
                        "tests/bad-method-list.hurl",
                        {
                            "protected_environment": True,
                            "methods": "POST",
                        },
                    ),
                    row(
                        "tests/bad-method-entry.hurl",
                        {
                            "protected_environment": True,
                            "methods": [123],
                        },
                    ),
                    row(
                        "tests/control.hurl",
                        {
                            "protected_environment": True,
                            "methods": ["PO\x1fST"],
                        },
                    ),
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert report.tests[0].safety == RunSafetyEvidence(
        protected_environment=True,
        safety="idempotent",
        safety_source="test metadata",
        methods=("POST",),
        blocked_reason="not blocked",
    )
    assert all(test.safety is None for test in report.tests[1:])


def test_write_json_report_includes_sanitized_response_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    suite = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="passed",
                exit_code=0,
                stdout=(
                    "HTTP/1.1 201 Created\n"
                    "Content-Type: application/json; charset=utf-8\n"
                    "Date: Sun, 31 May 2026 00:00:00 GMT\n"
                    "X-Request-Id: req_volatile\n"
                    "\n"
                    '{"id":"ord_123","approved":true,"items":[{"sku":"abc","qty":2}]}\n'
                ),
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=42,
            ),
        ),
    )
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.json"

    report_writer.write_json_report(report, output)

    response = json.loads(output.read_text(encoding="utf-8"))["tests"][0]["response"]
    assert response == {
        "status_code": 201,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body_shape": [
            "$:object",
            "$.approved:boolean",
            "$.id:string",
            "$.items:array",
            "$.items[]:object",
            "$.items[].qty:number",
            "$.items[].sku:string",
        ],
    }
    assert "req_volatile" not in json.dumps(response)


def test_build_run_report_omits_response_when_stdout_is_not_structured(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )

    assert report.tests[0].response is None
    assert "response" not in report_writer._test_report_to_dict(report.tests[0])


def test_write_json_report_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.json"
    output.parent.mkdir()
    output.write_text("old\n", encoding="utf-8")

    def fail_safe_write(path: Path, content: str, *, artifact: str) -> Path:
        _ = path, content, artifact
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(report_writer, "safe_write_text", fail_safe_write)

    with pytest.raises(report_writer.ReportWriterError, match="temporary write failed"):
        report_writer.write_json_report(report, output)

    assert output.read_text(encoding="utf-8") == "old\n"


def test_junit_elementtree_nosec_documents_construction_only() -> None:
    source = Path(report_rendering.__file__).read_text(encoding="utf-8")
    lines = source.splitlines()
    import_index, import_line = next(
        (index, line)
        for index, line in enumerate(lines)
        if "from xml.etree import ElementTree" in line
    )
    rationale_line = lines[import_index - 1]

    assert import_line == "from xml.etree import ElementTree  # nosec B405"
    assert "constructs JUnit XML" in rationale_line
    assert "no external XML parsing" in rationale_line
    parsed = ast.parse(source)
    forbidden_parser_calls = {"XML", "XMLParser", "fromstring", "iterparse", "parse"}
    element_tree_names = {"ElementTree"}
    direct_parser_names: set[str] = set()
    for node in ast.walk(parsed):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "xml.etree":
            element_tree_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "ElementTree"
            )
        if node.module == "xml.etree.ElementTree":
            direct_parser_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in forbidden_parser_calls
            )

    def dotted_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent is not None else None
        return None

    used_parser_calls: set[str] = set()
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call):
            continue
        call_name = dotted_name(node.func)
        if call_name in direct_parser_names:
            used_parser_calls.add(call_name)
            continue
        owner, _, function_name = (call_name or "").rpartition(".")
        if owner in element_tree_names and function_name in forbidden_parser_calls:
            used_parser_calls.add(call_name or function_name)
    assert used_parser_calls == set()


def test_write_junit_report_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"
    output.parent.mkdir()
    output.write_text("<old />\n", encoding="utf-8")

    def fail_safe_write(path: Path, content: bytes, *, artifact: str) -> Path:
        _ = path, content, artifact
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(report_writer, "safe_write_bytes", fail_safe_write)

    with pytest.raises(report_writer.ReportWriterError, match="temporary write failed"):
        report_writer.write_junit_report(report, output)

    assert output.read_text(encoding="utf-8") == "<old />\n"


def test_write_html_report_escapes_failure_output(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, '<script>alert("x")</script>\n'),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.html"

    report_writer.write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<title>Entroping checkout-api</title>" in html
    assert "Environment" in html
    assert "local" in html
    assert "tests/health.hurl" in html
    assert "global_latency" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "live-secret" not in html


def test_write_html_report_escapes_summary_text_defensively(tmp_path: Path) -> None:
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-01T00:00:00+00:00",
        summary=RunReportSummary(
            passed=cast(int, "0 <em>passed</em>"),
            failed=cast(int, "1 & failed"),
            total=cast(int, "1 <script>alert('x')</script>"),
            exit_code=1,
        ),
        tests=(),
    )
    output = tmp_path / "reports" / "run-latest.html"

    report_writer.write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "<em>passed</em>" not in html
    assert "0 &lt;em&gt;passed&lt;/em&gt; passed" in html
    assert "1 &amp; failed failed" in html
    assert "1 &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; total" in html


@pytest.mark.parametrize(
    ("captured_output", "expected_fence"),
    [
        ("before\n```text\ninjected\n```\nafter\n", "````"),
        ("before\n````\ninjected\n````\nafter\n", "`````"),
    ],
)
def test_render_bug_report_uses_fence_longer_than_captured_output(
    tmp_path: Path,
    captured_output: str,
    expected_fence: str,
) -> None:
    source = tmp_path / "tests" / "fence.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "fence.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, captured_output),
        project_root=tmp_path,
    )

    bug = report_writer.render_bug_report(report)

    output_section = bug.split("## Output\n\n", maxsplit=1)[1]
    assert output_section.startswith(f"{expected_fence}text\n")
    assert output_section.endswith(f"\n{expected_fence}\n")
    assert captured_output.strip() in output_section


def test_render_bug_report_quotes_structural_markdown_fields() -> None:
    report = RunReport(
        project=" checkout-api\n## forged project [link](https://evil.test) ",
        environment="local\r\t\x00\n## forged environment <script>alert(1)</script>",
        generated_at="2026-06-01T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/checkout`danger`.hurl\n## forged test",
                execution_path=".entroping/run-1/checkout.hurl",
                status="failed\n## forged status",
                exit_code=1,
                duration_ms=50,
                rule_ids=("[global_latency](https://evil.test)\n## forged rule",),
                stdout="",
                stderr="assert failed\n",
            ),
        ),
    )

    bug = report_writer.render_bug_report(report)

    summary_section = bug.split("## Output\n\n", maxsplit=1)[0]
    assert (
        "- Project: `  checkout-api\\n## forged project [link](https://evil.test)  `"
        in summary_section
    )
    assert (
        "- Environment: `local\\r\\t\\u0000\\n## forged environment <script>alert(1)</script>`"
        in summary_section
    )
    assert "- Test: ``tests/checkout`danger`.hurl\\n## forged test``" in summary_section
    assert "- Status: `failed\\n## forged status`" in summary_section
    assert "- Rule IDs: `[global_latency](https://evil.test)\\n## forged rule`" in summary_section
    assert "\n## forged project" not in summary_section
    assert "\n## forged environment" not in summary_section
    assert "\n## forged test" not in summary_section
    assert "\n## forged status" not in summary_section
    assert "\n## forged rule" not in summary_section


def test_render_bug_report_replaces_nonprintable_output_controls() -> None:
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-01T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/control.hurl",
                execution_path=".entroping/run-1/control.hurl",
                status="failed",
                exit_code=1,
                duration_ms=50,
                rule_ids=("global_latency",),
                stdout="before\x00after",
                stderr="red\x1b[31m\n",
            ),
        ),
    )

    bug = report_writer.render_bug_report(report)

    output_section = bug.split("## Output\n\n", maxsplit=1)[1]
    assert "\x00" not in output_section
    assert "\x1b" not in output_section
    assert "before<U+0000>after" in output_section
    assert "red<U+001B>[31m" in output_section


def test_write_bug_report_rejects_symlinked_output_path(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "bug.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.md"
    output.symlink_to(outside)

    try:
        report_writer.write_bug_report(report, output)
    except report_writer.ReportWriterError as exc:
        assert "symlinked bug report" in str(exc)
    else:
        raise AssertionError("expected symlinked report path to be rejected")
    assert not outside.exists()


def test_write_report_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (tmp_path / "reports").symlink_to(outside_dir, target_is_directory=True)

    try:
        report_writer.write_json_report(report, tmp_path / "reports" / "run-latest.json")
    except report_writer.ReportWriterError as exc:
        assert "symlinked path component" in str(exc)
    else:
        raise AssertionError("expected symlinked report parent to be rejected")
    assert not (outside_dir / "run-latest.json").exists()
