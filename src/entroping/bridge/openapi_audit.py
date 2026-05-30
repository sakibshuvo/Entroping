"""Deterministic OpenAPI coverage audit for Architect.

This module is a pure bridge: it compares OpenAPI-derived operation metadata
against discovered Hurl tests. It does not read files, invoke Hurl, call LLMs,
or write reports.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
from entroping.models.hurl import HurlExchange, HurlTest

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


@dataclass(frozen=True)
class OpenApiAuditFinding:
    """One deterministic Architect audit finding."""

    code: str
    severity: str
    operation_id: str
    method: str
    path: str
    message: str


@dataclass(frozen=True)
class OpenApiAuditReport:
    """OpenAPI coverage audit result."""

    total_operations: int
    covered_operations: int
    missing_operations: int
    findings: tuple[OpenApiAuditFinding, ...]

    @property
    def passed(self) -> bool:
        """Return true when the audit found no coverage gaps."""

        return not self.findings


@dataclass(frozen=True)
class _ExpectedOperation:
    operation_id: str
    method: str
    path: str


def audit_openapi_coverage(
    document: Mapping[str, object],
    hurl_tests: Sequence[HurlTest],
) -> OpenApiAuditReport:
    """Report OpenAPI operations missing committed Hurl coverage."""

    expected_operations = _expected_operations(document)
    expected_by_id = {operation.operation_id: operation for operation in expected_operations}
    covered_operation_ids = _covered_openapi_operation_ids(hurl_tests, expected_by_id)
    findings = tuple(
        _missing_coverage_finding(operation)
        for operation in expected_operations
        if operation.operation_id not in covered_operation_ids
    )
    return OpenApiAuditReport(
        total_operations=len(expected_operations),
        covered_operations=len(expected_operations) - len(findings),
        missing_operations=len(findings),
        findings=findings,
    )


def render_audit_markdown(report: OpenApiAuditReport) -> str:
    """Render a compact Markdown audit report for humans."""

    lines = [
        "# Architect Audit",
        "",
        "## OpenAPI Coverage",
        "",
        (
            f"Covered {report.covered_operations}/{report.total_operations} "
            "OpenAPI operations with committed Hurl tests."
        ),
        "",
    ]
    if report.passed:
        lines.append("No OpenAPI coverage gaps found.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Severity | Code | Operation | Method | Path |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for finding in report.findings:
        lines.append(
            "| "
            f"{_markdown_table_cell(finding.severity)} | "
            f"{_markdown_table_cell(finding.code)} | "
            f"{_markdown_table_cell(finding.operation_id)} | "
            f"{_markdown_table_cell(finding.method)} | "
            f"{_markdown_table_cell(finding.path)} |"
        )
    return "\n".join(lines)


def audit_report_to_dict(report: OpenApiAuditReport) -> dict[str, object]:
    """Return a deterministic JSON-serializable audit payload."""

    return {
        "status": "pass" if report.passed else "fail",
        "summary": {
            "total_operations": report.total_operations,
            "covered_operations": report.covered_operations,
            "missing_operations": report.missing_operations,
        },
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "operation_id": finding.operation_id,
                "method": finding.method,
                "path": finding.path,
                "message": finding.message,
            }
            for finding in report.findings
        ],
    }


def _expected_operations(document: Mapping[str, object]) -> tuple[_ExpectedOperation, ...]:
    expected: list[_ExpectedOperation] = []
    seen_operation_ids: set[str] = set()
    paths = _mapping_field(document, "paths", "OpenAPI document must contain a paths mapping")
    for raw_path, path_item_value in paths.items():
        if not isinstance(raw_path, str) or not raw_path.startswith("/") or _has_control(raw_path):
            msg = f"OpenAPI path keys must be absolute path strings, got {raw_path!r}"
            raise OpenApiCompilationError(msg)
        path_item = _ensure_mapping(path_item_value, f"OpenAPI path {raw_path!r}")
        for raw_method, operation_value in path_item.items():
            method = raw_method.lower() if isinstance(raw_method, str) else ""
            if method not in _HTTP_METHODS:
                continue
            operation = _ensure_mapping(
                operation_value,
                f"OpenAPI operation {raw_method!r} {raw_path}",
            )
            operation_id = _operation_id(operation, method=method, path=raw_path)
            if operation_id in seen_operation_ids:
                msg = f"OpenAPI operationId must be unique for audit coverage: {operation_id!r}"
                raise OpenApiCompilationError(msg)
            seen_operation_ids.add(operation_id)
            expected.append(
                _ExpectedOperation(
                    operation_id=operation_id,
                    method=method.upper(),
                    path=raw_path,
                )
            )
    if not expected:
        msg = "OpenAPI document does not contain supported HTTP operations"
        raise OpenApiCompilationError(msg)
    return tuple(expected)


def _covered_openapi_operation_ids(
    hurl_tests: Sequence[HurlTest],
    expected_by_id: Mapping[str, _ExpectedOperation],
) -> frozenset[str]:
    covered: set[str] = set()
    for hurl_test in hurl_tests:
        if hurl_test.metadata.meta.get("source") != "openapi":
            continue
        if not hurl_test.exchanges:
            continue
        operation_id = hurl_test.metadata.meta.get("operation_id")
        if operation_id is None:
            continue
        expected = expected_by_id.get(operation_id)
        if expected is None:
            continue
        if any(_exchange_covers_operation(exchange, expected) for exchange in hurl_test.exchanges):
            covered.add(operation_id)
    return frozenset(covered)


def _exchange_covers_operation(exchange: HurlExchange, expected: _ExpectedOperation) -> bool:
    return (
        exchange.method.upper() == expected.method
        and _path_matches_openapi_template(expected.path, exchange.path)
    )


def _path_matches_openapi_template(template: str, actual: str) -> bool:
    pattern = "^" + re.sub(r"\\\{[^{}]+\\\}", r"[^/]+", re.escape(template)) + "$"
    return re.fullmatch(pattern, actual) is not None


def _missing_coverage_finding(operation: _ExpectedOperation) -> OpenApiAuditFinding:
    return OpenApiAuditFinding(
        code="OPENAPI_COVERAGE_MISSING",
        severity="error",
        operation_id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        message=f"OpenAPI operation {operation.operation_id!r} has no committed Hurl coverage.",
    )


def _operation_id(operation: Mapping[str, object], *, method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        stripped = operation_id.strip()
        if _has_control(stripped):
            msg = f"OpenAPI operationId is not safe for audit output: {operation_id!r}"
            raise OpenApiCompilationError(msg)
        return stripped
    path_slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method}_{path_slug or 'root'}"


def _mapping_field(
    mapping: Mapping[str, object],
    key: str,
    error: str,
) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise OpenApiCompilationError(error)
    return _ensure_string_keys(value, context=key)


def _ensure_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{context} must be a mapping"
        raise OpenApiCompilationError(msg)
    return _ensure_string_keys(value, context=context)


def _ensure_string_keys(value: Mapping[object, object], *, context: str) -> Mapping[str, object]:
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            msg = f"{context} keys must be strings"
            raise OpenApiCompilationError(msg)
        normalized[key] = item
    return normalized


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _markdown_table_cell(value: str) -> str:
    escaped = escape(value, quote=True)
    return escaped.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
