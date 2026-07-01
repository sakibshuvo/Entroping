"""Unit and adapter tests for deterministic run report writers."""

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import pytest

import entroping.core.report_rendering as report_rendering
import entroping.core.report_serialization as report_serialization
import entroping.core.report_writer as report_writer
from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import AppliedKnownFailure, HurlExecutionCopy
from entroping.core.hurl_runner import HurlAttemptEvidence, HurlFileResult, HurlSuiteResult
from entroping.core.report_writer import (
    ReportWriterError,
    build_run_report,
    load_run_report,
    render_bug_report,
    write_bug_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.safe_write import SafeWriteError
from entroping.models.report import (
    RunReport,
    RunReportSummary,
    RunSafetyEvidence,
    RunTestReport,
)


def _execution_copy(
    source: Path,
    execution: Path,
    known_failures: tuple[AppliedKnownFailure, ...] = (),
    operation_id: str | None = None,
    source_kind: str | None = None,
    negative_category: str | None = None,
    severity: str | None = None,
    auth_flow: str | None = None,
    auth_requires: tuple[str, ...] = (),
    auth_produces: tuple[str, ...] = (),
) -> HurlExecutionCopy:
    return HurlExecutionCopy(
        source_path=source,
        execution_path=execution,
        injected_gates=(
            HurlGateAssertion(
                rule_id="global_latency",
                assertion="duration < 2000",
                enforcement="block",
                condition="true",
            ),
        ),
        known_failures=known_failures,
        operation_id=operation_id,
        source=source_kind,
        negative_category=negative_category,
        severity=severity,
        auth_flow=auth_flow,
        auth_requires=auth_requires,
        auth_produces=auth_produces,
    )


def _suite_result(execution: Path, stderr: str) -> HurlSuiteResult:
    return HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="failed",
                exit_code=1,
                stdout="Authorization: Bearer live-secret\n",
                stderr=stderr,
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=123,
                timeout_ms=2500,
            ),
        ),
    )


def test_write_json_report_includes_ci_debug_fields_and_redacts_output(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "token=live-secret\nassert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.json"

    write_json_report(report, output)

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
    write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.timeout_ms"] == "2500"

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<th>Timeout</th>" in html
    assert "<td>2500 ms</td>" in html


def test_reports_include_operation_id_evidence(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution, operation_id="createCheckout")],
        suite=_suite_result(execution, ""),
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["operation_id"] == "createCheckout"

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.operation_id"] == "createCheckout"

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<th>Operation</th>" in html
    assert "createCheckout" in html


def test_reports_include_generated_negative_path_metadata(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "generated" / "negative" / "checkout_boundary.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout_boundary.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[
            _execution_copy(
                source,
                execution,
                operation_id="createCheckout",
                source_kind="openapi",
                negative_category="boundary-values",
                severity="medium",
            )
        ],
        suite=_suite_result(execution, ""),
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["source"] == "openapi"
    assert first_test["negative_category"] == "boundary-values"
    assert first_test["severity"] == "medium"

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.source"] == "openapi"
    assert values["entroping.negative_category"] == "boundary-values"
    assert values["entroping.severity"] == "medium"

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "boundary-values" in html
    assert "medium" in html


