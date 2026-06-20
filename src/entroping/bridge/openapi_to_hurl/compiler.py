"""OpenAPI-to-Hurl compiler boundary.

This module owns only OpenAPI operation/schema translation. It must not call
LLMs, invoke Hurl, write files directly, or apply merge behavior.
"""

import json
import re
from collections.abc import Mapping, Sequence

from entroping.bridge.openapi_to_hurl.models import (
    _MISSING,
    GeneratedHurlFile,
    OpenApiCompilationError,
    OpenApiHurlCompilationResult,
    OpenApiSecurityCoverageFinding,
    _JsonContentSchema,
    _NegativePathCase,
    _OpenApiParameter,
    _ParameterExampleValue,
    _ScalarParameterValue,
    _SecurityScheme,
    _TraversalBudget,
)
from entroping.bridge.openapi_to_hurl.parameters import (
    _HTTP_TOKEN_RE,
    _MAX_PARAMETER_REF_DEPTH,
    _PARAMETER_LOCATIONS,
    _PARAMETER_REF_PREFIX,
    _PATH_PARAMETER_RE,
    _SENSITIVE_VARIABLE_PARTS,
    _ensure_array_parameter_value,
    _ensure_scalar_parameter_value,
    _is_secret_like_variable_name,
    _merge_parameters,
    _operation_parameters,
    _parameter_example_value,
    _parameter_explode,
    _parameter_location,
    _parameter_name,
    _parameter_style,
    _parameter_value_token,
    _parameters_from_container,
    _parse_parameter,
    _render_parameter_headers,
    _render_query_parameter,
    _render_request_target,
    _resolve_parameter_ref,
    _scalar_to_text,
    _url_component,
    _validate_fallback_variable_names,
    _validate_path_template,
    _variable_name,
)
from entroping.bridge.openapi_to_hurl.schema import (
    _MAX_OPENAPI_GENERATED_STRING_LENGTH,
    _MAX_OPENAPI_JSON_DEPTH,
    _MAX_OPENAPI_JSON_NODES,
    _MAX_OPENAPI_SCHEMA_DEPTH,
    _MAX_OPENAPI_SCHEMA_NODES,
    _check_openapi_json_budget,
    _check_openapi_schema_budget,
    _ensure_json_value,
    _example_for_schema,
    _finite_numeric_bound,
    _first_enum_value,
    _first_example_value,
    _generated_string,
    _schema_preferred_value,
)
from entroping.bridge.openapi_to_hurl.validation import (
    _ensure_mapping,
    _ensure_string_keys,
    _has_control,
    _has_hurl_template_delimiter,
    _mapping_field,
    _string_sequence,
    _validate_json_object_key,
)

