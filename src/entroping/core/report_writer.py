"""Report writers for deterministic Entroping runs."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult, redact_hurl_output
from entroping.core.report_errors import ReportWriterError
from entroping.core.report_fingerprint import (
    _extract_response_fingerprint,
    _json_body_shape,
    _parse_response_lines,
    _walk_json_shape,
)
from entroping.core.report_rendering import (
    render_bug_report,
    render_html_report,
    render_junit_report,
)
from entroping.core.report_serialization import (
    RUN_REPORT_SCHEMA_VERSION,
    _response_to_dict,
    _serialized_known_failures,
    _test_report_to_dict,
    load_run_report,
    run_report_to_dict,
)
from entroping.core.safe_write import SafeWriteError, safe_write_bytes, safe_write_text
from entroping.models.report import (
    KnownFailureEvidence,
    RunAttemptEvidence,
    RunReport,
    RunReportSummary,
    RunRetryEvidence,
    RunTestReport,
)

__all__ = [
    "RUN_REPORT_SCHEMA_VERSION",
    "ReportWriterError",
    "build_run_report",
    "load_run_report",
    "render_bug_report",
    "run_report_to_dict",
    "write_bug_report",
    "write_html_report",
    "write_json_report",
    "write_junit_report",
    "_extract_response_fingerprint",
    "_json_body_shape",
    "_parse_response_lines",
    "_response_to_dict",
    "_serialized_known_failures",
    "_test_report_to_dict",
    "_walk_json_shape",
]


def build_run_report(
    *,
    project: str,
    environment: str,
    execution_copies: Sequence[HurlExecutionCopy],
    suite: HurlSuiteResult,
    project_root: Path,
) -> RunReport:
    """Build a serializable report from Hurl execution copies and results."""

    if len(execution_copies) != len(suite.results) and (
        not suite.fail_fast or len(suite.results) > len(execution_copies)
    ):
        msg = "Execution copy count does not match Hurl result count"
        raise ReportWriterError(msg)

    root = project_root.expanduser().resolve()
    execution_copies_by_path = {
        execution_copy.execution_path.expanduser().resolve(): execution_copy
        for execution_copy in execution_copies
    }
    tests: list[RunTestReport] = []
    for result in suite.results:
        execution_copy = execution_copies_by_path.get(result.path.expanduser().resolve())
        if execution_copy is None:
            msg = "Hurl result path does not match an execution copy"
            raise ReportWriterError(msg)
        stdout = redact_hurl_output(result.stdout)
        stderr = redact_hurl_output(result.stderr)
        response_status_code, response_headers, response_body_shape = _extract_response_fingerprint(
            stdout
        )
        tests.append(
            RunTestReport(
                path=_display_path(execution_copy.source_path, root),
                execution_path=_display_path(execution_copy.execution_path, root),
                status=result.status,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                rule_ids=tuple(gate.rule_id for gate in execution_copy.injected_gates),
                stdout=stdout,
                stderr=stderr,
                timeout_ms=result.timeout_ms,
                operation_id=execution_copy.operation_id,
                response_status_code=response_status_code,
                response_headers=response_headers,
                response_body_shape=response_body_shape,
                retry=_retry_evidence_from_result(result),
                known_failures=tuple(
                    KnownFailureEvidence(
                        test=known_failure.test,
                        rule_id=known_failure.rule_id,
                        issue_id=known_failure.issue_id,
                        expires=known_failure.expires,
                        reason=known_failure.reason,
                    )
                    for known_failure in execution_copy.known_failures
                ),
            )
        )

    return RunReport(
        project=project,
        environment=environment or "default",
        generated_at=datetime.now(UTC).isoformat(),
        summary=RunReportSummary(
            total=suite.total,
            passed=suite.passed,
            failed=suite.failed,
            exit_code=suite.exit_code,
            selected=suite.selected_count,
            executed=suite.total,
            not_scheduled=suite.not_scheduled,
            fail_fast=suite.fail_fast,
        ),
        tests=tuple(tests),
    )


def _retry_evidence_from_result(result: HurlFileResult) -> RunRetryEvidence:
    attempts = result.attempts
    if not attempts:
        return RunRetryEvidence(
            attempts=(
                RunAttemptEvidence(
                    attempt=1,
                    status=result.status,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stdout_truncated=result.stdout_truncated,
                    stderr_truncated=result.stderr_truncated,
                ),
            )
        )
    return RunRetryEvidence(
        retry_count=result.retry_count,
        unstable=result.unstable,
        attempts=tuple(
            RunAttemptEvidence(
                attempt=attempt.attempt,
                status=attempt.status,
                exit_code=attempt.exit_code,
                duration_ms=attempt.duration_ms,
                stdout_truncated=attempt.stdout_truncated,
                stderr_truncated=attempt.stderr_truncated,
            )
            for attempt in attempts
        ),
    )


def write_json_report(report: RunReport, path: Path) -> Path:
    """Write a redacted JSON run report."""

    return _write_report_text(
        path,
        json.dumps(run_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        artifact="path",
    )


def write_junit_report(report: RunReport, path: Path) -> Path:
    """Write a CI-consumable JUnit XML report."""

    return _write_report_bytes(path, render_junit_report(report), artifact="path")


def write_html_report(report: RunReport, path: Path) -> Path:
    """Write a dependency-free human-readable HTML report."""

    return _write_report_text(path, render_html_report(report), artifact="path")


def write_bug_report(report: RunReport, path: Path) -> Path:
    """Write a Markdown bug handoff with the same path safety as other reports."""

    return _write_report_text(path, render_bug_report(report), artifact="path")


def _display_path(path: Path, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _write_report_text(path: Path, content: str, *, artifact: str) -> Path:
    try:
        return safe_write_text(path, content, artifact=artifact)
    except SafeWriteError as exc:
        raise ReportWriterError(str(exc)) from exc


def _write_report_bytes(path: Path, content: bytes, *, artifact: str) -> Path:
    try:
        return safe_write_bytes(path, content, artifact=artifact)
    except SafeWriteError as exc:
        raise ReportWriterError(str(exc)) from exc
