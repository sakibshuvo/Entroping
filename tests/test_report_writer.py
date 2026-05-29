"""Unit and adapter tests for deterministic run report writers."""

import json
from pathlib import Path
from xml.etree import ElementTree

from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult
from entroping.core.report_writer import (
    ReportWriterError,
    build_run_report,
    load_run_report,
    render_bug_report,
    write_bug_report,
    write_json_report,
    write_junit_report,
)


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