__all__ = (
    "GeneratedHurlFile",
    "OpenApiCompilationError",
    "OpenApiHurlCompilationResult",
    "OpenApiSecurityCoverageFinding",
    "compile_openapi_to_hurl",
    "compile_openapi_to_hurl_with_report",
    "_HTTP_TOKEN_RE",
    "_JsonContentSchema",
    "_MAX_OPENAPI_GENERATED_STRING_LENGTH",
    "_MAX_OPENAPI_JSON_DEPTH",
    "_MAX_OPENAPI_JSON_NODES",
    "_MAX_PARAMETER_REF_DEPTH",
    "_MAX_OPENAPI_SCHEMA_DEPTH",
    "_MAX_OPENAPI_SCHEMA_NODES",
    "_NegativePathCase",
    "_OpenApiParameter",
    "_PARAMETER_LOCATIONS",
    "_PARAMETER_REF_PREFIX",
    "_PATH_PARAMETER_RE",
    "_ParameterExampleValue",
    "_SENSITIVE_VARIABLE_PARTS",
    "_ScalarParameterValue",
    "_SecurityScheme",
    "_TraversalBudget",
    "_check_openapi_json_budget",
    "_check_openapi_schema_budget",
    "_ensure_array_parameter_value",
    "_ensure_json_value",
    "_ensure_scalar_parameter_value",
    "_ensure_string_keys",
    "_example_for_schema",
    "_first_enum_value",
    "_first_example_value",
    "_generated_string",
    "_is_secret_like_variable_name",
    "_merge_parameters",
    "_operation_parameters",
    "_parameter_example_value",
    "_parameter_explode",
    "_parameter_location",
    "_parameter_name",
    "_parameter_style",
    "_parameter_value_token",
    "_parameters_from_container",
    "_parse_parameter",
    "_render_parameter_headers",
    "_render_query_parameter",
    "_render_request_target",
    "_resolve_parameter_ref",
    "_scalar_to_text",
    "_schema_negative_files",
    "_schema_preferred_value",
    "_url_component",
    "_validate_fallback_variable_names",
    "_validate_path_template",
    "_variable_name",
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_JSONPATH_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VENDOR_JSON_MEDIA_RE = re.compile(
    r"^application/[!#$%&'*+\-.^_`|~0-9A-Za-z]+\+json$",
    re.IGNORECASE,
)
_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_VALIDATION_FAILURE_STATUSES = ("400", "422")

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
    parameter_components = _parameter_components(document)
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
                        parameter_components=parameter_components,
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
                parameter_components=parameter_components,
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
                parameter_components=parameter_components,
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
    parameter_components: Mapping[str, object],
) -> str:
    status, response_content = _select_response(operation)
    parameters = _operation_parameters(
        path_item=path_item,
        operation=operation,
        path=path,
        parameter_components=parameter_components,
    )
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        f"# entroping: operation_id={operation_id}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{_render_request_target(path, parameters)}",
    ]
    lines.extend(_render_parameter_headers(parameters))

    request_content = _json_request_schema(operation)
    if request_content is not None:
        lines.append(f"Content-Type: {request_content.media_type}")
        lines.extend(
            json.dumps(
                _example_for_schema(request_content.schema),
                indent=2,
                allow_nan=False,
            ).splitlines()
        )

    lines.append(f"HTTP {status}")
    assertions = _response_assertions(response_content.schema if response_content else None)
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
    parameter_components: Mapping[str, object],
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
                    parameter_components=parameter_components,
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
                parameter_components=parameter_components,
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
    parameter_components: Mapping[str, object],
) -> str:
    parameters = _operation_parameters(
        path_item=path_item,
        operation=operation,
        path=path,
        parameter_components=parameter_components,
    )
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

    request_content = _json_request_schema(operation)
    if request_content is not None:
        lines.append(f"Content-Type: {request_content.media_type}")
        lines.extend(
            json.dumps(
                _example_for_schema(request_content.schema),
                indent=2,
                allow_nan=False,
            ).splitlines()
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
    parameter_components: Mapping[str, object],
) -> tuple[GeneratedHurlFile, ...]:
    status = _validation_failure_status(operation)
    request_content = _json_request_schema(operation)
    if status is None or request_content is None:
        return ()

    parameters = _operation_parameters(
        path_item=path_item,
        operation=operation,
        path=path,
        parameter_components=parameter_components,
    )
    cases = _schema_negative_cases(
        schema=request_content.schema,
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
                content_type=request_content.media_type,
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
    content_type: str,
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
        f"Content-Type: {content_type}",
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
        minimum = _finite_numeric_bound(schema.get("minimum"))
        if minimum is not None:
            value = minimum - 1
            return int(value) if schema_type == "integer" else value
        maximum = _finite_numeric_bound(schema.get("maximum"))
        if maximum is not None:
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


def _select_response(operation: Mapping[str, object]) -> tuple[str, _JsonContentSchema | None]:
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


def _json_request_schema(operation: Mapping[str, object]) -> _JsonContentSchema | None:
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


def _parameter_components(document: Mapping[str, object]) -> Mapping[str, object]:
    components = document.get("components")
    if components is None:
        return {}
    components_mapping = _ensure_mapping(components, "OpenAPI components")
    parameters = components_mapping.get("parameters")
    if parameters is None:
        return {}
    return _ensure_mapping(parameters, "OpenAPI components parameters")


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


def _json_content_schema(container: Mapping[str, object]) -> _JsonContentSchema | None:
    content = container.get("content")
    if content is None:
        return None
    content_mapping = _ensure_mapping(content, "OpenAPI content")
    media_type = _select_json_media_type(content_mapping)
    if media_type is None:
        return None
    media = content_mapping[media_type]
    media_mapping = _ensure_mapping(media, f"OpenAPI {media_type} content")
    schema = media_mapping.get("schema")
    if schema is None:
        return None
    return _JsonContentSchema(
        media_type=media_type,
        schema=_ensure_mapping(schema, "OpenAPI JSON schema"),
    )


def _select_json_media_type(content: Mapping[str, object]) -> str | None:
    if "application/json" in content:
        return "application/json"
    exact_json_media_types = [
        media_type
        for media_type in content
        if isinstance(media_type, str) and media_type.lower() == "application/json"
    ]
    if exact_json_media_types:
        return sorted(exact_json_media_types, key=lambda value: (value.lower(), value))[0]
    vendor_media_types = [
        media_type
        for media_type in content
        if isinstance(media_type, str) and _VENDOR_JSON_MEDIA_RE.fullmatch(media_type) is not None
    ]
    if not vendor_media_types:
        return None
    # Deterministic fallback when exact JSON is absent; do not infer semantic
    # priority between vendor JSON types beyond stable media-type ordering.
    return sorted(vendor_media_types, key=lambda value: (value.lower(), value))[0]


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


def _validate_security_scheme_name(value: str, *, context: str) -> str:
    if _has_control(value):
        msg = f"{context} security scheme name contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = f"{context} security scheme name contains Hurl template delimiters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value



def _is_safe_openapi_path(value: str) -> bool:
    return (
        value.startswith("/")
        and not _has_control(value)
        and not any(char.isspace() for char in value)
    )
