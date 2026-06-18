"""Pure traffic-route audit against OpenAPI operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
from entroping.bridge.traffic_to_graph import TrafficDependencyGraph, TrafficDependencyRoute

TRAFFIC_OPENAPI_AUDIT_SCHEMA_VERSION = "entroping.traffic-openapi-audit.v1"
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


class TrafficOpenApiAuditError(ValueError):
    """Raised when captured route summaries are unsafe to audit."""


@dataclass(frozen=True, slots=True)
class TrafficDocumentedRoute:
    """Observed route that matches one or more OpenAPI operations."""

    method: str
    path_template: str
    call_count: int
    failure_count: int
    operation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrafficAmbiguousRoute:
    """Observed route that matches multiple OpenAPI operations."""

    method: str
    path_template: str
    call_count: int
    failure_count: int
    operation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrafficUndocumentedRoute:
    """Observed route that is absent from the OpenAPI contract."""

    method: str
    path_template: str
    call_count: int
    failure_count: int


@dataclass(frozen=True, slots=True)
class TrafficSpecOnlyRoute:
    """OpenAPI operation that was not observed in captured traffic."""

    method: str
    path_template: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class TrafficOpenApiAuditReport:
    """Conservative comparison of redacted traffic routes against OpenAPI."""

    documented: tuple[TrafficDocumentedRoute, ...]
    undocumented: tuple[TrafficUndocumentedRoute, ...]
    spec_only: tuple[TrafficSpecOnlyRoute, ...]
    ambiguous: tuple[TrafficAmbiguousRoute, ...] = ()

    @property
    def passed(self) -> bool:
        """Return true when no observed traffic route is undocumented."""

        return not self.undocumented


@dataclass(frozen=True, slots=True)
class _SpecOperation:
    method: str
    path_template: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class _ObservedRoute:
    method: str
    path_template: str
    call_count: int
    failure_count: int


def audit_traffic_routes_against_openapi(
    document: Mapping[str, object],
    graph: TrafficDependencyGraph,
) -> TrafficOpenApiAuditReport:
    """Compare redacted traffic route summaries to OpenAPI operations."""

    spec_operations = _spec_operations(document)
    observed_routes = tuple(_observed_route(route) for route in graph.routes)
    documented: list[TrafficDocumentedRoute] = []
    ambiguous: list[TrafficAmbiguousRoute] = []
    undocumented: list[TrafficUndocumentedRoute] = []
    observed_operation_ids: set[str] = set()

    for route in observed_routes:
        matches = tuple(
            operation
            for operation in spec_operations
            if _route_matches_operation(route, operation)
        )
        if not matches:
            undocumented.append(
                TrafficUndocumentedRoute(
                    method=route.method,
                    path_template=route.path_template,
                    call_count=route.call_count,
                    failure_count=route.failure_count,
                )
            )
            continue
        operation_ids = tuple(operation.operation_id for operation in matches)
        if len(matches) > 1:
            ambiguous.append(
                TrafficAmbiguousRoute(
                    method=route.method,
                    path_template=route.path_template,
                    call_count=route.call_count,
                    failure_count=route.failure_count,
                    operation_ids=operation_ids,
                )
            )
            continue
        observed_operation_ids.update(operation_ids)
        documented.append(
            TrafficDocumentedRoute(
                method=route.method,
                path_template=route.path_template,
                call_count=route.call_count,
                failure_count=route.failure_count,
                operation_ids=operation_ids,
            )
        )

    spec_only = tuple(
        TrafficSpecOnlyRoute(
            method=operation.method,
            path_template=operation.path_template,
            operation_id=operation.operation_id,
        )
        for operation in spec_operations
        if operation.operation_id not in observed_operation_ids
    )
    return TrafficOpenApiAuditReport(
        documented=tuple(documented),
        undocumented=tuple(undocumented),
        spec_only=spec_only,
        ambiguous=tuple(ambiguous),
    )


def traffic_openapi_report_to_dict(report: TrafficOpenApiAuditReport) -> dict[str, object]:
    """Return a deterministic JSON-serializable traffic audit payload."""

    return {
        "schema_version": TRAFFIC_OPENAPI_AUDIT_SCHEMA_VERSION,
        "status": "pass" if report.passed else "fail",
        "summary": {
            "documented_routes": len(report.documented),
            "undocumented_routes": len(report.undocumented),
            "ambiguous_routes": len(report.ambiguous),
            "spec_only_routes": len(report.spec_only),
        },
        "documented_routes": [
            {
                "method": route.method,
                "path_template": route.path_template,
                "call_count": route.call_count,
                "failure_count": route.failure_count,
                "operation_ids": list(route.operation_ids),
            }
            for route in report.documented
        ],
        "ambiguous_routes": [
            {
                "method": route.method,
                "path_template": route.path_template,
                "call_count": route.call_count,
                "failure_count": route.failure_count,
                "operation_ids": list(route.operation_ids),
            }
            for route in report.ambiguous
        ],
        "undocumented_routes": [
            {
                "method": route.method,
                "path_template": route.path_template,
                "call_count": route.call_count,
                "failure_count": route.failure_count,
            }
            for route in report.undocumented
        ],
        "spec_only_routes": [
            {
                "method": route.method,
                "path_template": route.path_template,
                "operation_id": route.operation_id,
            }
            for route in report.spec_only
        ],
    }


def render_traffic_openapi_markdown(report: TrafficOpenApiAuditReport) -> str:
    """Render a compact Markdown route-audit section."""

    lines = [
        "## Traffic vs OpenAPI Routes",
        "",
        (
            f"Documented {len(report.documented)} observed routes; "
            f"ambiguous {len(report.ambiguous)} observed routes; "
            f"undocumented {len(report.undocumented)} observed routes; "
            f"spec-only {len(report.spec_only)} operations."
        ),
    ]
    if report.documented:
        lines.extend(
            [
                "",
                "### Documented Observed Routes",
                "",
                "| Method | Path | Operations | Calls | Failures |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for documented_route in report.documented:
            lines.append(
                "| "
                f"{_markdown_cell(documented_route.method)} | "
                f"{_markdown_cell(documented_route.path_template)} | "
                f"{_markdown_cell(', '.join(documented_route.operation_ids))} | "
                f"{documented_route.call_count} | "
                f"{documented_route.failure_count} |"
            )
    if report.ambiguous:
        lines.extend(
            [
                "",
                "### Ambiguous Observed Routes",
                "",
                "| Method | Path | Candidate Operations | Calls | Failures |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for ambiguous_route in report.ambiguous:
            lines.append(
                "| "
                f"{_markdown_cell(ambiguous_route.method)} | "
                f"{_markdown_cell(ambiguous_route.path_template)} | "
                f"{_markdown_cell(', '.join(ambiguous_route.operation_ids))} | "
                f"{ambiguous_route.call_count} | "
                f"{ambiguous_route.failure_count} |"
            )
    if report.undocumented:
        lines.extend(
            [
                "",
                "### Undocumented Observed Routes",
                "",
                "| Route | Calls | Failures |",
                "| --- | ---: | ---: |",
            ]
        )
        for undocumented_route in report.undocumented:
            route_label = (
                f"{undocumented_route.method} {undocumented_route.path_template}"
            )
            lines.append(
                "| "
                f"{_markdown_cell(route_label)} | "
                f"{undocumented_route.call_count} | "
                f"{undocumented_route.failure_count} |"
            )
    if report.spec_only:
        lines.extend(
            [
                "",
                "### Spec-Only Routes",
                "",
                "| Operation | Method | Path |",
                "| --- | --- | --- |",
            ]
        )
        for spec_only_route in report.spec_only:
            lines.append(
                "| "
                f"{_markdown_cell(spec_only_route.operation_id)} | "
                f"{_markdown_cell(spec_only_route.method)} | "
                f"{_markdown_cell(spec_only_route.path_template)} |"
            )
    return "\n".join(lines)


def _spec_operations(document: Mapping[str, object]) -> tuple[_SpecOperation, ...]:
    expected: list[_SpecOperation] = []
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
                msg = (
                    "OpenAPI operationId must be unique for traffic route audit: "
                    f"{operation_id!r}"
                )
                raise OpenApiCompilationError(msg)
            seen_operation_ids.add(operation_id)
            expected.append(
                _SpecOperation(
                    method=method.upper(),
                    path_template=raw_path,
                    operation_id=operation_id,
                )
            )
    if not expected:
        msg = "OpenAPI document does not contain supported HTTP operations"
        raise OpenApiCompilationError(msg)
    return tuple(expected)


def _observed_route(route: TrafficDependencyRoute) -> _ObservedRoute:
    method = _safe_method(route.method)
    path_template = _safe_path_template(route.path_template)
    if route.call_count < 0 or route.failure_count < 0:
        msg = "traffic route counts must be non-negative"
        raise TrafficOpenApiAuditError(msg)
    return _ObservedRoute(
        method=method,
        path_template=path_template,
        call_count=route.call_count,
        failure_count=route.failure_count,
    )


def _safe_method(method: str) -> str:
    normalized = method.strip().upper()
    if (
        not normalized
        or normalized.lower() not in _HTTP_METHODS
        or _has_control(normalized)
        or any(character.isspace() for character in normalized)
    ):
        msg = "traffic route method is unsafe"
        raise TrafficOpenApiAuditError(msg)
    return normalized


def _safe_path_template(path_template: str) -> str:
    path = path_template.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if not path:
        path = "/"
    if not path.startswith("/") or _has_control(path):
        msg = "traffic route path template is unsafe"
        raise TrafficOpenApiAuditError(msg)
    return path


def _route_matches_operation(route: _ObservedRoute, operation: _SpecOperation) -> bool:
    return route.method == operation.method and _path_templates_match(
        operation.path_template,
        route.path_template,
    )


def _path_templates_match(spec_template: str, observed_template: str) -> bool:
    spec_segments = _path_segments(spec_template)
    observed_segments = _path_segments(observed_template)
    if len(spec_segments) != len(observed_segments):
        return False
    return all(
        spec == observed or _is_template_segment(spec) or _is_template_segment(observed)
        for spec, observed in zip(spec_segments, observed_segments, strict=True)
    )


def _path_segments(path_template: str) -> tuple[str, ...]:
    return tuple(path_template.strip("/").split("/")) if path_template != "/" else ("",)


def _is_template_segment(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and len(segment) > 2


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


def _operation_id(operation: Mapping[str, object], *, method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        stripped = operation_id.strip()
        if _has_control(stripped):
            msg = f"OpenAPI operationId is not safe for traffic route audit: {operation_id!r}"
            raise OpenApiCompilationError(msg)
        return stripped
    path_slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method}_{path_slug or 'root'}"


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _markdown_cell(value: str) -> str:
    escaped = escape(value, quote=True)
    return escaped.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
