"""JSON serialization and deserialization for run reports."""

import json
from collections.abc import Mapping
from pathlib import Path

from entroping.core.report_fingerprint import (
    _has_control_character,
    _serialized_response_body_shape,
    _serialized_response_headers,
    _serialized_response_status,
)
from entroping.models.report import (
    KnownFailureEvidence,
    RunReport,
    RunReportSummary,
    RunTestReport,
)

RUN_REPORT_SCHEMA_VERSION = "entroping.run-report.v1"


def load_run_report(path: Path) -> RunReport:
    """Load a previously written JSON run report."""

    data = json.loads(path.read_text(encoding="utf-8"))
    summary_data = data["summary"]
    tests = tuple(
        RunTestReport(
            path=item["path"],
            execution_path=item["execution_path"],
            status=item["status"],
            exit_code=item["exit_code"],
            duration_ms=item["duration_ms"],
            rule_ids=tuple(item["rule_ids"]),
            stdout=item["stdout"],
            stderr=item["stderr"],
            response_status_code=_serialized_response_status(item.get("response")),
            response_headers=_serialized_response_headers(item.get("response")),
            response_body_shape=_serialized_response_body_shape(item.get("response")),
            known_failures=_serialized_known_failures(item.get("known_failures")),
        )
        for item in data["tests"]
    )
    return RunReport(
        project=data["project"],
        environment=data["environment"],
        generated_at=data["generated_at"],
        summary=RunReportSummary(
            total=summary_data["total"],
            passed=summary_data["passed"],
            failed=summary_data["failed"],
            exit_code=summary_data["exit_code"],
        ),
        tests=tests,
    )


def run_report_to_dict(report: RunReport) -> dict[str, object]:
    """Return the versioned JSON-serializable run report payload."""

    return {
        "schema_version": RUN_REPORT_SCHEMA_VERSION,
        "project": report.project,
        "environment": report.environment,
        "generated_at": report.generated_at,
        "summary": {
            "total": report.summary.total,
            "passed": report.summary.passed,
            "failed": report.summary.failed,
            "exit_code": report.summary.exit_code,
        },
        "tests": [_test_report_to_dict(test) for test in report.tests],
    }


def _test_report_to_dict(test: RunTestReport) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": test.path,
        "execution_path": test.execution_path,
        "status": test.status,
        "exit_code": test.exit_code,
        "duration_ms": test.duration_ms,
        "rule_ids": list(test.rule_ids),
        "stdout": test.stdout,
        "stderr": test.stderr,
    }
    response = _response_to_dict(test)
    if response is not None:
        payload["response"] = response
    if test.known_failures:
        payload["known_failures"] = [
            {
                "test": known_failure.test,
                "rule_id": known_failure.rule_id,
                "issue_id": known_failure.issue_id,
                "expires": known_failure.expires,
                "reason": known_failure.reason,
            }
            for known_failure in test.known_failures
        ]
    return payload


def _response_to_dict(test: RunTestReport) -> dict[str, object] | None:
    if (
        test.response_status_code is None
        and not test.response_headers
        and not test.response_body_shape
    ):
        return None
    return {
        "status_code": test.response_status_code,
        "headers": dict(test.response_headers),
        "body_shape": list(test.response_body_shape),
    }


def _serialized_known_failures(raw_known_failures: object) -> tuple[KnownFailureEvidence, ...]:
    if not isinstance(raw_known_failures, list):
        return ()
    known_failures: list[KnownFailureEvidence] = []
    for item in raw_known_failures:
        if not isinstance(item, Mapping):
            continue
        test = item.get("test")
        rule_id = item.get("rule_id")
        issue_id = item.get("issue_id")
        expires = item.get("expires")
        reason = item.get("reason")
        if (
            not isinstance(test, str)
            or not isinstance(rule_id, str)
            or not isinstance(issue_id, str)
            or not isinstance(expires, str)
            or not isinstance(reason, str)
        ):
            continue
        values = (test.strip(), rule_id.strip(), issue_id.strip(), expires.strip(), reason.strip())
        if not all(values) or any(_has_control_character(value) for value in values):
            continue
        known_failures.append(
            KnownFailureEvidence(
                test=values[0],
                rule_id=values[1],
                issue_id=values[2],
                expires=values[3],
                reason=values[4],
            )
        )
    return tuple(known_failures)