def test_reports_include_auth_chain_evidence_without_secret_values(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "auth_chain.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "auth_chain.hurl"
    report = build_run_report(
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
    write_json_report(report, output)
    loaded = load_run_report(output)
    assert loaded.tests[0].auth is not None
    assert loaded.tests[0].auth.flow == "oauth2-client-credentials"
    assert loaded.tests[0].auth.requires == ("access_token", "csrf_token")
    assert loaded.tests[0].auth.produces == ("session_cookie",)

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
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
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "auth_flow=oauth2-client-credentials" in html
    assert "auth_requires=access_token,csrf_token" in html
    assert "auth_produces=session_cookie" in html
    assert "live-auth-secret" not in html
    assert "live-csrf-secret" not in html


def test_reports_include_applied_known_failure_evidence(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    known_failure = AppliedKnownFailure(
        test="tests/health.hurl",
        rule_id="global_latency",
        issue_id="GH-123",
        expires="2026-06-30",
        reason="Temporary upstream latency regression.",
    )
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution, (known_failure,))],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["known_failures"] == [
        {
            "test": "tests/health.hurl",
            "rule_id": "global_latency",
            "issue_id": "GH-123",
            "expires": "2026-06-30",
            "reason": "Temporary upstream latency regression.",
        }
    ]

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    testcase = ElementTree.parse(junit_path).getroot().find("testcase")
    assert testcase is not None
    properties = testcase.find("properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.known_failure.global_latency"] == (
        "GH-123 expires 2026-06-30: Temporary upstream latency regression."
    )

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "Known failures" in html
    assert "GH-123" in html
    assert "Temporary upstream latency regression." in html


def test_reports_surface_timeout_failures_distinctly(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "slow.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "slow.hurl"
    suite = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="timeout",
                exit_code=124,
                stdout="",
                stderr="Hurl subprocess timed out after 250 ms",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=251,
                timeout_ms=250,
            ),
        ),
    )
    report = build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["status"] == "timeout"
    assert first_test["exit_code"] == 124
    assert first_test["timeout_ms"] == 250

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    failure = ElementTree.parse(junit_path).getroot().find("testcase/failure")
    assert failure is not None
    assert failure.attrib["message"] == "timeout"
    assert failure.attrib["type"] == "entroping.hurl.timeout"
    assert "timeout_ms: 250" in (failure.text or "")

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert 'class="timeout"' in html
    assert "Hurl subprocess timed out after 250 ms" in html


def test_reports_include_retry_and_flake_evidence_without_raw_attempt_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "eventual.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "eventual.hurl"
    suite = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="passed",
                exit_code=0,
                stdout="HTTP 200\n",
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=50,
                attempts=(
                    HurlAttemptEvidence(
                        attempt=1,
                        status="failed",
                        exit_code=42,
                        duration_ms=20,
                        stdout_truncated=True,
                        stderr_truncated=False,
                    ),
                    HurlAttemptEvidence(
                        attempt=2,
                        status="passed",
                        exit_code=0,
                        duration_ms=30,
                        stdout_truncated=False,
                        stderr_truncated=False,
                    ),
                ),
            ),
        ),
    )
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    tests_payload = payload["tests"]
    assert isinstance(tests_payload, list)
    first_test = tests_payload[0]
    assert isinstance(first_test, Mapping)
    assert first_test["retry"] == {
        "retry_count": 1,
        "unstable": True,
        "attempts": [
            {
                "attempt": 1,
                "status": "failed",
                "exit_code": 42,
                "duration_ms": 20,
                "stdout_truncated": True,
                "stderr_truncated": False,
            },
            {
                "attempt": 2,
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 30,
                "stdout_truncated": False,
                "stderr_truncated": False,
            },
        ],
    }
    assert "raw attempt" not in json.dumps(first_test)

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.retry_count"] == "1"
    assert values["entroping.unstable"] == "true"
    assert values["entroping.attempt.1"] == "failed exit=42 duration_ms=20"
    assert values["entroping.attempt.2"] == "passed exit=0 duration_ms=30"

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "Retry evidence" in html
    assert "unstable: true" in html
    assert "attempt 1: failed exit=42 duration_ms=20" in html


