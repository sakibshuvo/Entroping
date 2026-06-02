"""Report writers for deterministic Entroping runs."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlSuiteResult, redact_hurl_output
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
from entroping.models.report import KnownFailureEvidence, RunReport, RunReportSummary, RunTestReport

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

    if len(execution_copies) != len(suite.results):
        msg = "Execution copy count does not match Hurl result count"
        raise ReportWriterError(msg)

    root = project_root.expanduser().resolve()
    tests: list[RunTestReport] = []
    for execution_copy, result in zip(execution_copies, suite.results, strict=True):
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
                response_status_code=response_status_code,
                response_headers=response_headers,
                response_body_shape=response_body_shape,
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
        ),
        tests=tuple(tests),
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
