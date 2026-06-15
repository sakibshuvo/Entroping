"""JSON serialization and deserialization for run reports."""

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from entroping.core.report_fingerprint import (
    _has_control_character,
    _serialized_response_body_shape,
    _serialized_response_headers,
    _serialized_response_status,
)
from entroping.models.report import (
    KnownFailureEvidence,
    RunAttemptEvidence,
    RunAuthEvidence,
    RunReport,
    RunReportSummary,
    RunRetryEvidence,
    RunSafetyEvidence,
    RunTestReport,
)

RUN_REPORT_SCHEMA_VERSION = "entroping.run-report.v1"
_AUTH_FLOW_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_AUTH_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
            timeout_ms=_serialized_timeout_ms(item.get("timeout_ms")),
            operation_id=_serialized_operation_id(item.get("operation_id")),
            source=_serialized_metadata_value(item.get("source")),
            negative_category=_serialized_metadata_value(item.get("negative_category")),
            severity=_serialized_metadata_value(item.get("severity")),
            response_status_code=_serialized_response_status(item.get("response")),
            response_headers=_serialized_response_headers(item.get("response")),
            response_body_shape=_serialized_response_body_shape(item.get("response")),
            known_failures=_serialized_known_failures(item.get("known_failures")),
            retry=_serialized_retry(item.get("retry")),
            safety=_serialized_safety(item.get("safety")),
            auth=_serialized_auth(item.get("auth")),
        )
        for item in data["tests"]
    )
    not_scheduled = cast(
        int,
        _serialized_non_negative_int(
            summary_data.get("not_scheduled"),
            default=0,
        ),
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
            selected=_serialized_non_negative_int(summary_data.get("selected")),
            executed=_serialized_non_negative_int(summary_data.get("executed")),
            not_scheduled=not_scheduled,
            fail_fast=summary_data.get("fail_fast") is True,
        ),
        tests=tests,
    )


def run_report_to_dict(report: RunReport) -> dict[str, object]:
    """Return the versioned JSON-serializable run report payload."""

    summary: dict[str, object] = {
        "total": report.summary.total,
        "passed": report.summary.passed,
        "failed": report.summary.failed,
        "exit_code": report.summary.exit_code,
    }
    if report.summary.has_scheduling_evidence:
        summary.update(
            {
                "selected": report.summary.selected_count,
                "executed": report.summary.executed_count,
                "not_scheduled": report.summary.not_scheduled_count,
                "fail_fast": report.summary.fail_fast,
            }
        )

    return {
        "schema_version": RUN_REPORT_SCHEMA_VERSION,
        "project": report.project,
        "environment": report.environment,
        "generated_at": report.generated_at,
        "summary": summary,
        "tests": [_test_report_to_dict(test) for test in report.tests],
    }


def _test_report_to_dict(test: RunTestReport) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": test.path,
        "execution_path": test.execution_path,
        "status": test.status,
        "exit_code": test.exit_code,
        "duration_ms": test.duration_ms,
        "timeout_ms": test.timeout_ms,
        "rule_ids": list(test.rule_ids),
        "stdout": test.stdout,
        "stderr": test.stderr,
        "retry": _retry_to_dict(test.retry),
    }
    response = _response_to_dict(test)
    if test.operation_id is not None:
        payload["operation_id"] = test.operation_id
    if test.source is not None:
        payload["source"] = test.source
    if test.negative_category is not None:
        payload["negative_category"] = test.negative_category
    if test.severity is not None:
        payload["severity"] = test.severity
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
    if test.safety is not None:
        payload["safety"] = _safety_to_dict(test.safety)
    if test.auth is not None:
        payload["auth"] = _auth_to_dict(test.auth)
    return payload


def _safety_to_dict(safety: RunSafetyEvidence) -> dict[str, object]:
    return {
        "protected_environment": safety.protected_environment,
        "safety": safety.safety,
        "safety_source": safety.safety_source,
        "methods": list(safety.methods),
        "blocked_reason": safety.blocked_reason,
    }


def _auth_to_dict(auth: RunAuthEvidence) -> dict[str, object]:
    return {
        "flow": auth.flow,
        "requires": list(auth.requires),
        "produces": list(auth.produces),
    }


def _retry_to_dict(retry: RunRetryEvidence) -> dict[str, object]:
    return {
        "retry_count": retry.retry_count,
        "unstable": retry.unstable,
        "attempts": [
            {
                "attempt": attempt.attempt,
                "status": attempt.status,
                "exit_code": attempt.exit_code,
                "duration_ms": attempt.duration_ms,
                "stdout_truncated": attempt.stdout_truncated,
                "stderr_truncated": attempt.stderr_truncated,
            }
            for attempt in retry.attempts
        ],
    }


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