def test_junit_failure_text_includes_retry_evidence_for_final_failures(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "unstable-fail.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "unstable-fail.hurl"
    suite = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="failed",
                exit_code=42,
                stdout="",
                stderr="assert failed\n",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=50,
                attempts=(
                    HurlAttemptEvidence(
                        attempt=1,
                        status="timeout",
                        exit_code=124,
                        duration_ms=20,
                        stdout_truncated=False,
                        stderr_truncated=False,
                    ),
                    HurlAttemptEvidence(
                        attempt=2,
                        status="failed",
                        exit_code=42,
                        duration_ms=30,
                        stdout_truncated=False,
                        stderr_truncated=False,
                    ),
                ),
            ),
        ),
    )
    report = build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)

    failure = ElementTree.parse(junit_path).getroot().find("testcase/failure")
    assert failure is not None
    assert "retry: count=1; unstable=true" in (failure.text or "")
    assert "attempt 1 timeout exit=124 duration_ms=20" in (failure.text or "")


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
    report = build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"

    write_junit_report(report, output)

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
    report = build_run_report(
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

    write_junit_report(report, output)

    xml_text = output.read_text(encoding="utf-8")
    assert "\x01" not in xml_text
    properties = ElementTree.parse(output).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.operation_id"] == "checkout\ufffdCreate"


def test_load_run_report_round_trips_retry_evidence_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-03T00:00:00+00:00",
                "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/eventual.hurl",
                        "execution_path": ".entroping/run/eventual.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 50,
                        "timeout_ms": 2500,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "retry": {
                            "retry_count": 1,
                            "unstable": True,
                            "attempts": [
                                "not-a-dict",
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
                                    "status": "invalid",
                                    "exit_code": 0,
                                    "duration_ms": 30,
                                    "stdout_truncated": False,
                                    "stderr_truncated": False,
                                },
                            ],
                        },
                    },
                    {
                        "path": "tests/no-retry.hurl",
                        "execution_path": ".entroping/run/no-retry.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "retry": "not-a-dict",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert report.tests[0].timeout_ms == 2500
    assert report.tests[1].timeout_ms == 0
    assert report.tests[0].retry.retry_count == 1
    assert report.tests[0].retry.unstable
    assert [
        (
            attempt.attempt,
            attempt.status,
            attempt.exit_code,
            attempt.duration_ms,
            attempt.stdout_truncated,
            attempt.stderr_truncated,
        )
        for attempt in report.tests[0].retry.attempts
    ] == [(1, "failed", 42, 20, False, True)]
    assert report.tests[1].retry.retry_count == 0
    assert not report.tests[1].retry.unstable


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
        load_run_report(latest)
    if forbidden_error_fragment is not None:
        assert forbidden_error_fragment not in str(exc_info.value)


def test_load_run_report_rejects_non_object_payload(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        load_run_report(latest)


def test_load_run_report_rejects_oversize_report_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(" " * 9, encoding="utf-8")
    monkeypatch.setattr(report_serialization, "_MAX_RUN_REPORT_BYTES", 8, raising=False)

    with pytest.raises(ValueError, match="exceeds 8 bytes"):
        load_run_report(latest)


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
        load_run_report(latest)
    assert "private-runtime-value" not in str(exc_info.value)


def test_load_run_report_ignores_bool_optional_integer_fields(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "exit_code": 0,
                    "selected": True,
                    "executed": False,
                    "not_scheduled": True,
                },
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 1,
                        "timeout_ms": True,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert report.summary.selected is None
    assert report.summary.executed is None
    assert report.summary.not_scheduled == 0
    assert report.tests[0].timeout_ms == 0


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
        load_run_report(latest)
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

    report = load_run_report(latest)

    assert report.tests[0].safety == RunSafetyEvidence(
        protected_environment=True,
        safety="idempotent",
        safety_source="test metadata",
        methods=("POST",),
        blocked_reason="not blocked",
    )
    assert all(test.safety is None for test in report.tests[1:])


def test_junit_report_includes_safety_properties(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                    attempts=(
                        HurlAttemptEvidence(
                            attempt=1,
                            status="blocked",
                            exit_code=1,
                            duration_ms=0,
                            stdout_truncated=False,
                            stderr_truncated=False,
                        ),
                    ),
                ),
            ),
        ),
        project_root=tmp_path,
        safety_evidence_by_source_path={
            source.resolve(): RunSafetyEvidence(
                protected_environment=True,
                safety="idempotent",
                safety_source="test metadata",
                methods=("POST",),
                blocked_reason="mutating method POST requires safety metadata",
            )
        },
    )

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)

    properties = ElementTree.parse(junit_path).getroot().findall("testcase/properties/property")
    values = {item.attrib["name"]: item.attrib["value"] for item in properties}
    assert values["entroping.safety.protected_environment"] == "true"
    assert values["entroping.safety"] == "idempotent"
    assert values["entroping.safety.methods"] == "POST"
    assert values["entroping.safety.blocked_reason"] == (
        "mutating method POST requires safety metadata"
    )


