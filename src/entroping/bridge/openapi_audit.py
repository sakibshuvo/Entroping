"""Deterministic OpenAPI coverage audit for Architect.

This module is a pure bridge: it compares OpenAPI-derived operation metadata
against discovered Hurl tests. It does not read files, invoke Hurl, call LLMs,
or write reports.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
from entroping.models.hurl import HurlExchange, HurlTest

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
OPENAPI_AUDIT_SCHEMA_VERSION = "entroping.openapi-audit.v1"


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
class OpenApiOperationCoverage:
    """How a single OpenAPI operation maps to committed Hurl tests."""

    operation_id: str
    method: str
    path: str
    status: str
    test_paths: tuple[str, ...]


@dataclass(frozen=True)
class OpenApiStaleOperationReference:
    """Committed Hurl metadata that points at an operation absent from the spec."""

    operation_id: str
    test_path: str


@dataclass(frozen=True)
class OpenApiAuditReport:
    """OpenAPI coverage audit result."""

    total_operations: int
    covered_operations: int
    missing_operations: int
    findings: tuple[OpenApiAuditFinding, ...]
    operation_matrix: tuple[OpenApiOperationCoverage, ...] = ()
    stale_references: tuple[OpenApiStaleOperationReference, ...] = ()

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
    *,
    project_root: Path | None = None,
) -> OpenApiAuditReport:
    """Report OpenAPI operations missing committed Hurl coverage."""

    expected_operations = _expected_operations(document)
    expected_by_id = {operation.operation_id: operation for operation in expected_operations}
    operation_matrix = tuple(
        _operation_coverage_row(
            operation,
            hurl_tests,
            project_root=project_root,
        )
        for operation in expected_operations
    )
    findings = tuple(
        _missing_coverage_finding(operation)
        for operation, row in zip(expected_operations, operation_matrix, strict=True)
        if row.status == "uncovered"
    )
    return OpenApiAuditReport(
        total_operations=len(expected_operations),
        covered_operations=sum(1 for row in operation_matrix if row.status != "uncovered"),
        missing_operations=len(findings),
        findings=findings,
        operation_matrix=operation_matrix,
        stale_references=_stale_operation_references(
            hurl_tests,
            expected_by_id,
            project_root=project_root,
        ),
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
    else:
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
        lines.append("")

    lines.extend(
        [
            "## Operation Coverage Matrix",
            "",
            "| Operation | Method | Path | Status | Tests |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.operation_matrix:
        tests = ", ".join(row.test_paths) if row.test_paths else "-"
        lines.append(
            "| "
            f"{_markdown_table_cell(row.operation_id)} | "
            f"{_markdown_table_cell(row.method)} | "
            f"{_markdown_table_cell(row.path)} | "
            f"{_markdown_table_cell(row.status)} | "
            f"{_markdown_table_cell(tests)} |"
        )
    if report.stale_references:
        lines.extend(
            [
                "",
                "## Stale OpenAPI References",
                "",
                "| Operation | Test |",
                "| --- | --- |",
            ]
        )
        for reference in report.stale_references:
            lines.append(
                "| "
                f"{_markdown_table_cell(reference.operation_id)} | "
                f"{_markdown_table_cell(reference.test_path)} |"
            )
    return "\n".join(lines)


def audit_report_to_dict(report: OpenApiAuditReport) -> dict[str, object]:
    """Return a deterministic JSON-serializable audit payload."""

    return {
        "schema_version": OPENAPI_AUDIT_SCHEMA_VERSION,
        "status": "pass" if report.passed else "fail",
        "summary": {
            "total_operations": report.total_operations,
            "covered_operations": report.covered_operations,
            "missing_operations": report.missing_operations,
            "ambiguous_operations": sum(
                1 for row in report.operation_matrix if row.status == "ambiguous"
            ),
            "stale_references": len(report.stale_references),
        },
        "operation_matrix": [
            {
                "operation_id": row.operation_id,
                "method": row.method,
                "path": row.path,
                "status": row.status,
                "tests": list(row.test_paths),
            }
            for row in report.operation_matrix
        ],
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
        "stale_references": [
            {
                "operation_id": reference.operation_id,
                "test_path": reference.test_path,
            }
            for reference in report.stale_references
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


def _operation_coverage_row(
    operation: _ExpectedOperation,
    hurl_tests: Sequence[HurlTest],
    *,
    project_root: Path | None,
) -> OpenApiOperationCoverage:
    matching_paths = tuple(
        sorted(
            {
                _hurl_test_path(hurl_test, project_root=project_root)
                for hurl_test in hurl_tests
                if _hurl_test_covers_operation(hurl_test, operation)
            }
        )
    )
    if not matching_paths:
        status = "uncovered"
    elif len(matching_paths) == 1:
        status = "covered"
    else:
        status = "ambiguous"
    return OpenApiOperationCoverage(
        operation_id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        status=status,
        test_paths=matching_paths,
    )


def _stale_operation_references(
    hurl_tests: Sequence[HurlTest],
    expected_by_id: Mapping[str, _ExpectedOperation],
    *,
    project_root: Path | None,
) -> tuple[OpenApiStaleOperationReference, ...]:
    references: list[OpenApiStaleOperationReference] = []
    for hurl_test in hurl_tests:
        if hurl_test.metadata.meta.get("source") != "openapi":
            continue
        operation_id = hurl_test.metadata.meta.get("operation_id")
        if operation_id is None:
            continue
        if operation_id not in expected_by_id:
            references.append(
                OpenApiStaleOperationReference(
                    operation_id=operation_id,
                    test_path=_hurl_test_path(hurl_test, project_root=project_root),
                )
            )
    return tuple(
        sorted(references, key=lambda reference: (reference.operation_id, reference.test_path))
    )


def _hurl_test_covers_operation(hurl_test: HurlTest, expected: _ExpectedOperation) -> bool:
    if hurl_test.metadata.meta.get("source") != "openapi":
        return False
    if not hurl_test.exchanges:
        return False
    operation_id = hurl_test.metadata.meta.get("operation_id")
    if operation_id != expected.operation_id:
        return False
    return any(_exchange_covers_operation(exchange, expected) for exchange in hurl_test.exchanges)


def _hurl_test_path(hurl_test: HurlTest, *, project_root: Path | None) -> str:
    path = hurl_test.path
    if not path.is_absolute():
        return path.as_posix()
    if project_root is not None:
        root = project_root.expanduser().resolve()
        resolved = path.expanduser().resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            return path.name
    return path.as_posix()


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
