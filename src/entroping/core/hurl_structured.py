"""Bounded Hurl JSON evidence parsing and gate-result classification."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

_STRUCTURED_REPORT_FILE_LIMIT_BYTES = 256 * 1024
_STRUCTURED_JSON_LIMIT_BYTES = 4 * 1024 * 1024
_STRUCTURED_REPORT_ENTRY_LIMIT = 4096
_STRUCTURED_RESPONSE_BODY_LIMIT_BYTES = 256 * 1024

HurlRunStatus = Literal["passed", "failed", "timeout", "error", "blocked"]


class HurlRunnerError(RuntimeError):
    """Base class for deterministic Hurl runner failures."""


class HurlStructuredReportError(HurlRunnerError):
    """Raised when Hurl's bounded structured assertion report is unusable."""


@dataclass(frozen=True)
class HurlAssertionPolicy:
    """Classification policy for one generated Hurl assertion line."""

    line: int
    blocking: bool


@dataclass(frozen=True)
class HurlAssertionEvidence:
    """Structured result for one Hurl assertion line."""

    line: int
    success: bool


@dataclass(frozen=True)
class StructuredHurlReport:
    """Validated structured Hurl output needed by the run workflow."""

    assertions: tuple[HurlAssertionEvidence, ...]
    response_output: bytes | None


def read_hurl_json_output(
    stdout_file: BinaryIO,
    *,
    hurl_path: str | Path,
    expected_success: bool,
    capture_names: Sequence[str],
) -> StructuredHurlReport:
    """Read Hurl 4.3 JSON from a bounded private stdout handle."""

    payload = _read_report_envelope(
        stdout_file,
        hurl_path=hurl_path,
        expected_success=expected_success,
    )
    entries = _validated_structured_entries(payload)
    assertion_evidence = _structured_assertions(entries)
    from entroping.core.hurl_structured_response import structured_response_output

    return StructuredHurlReport(
        assertions=assertion_evidence,
        response_output=structured_response_output(entries, capture_names),
    )


def _read_report_envelope(
    stdout_file: BinaryIO,
    *,
    hurl_path: str | Path,
    expected_success: bool,
) -> Mapping[object, object]:
    payload = _read_json_payload(stdout_file)
    if not isinstance(payload, Mapping):
        raise HurlStructuredReportError
    _validate_report_envelope(
        payload,
        hurl_path=str(hurl_path),
        expected_success=expected_success,
    )
    return payload


def _read_json_payload(stdout_file: BinaryIO) -> object:
    try:
        stdout_file.seek(0)
        report_bytes = stdout_file.read(_STRUCTURED_JSON_LIMIT_BYTES + 1)
    except OSError as exc:
        raise HurlStructuredReportError from exc
    if len(report_bytes) > _STRUCTURED_JSON_LIMIT_BYTES:
        raise HurlStructuredReportError
    try:
        return json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HurlStructuredReportError from exc


def _validate_report_envelope(
    payload: Mapping[object, object],
    *,
    hurl_path: str,
    expected_success: bool,
) -> None:
    if payload.get("filename") != hurl_path:
        raise HurlStructuredReportError
    if not _is_expected_success(payload.get("success"), expected_success):
        raise HurlStructuredReportError


def _is_expected_success(value: object, expected: bool) -> bool:
    return isinstance(value, bool) and value == expected


def _validated_structured_entries(
    payload: Mapping[object, object],
) -> tuple[Mapping[object, object], ...]:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise HurlStructuredReportError
    if len(entries) > _STRUCTURED_REPORT_ENTRY_LIMIT:
        raise HurlStructuredReportError
    return tuple(_require_mapping(entry) for entry in entries)


def _require_mapping(value: object) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise HurlStructuredReportError
    return value


def _structured_assertions(
    entries: Sequence[Mapping[object, object]],
) -> tuple[HurlAssertionEvidence, ...]:
    return tuple(
        assertion
        for entry in entries
        for assertion in _entry_assertions(entry.get("asserts"))
    )


def _entry_assertions(raw_assertions: object) -> tuple[HurlAssertionEvidence, ...]:
    if not isinstance(raw_assertions, list):
        raise HurlStructuredReportError
    return tuple(_parse_assertion(assertion) for assertion in raw_assertions)