def test_junit_report_includes_suite_scheduling_properties(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                ),
            ),
            selected_count=2,
        ),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"

    write_junit_report(report, output)

    suite_properties = ElementTree.parse(output).getroot().findall("properties/property")
    values = {item.attrib["name"]: item.attrib["value"] for item in suite_properties}
    assert values == {
        "entroping.summary.selected": "2",
        "entroping.summary.executed": "1",
        "entroping.summary.not_scheduled": "1",
        "entroping.summary.fail_fast": "false",
    }


def test_normal_run_omits_suite_scheduling_evidence_across_report_formats(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("/bin/hurl", str(execution)),
                    status="passed",
                    exit_code=0,
                    stdout="HTTP 200\n",
                    stderr="",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=10,
                ),
            ),
        ),
        project_root=tmp_path,
    )

    payload = report_writer.run_report_to_dict(report)
    assert payload["summary"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "exit_code": 0,
    }

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    assert ElementTree.parse(junit_path).getroot().find("properties") is None

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<dt>Selected</dt>" not in html
    assert "<dt>Executed</dt>" not in html
    assert "<dt>Not scheduled</dt>" not in html
    assert "<dt>Fail fast</dt>" not in html


def test_selected_executed_gap_derives_scheduling_evidence_across_report_formats(
    tmp_path: Path,
) -> None:
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-15T00:00:00+00:00",
        summary=RunReportSummary(
            total=1,
            passed=0,
            failed=1,
            exit_code=1,
            selected=2,
            executed=1,
        ),
        tests=(
            RunTestReport(
                path="tests/write.hurl",
                execution_path=".entroping/run-1/write.hurl",
                status="blocked",
                exit_code=1,
                duration_ms=0,
                rule_ids=(),
                stdout="",
                stderr="Protected run blocked before Hurl execution",
            ),
        ),
    )

    payload = report_writer.run_report_to_dict(report)
    assert payload["summary"] == {
        "total": 1,
        "passed": 0,
        "failed": 1,
        "exit_code": 1,
        "selected": 2,
        "executed": 1,
        "not_scheduled": 1,
        "fail_fast": False,
    }

    junit_path = tmp_path / "reports" / "junit.xml"
    write_junit_report(report, junit_path)
    suite_properties = ElementTree.parse(junit_path).getroot().findall("properties/property")
    values = {item.attrib["name"]: item.attrib["value"] for item in suite_properties}
    assert values == {
        "entroping.summary.selected": "2",
        "entroping.summary.executed": "1",
        "entroping.summary.not_scheduled": "1",
        "entroping.summary.fail_fast": "false",
    }

    html_path = tmp_path / "reports" / "run-latest.html"
    write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<dt>Selected</dt><dd>2</dd>" in html
    assert "<dt>Executed</dt><dd>1</dd>" in html
    assert "<dt>Not scheduled</dt><dd>1</dd>" in html
    assert "<dt>Fail fast</dt><dd>false</dd>" in html


