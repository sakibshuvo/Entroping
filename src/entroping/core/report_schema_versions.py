"""Shared report schema version constants and boundary validation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeGuard, cast

from entroping.core import report_fingerprint
from entroping.core import report_gate_results as _report_gate_results

RUN_REPORT_SCHEMA_VERSION: Final = "entroping.run-report.v1"

EVIDENCE_INDEX_SCHEMA_VERSION: Final = "entroping.evidence-index.v1"
OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION: Final = (
    "entroping.observability-adapter-readiness.v1"
)
OTEL_MAPPING_SCHEMA_VERSION: Final = "entroping.otel-mapping.v1"

_REQUIRED_RUN_REPORT_STRING_FIELDS: Final[tuple[str, ...]] = (
    "project",
    "environment",
    "generated_at",
)
_RUN_REPORT_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "project",
        "environment",
        "generated_at",
        "summary",
        "tests",
    }
)
_REQUIRED_RUN_REPORT_SUMMARY_INT_FIELDS: Final[tuple[str, ...]] = (
    "total",
    "passed",
    "failed",
    "exit_code",
)
_RUN_REPORT_SUMMARY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "total",
        "passed",
        "failed",
        "exit_code",
        "selected",
        "executed",
        "not_scheduled",
        "fail_fast",
    }
)
_REQUIRED_RUN_REPORT_TEST_STRING_FIELDS: Final[tuple[str, ...]] = (
    "path",
    "execution_path",
    "status",
    "stdout",
    "stderr",
)
_REQUIRED_RUN_REPORT_TEST_INT_FIELDS: Final[tuple[str, ...]] = (
    "exit_code",
    "duration_ms",
)
_RUN_REPORT_TEST_KEYS: Final[frozenset[str]] = frozenset(
    {
        "path",
        "execution_path",
        "status",
        "exit_code",
        "duration_ms",
        "rule_ids",
        "stdout",
        "stderr",
        "timeout_ms",
        "operation_id",
        "source",
        "negative_category",
        "severity",
        "gate_results",
        "retry",
        "safety",
        "auth",
        "known_failures",
        "response",
    }
)
_RUN_REPORT_RETRY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "retry_count",
        "unstable",
        "attempts",
    }
)
_RUN_REPORT_RETRY_ATTEMPT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "attempt",
        "status",
        "exit_code",
        "duration_ms",
        "stdout_truncated",
        "stderr_truncated",
    }
)
_RUN_REPORT_AUTH_KEYS: Final[frozenset[str]] = frozenset({"flow", "requires", "produces"})
_RUN_REPORT_SAFETY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "protected_environment",
        "safety",
        "safety_source",
        "methods",
        "blocked_reason",
    }
)
_RUN_REPORT_RESPONSE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "status_code",
        "headers",
        "body_shape",
    }
)
_RUN_REPORT_KNOWN_FAILURE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "test",
        "rule_id",
        "issue_id",
        "expires",
        "reason",
    }
)
_RUN_REPORT_GATE_RESULT_KEYS: Final[frozenset[str]] = frozenset(
    {"rule_id", "enforcement", "result", "exit_code"}
)


def _require_run_report_schema(data: object, *, path: Path) -> None:
    if not isinstance(data, Mapping):
        msg = f"Run report {path} must be a JSON object"
        raise ValueError(msg)
    _require_object_keys(data, path=path, display_name="root", allowed=_RUN_REPORT_ROOT_KEYS)
    _require_schema_version(data, path=path)
    _require_string_fields(data, _REQUIRED_RUN_REPORT_STRING_FIELDS, path=path, prefix="")
    _require_run_report_summary(data, path=path)
    tests = _require_json_array(data, "tests", path=path)
    for index, item in enumerate(tests):
        _require_run_report_test(item, index=index, path=path)


def _require_schema_version(data: Mapping[object, object], *, path: Path) -> None:
    if "schema_version" not in data:
        msg = f"Run report {path} must use schema_version {RUN_REPORT_SCHEMA_VERSION}"
        raise ValueError(msg)
    schema_version = data["schema_version"]
    if not isinstance(schema_version, str):
        msg = f"Run report {path} field schema_version must be a string"
        raise ValueError(msg)
    if schema_version != RUN_REPORT_SCHEMA_VERSION:
        msg = f"Run report {path} must use schema_version {RUN_REPORT_SCHEMA_VERSION}"
        raise ValueError(msg)


def _require_run_report_summary(
    data: Mapping[object, object],
    *,
    path: Path,
) -> None:
    summary = _require_json_field(data, "summary", path=path)
    if not isinstance(summary, Mapping):
        msg = f"Run report {path} field summary must be a JSON object"
        raise ValueError(msg)
    _require_object_keys(
        summary,
        path=path,
        display_name="summary",
        allowed=_RUN_REPORT_SUMMARY_KEYS,
    )
    _require_int_fields(
        summary,
        _REQUIRED_RUN_REPORT_SUMMARY_INT_FIELDS,
        path=path,
        prefix="summary",
    )


def _require_run_report_test(item: object, *, path: Path, index: int) -> None:
    if not isinstance(item, Mapping):
        msg = f"Run report {path} field tests[{index}] must be a JSON object"
        raise ValueError(msg)
    test = cast(Mapping[object, object], item)
    _require_string_fields(
        test,
        _REQUIRED_RUN_REPORT_TEST_STRING_FIELDS,
        path=path,
        prefix=f"tests[{index}]",
    )
    _require_int_fields(
        test,
        _REQUIRED_RUN_REPORT_TEST_INT_FIELDS,
        path=path,
        prefix=f"tests[{index}]",
    )
    rule_ids = _require_json_array(
        test,
        f"tests[{index}].rule_ids",
        path=path,
        key="rule_ids",
    )
    for rule_index, rule_id in enumerate(rule_ids):
        _require_rule_id(
            rule_id,
            path=path,
            test_index=index,
            rule_index=rule_index,
            field="rule_ids",
        )
    _require_object_keys(
        test,
        path=path,
        display_name=f"tests[{index}]",
        allowed=_RUN_REPORT_TEST_KEYS,
    )
    _require_retry(test, path=path, test_index=index)
    _require_gate_result_items(test, path=path, test_index=index)
    if "auth" in test:
        raw_auth = test["auth"]
        if not isinstance(raw_auth, Mapping):
            msg = f"Run report {path} field tests[{index}].auth must be a JSON object"
            raise ValueError(msg)
        _require_object_keys(
            raw_auth,
            path=path,
            display_name=f"tests[{index}].auth",
            allowed=_RUN_REPORT_AUTH_KEYS,
        )
        _require_auth_shape(raw_auth, path=path, test_index=index)
    raw_safety = test.get("safety")
    if isinstance(raw_safety, Mapping):
        _require_object_keys(
            raw_safety,
            path=path,
            display_name=f"tests[{index}].safety",
            allowed=_RUN_REPORT_SAFETY_KEYS,
        )
    raw_response = test.get("response")
    if isinstance(raw_response, Mapping):
        _require_object_keys(
            raw_response,
            path=path,
            display_name=f"tests[{index}].response",
            allowed=_RUN_REPORT_RESPONSE_KEYS,
        )
    raw_known_failures = test.get("known_failures")
    if isinstance(raw_known_failures, list):
        _require_known_failures(
            raw_known_failures,
            path=path,
            test_index=index,
        )


def _require_retry(test: Mapping[object, object], *, path: Path, test_index: int) -> None:
    raw_retry = test.get("retry")
    if not isinstance(raw_retry, Mapping):
        return
    _require_object_keys(
        raw_retry,
        path=path,
        display_name=f"tests[{test_index}].retry",
        allowed=_RUN_REPORT_RETRY_KEYS,
    )
    raw_attempts = raw_retry.get("attempts")
    if not isinstance(raw_attempts, list):
        return
    for attempt_index, attempt in enumerate(raw_attempts):
        if not isinstance(attempt, Mapping):
            continue
        _require_object_keys(
            attempt,
            path=path,
            display_name=f"tests[{test_index}].retry.attempts[{attempt_index}]",
            allowed=_RUN_REPORT_RETRY_ATTEMPT_KEYS,
        )


def _require_known_failures(
    raw_known_failures: list[object],
    *,
    path: Path,
    test_index: int,
) -> None:
    for failure_index, known_failure in enumerate(raw_known_failures):
        if not isinstance(known_failure, Mapping):
            continue
        _require_object_keys(
            known_failure,
            path=path,
            display_name=f"tests[{test_index}].known_failures[{failure_index}]",
            allowed=_RUN_REPORT_KNOWN_FAILURE_KEYS,
        )


def _require_auth_shape(
    raw_auth: Mapping[object, object],
    *,
    path: Path,
    test_index: int,
) -> None:
    for key in ("flow", "requires", "produces"):
        if key not in raw_auth:
            msg = f"Run report {path} field tests[{test_index}].auth must include {key}"
            raise ValueError(msg)
    flow = raw_auth.get("flow")
    if flow is not None and not isinstance(flow, str):
        msg = f"Run report {path} field tests[{test_index}].auth.flow has invalid type"
        raise ValueError(msg)
    _require_auth_string_list(
        raw_auth,
        path=path,
        test_index=test_index,
        field="requires",
    )
    _require_auth_string_list(
        raw_auth,
        path=path,
        test_index=test_index,
        field="produces",
    )


def _require_auth_string_list(
    raw_auth: Mapping[object, object],
    *,
    path: Path,
    test_index: int,
    field: str,
) -> None:
    values = raw_auth.get(field)
    if not isinstance(values, list):
        msg = (
            f"Run report {path} field tests[{test_index}].auth.{field} must "
            "be an array of strings"
        )
        raise ValueError(msg)
    for raw_name in values:
        if not isinstance(raw_name, str):
            msg = (
                f"Run report {path} field tests[{test_index}].auth.{field} must "
                "be an array of strings"
            )
            raise ValueError(msg)


def _require_gate_result_items(
    item: Mapping[object, object],
    *,
    path: Path,
    test_index: int,
) -> None:
    raw_gate_results = item.get("gate_results")
    if isinstance(raw_gate_results, list):
        for gate_index, gate_result in enumerate(raw_gate_results):
            if isinstance(gate_result, Mapping):
                _require_object_keys(
                    gate_result,
                    path=path,
                    display_name=f"tests[{test_index}].gate_results[{gate_index}]",
                    allowed=_RUN_REPORT_GATE_RESULT_KEYS,
                )
    _require_gate_results(raw_gate_results=raw_gate_results, path=path, test_index=test_index)


def _require_gate_results(*, raw_gate_results: object, path: Path, test_index: int) -> None:
    _report_gate_results._require_gate_results(
        raw_gate_results,
        path=path,
        test_index=test_index,
    )


def _require_object_keys(
    data: Mapping[object, object],
    *,
    path: Path,
    display_name: str,
    allowed: frozenset[str],
) -> None:
    for key in data:
        if key not in allowed:
            msg = f"Run report {path} field {display_name} contains unknown fields"
            raise ValueError(msg)


def _require_string_fields(
    data: Mapping[object, object],
    fields: tuple[str, ...],
    *,
    path: Path,
    prefix: str = "",
) -> None:
    for field in fields:
        display_name = field if not prefix else f"{prefix}.{field}"
        _require_json_string(data, display_name, path=path, key=field)


def _require_int_fields(
    data: Mapping[object, object],
    fields: tuple[str, ...],
    *,
    path: Path,
    prefix: str = "",
) -> None:
    for field in fields:
        display_name = field if not prefix else f"{prefix}.{field}"
        _require_json_int(data, display_name, path=path, key=field)


def _require_rule_id(
    value: object,
    *,
    path: Path,
    test_index: int,
    rule_index: int,
    field: str,
) -> None:
    if not isinstance(value, str):
        msg = (
            f"Run report {path} field tests[{test_index}].{field}[{rule_index}] "
            "must be a string"
        )
        raise ValueError(msg)
    if not value.strip() or report_fingerprint._has_control_character(value):
        msg = (
            f"Run report {path} field tests[{test_index}].{field}[{rule_index}] "
            "must be a non-empty string without control characters"
        )
        raise ValueError(msg)


def _require_json_string(
    data: Mapping[object, object],
    display_name: str,
    *,
    path: Path,
    key: str | None = None,
) -> str:
    value = _require_json_field(data, display_name, path=path, key=key)
    if not isinstance(value, str):
        msg = f"Run report {path} field {display_name} must be a string"
        raise ValueError(msg)
    return value


def _require_json_int(
    data: Mapping[object, object],
    display_name: str,
    *,
    path: Path,
    key: str | None = None,
) -> int:
    value = _require_json_field(data, display_name, path=path, key=key)
    if not _is_json_int(value):
        msg = f"Run report {path} field {display_name} must be an integer"
        raise ValueError(msg)
    return value


def _require_json_array(
    data: Mapping[object, object],
    display_name: str,
    *,
    path: Path,
    key: str | None = None,
) -> list[object]:
    value = _require_json_field(data, display_name, path=path, key=key)
    if not isinstance(value, list):
        msg = f"Run report {path} field {display_name} must be a JSON array"
        raise ValueError(msg)
    return value


def _require_json_field(
    data: Mapping[object, object],
    display_name: str,
    *,
    path: Path,
    key: str | None = None,
) -> object:
    lookup_key = display_name if key is None else key
    if lookup_key not in data:
        msg = f"Run report {path} must include required field {display_name}"
        raise ValueError(msg)
    return data[lookup_key]


def _is_json_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
