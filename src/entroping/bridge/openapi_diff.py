"""Pure OpenAPI operation-change detection.

This module compares OpenAPI operation metadata only. It does not read files,
call Git, invoke Hurl, call providers, or write generated tests.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Literal

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
OpenApiOperationChangeType = Literal["added", "modified", "renamed", "removed"]
OpenApiBreakingDiffSeverity = Literal["info", "warning", "error"]
OPENAPI_BREAKING_DIFF_SCHEMA_VERSION = "entroping.openapi-breaking-diff.v1"


@dataclass(frozen=True)
class OpenApiOperationChange:
    """One changed OpenAPI operation relative to a baseline document."""

    change_type: OpenApiOperationChangeType
    operation_id: str
    method: str
    path: str
    previous_operation_id: str | None = None


@dataclass(frozen=True)
class OpenApiOperationChanges:
    """Deterministic OpenAPI operation-change result."""

    items: tuple[OpenApiOperationChange, ...]
    unchanged: int

    @property
    def generation_operation_ids(self) -> tuple[str, ...]:
        """Return current operation IDs that should be regenerated."""

        return tuple(
            item.operation_id
            for item in self.items
            if item.change_type in {"added", "modified", "renamed"}
        )

    @property
    def summary(self) -> dict[str, int]:
        """Return human-readable change counts."""

        return {
            "added": sum(1 for item in self.items if item.change_type == "added"),
            "modified": sum(1 for item in self.items if item.change_type == "modified"),
            "renamed": sum(1 for item in self.items if item.change_type == "renamed"),
            "removed": sum(1 for item in self.items if item.change_type == "removed"),
            "unchanged": self.unchanged,
        }


@dataclass(frozen=True)
class OpenApiBreakingChangeFinding:
    """One deterministic OpenAPI evolution finding."""

    code: str
    severity: OpenApiBreakingDiffSeverity
    operation_id: str
    method: str
    path: str
    message: str
    base_operation_id: str | None = None
    base_method: str | None = None
    base_path: str | None = None
    evidence: tuple[str, ...] = ()
    test_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpenApiBreakingDiffReport:
    """Deterministic OpenAPI breaking-change audit report."""

    base_ref: str | None
    operation_changes: OpenApiOperationChanges
    findings: tuple[OpenApiBreakingChangeFinding, ...]

    @property
    def passed(self) -> bool:
        """Return true when no breaking error findings were detected."""

        return not any(finding.severity == "error" for finding in self.findings)

    @property
    def summary(self) -> dict[str, int]:
        """Return stable summary counts for OpenAPI evolution findings."""

        summary = self.operation_changes.summary
        summary["breaking_findings"] = sum(
            1 for finding in self.findings if finding.severity == "error"
        )
        summary["warnings"] = sum(
            1 for finding in self.findings if finding.severity == "warning"
        )
        summary["informational"] = sum(
            1 for finding in self.findings if finding.severity == "info"
        )
        return summary


@dataclass(frozen=True)
class _OperationSnapshot:
    operation_id: str
    method: str
    path: str
    endpoint_key: tuple[str, str]
    fingerprint: str
    path_context: Mapping[str, object]
    operation: Mapping[str, object]


@dataclass(frozen=True)
class _ResponseSchema:
    schema_type: str | None
    required: frozenset[str]
    properties: Mapping[str, str | None]


@dataclass(frozen=True)
class _RequestBodyShape:
    required: bool
    required_fields: frozenset[str]


def detect_openapi_operation_changes(
    base_document: Mapping[str, object],
    current_document: Mapping[str, object],
) -> OpenApiOperationChanges:
    """Compare OpenAPI documents and classify operation-level changes."""

    base_operations = _operation_snapshots(base_document, document_name="baseline")
    current_operations = _operation_snapshots(current_document, document_name="current")
    base_by_id = _operations_by_id(base_operations, document_name="baseline")
    current_by_id = _operations_by_id(current_operations, document_name="current")
    base_by_endpoint = {operation.endpoint_key: operation for operation in base_operations}

    changes: list[OpenApiOperationChange] = []
    unchanged = 0
    renamed_base_ids: set[str] = set()
    for current in current_operations:
        base_by_same_id = base_by_id.get(current.operation_id)
        if base_by_same_id is None:
            previous = base_by_endpoint.get(current.endpoint_key)
            if previous is not None and previous.operation_id not in current_by_id:
                renamed_base_ids.add(previous.operation_id)
                changes.append(
                    OpenApiOperationChange(
                        change_type="renamed",
                        operation_id=current.operation_id,
                        method=current.method,
                        path=current.path,
                        previous_operation_id=previous.operation_id,
                    )
                )
            else:
                changes.append(
                    OpenApiOperationChange(
                        change_type="added",
                        operation_id=current.operation_id,
                        method=current.method,
                        path=current.path,
                    )
                )
            continue
        if current.fingerprint == base_by_same_id.fingerprint:
            unchanged += 1
            continue
        changes.append(
            OpenApiOperationChange(
                change_type="modified",
                operation_id=current.operation_id,
                method=current.method,
                path=current.path,
            )
        )

    for base in base_operations:
        if base.operation_id in current_by_id or base.operation_id in renamed_base_ids:
            continue
        changes.append(
            OpenApiOperationChange(
                change_type="removed",
                operation_id=base.operation_id,
                method=base.method,
                path=base.path,
            )
        )

    return OpenApiOperationChanges(items=tuple(changes), unchanged=unchanged)


def audit_openapi_breaking_changes(
    base_document: Mapping[str, object],
    current_document: Mapping[str, object],
    *,
    base_ref: str | None = None,
) -> OpenApiBreakingDiffReport:
    """Compare two OpenAPI documents and report deterministic evolution findings."""

    operation_changes = detect_openapi_operation_changes(base_document, current_document)
    base_operations = _operation_snapshots(base_document, document_name="baseline")
    current_operations = _operation_snapshots(current_document, document_name="current")
    base_by_id = _operations_by_id(base_operations, document_name="baseline")
    current_by_id = _operations_by_id(current_operations, document_name="current")
    findings: list[OpenApiBreakingChangeFinding] = []

    for change in operation_changes.items:
        if change.change_type == "added":
            findings.append(
                OpenApiBreakingChangeFinding(
                    code="OPENAPI_OPERATION_ADDED",
                    severity="info",
                    operation_id=change.operation_id,
                    method=change.method,
                    path=change.path,
                    message=(
                        f"OpenAPI operation {change.operation_id!r} was added at "
                        f"{change.method} {change.path}."
                    ),
                )
            )
            continue
        if change.change_type == "removed":
            findings.append(
                OpenApiBreakingChangeFinding(
                    code="OPENAPI_OPERATION_REMOVED",
                    severity="error",
                    operation_id=change.operation_id,
                    method=change.method,
                    path=change.path,
                    base_method=change.method,
                    base_path=change.path,
                    message=(
                        f"OpenAPI operation {change.operation_id!r} was removed from "
                        f"{change.method} {change.path}."
                    ),
                )
            )
            continue
        if change.change_type == "renamed":
            findings.append(
                OpenApiBreakingChangeFinding(
                    code="OPENAPI_OPERATION_RENAMED",
                    severity="warning",
                    operation_id=change.operation_id,
                    method=change.method,
                    path=change.path,
                    base_operation_id=change.previous_operation_id,
                    base_method=change.method,
                    base_path=change.path,
                    evidence=(
                        ()
                        if change.previous_operation_id is None
                        else (change.previous_operation_id,)
                    ),
                    message=(
                        f"OpenAPI operation at {change.method} {change.path} was renamed "
                        f"from {change.previous_operation_id!r} to {change.operation_id!r}."
                    ),
                )
            )
            continue

        base = base_by_id[change.operation_id]
        current = current_by_id[change.operation_id]
        before_count = len(findings)
        _append_operation_detail_findings(findings, base=base, current=current)
        if len(findings) == before_count:
            findings.append(
                OpenApiBreakingChangeFinding(
                    code="OPENAPI_OPERATION_MODIFIED",
                    severity="warning",
                    operation_id=current.operation_id,
                    method=current.method,
                    path=current.path,
                    base_method=base.method,
                    base_path=base.path,
                    message=(
                        f"OpenAPI operation {current.operation_id!r} changed, but no "
                        "supported breaking-change rule matched the diff."
                    ),
                )
            )

    _append_unsupported_construct_findings(findings, current_operations)

    return OpenApiBreakingDiffReport(
        base_ref=base_ref,
        operation_changes=operation_changes,
        findings=tuple(findings),
    )


def attach_openapi_breaking_diff_test_paths(
    report: OpenApiBreakingDiffReport,
    test_paths_by_operation_id: Mapping[str, Sequence[str]],
) -> OpenApiBreakingDiffReport:
    """Return a copy of a breaking diff report enriched with known Hurl test paths."""

    findings = tuple(
        OpenApiBreakingChangeFinding(
            code=finding.code,
            severity=finding.severity,
            operation_id=finding.operation_id,
            method=finding.method,
            path=finding.path,
            message=finding.message,
            base_operation_id=finding.base_operation_id,
            base_method=finding.base_method,
            base_path=finding.base_path,
            evidence=finding.evidence,
            test_paths=tuple(
                sorted(
                    {
                        str(path)
                        for path in test_paths_by_operation_id.get(finding.operation_id, ())
                    }
                )
            ),
        )
        for finding in report.findings
    )
    return OpenApiBreakingDiffReport(
        base_ref=report.base_ref,
        operation_changes=report.operation_changes,
        findings=findings,
    )


def breaking_diff_report_to_dict(report: OpenApiBreakingDiffReport) -> dict[str, object]:
    """Return a deterministic JSON-serializable OpenAPI diff audit payload."""

    return {
        "schema_version": OPENAPI_BREAKING_DIFF_SCHEMA_VERSION,
        "status": "pass" if report.passed else "fail",
        "base_ref": report.base_ref,
        "summary": report.summary,
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "operation_id": finding.operation_id,
                "method": finding.method,
                "path": finding.path,
                "message": finding.message,
                "base_operation_id": finding.base_operation_id,
                "base_method": finding.base_method,
                "base_path": finding.base_path,
                "evidence": list(finding.evidence),
                "test_paths": list(finding.test_paths),
            }
            for finding in report.findings
        ],
    }


def render_breaking_diff_markdown(report: OpenApiBreakingDiffReport) -> str:
    """Render OpenAPI breaking-change findings as compact Markdown."""

    base = report.base_ref or "baseline"
    lines = [
        "## OpenAPI Breaking-Change Diff",
        "",
        f"Compared current OpenAPI spec with { _markdown_table_cell(base) }.",
        "",
    ]
    if not report.findings:
        lines.append("No OpenAPI operation changes found.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Severity | Code | Operation | Method | Path | Evidence | Tests |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for finding in report.findings:
        evidence = ", ".join(finding.evidence) if finding.evidence else "-"
        tests = ", ".join(finding.test_paths) if finding.test_paths else "-"
        lines.append(
            "| "
            f"{_markdown_table_cell(finding.severity)} | "
            f"{_markdown_table_cell(finding.code)} | "
            f"{_markdown_table_cell(finding.operation_id)} | "
            f"{_markdown_table_cell(finding.method)} | "
            f"{_markdown_table_cell(finding.path)} | "
            f"{_markdown_table_cell(evidence)} | "
            f"{_markdown_table_cell(tests)} |"
        )
    return "\n".join(lines)


def _append_operation_detail_findings(
    findings: list[OpenApiBreakingChangeFinding],
    *,
    base: _OperationSnapshot,
    current: _OperationSnapshot,
) -> None:
    if current.method != base.method:
        findings.append(
            _operation_finding(
                code="OPENAPI_METHOD_CHANGED",
                severity="error",
                operation=current,
                base=base,
                evidence=(f"{base.method}->{current.method}",),
                message=(
                    f"OpenAPI operation {current.operation_id!r} changed method "
                    f"from {base.method} to {current.method}."
                ),
            )
        )
    if current.path != base.path:
        findings.append(
            _operation_finding(
                code="OPENAPI_PATH_CHANGED",
                severity="error",
                operation=current,
                base=base,
                evidence=(f"{base.path}->{current.path}",),
                message=(
                    f"OpenAPI operation {current.operation_id!r} changed path "
                    f"from {base.path} to {current.path}."
                ),
            )
        )

    base_statuses = _response_status_codes(base)
    current_statuses = _response_status_codes(current)
    for status in sorted(current_statuses - base_statuses):
        findings.append(
            _operation_finding(
                code="OPENAPI_RESPONSE_STATUS_ADDED",
                severity="info",
                operation=current,
                base=base,
                evidence=(status,),
                message=f"OpenAPI operation {current.operation_id!r} added response {status}.",
            )
        )
    for status in sorted(base_statuses - current_statuses):
        findings.append(
            _operation_finding(
                code="OPENAPI_RESPONSE_STATUS_REMOVED",
                severity="error",
                operation=current,
                base=base,
                evidence=(status,),
                message=f"OpenAPI operation {current.operation_id!r} removed response {status}.",
            )
        )

    base_required_parameters = _required_parameter_keys(base)
    current_required_parameters = _required_parameter_keys(current)
    for parameter in sorted(current_required_parameters - base_required_parameters):
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_PARAMETER_ADDED",
                severity="error",
                operation=current,
                base=base,
                evidence=(parameter,),
                message=(
                    f"OpenAPI operation {current.operation_id!r} added required "
                    f"parameter {parameter!r}."
                ),
            )
        )
    for parameter in sorted(base_required_parameters - current_required_parameters):
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_PARAMETER_REMOVED",
                severity="info",
                operation=current,
                base=base,
                evidence=(parameter,),
                message=(
                    f"OpenAPI operation {current.operation_id!r} removed required "
                    f"parameter {parameter!r}."
                ),
            )
        )

    base_body = _request_body_shape(base)
    current_body = _request_body_shape(current)
    if current_body.required and not base_body.required:
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_BODY_ADDED",
                severity="error",
                operation=current,
                base=base,
                message=f"OpenAPI operation {current.operation_id!r} now requires a request body.",
            )
        )
    if base_body.required and not current_body.required:
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_BODY_REMOVED",
                severity="info",
                operation=current,
                base=base,
                message=(
                    f"OpenAPI operation {current.operation_id!r} no longer requires "
                    "a request body."
                ),
            )
        )
    for field in sorted(current_body.required_fields - base_body.required_fields):
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_BODY_FIELD_ADDED",
                severity="error",
                operation=current,
                base=base,
                evidence=(field,),
                message=(
                    f"OpenAPI operation {current.operation_id!r} added required "
                    f"request body field {field!r}."
                ),
            )
        )
    for field in sorted(base_body.required_fields - current_body.required_fields):
        findings.append(
            _operation_finding(
                code="OPENAPI_REQUIRED_BODY_FIELD_REMOVED",
                severity="info",
                operation=current,
                base=base,
                evidence=(field,),
                message=(
                    f"OpenAPI operation {current.operation_id!r} removed required "
                    f"request body field {field!r}."
                ),
            )
        )

    _append_response_schema_findings(findings, base=base, current=current)


def _operation_finding(
    *,
    code: str,
    severity: OpenApiBreakingDiffSeverity,
    operation: _OperationSnapshot,
    base: _OperationSnapshot,
    message: str,
    evidence: tuple[str, ...] = (),
) -> OpenApiBreakingChangeFinding:
    return OpenApiBreakingChangeFinding(
        code=code,
        severity=severity,
        operation_id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        message=message,
        base_method=base.method,
        base_path=base.path,
        evidence=evidence,
    )


def _response_status_codes(operation: _OperationSnapshot) -> frozenset[str]:
    return frozenset(_responses(operation).keys())


def _responses(operation: _OperationSnapshot) -> Mapping[str, object]:
    value = operation.operation.get("responses")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"OpenAPI operation {operation.method} {operation.path} responses must be a mapping"
        raise OpenApiCompilationError(msg)
    return _ensure_string_keys(value, context=f"{operation.method} {operation.path} responses")


def _required_parameter_keys(operation: _OperationSnapshot) -> frozenset[str]:
    required: set[str] = set()
    for source, value in (
        ("path item", operation.path_context.get("parameters")),
        ("operation", operation.operation.get("parameters")),
    ):
        if value is None:
            continue
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            msg = (
                f"OpenAPI {source} parameters for {operation.method} "
                f"{operation.path} must be a list"
            )
            raise OpenApiCompilationError(msg)
        for index, parameter_value in enumerate(value):
            parameter = _ensure_mapping(
                parameter_value,
                f"OpenAPI {source} parameter {index} for {operation.method} {operation.path}",
            )
            if "$ref" in parameter:
                continue
            name = parameter.get("name")
            location = parameter.get("in")
            if not isinstance(name, str) or not name.strip():
                msg = (
                    f"OpenAPI parameter {index} for {operation.method} "
                    f"{operation.path} needs a name"
                )
                raise OpenApiCompilationError(msg)
            if not isinstance(location, str) or not location.strip():
                msg = (
                    f"OpenAPI parameter {name!r} for {operation.method} "
                    f"{operation.path} needs a location"
                )
                raise OpenApiCompilationError(msg)
            if parameter.get("required") is True or location == "path":
                required.add(f"{location}:{name}")
    return frozenset(required)


def _request_body_shape(operation: _OperationSnapshot) -> _RequestBodyShape:
    body_value = operation.operation.get("requestBody")
    if body_value is None:
        return _RequestBodyShape(required=False, required_fields=frozenset())
    request_context = f"{operation.method} {operation.path} requestBody"
    body = _ensure_mapping(
        body_value,
        f"OpenAPI requestBody for {operation.method} {operation.path}",
    )
    if "$ref" in body:
        return _RequestBodyShape(required=False, required_fields=frozenset())
    required = body.get("required") is True
    schema = _json_schema_from_content(body, context=request_context)
    if schema is None:
        return _RequestBodyShape(required=required, required_fields=frozenset())
    return _RequestBodyShape(
        required=required,
        required_fields=_required_fields(schema, context=request_context),
    )


def _append_response_schema_findings(
    findings: list[OpenApiBreakingChangeFinding],
    *,
    base: _OperationSnapshot,
    current: _OperationSnapshot,
) -> None:
    base_schemas = _response_schemas(base)
    current_schemas = _response_schemas(current)
    for key in sorted(base_schemas.keys() & current_schemas.keys()):
        status, media_type = key
        base_schema = base_schemas[key]
        current_schema = current_schemas[key]
        evidence_prefix = f"{status}:{media_type}"
        if base_schema.schema_type != current_schema.schema_type:
            findings.append(
                _operation_finding(
                    code="OPENAPI_RESPONSE_SCHEMA_TYPE_CHANGED",
                    severity="error",
                    operation=current,
                    base=base,
                    evidence=(f"{evidence_prefix}:schema",),
                    message=(
                        f"OpenAPI operation {current.operation_id!r} changed response "
                        f"{status} {media_type} schema type."
                    ),
                )
            )
        for field in sorted(base_schema.required - current_schema.required):
            findings.append(
                _operation_finding(
                    code="OPENAPI_RESPONSE_REQUIRED_FIELD_REMOVED",
                    severity="error",
                    operation=current,
                    base=base,
                    evidence=(f"{evidence_prefix}:{field}",),
                    message=(
                        f"OpenAPI operation {current.operation_id!r} removed required "
                        f"response field {field!r} from {status} {media_type}."
                    ),
                )
            )
        for field in sorted(base_schema.properties.keys() - current_schema.properties.keys()):
            findings.append(
                _operation_finding(
                    code="OPENAPI_RESPONSE_FIELD_REMOVED",
                    severity="error",
                    operation=current,
                    base=base,
                    evidence=(f"{evidence_prefix}:{field}",),
                    message=(
                        f"OpenAPI operation {current.operation_id!r} removed response "
                        f"field {field!r} from {status} {media_type}."
                    ),
                )
            )
        for field in sorted(base_schema.properties.keys() & current_schema.properties.keys()):
            base_type = base_schema.properties[field]
            current_type = current_schema.properties[field]
            if base_type != current_type:
                findings.append(
                    _operation_finding(
                        code="OPENAPI_RESPONSE_FIELD_TYPE_CHANGED",
                        severity="error",
                        operation=current,
                        base=base,
                        evidence=(f"{evidence_prefix}:{field}",),
                        message=(
                            f"OpenAPI operation {current.operation_id!r} changed response "
                            f"field {field!r} type from {base_type!r} to {current_type!r}."
                        ),
                    )
                )


def _response_schemas(operation: _OperationSnapshot) -> Mapping[tuple[str, str], _ResponseSchema]:
    schemas: dict[tuple[str, str], _ResponseSchema] = {}
    for status, response_value in _responses(operation).items():
        response = _ensure_mapping(
            response_value,
            f"OpenAPI response {status} for {operation.method} {operation.path}",
        )
        content = response.get("content")
        if content is None:
            continue
        content_mapping = _ensure_mapping(
            content,
            f"OpenAPI response {status} content for {operation.method} {operation.path}",
        )
        for media_type, media_value in content_mapping.items():
            if media_type != "application/json":
                continue
            media = _ensure_mapping(
                media_value,
                f"OpenAPI response {status} {media_type} for {operation.method} {operation.path}",
            )
            schema = _schema_from_value(
                media.get("schema"),
                context=f"{operation.method} {operation.path} response {status} {media_type}",
            )
            if schema is not None:
                schemas[(status, media_type)] = schema
    return schemas


def _json_schema_from_content(
    mapping: Mapping[str, object],
    *,
    context: str,
) -> Mapping[str, object] | None:
    content_value = mapping.get("content")
    if content_value is None:
        return None
    content = _ensure_mapping(content_value, f"{context} content")
    media_value = content.get("application/json")
    if media_value is None:
        return None
    media = _ensure_mapping(media_value, f"{context} application/json")
    schema_value = media.get("schema")
    if schema_value is None:
        return None
    return _ensure_mapping(schema_value, f"{context} application/json schema")


def _schema_from_value(value: object, *, context: str) -> _ResponseSchema | None:
    if value is None:
        return None
    schema = _ensure_mapping(value, f"{context} schema")
    if _schema_is_unsupported(schema):
        return None
    return _ResponseSchema(
        schema_type=_schema_type(schema, context=context),
        required=_required_fields(schema, context=context),
        properties=_property_types(schema, context=context),
    )


def _required_fields(schema: Mapping[str, object], *, context: str) -> frozenset[str]:
    value = schema.get("required")
    if value is None:
        return frozenset()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"OpenAPI {context} required must be a list"
        raise OpenApiCompilationError(msg)
    fields: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            msg = f"OpenAPI {context} required field {index} must be a string"
            raise OpenApiCompilationError(msg)
        fields.add(item)
    return frozenset(fields)


def _property_types(schema: Mapping[str, object], *, context: str) -> Mapping[str, str | None]:
    value = schema.get("properties")
    if value is None:
        return {}
    properties = _ensure_mapping(value, f"OpenAPI {context} properties")
    result: dict[str, str | None] = {}
    for name, property_value in properties.items():
        property_schema = _ensure_mapping(
            property_value,
            f"OpenAPI {context} property {name!r}",
        )
        result[name] = _schema_type(property_schema, context=f"{context} property {name}")
    return result


def _schema_type(schema: Mapping[str, object], *, context: str) -> str | None:
    value = schema.get("type")
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        types: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                msg = f"OpenAPI {context} type entry {index} must be a string"
                raise OpenApiCompilationError(msg)
            types.append(item)
        return "|".join(sorted(types))
    msg = f"OpenAPI {context} type must be a string or string list"
    raise OpenApiCompilationError(msg)


def _schema_is_unsupported(schema: Mapping[str, object]) -> bool:
    return any(keyword in schema for keyword in ("$ref", "oneOf", "anyOf", "allOf"))


def _append_unsupported_construct_findings(
    findings: list[OpenApiBreakingChangeFinding],
    operations: Sequence[_OperationSnapshot],
) -> None:
    seen: set[tuple[str, str]] = {
        (finding.code, finding.operation_id) for finding in findings
    }
    for operation in operations:
        evidence = _unsupported_response_schema_evidence(operation)
        key = ("OPENAPI_RESPONSE_SCHEMA_UNANALYZED", operation.operation_id)
        if not evidence or key in seen:
            continue
        seen.add(key)
        findings.append(
            OpenApiBreakingChangeFinding(
                code="OPENAPI_RESPONSE_SCHEMA_UNANALYZED",
                severity="warning",
                operation_id=operation.operation_id,
                method=operation.method,
                path=operation.path,
                evidence=evidence,
                message=(
                    f"OpenAPI operation {operation.operation_id!r} contains response "
                    "schema constructs that require explicit review."
                ),
            )
        )


def _unsupported_response_schema_evidence(operation: _OperationSnapshot) -> tuple[str, ...]:
    evidence: list[str] = []
    for status, response_value in _responses(operation).items():
        response = _ensure_mapping(
            response_value,
            f"OpenAPI response {status} for {operation.method} {operation.path}",
        )
        content_value = response.get("content")
        if content_value is None:
            continue
        content = _ensure_mapping(
            content_value,
            f"OpenAPI response {status} content for {operation.method} {operation.path}",
        )
        media_value = content.get("application/json")
        if media_value is None:
            continue
        media = _ensure_mapping(
            media_value,
            f"OpenAPI response {status} application/json for {operation.method} {operation.path}",
        )
        schema_value = media.get("schema")
        if schema_value is None:
            continue
        schema = _ensure_mapping(
            schema_value,
            (
                f"OpenAPI response {status} application/json schema for "
                f"{operation.method} {operation.path}"
            ),
        )
        if _schema_is_unsupported(schema):
            evidence.append(f"{status}:application/json")
    return tuple(evidence)


def _operation_snapshots(
    document: Mapping[str, object],
    *,
    document_name: str,
) -> tuple[_OperationSnapshot, ...]:
    paths = _mapping_field(
        document,
        "paths",
        f"OpenAPI {document_name} document must contain a paths mapping",
    )
    snapshots: list[_OperationSnapshot] = []
    for raw_path, path_item_value in paths.items():
        if not isinstance(raw_path, str) or not raw_path.startswith("/") or _has_control(raw_path):
            msg = f"OpenAPI path keys must be absolute path strings, got {raw_path!r}"
            raise OpenApiCompilationError(msg)
        path_item = _ensure_mapping(path_item_value, f"OpenAPI path {raw_path!r}")
        path_context = {
            key: value
            for key, value in path_item.items()
            if not (isinstance(key, str) and key.lower() in _HTTP_METHODS)
        }
        for raw_method, operation_value in path_item.items():
            method = raw_method.lower() if isinstance(raw_method, str) else ""
            if method not in _HTTP_METHODS:
                continue
            operation = _ensure_mapping(
                operation_value,
                f"OpenAPI operation {raw_method!r} {raw_path}",
            )
            operation_id = _operation_id(operation, method=method, path=raw_path)
            method_upper = method.upper()
            snapshots.append(
                _OperationSnapshot(
                    operation_id=operation_id,
                    method=method_upper,
                    path=raw_path,
                    endpoint_key=(method_upper, raw_path),
                    fingerprint=_operation_fingerprint(
                        method=method_upper,
                        path=raw_path,
                        path_context=path_context,
                        operation=operation,
                    ),
                    path_context=path_context,
                    operation=operation,
                )
            )
    return tuple(snapshots)


def _operations_by_id(
    operations: Sequence[_OperationSnapshot],
    *,
    document_name: str,
) -> dict[str, _OperationSnapshot]:
    by_id: dict[str, _OperationSnapshot] = {}
    for operation in operations:
        if operation.operation_id in by_id:
            msg = (
                f"OpenAPI operationId must be unique in {document_name} document: "
                f"{operation.operation_id!r}"
            )
            raise OpenApiCompilationError(msg)
        by_id[operation.operation_id] = operation
    return by_id


def _operation_fingerprint(
    *,
    method: str,
    path: str,
    path_context: Mapping[str, object],
    operation: Mapping[str, object],
) -> str:
    normalized_operation = {
        key: value for key, value in operation.items() if key != "operationId"
    }
    payload = {
        "method": method,
        "path": path,
        "path_context": _ensure_json_value(path_context, context=f"{method} {path} path item"),
        "operation": _ensure_json_value(normalized_operation, context=f"{method} {path} operation"),
    }
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _operation_id(operation: Mapping[str, object], *, method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        stripped = operation_id.strip()
        if _has_control(stripped):
            msg = f"OpenAPI operationId is not safe for change detection: {operation_id!r}"
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


def _ensure_json_value(value: object, *, context: str) -> object:
    if value is None or isinstance(value, str | bool | int):
        if isinstance(value, str) and _has_control(value):
            msg = f"{context} contains control characters"
            raise OpenApiCompilationError(msg)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            msg = f"{context} must be finite"
            raise OpenApiCompilationError(msg)
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_ensure_json_value(item, context=context) for item in value]
    if isinstance(value, Mapping):
        normalized = _ensure_string_keys(value, context=context)
        return {
            key: _ensure_json_value(item, context=f"{context}.{key}")
            for key, item in normalized.items()
        }
    msg = f"{context} must be JSON-compatible"
    raise OpenApiCompilationError(msg)


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _markdown_table_cell(value: str) -> str:
    escaped = escape(value, quote=True)
    return escaped.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
