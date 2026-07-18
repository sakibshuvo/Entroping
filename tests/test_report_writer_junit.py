"""JUnit output-boundary tests for deterministic run reports."""

from pathlib import Path
from xml.etree import ElementTree

from report_writer_test_helpers import _execution_copy, _suite_result

import entroping.core.report_writer as report_writer
from entroping.core.hurl_runner import HurlAttemptEvidence, HurlFileResult, HurlSuiteResult
from entroping.models.report import RunSafetyEvidence


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
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="ci",
        execution_copies=[_execution_copy(source, execution)],
        suite=suite,
        project_root=tmp_path,
    )

    junit_path = tmp_path / "reports" / "junit.xml"
    report_writer.write_junit_report(report, junit_path)

    failure = ElementTree.parse(junit_path).getroot().find("testcase/failure")
    assert failure is not None
    assert "retry: count=1; unstable=true" in (failure.text or "")
    assert "attempt 1 timeout exit=124 duration_ms=20" in (failure.text or "")


def test_junit_report_includes_safety_properties(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = report_writer.build_run_report(
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
    report_writer.write_junit_report(report, junit_path)

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
    report = report_writer.build_run_report(
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

    report_writer.write_junit_report(report, output)

    suite_properties = ElementTree.parse(output).getroot().findall("properties/property")
    values = {item.attrib["name"]: item.attrib["value"] for item in suite_properties}
    assert values == {
        "entroping.summary.selected": "2",
        "entroping.summary.executed": "1",
        "entroping.summary.not_scheduled": "1",
        "entroping.summary.fail_fast": "false",
    }


def test_write_junit_report_is_valid_ci_consumable_xml(tmp_path: Path) -> None:
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

    report_writer.write_junit_report(report, output)

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
