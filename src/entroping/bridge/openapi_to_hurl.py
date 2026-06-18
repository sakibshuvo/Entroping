"""OpenAPI-to-Hurl compiler boundary.

This module owns only OpenAPI operation/schema translation. It must not call
LLMs, invoke Hurl, write files directly, or apply merge behavior.
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import quote

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_JSONPATH_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PATH_PARAMETER_RE = re.compile(r"\{([^{}]+)\}")
_HTTP_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PARAMETER_LOCATIONS = frozenset({"path", "query", "header", "cookie"})
_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_VALIDATION_FAILURE_STATUSES = ("400", "422")
_MAX_OPENAPI_SCHEMA_DEPTH = 64
_MAX_OPENAPI_SCHEMA_NODES = 10_000
_MAX_OPENAPI_JSON_DEPTH = 64
_MAX_OPENAPI_JSON_NODES = 10_000
_MAX_OPENAPI_GENERATED_STRING_LENGTH = 4096
_SENSITIVE_VARIABLE_PARTS = (
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "jwt",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "session",
    "token",
)

_ScalarParameterValue = str | int | float | bool
_ParameterExampleValue = _ScalarParameterValue | tuple[_ScalarParameterValue, ...]


class _MissingValue:
    """Sentinel for absent OpenAPI examples/defaults."""


_MISSING = _MissingValue()


class OpenApiCompilationError(ValueError):
    """Raised when an OpenAPI document cannot be compiled into Hurl content."""


@dataclass(frozen=True)
class GeneratedHurlFile:
    """Generated Hurl file content plus its deterministic repository path."""

    relative_path: str
    content: str


@dataclass(frozen=True)
class OpenApiSecurityCoverageFinding:
    """Security coverage gap found while compiling OpenAPI auth tests."""

    operation_id: str
    method: str
    path: str
    scheme_name: str
    reason: str


@dataclass(frozen=True)
class OpenApiHurlCompilationResult:
    """Generated Hurl files plus non-blocking OpenAPI security findings."""

    files: tuple[GeneratedHurlFile, ...]
    security_findings: tuple[OpenApiSecurityCoverageFinding, ...]


@dataclass(frozen=True)
class _OpenApiParameter:
    """Normalized OpenAPI parameter data used by the pure compiler."""

    name: str
    location: str
    variable_name: str
    example_value: _ParameterExampleValue | None
    style: str
    explode: bool


@dataclass(frozen=True)
class _SecurityScheme:
    """Supported OpenAPI security scheme rendering metadata."""

    name: str
    auth_lines: tuple[str, ...]
    query_parameter: tuple[str, str] | None = None


@dataclass(frozen=True)
class _NegativePathCase:
    """One deterministic negative-path Hurl variant for an OpenAPI operation."""

    category: str
    severity: str
    target: str
    body: object | str


@dataclass(slots=True)
class _TraversalBudget:
    """Mutable traversal budget for untrusted OpenAPI structures."""

    nodes: int = 0


def compile_openapi_to_hurl(
    document: Mapping[str, object],
    *,
    tags: frozenset[str],
    operation_ids: frozenset[str] | None = None,
) -> tuple[GeneratedHurlFile, ...]:
    """Compile supported OpenAPI operations into deterministic Hurl files."""

    return compile_openapi_to_hurl_with_report(
        document,
        tags=tags,
        operation_ids=operation_ids,
    ).files


def compile_openapi_to_hurl_with_report(
    document: Mapping[str, object],
    *,
    tags: frozenset[str],
    operation_ids: frozenset[str] | None = None,
) -> OpenApiHurlCompilationResult:
    """Compile OpenAPI operations and return non-blocking security findings."""

    paths = _mapping_field(document, "paths", "OpenAPI document must contain a paths mapping")
    security_schemes = _security_schemes(document)
    document_security = _security_requirements(
        document.get("security"),
        context="OpenAPI document security",
    )
    generated: list[GeneratedHurlFile] = []
    security_findings: list[OpenApiSecurityCoverageFinding] = []
    used_paths: set[str] = set()

    for raw_path, path_item_value in paths.items():
        if not isinstance(raw_path, str) or not _is_safe_openapi_path(raw_path):
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
            if operation_ids is not None and operation_id not in operation_ids:
                continue
            relative_path = f"tests/generated/{_slugify_operation_id(operation_id)}.hurl"
            if relative_path in used_paths:
                msg = f"OpenAPI operations compile to duplicate Hurl path: {relative_path}"
                raise OpenApiCompilationError(msg)
            used_paths.add(relative_path)

            method_name = method.upper()
            generated.append(
                GeneratedHurlFile(
                    relative_path=relative_path,
                    content=_render_operation(
                        method=method_name,
                        path=raw_path,
                        path_item=path_item,
                        operation=operation,
                        operation_id=operation_id,
                        tags=tags,
                    ),
                )
            )
            security_result = _security_negative_files(
                method=method_name,
                path=raw_path,
                path_item=path_item,
                operation=operation,
                operation_id=operation_id,
                tags=tags,
                security_schemes=security_schemes,
                document_security=document_security,
            )
            for item in security_result.files:
                if item.relative_path in used_paths:
                    msg = f"OpenAPI operations compile to duplicate Hurl path: {item.relative_path}"
                    raise OpenApiCompilationError(msg)
                used_paths.add(item.relative_path)
                generated.append(item)
            security_findings.extend(security_result.security_findings)

            for item in _schema_negative_files(
                method=method_name,
                path=raw_path,
                path_item=path_item,
                operation=operation,
                operation_id=operation_id,
                tags=tags,
            ):
                if item.relative_path in used_paths:
                    msg = f"OpenAPI operations compile to duplicate Hurl path: {item.relative_path}"
                    raise OpenApiCompilationError(msg)
                used_paths.add(item.relative_path)
                generated.append(item)

    if not generated and operation_ids is not None:
        msg = "OpenAPI document does not contain selected operations for Hurl generation"
        raise OpenApiCompilationError(msg)
    if not generated:
        msg = "OpenAPI document does not contain supported HTTP operations"
        raise OpenApiCompilationError(msg)
    return OpenApiHurlCompilationResult(
        files=tuple(generated),
        security_findings=tuple(security_findings),
    )


def _render_operation(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
) -> str:
    status, response_schema = _select_response(operation)
    parameters = _operation_parameters(path_item=path_item, operation=operation, path=path)
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        f"# entroping: operation_id={operation_id}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{_render_request_target(path, parameters)}",
    ]
    lines.extend(_render_parameter_headers(parameters))

    request_schema = _json_request_schema(operation)
    if request_schema is not None:
        lines.append("Content-Type: application/json")
        lines.extend(
            json.dumps(_example_for_schema(request_schema), indent=2, allow_nan=False).splitlines()
        )

    lines.append(f"HTTP {status}")
    assertions = _response_assertions(response_schema)
    if assertions:
        lines.append("[Asserts]")
        lines.extend(assertions)
    lines.append("")
    return "\n".join(lines)


def _security_negative_files(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
    security_schemes: Mapping[str, object],
    document_security: tuple[tuple[str, ...], ...] | None,
) -> OpenApiHurlCompilationResult:
    requirements = _operation_security_requirements(
        operation,
        document_security=document_security,
        operation_id=operation_id,
    )
    if not requirements:
        return OpenApiHurlCompilationResult(files=(), security_findings=())
    if any(not requirement for requirement in requirements):
        return OpenApiHurlCompilationResult(files=(), security_findings=())

    supported: list[_SecurityScheme] = []
    findings: list[OpenApiSecurityCoverageFinding] = []
    seen_schemes: set[str] = set()
    for scheme_name in (scheme for requirement in requirements for scheme in requirement):
        if scheme_name in seen_schemes:
            continue
        seen_schemes.add(scheme_name)
        scheme = _supported_security_scheme(
            scheme_name,
            security_schemes=security_schemes,
            operation_id=operation_id,
            method=method,
            path=path,
        )
        if isinstance(scheme, OpenApiSecurityCoverageFinding):
            findings.append(scheme)
        else:
            supported.append(scheme)

    unauthorized_status = _auth_failure_status(operation)
    if unauthorized_status is None:
        findings.extend(
            OpenApiSecurityCoverageFinding(
                operation_id=operation_id,
                method=method,
                path=path,
                scheme_name=scheme.name,
                reason="missing explicit 401 or 403 response for auth-negative test",
            )
            for scheme in supported
        )
        return OpenApiHurlCompilationResult(files=(), security_findings=tuple(findings))

    security_tags = frozenset({*tags, "auth", "invalid-auth", "negative"})
    slug = _slugify_operation_id(operation_id)
    files: list[GeneratedHurlFile] = []
    if supported:
        files.append(
            GeneratedHurlFile(
                relative_path=f"tests/generated/security/{slug}_missing_auth.hurl",
                content=_render_security_negative_operation(
                    method=method,
                    path=path,
                    path_item=path_item,
                    operation=operation,
                    operation_id=operation_id,
                    tags=security_tags,
                    status=unauthorized_status,
                    security="missing_auth",
                    scheme_name="*",
                    auth_lines=(),
                    query_parameter=None,
                ),
            )
        )
    files.extend(
        GeneratedHurlFile(
            relative_path=(
                "tests/generated/security/"
                f"{slug}_invalid_{_slugify_operation_id(scheme.name)}.hurl"
            ),
            content=_render_security_negative_operation(
                method=method,
                path=path,
                path_item=path_item,
                operation=operation,
                operation_id=operation_id,
                tags=security_tags,
                status=unauthorized_status,
                security="invalid_auth",
                scheme_name=scheme.name,
                auth_lines=scheme.auth_lines,
                query_parameter=scheme.query_parameter,
            ),
        )
        for scheme in supported
    )
    return OpenApiHurlCompilationResult(
        files=tuple(files),
        security_findings=tuple(findings),
    )


def _render_security_negative_operation(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
    status: str,
    security: str,
    scheme_name: str,
    auth_lines: tuple[str, ...],
    query_parameter: tuple[str, str] | None,
) -> str:
    parameters = _operation_parameters(path_item=path_item, operation=operation, path=path)
    target = _render_request_target(path, parameters)
    if query_parameter is not None:
        separator = "&" if "?" in target else "?"
        target = (
            f"{target}{separator}"
            f"{_url_component(query_parameter[0])}={_url_component(query_parameter[1])}"
        )
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        f"# entroping: operation_id={operation_id}",
        "# entroping: negative_category=invalid-auth",
        "# entroping: severity=high",
        f"# entroping: safety={_negative_path_safety(method)}",
        f"# entroping: security={security}",
        f"# entroping: security_scheme={scheme_name}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{target}",
    ]
    lines.extend(_render_parameter_headers(parameters))
    lines.extend(auth_lines)

    request_schema = _json_request_schema(operation)
    if request_schema is not None:
        lines.append("Content-Type: application/json")
        lines.extend(
            json.dumps(_example_for_schema(request_schema), indent=2, allow_nan=False).splitlines()
        )

    lines.extend((f"HTTP {status}", ""))
    return "\n".join(lines)


def _schema_negative_files(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
) -> tuple[GeneratedHurlFile, ...]:
    status = _validation_failure_status(operation)
    request_schema = _json_request_schema(operation)
    if status is None or request_schema is None:
        return ()

    parameters = _operation_parameters(path_item=path_item, operation=operation, path=path)
    cases = _schema_negative_cases(
        schema=request_schema,
        path=path,
        parameters=parameters,
    )
    slug = _slugify_operation_id(operation_id)
    return tuple(
        GeneratedHurlFile(
            relative_path=f"tests/generated/negative/{slug}_{case.category.replace('-', '_')}.hurl",
            content=_render_schema_negative_operation(
                method=method,
                path=path,
                operation_id=operation_id,
                tags=frozenset({*tags, "negative", case.category}),
                status=status,
                case=case,
            ),
        )
        for case in cases
    )


def _schema_negative_cases(
    *,
    schema: Mapping[str, object],
    path: str,
    parameters: tuple[_OpenApiParameter, ...],
) -> tuple[_NegativePathCase, ...]:
    cases: list[_NegativePathCase] = [
        _NegativePathCase(
            category="malformed-json",
            severity="medium",
            target=_render_request_target(path, parameters),
            body='`{"entroping_malformed":`',
        )
    ]
    if schema.get("type") != "object":
        return tuple(cases)

    properties = _ensure_mapping(schema.get("properties", {}), "OpenAPI object properties")
    required = _string_sequence(schema.get("required"), "OpenAPI object required")
    base_body = _object_example_for_negative_schema(schema)

    schema_violation = _schema_violation_body(base_body=base_body, required=required)
    if schema_violation is not None:
        cases.append(
            _NegativePathCase(
                category="schema-violations",
                severity="medium",
                target=_render_request_target(path, parameters),
                body=schema_violation,
            )
        )

    boundary_body = _boundary_violation_body(
        base_body=base_body,
        properties=properties,
    )
    if boundary_body is not None:
        cases.append(
            _NegativePathCase(
                category="boundary-values",
                severity="medium",
                target=_render_request_target(path, parameters),
                body=boundary_body,
            )
        )

    sqli_body = _sqli_like_body(
        base_body=base_body,
        properties=properties,
        required=required,
    )
    if sqli_body is not None:
        cases.append(
            _NegativePathCase(
                category="sqli-like-strings",
                severity="high",
                target=_render_request_target(path, parameters),
                body=sqli_body,
            )
        )

    idor_target = _idor_path_variant_target(path=path, parameters=parameters)
    if idor_target is not None:
        cases.append(
            _NegativePathCase(
                category="idor-path-variants",
                severity="high",
                target=idor_target,
                body=base_body,
            )
        )

    return tuple(cases)


def _render_schema_negative_operation(
    *,
    method: str,
    path: str,
    operation_id: str,
    tags: frozenset[str],
    status: str,
    case: _NegativePathCase,
) -> str:
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        "# entroping: generation=negative-path-fuzzing",
        f"# entroping: operation_id={operation_id}",
        f"# entroping: negative_category={case.category}",
        f"# entroping: severity={case.severity}",
        f"# entroping: safety={_negative_path_safety(method)}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{case.target}",
        "Content-Type: application/json",
    ]
    if isinstance(case.body, str):
        lines.append(case.body)
    else:
        lines.extend(json.dumps(case.body, indent=2, allow_nan=False).splitlines())
    lines.extend((f"HTTP {status}", ""))
    return "\n".join(lines)


def _validation_failure_status(operation: Mapping[str, object]) -> str | None:
    responses = _mapping_field(operation, "responses", "OpenAPI operation must contain responses")
    for status in _VALIDATION_FAILURE_STATUSES:
        if status in responses:
            return status
    return None


def _negative_path_safety(method: str) -> str:
    if method.upper() in _READ_ONLY_METHODS:
        return "read-only"
    return "destructive"


def _object_example_for_negative_schema(schema: Mapping[str, object]) -> dict[str, object]:
    example = _example_for_schema(schema)
    if not isinstance(example, Mapping):
        return {}
    normalized = _ensure_mapping(example, "OpenAPI object example")
    return {key: item for key, item in normalized.items()}


def _schema_violation_body(
    *,
    base_body: Mapping[str, object],
    required: tuple[str, ...],
) -> dict[str, object] | None:
    if not required:
        return None
    omitted = required[0]
    return {key: item for key, item in base_body.items() if key != omitted}


def _boundary_violation_body(
    *,
    base_body: Mapping[str, object],
    properties: Mapping[str, object],
) -> dict[str, object] | None:
    body = dict(base_body)
    changed = False
    for field_name, raw_schema in properties.items():
        field_schema = _ensure_mapping(raw_schema, f"schema for {field_name!r}")
        value = _boundary_violation_value(field_schema)
        if value is _MISSING:
            continue
        body[_validate_json_object_key(field_name, context="OpenAPI object properties")] = value
        changed = True
    if not changed:
        return None
    return body


def _boundary_violation_value(schema: Mapping[str, object]) -> object:
    schema_type = schema.get("type")
    if schema_type == "string":
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and not isinstance(min_length, bool) and min_length > 0:
            return _generated_string(
                min_length - 1,
                context="OpenAPI string boundary violation",
            )
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and not isinstance(max_length, bool) and max_length >= 0:
            return _generated_string(
                max_length + 1,
                context="OpenAPI string boundary violation",
            )
    if schema_type in {"integer", "number"}:
        minimum = schema.get("minimum")
        if isinstance(minimum, int | float) and not isinstance(minimum, bool):
            value = minimum - 1
            return int(value) if schema_type == "integer" else value
        maximum = schema.get("maximum")
        if isinstance(maximum, int | float) and not isinstance(maximum, bool):
            value = maximum + 1
            return int(value) if schema_type == "integer" else value
    return _MISSING


def _sqli_like_body(
    *,
    base_body: Mapping[str, object],
    properties: Mapping[str, object],
    required: tuple[str, ...],
) -> dict[str, object] | None:
    required_fields = set(required)
    candidates: list[str] = []
    for field_name, raw_schema in properties.items():
        field_schema = _ensure_mapping(raw_schema, f"schema for {field_name!r}")
        if field_schema.get("type") == "string":
            candidates.append(
                _validate_json_object_key(
                    field_name,
                    context="OpenAPI object properties",
                )
            )
    if not candidates:
        return None
    field_name = next(
        (candidate for candidate in candidates if candidate not in required_fields),
        candidates[0],
    )
    body = dict(base_body)
    body[field_name] = "' OR '1'='1"
    return body


def _idor_path_variant_target(
    *,
    path: str,
    parameters: tuple[_OpenApiParameter, ...],
) -> str | None:
    path_parameters = [parameter for parameter in parameters if parameter.location == "path"]
    if not path_parameters:
        return None
    overrides = {path_parameters[0].name: _idor_variant_value(path_parameters[0])}
    return _render_request_target(path, parameters, path_overrides=overrides)


def _idor_variant_value(parameter: _OpenApiParameter) -> str | int | float | bool:
    value = parameter.example_value
    if isinstance(value, bool):
        return not value
    if isinstance(value, int) and not isinstance(value, bool):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str) and value:
        prefix = value.split("-", maxsplit=1)[0]
        if prefix and prefix != value:
            return f"{prefix}-other"
        return f"{value}-other"
    return "entroping-other"


def _operation_parameters(
    *,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    path: str,
) -> tuple[_OpenApiParameter, ...]:
    path_parameters = _parameters_from_container(path_item, context=f"OpenAPI path {path!r}")
    operation_parameters = _parameters_from_container(
        operation,
        context=f"OpenAPI operation for {path!r}",
    )
    parameters = _merge_parameters(path_parameters, operation_parameters)
    _validate_path_template(path)
    _validate_fallback_variable_names(parameters, path=path)
    return parameters


def _parameters_from_container(
    container: Mapping[str, object],
    *,
    context: str,
) -> tuple[_OpenApiParameter, ...]:
    raw_parameters = container.get("parameters")
    if raw_parameters is None:
        return ()
    if not isinstance(raw_parameters, Sequence) or isinstance(raw_parameters, str | bytes):
        msg = f"{context} parameters must be a list"
        raise OpenApiCompilationError(msg)

    parsed: list[_OpenApiParameter] = []
    for index, raw_parameter in enumerate(raw_parameters):
        parameter = _ensure_mapping(raw_parameter, f"{context} parameter {index}")
        parsed.append(_parse_parameter(parameter, context=f"{context} parameter {index}"))
    return tuple(parsed)


def _parse_parameter(
    parameter: Mapping[str, object],
    *,
    context: str,
) -> _OpenApiParameter:
    name = _parameter_name(parameter.get("name"), context=context)
    location = _parameter_location(parameter.get("in"), context=context)
    if location in {"header", "cookie"} and _HTTP_TOKEN_RE.fullmatch(name) is None:
        msg = f"{context} parameter name is not safe for {location}: {name!r}"
        raise OpenApiCompilationError(msg)

    schema = parameter.get("schema")
    schema_mapping = _ensure_mapping(schema, f"{context} schema") if schema is not None else {}
    style = _parameter_style(parameter.get("style"), location=location, context=context)
    explode = _parameter_explode(parameter.get("explode"), style=style, context=context)
    value = _parameter_example_value(
        parameter,
        schema_mapping,
        location=location,
        style=style,
        context=context,
    )
    return _OpenApiParameter(
        name=name,
        location=location,
        variable_name=_variable_name(name),
        example_value=value,
        style=style,
        explode=explode,
    )


def _parameter_name(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        msg = f"{context} parameter name must be a non-empty string"
        raise OpenApiCompilationError(msg)
    if _has_control(value):
        msg = f"{context} parameter name contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value


def _parameter_location(value: object, *, context: str) -> str:
    if not isinstance(value, str) or _has_control(value):
        msg = f"{context} parameter location must be one of {sorted(_PARAMETER_LOCATIONS)}"
        raise OpenApiCompilationError(msg)
    location = value.lower()
    if location not in _PARAMETER_LOCATIONS:
        msg = f"{context} parameter location is not supported: {value!r}"
        raise OpenApiCompilationError(msg)
    return location


def _parameter_example_value(
    parameter: Mapping[str, object],
    schema: Mapping[str, object],
    *,
    location: str,
    style: str,
    context: str,
) -> _ParameterExampleValue | None:
    value = parameter.get("example", _MISSING)
    if value is _MISSING:
        value = _schema_preferred_value(schema, context=f"{context} schema")
    if value is _MISSING or value is None:
        return None
    if schema.get("type") == "array":
        return _ensure_array_parameter_value(
            value,
            location=location,
            style=style,
            context=context,
        )
    return _ensure_scalar_parameter_value(value, context=context)


def _ensure_scalar_parameter_value(
    value: object,
    *,
    context: str,
) -> _ScalarParameterValue:
    if not isinstance(value, str | int | float | bool):
        msg = f"{context} parameter example/default must be a scalar"
        raise OpenApiCompilationError(msg)
    if isinstance(value, str) and _has_control(value):
        msg = f"{context} parameter example/default contains control characters"
        raise OpenApiCompilationError(msg)
    if isinstance(value, str) and _has_hurl_template_delimiter(value):
        msg = f"{context} parameter example/default contains Hurl template delimiters"
        raise OpenApiCompilationError(msg)
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{context} parameter example/default must be finite"
        raise OpenApiCompilationError(msg)
    return value


def _ensure_array_parameter_value(
    value: object,
    *,
    location: str,
    style: str,
    context: str,
) -> tuple[_ScalarParameterValue, ...]:
    if location != "query":
        msg = (
            f"{context} array parameter examples/defaults are only supported for "
            "query parameters"
        )
        raise OpenApiCompilationError(msg)
    if style != "form":
        msg = (
            f"{context} array query parameter style {style!r} is not supported; "
            "supported style is 'form'"
        )
        raise OpenApiCompilationError(msg)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"{context} array query parameter example/default must be a list"
        raise OpenApiCompilationError(msg)
    if not value:
        msg = f"{context} array query parameter example/default must contain at least one item"
        raise OpenApiCompilationError(msg)
    return tuple(
        _ensure_scalar_parameter_value(
            item,
            context=f"{context} array item {index}",
        )
        for index, item in enumerate(value)
    )


def _parameter_style(value: object, *, location: str, context: str) -> str:
    if value is None:
        return "form" if location in {"query", "cookie"} else "simple"
    if not isinstance(value, str) or _has_control(value):
        msg = f"{context} parameter style must be a string without control characters"
        raise OpenApiCompilationError(msg)
    return value


def _parameter_explode(value: object, *, style: str, context: str) -> bool:
    if value is None:
        return style == "form"
    if not isinstance(value, bool):
        msg = f"{context} parameter explode must be a boolean"
        raise OpenApiCompilationError(msg)
    return value


def _merge_parameters(
    path_parameters: tuple[_OpenApiParameter, ...],
    operation_parameters: tuple[_OpenApiParameter, ...],
) -> tuple[_OpenApiParameter, ...]:
    merged: list[_OpenApiParameter] = []
    indexes: dict[tuple[str, str], int] = {}
    for parameter in (*path_parameters, *operation_parameters):
        key = (parameter.location, parameter.name)
        if key in indexes:
            merged[indexes[key]] = parameter
            continue
        indexes[key] = len(merged)
        merged.append(parameter)
    return tuple(merged)


def _validate_path_template(path: str) -> None:
    stripped = _PATH_PARAMETER_RE.sub("", path)
    if "{" in stripped or "}" in stripped:
        msg = f"OpenAPI path template contains malformed parameter braces: {path!r}"
        raise OpenApiCompilationError(msg)
    for raw_name in _PATH_PARAMETER_RE.findall(path):
        if _has_control(raw_name):
            msg = f"OpenAPI path parameter name contains control characters: {raw_name!r}"
            raise OpenApiCompilationError(msg)
        _variable_name(raw_name)


def _validate_fallback_variable_names(
    parameters: tuple[_OpenApiParameter, ...],
    *,
    path: str,
) -> None:
    path_parameter_names = {
        parameter.name for parameter in parameters if parameter.location == "path"
    }
    seen: dict[str, str] = {}

    def remember(variable_name: str, descriptor: str) -> None:
        if _is_secret_like_variable_name(variable_name):
            msg = (
                "OpenAPI parameter would compile to secret-like fallback variable "
                f"{variable_name!r}: {descriptor}. Provide an explicit safe example "
                "or default instead."
            )
            raise OpenApiCompilationError(msg)
        previous = seen.get(variable_name)
        if previous is not None and previous != descriptor:
            msg = (
                "OpenAPI parameters compile to duplicate fallback variable "
                f"{variable_name!r}: {previous} and {descriptor}"
            )
            raise OpenApiCompilationError(msg)
        seen[variable_name] = descriptor

    for parameter in parameters:
        if parameter.example_value is None:
            remember(
                parameter.variable_name,
                f"{parameter.location} parameter {parameter.name!r}",
            )

    for raw_name in _PATH_PARAMETER_RE.findall(path):
        if raw_name not in path_parameter_names:
            remember(_variable_name(raw_name), f"path template parameter {raw_name!r}")


def _render_request_target(
    path: str,
    parameters: tuple[_OpenApiParameter, ...],
    *,
    path_overrides: Mapping[str, _ScalarParameterValue] | None = None,
) -> str:
    path_parameters = {
        parameter.name: parameter for parameter in parameters if parameter.location == "path"
    }
    overrides = path_overrides or {}

    def replace_path_parameter(match: re.Match[str]) -> str:
        raw_name = match.group(1)
        if raw_name in overrides:
            return _url_component(overrides[raw_name])
        parameter = path_parameters.get(raw_name)
        if parameter is None:
            return f"{{{{{_variable_name(raw_name)}}}}}"
        if parameter.example_value is None:
            return f"{{{{{parameter.variable_name}}}}}"
        if isinstance(parameter.example_value, tuple):
            msg = "array parameter values can only be rendered as query parameters"
            raise OpenApiCompilationError(msg)
        return _url_component(parameter.example_value)

    rendered_path = _PATH_PARAMETER_RE.sub(replace_path_parameter, path)
    query_parts = [
        part
        for parameter in parameters
        if parameter.location == "query"
        for part in _render_query_parameter(parameter)
    ]
    if not query_parts:
        return rendered_path
    return f"{rendered_path}?{'&'.join(query_parts)}"


def _render_query_parameter(parameter: _OpenApiParameter) -> tuple[str, ...]:
    name = _url_component(parameter.name)
    value = parameter.example_value
    if isinstance(value, tuple):
        if parameter.explode:
            return tuple(f"{name}={_url_component(item)}" for item in value)
        return (f"{name}={','.join(_url_component(item) for item in value)}",)
    return (f"{name}={_parameter_value_token(parameter, url_component=True)}",)


def _render_parameter_headers(parameters: tuple[_OpenApiParameter, ...]) -> list[str]:
    headers = [
        f"{parameter.name}: {_parameter_value_token(parameter, url_component=False)}"
        for parameter in parameters
        if parameter.location == "header"
    ]
    cookie_parameters = [parameter for parameter in parameters if parameter.location == "cookie"]
    if cookie_parameters:
        cookie = "; ".join(
            f"{parameter.name}={_parameter_value_token(parameter, url_component=True)}"
            for parameter in cookie_parameters
        )
        headers.append(f"Cookie: {cookie}")
    return headers


def _parameter_value_token(parameter: _OpenApiParameter, *, url_component: bool) -> str:
    if parameter.example_value is None:
        return f"{{{{{parameter.variable_name}}}}}"
    if isinstance(parameter.example_value, tuple):
        msg = "array parameter values can only be rendered as query parameters"
        raise OpenApiCompilationError(msg)
    if url_component:
        return _url_component(parameter.example_value)
    return _scalar_to_text(parameter.example_value)


def _url_component(value: _ScalarParameterValue) -> str:
    return quote(_scalar_to_text(value), safe="-._~")


def _scalar_to_text(value: _ScalarParameterValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _variable_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    if not normalized:
        msg = f"OpenAPI parameter name cannot produce a safe variable name: {name!r}"
        raise OpenApiCompilationError(msg)
    if normalized[0].isdigit():
        normalized = f"param_{normalized}"
    return normalized


def _select_response(operation: Mapping[str, object]) -> tuple[str, Mapping[str, object] | None]:
    responses = _mapping_field(operation, "responses", "OpenAPI operation must contain responses")
    statuses = [status for status in responses if isinstance(status, str)]
    preferred = sorted(status for status in statuses if status.isdigit() and status.startswith("2"))
    if preferred:
        status = preferred[0]
    else:
        numeric = sorted(status for status in statuses if status.isdigit())
        if not numeric:
            msg = "OpenAPI operation must contain at least one numeric response status"
            raise OpenApiCompilationError(msg)
        status = numeric[0]

    response = _ensure_mapping(responses[status], f"OpenAPI response {status}")
    return status, _json_content_schema(response)


def _json_request_schema(operation: Mapping[str, object]) -> Mapping[str, object] | None:
    request_body = operation.get("requestBody")
    if request_body is None:
        return None
    return _json_content_schema(_ensure_mapping(request_body, "OpenAPI requestBody"))


def _security_schemes(document: Mapping[str, object]) -> Mapping[str, object]:
    components = document.get("components")
    if components is None:
        return {}
    components_mapping = _ensure_mapping(components, "OpenAPI components")
    security_schemes = components_mapping.get("securitySchemes")
    if security_schemes is None:
        return {}
    normalized = _ensure_mapping(security_schemes, "OpenAPI securitySchemes")
    for scheme_name in normalized:
        _validate_security_scheme_name(scheme_name, context="OpenAPI securitySchemes")
    return normalized


def _security_requirements(
    raw_security: object,
    *,
    context: str,
) -> tuple[tuple[str, ...], ...] | None:
    if raw_security is None:
        return None
    if not isinstance(raw_security, Sequence) or isinstance(raw_security, str | bytes):
        msg = f"{context} must be a list"
        raise OpenApiCompilationError(msg)
    requirements: list[tuple[str, ...]] = []
    for index, raw_requirement in enumerate(raw_security):
        requirement = _ensure_mapping(raw_requirement, f"{context} requirement {index}")
        requirements.append(
            tuple(
                _validate_security_scheme_name(
                    scheme_name,
                    context=f"{context} requirement {index}",
                )
                for scheme_name in requirement
            )
        )
    return tuple(requirements)


def _operation_security_requirements(
    operation: Mapping[str, object],
    *,
    document_security: tuple[tuple[str, ...], ...] | None,
    operation_id: str,
) -> tuple[tuple[str, ...], ...]:
    operation_security = _security_requirements(
        operation.get("security"),
        context=f"OpenAPI operation {operation_id!r} security",
    )
    if operation_security is not None:
        return operation_security
    return document_security or ()


def _supported_security_scheme(
    scheme_name: str,
    *,
    security_schemes: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    raw_scheme = security_schemes.get(scheme_name)
    if raw_scheme is None:
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="security scheme is not defined",
        )
    scheme = _ensure_mapping(raw_scheme, f"OpenAPI security scheme {scheme_name!r}")
    scheme_type = scheme.get("type")
    if scheme_type == "http":
        return _supported_http_security_scheme(
            scheme_name,
            scheme=scheme,
            operation_id=operation_id,
            method=method,
            path=path,
        )
    if scheme_type == "apiKey":
        return _supported_api_key_security_scheme(
            scheme_name,
            scheme=scheme,
            operation_id=operation_id,
            method=method,
            path=path,
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported security scheme type {scheme_type}",
    )


def _supported_http_security_scheme(
    scheme_name: str,
    *,
    scheme: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    http_scheme = scheme.get("scheme")
    if not isinstance(http_scheme, str):
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="http security scheme is missing a string scheme",
        )
    normalized = http_scheme.lower()
    if normalized == "bearer":
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=("Authorization: Bearer invalid-token",),
        )
    if normalized == "basic":
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=("Authorization: Basic ZW50cm9waW5nOmludmFsaWQ=",),
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported http security scheme {http_scheme}",
    )


def _supported_api_key_security_scheme(
    scheme_name: str,
    *,
    scheme: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    api_key_location = scheme.get("in")
    api_key_name = scheme.get("name")
    if not isinstance(api_key_location, str) or not isinstance(api_key_name, str):
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="apiKey security scheme requires string in and name fields",
        )
    if api_key_location == "header" and _HTTP_TOKEN_RE.fullmatch(api_key_name) is not None:
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(f"{api_key_name}: invalid-api-key",),
        )
    if api_key_location == "query" and not _has_control(api_key_name):
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(),
            query_parameter=(api_key_name, "invalid-api-key"),
        )
    if api_key_location == "cookie" and _HTTP_TOKEN_RE.fullmatch(api_key_name) is not None:
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(f"Cookie: {api_key_name}=invalid-session",),
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported apiKey location or name {api_key_location!r}",
    )


def _auth_failure_status(operation: Mapping[str, object]) -> str | None:
    responses = _mapping_field(operation, "responses", "OpenAPI operation must contain responses")
    if "401" in responses:
        return "401"
    if "403" in responses:
        return "403"
    return None


def _security_finding(
    *,
    operation_id: str,
    method: str,
    path: str,
    scheme_name: str,
    reason: str,
) -> OpenApiSecurityCoverageFinding:
    return OpenApiSecurityCoverageFinding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=reason,
    )


def _json_content_schema(container: Mapping[str, object]) -> Mapping[str, object] | None:
    content = container.get("content")
    if content is None:
        return None
    content_mapping = _ensure_mapping(content, "OpenAPI content")
    media = content_mapping.get("application/json")
    if media is None:
        return None
    media_mapping = _ensure_mapping(media, "OpenAPI application/json content")
    schema = media_mapping.get("schema")
    if schema is None:
        return None
    return _ensure_mapping(schema, "OpenAPI JSON schema")


def _response_assertions(schema: Mapping[str, object] | None) -> list[str]:
    if schema is None:
        return []
    required = _string_sequence(schema.get("required"), "OpenAPI schema required")
    if not required:
        return []

    properties = _ensure_mapping(schema.get("properties", {}), "OpenAPI schema properties")
    assertions: list[str] = []
    for field_name in required:
        jsonpath = _jsonpath_for_field(field_name)
        assertions.append(f'jsonpath "{jsonpath}" exists')
        property_schema = properties.get(field_name)
        if property_schema is None:
            continue
        enum_value = _first_enum_value(
            _ensure_mapping(property_schema, f"schema for {field_name!r}")
        )
        if enum_value is not None:
            assertions.append(f'jsonpath "{jsonpath}" == {json.dumps(enum_value)}')
    return assertions


def _first_enum_value(schema: Mapping[str, object]) -> str | int | float | bool | None:
    raw_enum = schema.get("enum")
    if not isinstance(raw_enum, Sequence) or isinstance(raw_enum, str):
        return None
    for value in raw_enum:
        if isinstance(value, str | int | float | bool):
            return value
    return None


def _example_for_schema(
    schema: Mapping[str, object],
    *,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> object:
    budget = budget or _TraversalBudget()
    _check_openapi_schema_budget(depth=depth, budget=budget, context="OpenAPI schema")
    preferred = _schema_preferred_value(
        schema,
        context="OpenAPI schema",
        depth=depth,
        budget=budget,
    )
    if preferred is not _MISSING:
        return preferred

    schema_type = schema.get("type")
    if schema_type == "object":
        properties = _ensure_mapping(schema.get("properties", {}), "OpenAPI object properties")
        required = _string_sequence(schema.get("required"), "OpenAPI object required")
        return {
            _validate_json_object_key(
                field_name,
                context="OpenAPI object required",
            ): _example_for_schema(
                _ensure_mapping(properties.get(field_name, {}), f"schema for {field_name!r}"),
                depth=depth + 1,
                budget=budget,
            )
            for field_name in required
        }
    if schema_type == "array":
        return []
    if schema_type in {"integer", "number"}:
        minimum = schema.get("minimum")
        if isinstance(minimum, int | float) and not isinstance(minimum, bool):
            return int(minimum) if schema_type == "integer" else minimum
        maximum = schema.get("maximum")
        if isinstance(maximum, int | float) and not isinstance(maximum, bool):
            return int(maximum) if schema_type == "integer" else maximum
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and not isinstance(min_length, bool) and min_length > 0:
            return _generated_string(min_length, context="OpenAPI string schema example")
        max_length = schema.get("maxLength")
        if (
            isinstance(max_length, int)
            and not isinstance(max_length, bool)
            and max_length >= 0
            and max_length < len("string")
        ):
            return _generated_string(max_length, context="OpenAPI string schema example")
    return "string"


def _schema_preferred_value(
    schema: Mapping[str, object],
    *,
    context: str,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> object:
    budget = budget or _TraversalBudget()
    if "example" in schema:
        return _ensure_json_value(
            schema["example"],
            context=f"{context} example",
            depth=depth,
            budget=budget,
        )

    examples_value = schema.get("examples", _MISSING)
    if examples_value is not _MISSING:
        extracted = _first_example_value(
            examples_value,
            context=f"{context} examples",
            depth=depth,
            budget=budget,
        )
        if extracted is not _MISSING:
            return extracted

    if "default" in schema:
        return _ensure_json_value(
            schema["default"],
            context=f"{context} default",
            depth=depth,
            budget=budget,
        )
    if "const" in schema:
        return _ensure_json_value(
            schema["const"],
            context=f"{context} const",
            depth=depth,
            budget=budget,
        )

    enum_value = _first_enum_value(schema)
    if enum_value is not None:
        return enum_value
    return _MISSING


def _first_example_value(
    value: object,
    *,
    context: str,
    depth: int,
    budget: _TraversalBudget,
) -> object:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            return _ensure_json_value(item, context=context, depth=depth, budget=budget)
        return _MISSING
    if isinstance(value, Mapping):
        normalized = _ensure_mapping(value, context)
        for item in normalized.values():
            example = _ensure_mapping(item, f"{context} item")
            if "value" in example:
                return _ensure_json_value(
                    example["value"],
                    context=context,
                    depth=depth,
                    budget=budget,
                )
        return _MISSING
    msg = f"{context} must be a list or mapping"
    raise OpenApiCompilationError(msg)


def _ensure_json_value(
    value: object,
    *,
    context: str,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> object:
    budget = budget or _TraversalBudget()
    _check_openapi_json_budget(depth=depth, budget=budget, context=context)
    if value is None:
        return value
    if isinstance(value, str):
        if _has_control(value):
            msg = f"{context} contains control characters"
            raise OpenApiCompilationError(msg)
        if _has_hurl_template_delimiter(value):
            msg = f"{context} contains Hurl template delimiters"
            raise OpenApiCompilationError(msg)
        return value
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{context} must be finite"
        raise OpenApiCompilationError(msg)
    if isinstance(value, int | float | bool):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [
            _ensure_json_value(item, context=context, depth=depth + 1, budget=budget)
            for item in value
        ]
    if isinstance(value, Mapping):
        normalized = _ensure_mapping(value, context)
        return {
            _validate_json_object_key(key, context=context): _ensure_json_value(
                item,
                context=f"{context}.{key}",
                depth=depth + 1,
                budget=budget,
            )
            for key, item in normalized.items()
        }
    msg = f"{context} must be JSON-compatible"
    raise OpenApiCompilationError(msg)


def _generated_string(length: int, *, context: str) -> str:
    if length > _MAX_OPENAPI_GENERATED_STRING_LENGTH:
        msg = f"{context} string length exceeds {_MAX_OPENAPI_GENERATED_STRING_LENGTH}"
        raise OpenApiCompilationError(msg)
    return "x" * length


def _check_openapi_schema_budget(
    *,
    depth: int,
    budget: _TraversalBudget,
    context: str,
) -> None:
    if depth > _MAX_OPENAPI_SCHEMA_DEPTH:
        msg = f"{context} schema depth exceeds {_MAX_OPENAPI_SCHEMA_DEPTH}"
        raise OpenApiCompilationError(msg)
    budget.nodes += 1
    if budget.nodes > _MAX_OPENAPI_SCHEMA_NODES:
        msg = f"{context} schema traversal exceeds {_MAX_OPENAPI_SCHEMA_NODES} nodes"
        raise OpenApiCompilationError(msg)


def _check_openapi_json_budget(
    *,
    depth: int,
    budget: _TraversalBudget,
    context: str,
) -> None:
    if depth > _MAX_OPENAPI_JSON_DEPTH:
        msg = f"{context} JSON depth exceeds {_MAX_OPENAPI_JSON_DEPTH}"
        raise OpenApiCompilationError(msg)
    budget.nodes += 1
    if budget.nodes > _MAX_OPENAPI_JSON_NODES:
        msg = f"{context} JSON traversal exceeds {_MAX_OPENAPI_JSON_NODES} nodes"
        raise OpenApiCompilationError(msg)


def _operation_id(operation: Mapping[str, object], *, method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        stripped = operation_id.strip()
        if _has_control(stripped):
            msg = f"OpenAPI operationId is not safe for metadata comments: {operation_id!r}"
            raise OpenApiCompilationError(msg)
        return stripped
    path_slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method}_{path_slug or 'root'}"


def _slugify_operation_id(operation_id: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", operation_id).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", snake).strip("_")
    if not slug:
        msg = f"OpenAPI operationId cannot produce a safe file name: {operation_id!r}"
        raise OpenApiCompilationError(msg)
    return slug


def _render_tags(tags: frozenset[str]) -> str:
    normalized = {"generated", *tags}
    for tag in normalized:
        if not tag.strip():
            msg = "OpenAPI generated tags must not be empty"
            raise OpenApiCompilationError(msg)
        if "\n" in tag or "\r" in tag or "," in tag:
            msg = f"OpenAPI generated tag is not safe for metadata comments: {tag!r}"
            raise OpenApiCompilationError(msg)
    return ",".join(sorted(normalized))


def _jsonpath_for_field(field_name: str) -> str:
    if _JSONPATH_FIELD_RE.fullmatch(field_name) is None:
        msg = f"OpenAPI JSONPath field is not supported yet: {field_name!r}"
        raise OpenApiCompilationError(msg)
    return f"$.{field_name}"


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value


def _validate_json_object_key(value: str, *, context: str) -> str:
    if _has_control(value):
        msg = f"{context} JSON object key contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = f"{context} JSON object key contains Hurl template delimiters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value


def _validate_security_scheme_name(value: str, *, context: str) -> str:
    if _has_control(value):
        msg = f"{context} security scheme name contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = f"{context} security scheme name contains Hurl template delimiters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value


def _is_secret_like_variable_name(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_VARIABLE_PARTS)


def _is_safe_openapi_path(value: str) -> bool:
    return (
        value.startswith("/")
        and not _has_control(value)
        and not any(char.isspace() for char in value)
    )


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


def _string_sequence(value: object, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        msg = f"{context} must be a list of strings"
        raise OpenApiCompilationError(msg)
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            msg = f"{context} must contain only non-empty strings"
            raise OpenApiCompilationError(msg)
        items.append(item)
    return tuple(items)
