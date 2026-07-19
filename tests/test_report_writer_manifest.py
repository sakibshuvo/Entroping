"""Manifest and lifecycle tests for deterministic run reports."""

import json
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree

import pytest
from report_writer_test_helpers import _execution_copy, _suite_result

import entroping.core.report_writer as report_writer
from entroping.core.gate_injector import AppliedKnownFailure
from entroping.core.hurl_runner import HurlAttemptEvidence, HurlFileResult, HurlSuiteResult
from entroping.models.report import RunReport, RunReportSummary, RunTestReport


def test_reports_include_operation_id_evidence(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
    properties = ElementTree.parse(junit_path).getroot().find("testcase/properties")
    assert properties is not None
    values = {
        property_node.attrib["name"]: property_node.attrib["value"]
        for property_node in properties.findall("property")
    }
    assert values["entroping.operation_id"] == "createCheckout"

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<th>Operation</th>" in html
    assert "createCheckout" in html


def test_reports_include_generated_negative_path_metadata(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "generated" / "negative" / "checkout_boundary.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout_boundary.hurl"
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
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
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "boundary-values" in html
    assert "medium" in html


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
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
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
    report_writer.write_html_report(report, html_path)
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
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
    failure = ElementTree.parse(junit_path).getroot().find("testcase/failure")
    assert failure is not None
    assert failure.attrib["message"] == "timeout"
    assert failure.attrib["type"] == "entroping.hurl.timeout"
    assert "timeout_ms: 250" in (failure.text or "")

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
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
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
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
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "Retry evidence" in html
    assert "unstable: true" in html
    assert "attempt 1: failed exit=42 duration_ms=20" in html


def test_normal_run_omits_suite_scheduling_evidence_across_report_formats(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)
    assert ElementTree.parse(junit_path).getroot().find("properties") is None

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
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
    report_writer.write_junit_report(report, junit_path)
    suite_properties = ElementTree.parse(junit_path).getroot().findall("properties/property")
    values = {item.attrib["name"]: item.attrib["value"] for item in suite_properties}
    assert values == {
        "entroping.summary.selected": "2",
        "entroping.summary.executed": "1",
        "entroping.summary.not_scheduled": "1",
        "entroping.summary.fail_fast": "false",
    }

    html_path = tmp_path / "reports" / "run-latest.html"
    report_writer.write_html_report(report, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "<dt>Selected</dt><dd>2</dd>" in html
    assert "<dt>Executed</dt><dd>1</dd>" in html
    assert "<dt>Not scheduled</dt><dd>1</dd>" in html
    assert "<dt>Fail fast</dt><dd>false</dd>" in html


def test_report_writers_use_concrete_artifact_labels(
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

    report_writer.write_json_report(report, tmp_path / "reports" / "run-latest.json")
    report_writer.write_html_report(report, tmp_path / "reports" / "run.html")
    report_writer.write_bug_report(report, tmp_path / "reports" / "bug.md")
    report_writer.write_junit_report(report, tmp_path / "reports" / "junit.xml")

    assert text_artifacts == ["run report", "HTML report", "bug report"]
    assert byte_artifacts == ["JUnit XML report"]


def test_build_run_report_rejects_mismatched_execution_and_result_counts(tmp_path: Path) -> None:
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"

    with pytest.raises(
        report_writer.ReportWriterError, match="Execution copy count does not match"
    ):
        report_writer.build_run_report(
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

    with pytest.raises(report_writer.ReportWriterError, match="Hurl result path does not match"):
        report_writer.build_run_report(
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

    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(outside_source, outside_execution)],
        suite=_suite_result(outside_execution, "assert failed\n"),
        project_root=tmp_path,
    )

    assert report.tests[0].path == str(outside_source.resolve())
    assert report.tests[0].execution_path == str(outside_execution.resolve())


def test_latest_run_state_round_trips_and_renders_bug_report(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "health.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "health.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(source, execution)],
        suite=_suite_result(execution, "assert failed\n"),
        project_root=tmp_path,
    )
    latest = tmp_path / ".entroping" / "latest-run.json"

    report_writer.write_json_report(report, latest)
    loaded = report_writer.load_run_report(latest)
    bug = report_writer.render_bug_report(loaded)

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
    run_report = report_writer.build_run_report(
        project="checkout-api",
        environment="local",
        execution_copies=[_execution_copy(Path("tests/health.hurl"), Path("tests/health.hurl"))],
        suite=report,
        project_root=Path("."),
    )

    assert report_writer.render_bug_report(run_report) == (
        "No failing Entroping run is available for bug report generation.\n"
    )


def test_write_bug_report_writes_failure_markdown(tmp_path: Path) -> None:
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

    written = report_writer.write_bug_report(report, output)

    assert written == output.resolve()
    assert "# Entroping Failure Report" in output.read_text(encoding="utf-8")
    assert "tests/health.hurl" in output.read_text(encoding="utf-8")