def test_html_report_includes_safety_summary_and_none_fallback(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                ),
            ),
        ),
        project_root=tmp_path,
        safety_evidence_by_source_path={
            source.resolve(): RunSafetyEvidence(
                protected_environment=True,
                safety=None,
                safety_source=None,
                methods=("PATCH",),
                blocked_reason=(
                    "mutating method PATCH requires safety metadata in protected environments"
                ),
            )
        },
    )
    output = tmp_path / "reports" / "run-latest.html"

    write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<strong>Safety</strong>" in html
    assert "protected_environment=true; safety=unspecified; source=none;" in html
    assert (
        report_rendering._safety_summary(
            RunTestReport(
                path="tests/no-safety.hurl",
                execution_path=".entroping/run/no-safety.hurl",
                status="passed",
                exit_code=0,
                duration_ms=0,
                rule_ids=(),
                stdout="",
                stderr="",
            )
        )
        == "none"
    )


def test_html_report_includes_suite_scheduling_summary(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                ),
            ),
            selected_count=2,
        ),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.html"

    write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<dt>Selected</dt><dd>2</dd>" in html
    assert "<dt>Executed</dt><dd>1</dd>" in html
    assert "<dt>Not scheduled</dt><dd>1</dd>" in html


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
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.json"

    write_json_report(report, output)

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
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )

    assert report.tests[0].response is None
    assert "response" not in report_writer._test_report_to_dict(report.tests[0])


def test_load_run_report_round_trips_response_fingerprint(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "status_code": 201,
                            "headers": {"content-type": "application/json"},
                            "body_shape": ["$:object", "$.id:string"],
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    response = report.tests[0].response
    assert response is not None
    assert response.status_code == 201
    assert {header.name: header.value for header in response.headers} == {
        "content-type": "application/json",
    }
    assert response.body_shape == ("$:object", "$.id:string")


def test_load_run_report_ignores_malformed_optional_response_fields(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "status_code": "201",
                            "headers": {
                                "content-type": 123,
                                "date": "volatile",
                                7: "ignored",
                            },
                            "body_shape": "not-a-list",
                        },
                    },
                    {
                        "path": "tests/bad-shape.hurl",
                        "execution_path": ".entroping/run/bad-shape.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "headers": "not-a-dict",
                            "body_shape": "not-a-list",
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert report.tests[0].response is None
    assert report.tests[1].response is None


def test_load_run_report_round_trips_valid_known_failures_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "known_failures": [
                            "not-a-dict",
                            {
                                "test": 123,
                                "rule_id": "latency",
                                "issue_id": "GH-001",
                                "expires": "2026-06-30",
                                "reason": "wrong type",
                            },
                            {
                                "test": "",
                                "rule_id": "latency",
                                "issue_id": "GH-002",
                                "expires": "2026-06-30",
                                "reason": "empty test",
                            },
                            {
                                "test": "tests/bad\n.hurl",
                                "rule_id": "latency",
                                "issue_id": "GH-003",
                                "expires": "2026-06-30",
                                "reason": "control character",
                            },
                            {
                                "test": " tests/health.hurl ",
                                "rule_id": " latency ",
                                "issue_id": " GH-123 ",
                                "expires": " 2026-06-30 ",
                                "reason": " Temporary upstream latency regression. ",
                            },
                        ],
                    },
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "known_failures": "not-a-list",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert [
        (
            known_failure.test,
            known_failure.rule_id,
            known_failure.issue_id,
            known_failure.expires,
            known_failure.reason,
        )
        for known_failure in report.tests[0].known_failures
    ] == [
        (
            "tests/health.hurl",
            "latency",
            "GH-123",
            "2026-06-30",
            "Temporary upstream latency regression.",
        )
    ]
    assert report.tests[1].known_failures == ()