def _parse_assertion(raw_assertion: object) -> HurlAssertionEvidence:
    assertion = _require_mapping(raw_assertion)
    line = _positive_int(assertion.get("line"))
    success = _strict_bool(assertion.get("success"))
    return HurlAssertionEvidence(line=line, success=success)


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HurlStructuredReportError
    return value


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise HurlStructuredReportError
    return value


def classify_structured_result(
    *,
    status: HurlRunStatus,
    exit_code: int,
    assertions: Sequence[HurlAssertionEvidence],
    policies: Sequence[HurlAssertionPolicy],
) -> tuple[HurlRunStatus, int]:
    policies_by_line = _policies_by_line(policies)
    if policies_by_line is None:
        return "error", 126
    observed_by_line = _observed_by_line(assertions)
    return _classify_observed_result(
        status=status,
        exit_code=exit_code,
        assertions=assertions,
        policies=policies,
        policies_by_line=policies_by_line,
        observed_by_line=observed_by_line,
    )


def _classify_observed_result(
    *,
    status: HurlRunStatus,
    exit_code: int,
    assertions: Sequence[HurlAssertionEvidence],
    policies: Sequence[HurlAssertionPolicy],
    policies_by_line: Mapping[int, HurlAssertionPolicy],
    observed_by_line: Mapping[int, Sequence[bool]],
) -> tuple[HurlRunStatus, int]:
    if _missing_policy_evidence(policies, observed_by_line):
        return "error", 126
    if _source_failed(assertions, policies_by_line) or _blocking_gate_failed(
        policies,
        observed_by_line,
    ):
        return _blocking_result(status, exit_code)
    if _any_gate_failed(policies, observed_by_line):
        return "passed", 0
    return status, exit_code


def _policies_by_line(
    policies: Sequence[HurlAssertionPolicy],
) -> dict[int, HurlAssertionPolicy] | None:
    policies_by_line: dict[int, HurlAssertionPolicy] = {}
    for policy in policies:
        if policy.line in policies_by_line:
            return None
        policies_by_line[policy.line] = policy
    return policies_by_line


def _observed_by_line(
    assertions: Sequence[HurlAssertionEvidence],
) -> dict[int, list[bool]]:
    observed: dict[int, list[bool]] = {}
    for assertion in assertions:
        observed.setdefault(assertion.line, []).append(assertion.success)
    return observed


def _missing_policy_evidence(
    policies: Sequence[HurlAssertionPolicy],
    observed: Mapping[int, Sequence[bool]],
) -> bool:
    return any(len(observed.get(policy.line, ())) != 1 for policy in policies)


def _source_failed(
    assertions: Sequence[HurlAssertionEvidence],
    policies_by_line: Mapping[int, HurlAssertionPolicy],
) -> bool:
    return any(
        not assertion.success and assertion.line not in policies_by_line
        for assertion in assertions
    )


def _blocking_gate_failed(
    policies: Sequence[HurlAssertionPolicy],
    observed: Mapping[int, Sequence[bool]],
) -> bool:
    return any(policy.blocking and not observed[policy.line][0] for policy in policies)


def _any_gate_failed(
    policies: Sequence[HurlAssertionPolicy],
    observed: Mapping[int, Sequence[bool]],
) -> bool:
    return any(not observed[policy.line][0] for policy in policies)


def _blocking_result(status: HurlRunStatus, exit_code: int) -> tuple[HurlRunStatus, int]:
    if status == "passed":
        return "failed", max(1, exit_code)
    return status, exit_code


def has_only_injected_gate_failures(
    assertions: Sequence[HurlAssertionEvidence],
    policies: Sequence[HurlAssertionPolicy],
) -> bool:
    policy_lines = {policy.line for policy in policies}
    return (
        bool(policy_lines)
        and _has_injected_failure(assertions, policy_lines)
        and _all_other_assertions_pass(assertions, policy_lines)
    )


def _all_other_assertions_pass(
    assertions: Sequence[HurlAssertionEvidence],
    policy_lines: set[int],
) -> bool:
    return all(assertion.success or assertion.line in policy_lines for assertion in assertions)


def _has_injected_failure(
    assertions: Sequence[HurlAssertionEvidence],
    policy_lines: set[int],
) -> bool:
    return any(not assertion.success and assertion.line in policy_lines for assertion in assertions)
