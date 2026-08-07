"""Bounded subprocess-attempt glue for structured Hurl evidence."""

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal

from entroping.core.hurl_structured import (
    HurlAssertionEvidence,
    HurlAssertionPolicy,
    HurlRunStatus,
    HurlStructuredReportError,
    StructuredHurlReport,
    classify_structured_result,
    has_only_injected_gate_failures,
    read_hurl_json_output,
)
from entroping.models.secrets import REDACTED, redact_secret_like_values

_TRUNCATION_TEMPLATE = "\n[entroping: {stream_name} truncated]\n"


def read_structured_attempt(
    *,
    status: HurlRunStatus,
    exit_code: int,
    extra_stderr: str,
    completed_process: bool,
    stdout_file: BinaryIO,
    capture_assertions: bool,
    capture_names: Sequence[str],
    hurl_path: Path,
) -> tuple[HurlRunStatus, int, StructuredHurlReport | None, str]:
    """Parse one completed structured-output attempt, if enabled."""

    if not capture_assertions or not completed_process:
        return status, exit_code, None, extra_stderr
    try:
        structured_report = read_hurl_json_output(
            stdout_file,
            hurl_path=str(hurl_path),
            expected_success=exit_code == 0,
            capture_names=capture_names,
        )
    except HurlStructuredReportError:
        return "error", 126, None, "Hurl structured assertion report invalid"
    return status, exit_code, structured_report, extra_stderr


def apply_structured_result(
    *,
    status: HurlRunStatus,
    exit_code: int,
    structured_report: StructuredHurlReport,
    policies: Sequence[HurlAssertionPolicy],
) -> tuple[HurlRunStatus, int, tuple[HurlAssertionEvidence, ...] | None]:
    """Classify structured assertions and return their sanitized evidence."""

    if policies:
        status, exit_code = classify_structured_result(
            status=status,
            exit_code=exit_code,
            assertions=structured_report.assertions,
            policies=policies,
        )
    return status, exit_code, structured_report.assertions


def read_attempt_stdout(
    *,
    stdout_file: BinaryIO,
    capture_assertions: bool,
    structured_report: StructuredHurlReport | None,
    output_limit_bytes: int,
    redacted_values: Sequence[str],
) -> tuple[str, bool]:
    """Read normal stdout, suppressing raw structured JSON."""

    if structured_report is not None or capture_assertions:
        return "", False
    return _read_process_output(
        stdout_file,
        stream_name="stdout",
        limit_bytes=output_limit_bytes,
        redacted_values=redacted_values,
    )


def finalize_structured_result(
    *,
    status: HurlRunStatus,
    exit_code: int,
    stdout: str,
    stdout_truncated: bool,
    structured_report: StructuredHurlReport | None,
    policies: Sequence[HurlAssertionPolicy],
    output_limit_bytes: int,
    redacted_values: Sequence[str],
) -> tuple[HurlRunStatus, int, str, bool, tuple[HurlAssertionEvidence, ...] | None]:
    """Classify one structured result and restore sanitized response evidence."""

    if structured_report is None:
        return status, exit_code, stdout, stdout_truncated, None
    status, exit_code, assertion_evidence = apply_structured_result(
        status=status,
        exit_code=exit_code,
        structured_report=structured_report,
        policies=policies,
    )
    stdout, stdout_truncated = _restore_structured_stdout(
        status=status,
        stdout=stdout,
        stdout_truncated=stdout_truncated,
        structured_report=structured_report,
        policies=policies,
        output_limit_bytes=output_limit_bytes,
        redacted_values=redacted_values,
    )
    return status, exit_code, stdout, stdout_truncated, assertion_evidence


def redact_hurl_output(text: str, extra_secret_values: Sequence[str] = ()) -> str:
    """Redact sensitive values from captured Hurl output."""

    redacted = redact_secret_like_values(text)
    for secret_value in extra_secret_values:
        if secret_value:
            redacted = redacted.replace(secret_value, REDACTED)
    return redacted


def _restore_structured_stdout(
    *,
    status: HurlRunStatus,
    stdout: str,
    stdout_truncated: bool,
    structured_report: StructuredHurlReport,
    policies: Sequence[HurlAssertionPolicy],
    output_limit_bytes: int,
    redacted_values: Sequence[str],
) -> tuple[str, bool]:
    response_output = structured_report.response_output
    if (
        stdout
        or response_output is None
        or not _can_restore_response(status, structured_report, policies)
    ):
        return stdout, stdout_truncated
    return _read_process_output(
        BytesIO(response_output),
        stream_name="stdout",
        limit_bytes=output_limit_bytes,
        redacted_values=redacted_values,
    )


def _can_restore_response(
    status: HurlRunStatus,
    structured_report: StructuredHurlReport,
    policies: Sequence[HurlAssertionPolicy],
) -> bool:
    return status == "passed" or (
        bool(policies)
        and has_only_injected_gate_failures(structured_report.assertions, policies)
    )


def _read_process_output(
    handle: BinaryIO,
    *,
    stream_name: Literal["stdout", "stderr"],
    limit_bytes: int,
    redacted_values: Sequence[str],
) -> tuple[str, bool]:
    handle.seek(0)
    raw_bytes = handle.read(limit_bytes + 1)
    truncated = len(raw_bytes) > limit_bytes
    if truncated:
        raw_bytes = raw_bytes[:limit_bytes]

    text = raw_bytes.decode("utf-8", errors="replace")
    text = redact_hurl_output(text, redacted_values)
    if truncated:
        text += _TRUNCATION_TEMPLATE.format(stream_name=stream_name)
    return text, truncated