def test_load_run_report_round_trips_auth_evidence_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-12T00:00:00+00:00",
                "summary": {"total": 4, "passed": 4, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/auth.hurl",
                        "execution_path": ".entroping/run/auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": " oauth2-client-credentials ",
                            "requires": [
                                " access_token ",
                                "bad name",
                                123,
                                "access_token",
                                "csrf_token",
                            ],
                            "produces": [" session_cookie "],
                        },
                    },
                    {
                        "path": "tests/no-auth.hurl",
                        "execution_path": ".entroping/run/no-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {},
                    },
                    {
                        "path": "tests/malformed-auth.hurl",
                        "execution_path": ".entroping/run/malformed-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": "not-a-dict",
                    },
                    {
                        "path": "tests/invalid-flow.hurl",
                        "execution_path": ".entroping/run/invalid-flow.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": "oauth2 live-secret",
                            "requires": ["session_token"],
                            "produces": [],
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert report.tests[0].auth is not None
    assert report.tests[0].auth.flow == "oauth2-client-credentials"
    assert report.tests[0].auth.requires == ("access_token", "csrf_token")
    assert report.tests[0].auth.produces == ("session_cookie",)
    assert report.tests[1].auth is None
    assert report.tests[2].auth is None
    assert report.tests[3].auth is not None
    assert report.tests[3].auth.flow is None
    assert report.tests[3].auth.requires == ("session_token",)


def test_load_run_report_trims_valid_operation_ids_and_ignores_malformed_values(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    tests = [
        {
            "path": "tests/not-string.hurl",
            "execution_path": ".entroping/run/not-string.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": 123,
        },
        {
            "path": "tests/control.hurl",
            "execution_path": ".entroping/run/control.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": "create\nCheckout",
        },
        {
            "path": "tests/valid.hurl",
            "execution_path": ".entroping/run/valid.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": " createCheckout ",
        },
    ]
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 3, "passed": 3, "failed": 0, "exit_code": 0},
                "tests": tests,
            },
        ),
        encoding="utf-8",
    )

    report = load_run_report(latest)

    assert [test.operation_id for test in report.tests] == [None, None, "createCheckout"]


def test_write_json_report_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
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

    with pytest.raises(ReportWriterError, match="temporary write failed"):
        write_json_report(report, output)

    assert output.read_text(encoding="utf-8") == "old\n"


def test_report_writers_use_concrete_artifact_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    text_artifacts: list[str] = []
    byte_artifacts: list[str] = []

    def capture_safe_write_text(path: Path, content: str, *, artifact: str) -> Path:
        _ = content
        text_artifacts.append(artifact)
        return path.resolve()

    def capture_safe_write_bytes(path: Path, content: bytes, *, artifact: str) -> Path:
        _ = content
        byte_artifacts.append(artifact)
        return path.resolve()

    monkeypatch.setattr(report_writer, "safe_write_text", capture_safe_write_text)
    monkeypatch.setattr(report_writer, "safe_write_bytes", capture_safe_write_bytes)

    write_json_report(report, tmp_path / "reports" / "run-latest.json")
    write_html_report(report, tmp_path / "reports" / "run.html")
    write_bug_report(report, tmp_path / "reports" / "bug.md")
    write_junit_report(report, tmp_path / "reports" / "junit.xml")

    assert text_artifacts == ["run report", "HTML report", "bug report"]
    assert byte_artifacts == ["JUnit XML report"]


def test_build_run_report_rejects_mismatched_execution_and_result_counts(tmp_path: Path) -> None:
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"

    with pytest.raises(ReportWriterError, match="Execution copy count does not match"):
        build_run_report(
            project="checkout-api",
            environment="local",
            execution_copies=[],
            suite=_suite_result(execution, "assert failed\n"),
            project_root=tmp_path,
        )


def test_build_run_report_rejects_result_without_execution_copy(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    unrelated_execution = tmp_path / ".entroping" / "run-1" / "other.hurl"

    with pytest.raises(ReportWriterError, match="Hurl result path does not match"):
        build_run_report(
            project="checkout-api",
            environment="local",
            execution_copies=[_execution_copy(source, execution)],
            suite=HurlSuiteResult(
                results=_suite_result(unrelated_execution, "assert failed\n").results,
                fail_fast=True,
            ),
            project_root=tmp_path,
        )


def test_build_run_report_displays_absolute_paths_outside_project_root(tmp_path: Path) -> None:
    outside_source = tmp_path.parent / "external-health.hurl"
    outside_execution = tmp_path.parent / "external-run-health.hurl"

    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(outside_source, outside_execution)],
        suite=_suite_result(outside_execution, "assert failed\n"),
        project_root=tmp_path,
    )

    assert report.tests[0].path == str(outside_source.resolve())
    assert report.tests[0].execution_path == str(outside_execution.resolve())


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