def _serialized_retry(raw_retry: object) -> RunRetryEvidence:
    if not isinstance(raw_retry, Mapping):
        return RunRetryEvidence()
    retry_count = raw_retry.get("retry_count")
    unstable = raw_retry.get("unstable")
    raw_attempts = raw_retry.get("attempts")
    attempts: list[RunAttemptEvidence] = []
    if isinstance(raw_attempts, list):
        for item in raw_attempts:
            if not isinstance(item, Mapping):
                continue
            attempt = item.get("attempt")
            status = item.get("status")
            exit_code = item.get("exit_code")
            duration_ms = item.get("duration_ms")
            stdout_truncated = item.get("stdout_truncated")
            stderr_truncated = item.get("stderr_truncated")
            if (
                not isinstance(attempt, int)
                or attempt <= 0
                or status not in {"passed", "failed", "timeout", "error", "blocked"}
                or not isinstance(exit_code, int)
                or not isinstance(duration_ms, int)
                or duration_ms < 0
                or not isinstance(stdout_truncated, bool)
                or not isinstance(stderr_truncated, bool)
            ):
                continue
            attempts.append(
                RunAttemptEvidence(
                    attempt=attempt,
                    status=status,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                )
            )
    return RunRetryEvidence(
        retry_count=retry_count if isinstance(retry_count, int) and retry_count >= 0 else 0,
        unstable=unstable if isinstance(unstable, bool) else False,
        attempts=tuple(attempts),
    )


def _serialized_safety(raw_safety: object) -> RunSafetyEvidence | None:
    if not isinstance(raw_safety, Mapping):
        return None
    protected_environment = raw_safety.get("protected_environment")
    safety = raw_safety.get("safety")
    safety_source = raw_safety.get("safety_source")
    raw_methods = raw_safety.get("methods")
    blocked_reason = raw_safety.get("blocked_reason")
    if not isinstance(protected_environment, bool):
        return None
    if safety is not None and not isinstance(safety, str):
        return None
    if safety_source is not None and not isinstance(safety_source, str):
        return None
    if blocked_reason is not None and not isinstance(blocked_reason, str):
        return None
    if not isinstance(raw_methods, list) or not all(
        isinstance(method, str) for method in raw_methods
    ):
        return None
    strings = tuple(
        value
        for value in (
            *(item.strip() for item in raw_methods),
            *((safety.strip(),) if isinstance(safety, str) else ()),
            *((safety_source.strip(),) if isinstance(safety_source, str) else ()),
            *((blocked_reason.strip(),) if isinstance(blocked_reason, str) else ()),
        )
        if value
    )
    if any(_has_control_character(value) for value in strings):
        return None
    return RunSafetyEvidence(
        protected_environment=protected_environment,
        safety=safety.strip() if isinstance(safety, str) and safety.strip() else None,
        safety_source=(
            safety_source.strip()
            if isinstance(safety_source, str) and safety_source.strip()
            else None
        ),
        methods=tuple(item.strip() for item in raw_methods if item.strip()),
        blocked_reason=(
            blocked_reason.strip()
            if isinstance(blocked_reason, str) and blocked_reason.strip()
            else None
        ),
    )


def _serialized_auth(raw_auth: object) -> RunAuthEvidence | None:
    if not isinstance(raw_auth, Mapping):
        return None
    flow = _serialized_auth_flow(raw_auth.get("flow"))
    requires = _serialized_auth_variables(raw_auth.get("requires"))
    produces = _serialized_auth_variables(raw_auth.get("produces"))
    if flow is None and not requires and not produces:
        return None
    return RunAuthEvidence(flow=flow, requires=requires, produces=produces)


def _serialized_auth_flow(raw_flow: object) -> str | None:
    flow = _serialized_metadata_value(raw_flow)
    if flow is None or _AUTH_FLOW_RE.fullmatch(flow) is None:
        return None
    return flow


def _serialized_auth_variables(raw_variables: object) -> tuple[str, ...]:
    if not isinstance(raw_variables, list):
        return ()
    variables: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_variables:
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if (
            not name
            or _has_control_character(name)
            or _AUTH_VARIABLE_NAME_RE.fullmatch(name) is None
            or name in seen
        ):
            continue
        variables.append(name)
        seen.add(name)
    return tuple(variables)


def _serialized_timeout_ms(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _serialized_non_negative_int(value: object, *, default: int | None = None) -> int | None:
    return value if isinstance(value, int) and value >= 0 else default


def _serialized_operation_id(value: object) -> str | None:
    return _serialized_metadata_value(value)


def _serialized_metadata_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or _has_control_character(stripped):
        return None
    return stripped


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
