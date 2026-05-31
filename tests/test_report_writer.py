"""Unit and adapter tests for deterministic run report writers."""

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

import entroping.core.report_writer as report_writer
from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult
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


def _execution_copy(source: Path, execution: Path) -> HurlExecutionCopy:
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
    assert "live-secret" not in output.read_text(encoding="utf-8")
    assert "Authorization: [REDACTED]" in data["tests"][0]["stdout"]
    assert "token=[REDACTED]" in data["tests"][0]["stderr"]


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


def test_response_fingerprint_ignores_malformed_http_output_and_shapes_nulls() -> None:
    status_code, headers, body_shape = report_writer._extract_response_fingerprint(
        'HTTP 200\nnot-a-header\n{"ok":true}\n',
    )

    assert status_code == 200
    assert headers == ()
    assert body_shape == ()
    assert report_writer._walk_json_shape(
        {1: "ignored", "bad\n": "ignored", "ok": None},
        "$",
    ) == ["$:object", "$.ok:null"]


def test_load_run_report_round_trips_response_fingerprint(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
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
        assert "symlinked path" in str(exc)
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