def test_write_junit_report_is_valid_ci_consumable_xml(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "junit.xml"

    write_junit_report(report, output)

    root = ElementTree.parse(output).getroot()
    assert root.tag == "testsuite"
    assert root.attrib["name"] == "Entroping checkout-api"
    assert root.attrib["tests"] == "1"
    assert root.attrib["failures"] == "1"
    testcase = root.find("testcase")
    assert testcase is not None
    assert testcase.attrib["classname"] == "tests"
    assert testcase.attrib["name"] == "health.hurl"
    failure = testcase.find("failure")
    assert failure is not None
    assert failure.attrib["message"] == "failed"
    assert "global_latency" in (failure.text or "")


def test_write_junit_report_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
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

    with pytest.raises(ReportWriterError, match="temporary write failed"):
        write_junit_report(report, output)

    assert output.read_text(encoding="utf-8") == "<old />\n"


def test_write_html_report_escapes_failure_output(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, '<script>alert("x")</script>\n'),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.html"

    write_html_report(report, output)

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

    write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "<em>passed</em>" not in html
    assert "0 &lt;em&gt;passed&lt;/em&gt; passed" in html
    assert "1 &amp; failed failed" in html
    assert "1 &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; total" in html


def test_latest_run_state_round_trips_and_renders_bug_report(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    latest = tmp_path / ".entroping" / "latest-run.json"

    write_json_report(report, latest)
    loaded = load_run_report(latest)
    bug = render_bug_report(loaded)

    assert loaded.summary.failed == 1
    assert "tests/health.hurl" in bug
    assert "global_latency" in bug
    assert "entroping run --tag" in bug


def test_render_bug_report_without_failures_returns_guidance() -> None:
    report = HurlSuiteResult(
        results=(
            HurlFileResult(
                path=Path("tests/health.hurl"),
                command=("/bin/hurl", "tests/health.hurl"),
                status="passed",
                exit_code=0,
                stdout="",
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=50,
            ),
        ),
    )
    run_report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(Path("tests/health.hurl"), Path("tests/health.hurl"))],
        suite=report,
        project_root=Path("."),
    )

    assert render_bug_report(run_report) == (
        "No failing Entroping run is available for bug report generation.\n"
    )


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
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, captured_output),
        project_root=tmp_path,
    )

    bug = render_bug_report(report)

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

    bug = render_bug_report(report)

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
    assert (
        "- Rule IDs: `[global_latency](https://evil.test)\\n## forged rule`"
        in summary_section
    )
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

    bug = render_bug_report(report)

    output_section = bug.split("## Output\n\n", maxsplit=1)[1]
    assert "\x00" not in output_section
    assert "\x1b" not in output_section
    assert "before<U+0000>after" in output_section
    assert "red<U+001B>[31m" in output_section


def test_write_bug_report_writes_failure_markdown(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "bug.md"

    written = write_bug_report(report, output)

    assert written == output.resolve()
    assert "# Entroping Failure Report" in output.read_text(encoding="utf-8")
    assert "tests/health.hurl" in output.read_text(encoding="utf-8")


def test_write_bug_report_rejects_symlinked_output_path(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
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
        write_bug_report(report, output)
    except ReportWriterError as exc:
        assert "symlinked bug report" in str(exc)
    else:
        raise AssertionError("expected symlinked report path to be rejected")
    assert not outside.exists()


def test_write_report_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = build_run_report(
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
        write_json_report(report, tmp_path / "reports" / "run-latest.json")
    except ReportWriterError as exc:
        assert "symlinked path component" in str(exc)
    else:
        raise AssertionError("expected symlinked report parent to be rejected")
    assert not (outside_dir / "run-latest.json").exists()
