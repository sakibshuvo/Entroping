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
from entroping.bridge.openapi_to_hurl.rendering import (
    _negative_path_safety,
    _render_tags,
    _slugify_operation_id,
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
from entroping.bridge.openapi_to_hurl.security import _security_negative_files
from entroping.bridge.openapi_to_hurl.security_schemes import (
    _security_requirements,
    _security_schemes,
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
_VALIDATION_FAILURE_STATUSES = ("400", "422")
_SCHEMA_REF_PREFIX = "#/components/schemas/"
_MAX_RESPONSE_SCHEMA_REF_DEPTH = 64
_INVALID_ENUM_VALUE = "entroping_invalid_enum"


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
    schema_components = _schema_components(document)
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
                        schema_components=schema_components,
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
                request_content=_json_request_schema(operation),
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
    schema_components: Mapping[str, object],
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
    assertions = _response_assertions(
        response_content.schema if response_content else None,
        schema_components=schema_components,
    )
    if assertions:
        lines.append("[Asserts]")
        lines.extend(assertions)
    lines.append("")
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

    enum_body = _invalid_enum_body(base_body=base_body, properties=properties)
    enum_target = _invalid_enum_target(path=path, parameters=parameters)
    if enum_body is not None or enum_target is not None:
        cases.append(
            _NegativePathCase(
                category="invalid-enum-values",
                severity="medium",
                target=enum_target or _render_request_target(path, parameters),
                body=enum_body or base_body,
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


def _invalid_enum_body(
    *,
    base_body: Mapping[str, object],
    properties: Mapping[str, object],
) -> dict[str, object] | None:
    body = dict(base_body)
    changed = False
    for field_name, raw_schema in properties.items():
        field_schema = _ensure_mapping(raw_schema, f"schema for {field_name!r}")
        value = _invalid_enum_value(field_schema)
        if value is None:
            continue
        body[_validate_json_object_key(field_name, context="OpenAPI object properties")] = value
        changed = True
    if not changed:
        return None
    return body


def _invalid_enum_target(
    *,
    path: str,
    parameters: tuple[_OpenApiParameter, ...],
) -> str | None:
    path_overrides: dict[str, _ScalarParameterValue] = {}
    query_overrides: dict[str, _ScalarParameterValue] = {}
    for parameter in parameters:
        if parameter.location not in {"path", "query"}:
            continue
        if parameter.schema is None or parameter.schema.get("type") == "array":
            continue
        value = _invalid_enum_value(parameter.schema)
        if value is None:
            continue
        if parameter.location == "path":
            path_overrides[parameter.name] = value
        else:
            query_overrides[parameter.name] = value
    if not path_overrides and not query_overrides:
        return None
    return _render_request_target(
        path,
        parameters,
        path_overrides=path_overrides,
        query_overrides=query_overrides,
    )


def _invalid_enum_value(schema: Mapping[str, object]) -> str | None:
    raw_enum = schema.get("enum")
    if not isinstance(raw_enum, Sequence) or isinstance(raw_enum, str | bytes) or not raw_enum:
        return None
    candidate = _INVALID_ENUM_VALUE
    suffix = 2
    while any(value == candidate for value in raw_enum):
        candidate = f"{_INVALID_ENUM_VALUE}_{suffix}"
        suffix += 1
    return candidate


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


def _parameter_components(document: Mapping[str, object]) -> Mapping[str, object]:
    components = document.get("components")
    if components is None:
        return {}
    components_mapping = _ensure_mapping(components, "OpenAPI components")
    parameters = components_mapping.get("parameters")
    if parameters is None:
        return {}
    return _ensure_mapping(parameters, "OpenAPI components parameters")


def _schema_components(document: Mapping[str, object]) -> Mapping[str, object]:
    components = document.get("components")
    if components is None:
        return {}
    components_mapping = _ensure_mapping(components, "OpenAPI components")
    schemas = components_mapping.get("schemas")
    if schemas is None:
        return {}
    return _ensure_mapping(schemas, "OpenAPI components schemas")


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


def _resolve_response_schema_ref(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    seen_refs: tuple[str, ...] = (),
) -> Mapping[str, object]:
    resolved_schema, _ = _resolve_response_schema_ref_with_seen(
        schema,
        schema_components=schema_components,
        context=context,
        seen_refs=seen_refs,
    )
    return resolved_schema


def _resolve_response_schema_ref_with_seen(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    seen_refs: tuple[str, ...] = (),
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    if "$ref" not in schema:
        return schema, seen_refs
    if len(schema) != 1:
        msg = f"{context} response schema ref must not define sibling fields"
        raise OpenApiCompilationError(msg)
    raw_ref = schema["$ref"]
    if not isinstance(raw_ref, str):
        msg = f"{context} response schema ref must be a string"
        raise OpenApiCompilationError(msg)
    if not raw_ref.startswith("#/"):
        msg = f"{context} only local response schema refs are supported"
        raise OpenApiCompilationError(msg)
    if not raw_ref.startswith(_SCHEMA_REF_PREFIX):
        msg = f"{context} unsupported response schema ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    if len(seen_refs) >= _MAX_RESPONSE_SCHEMA_REF_DEPTH:
        msg = f"{context} response schema ref depth exceeds {_MAX_RESPONSE_SCHEMA_REF_DEPTH}"
        raise OpenApiCompilationError(msg)
    component_name = _schema_component_name(raw_ref, context=context)
    if raw_ref in seen_refs:
        msg = f"{context} cyclic response schema ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    target = schema_components.get(component_name)
    if target is None:
        msg = f"{context} unknown response schema ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    target_mapping = _ensure_mapping(
        target,
        f"{context} response schema ref target {raw_ref!r}",
    )
    return _resolve_response_schema_ref_with_seen(
        target_mapping,
        schema_components=schema_components,
        context=f"{context} ref {raw_ref!r}",
        seen_refs=(*seen_refs, raw_ref),
    )


def _schema_component_name(raw_ref: str, *, context: str) -> str:
    component_name = raw_ref.removeprefix(_SCHEMA_REF_PREFIX)
    if not component_name or "/" in component_name:
        msg = f"{context} malformed response schema ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)

    decoded: list[str] = []
    index = 0
    while index < len(component_name):
        character = component_name[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(component_name):
            msg = f"{context} malformed response schema ref {raw_ref!r}"
            raise OpenApiCompilationError(msg)
        escape = component_name[index + 1]
        if escape == "0":
            decoded.append("~")
        elif escape == "1":
            decoded.append("/")
        else:
            msg = f"{context} malformed response schema ref {raw_ref!r}"
            raise OpenApiCompilationError(msg)
        index += 2
    return "".join(decoded)


def _response_assertions(
    schema: Mapping[str, object] | None,
    *,
    schema_components: Mapping[str, object],
) -> list[str]:
    if schema is None:
        return []
    return _response_assertion_lines(
        schema,
        schema_components=schema_components,
        context="OpenAPI response schema",
    )


def _response_assertion_lines(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    field_path: tuple[str, ...] = (),
    schema_refs: tuple[str, ...] = (),
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> list[str]:
    budget = budget or _TraversalBudget()
    _check_openapi_schema_budget(depth=depth, budget=budget, context=context)
    _, schema_refs = _resolve_response_schema_ref_with_seen(
        schema,
        schema_components=schema_components,
        context=context,
        seen_refs=schema_refs,
    )
    required, properties = _response_assertion_shape(
        schema,
        schema_components=schema_components,
        context=context,
        depth=depth,
        budget=budget,
    )
    if not required:
        return []

    assertions: list[str] = []
    for field_name in required:
        next_field_path = (*field_path, field_name)
        jsonpath = _jsonpath_for_fields(next_field_path)
        assertions.append(f'jsonpath "{jsonpath}" exists')
        property_schema = properties.get(field_name, _MISSING)
        if property_schema is _MISSING:
            continue
        property_schema_mapping = _ensure_mapping(property_schema, f"schema for {field_name!r}")
        _response_property_schema_kind(
            property_schema_mapping,
            schema_components=schema_components,
            context=f"schema for {field_name!r}",
            depth=depth + 1,
            budget=budget,
        )
        enum_value = _response_property_enum_value(
            property_schema_mapping,
            schema_components=schema_components,
            context=f"schema for {field_name!r}",
            depth=depth + 1,
            budget=budget,
        )
        if enum_value is not _MISSING:
            assertions.append(f'jsonpath "{jsonpath}" == {json.dumps(enum_value)}')
        assertions.extend(
            _response_assertion_lines(
                property_schema_mapping,
                schema_components=schema_components,
                context=f"schema for {field_name!r}",
                field_path=next_field_path,
                schema_refs=schema_refs,
                depth=depth + 1,
                budget=budget,
            )
        )
    return assertions


def _response_assertion_shape(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
    composition_refs: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], dict[str, object]]:
    budget = budget or _TraversalBudget()
    _check_openapi_schema_budget(depth=depth, budget=budget, context=context)
    composition_refs = _response_schema_composition_refs(
        schema,
        context=context,
        seen_refs=composition_refs,
    )
    schema = _resolve_response_schema_ref(
        schema,
        schema_components=schema_components,
        context=context,
    )
    if "oneOf" in schema or "anyOf" in schema:
        msg = f"{context} unsupported response schema composition"
        raise OpenApiCompilationError(msg)
    if _is_explicit_non_object_response_schema(schema):
        if "required" in schema or "properties" in schema:
            msg = f"{context} non-object response schema must not define required/properties"
            raise OpenApiCompilationError(msg)
        return (), {}

    required_context = (
        "OpenAPI schema required"
        if context == "OpenAPI response schema"
        else f"{context} required"
    )
    properties_context = (
        "OpenAPI schema properties"
        if context == "OpenAPI response schema"
        else f"{context} properties"
    )
    required = list(_string_sequence(schema.get("required"), required_context))
    properties = dict(_ensure_mapping(schema.get("properties", {}), properties_context))

    raw_all_of = schema.get("allOf")
    if raw_all_of is None:
        return tuple(dict.fromkeys(required)), properties
    if not isinstance(raw_all_of, Sequence) or isinstance(raw_all_of, str | bytes):
        msg = f"{context} allOf must be an array"
        raise OpenApiCompilationError(msg)

    for index, raw_member in enumerate(raw_all_of):
        member = _ensure_mapping(raw_member, f"{context} allOf member {index}")
        member_required, member_properties = _response_assertion_shape(
            member,
            schema_components=schema_components,
            context=f"{context} allOf member {index}",
            depth=depth + 1,
            budget=budget,
            composition_refs=composition_refs,
        )
        required.extend(member_required)
        for field_name, property_schema in member_properties.items():
            properties[field_name] = _merge_response_property_schema(
                properties.get(field_name, _MISSING),
                property_schema,
                field_name=field_name,
                schema_components=schema_components,
                context=context,
                depth=depth + 1,
                budget=budget,
            )
    return tuple(dict.fromkeys(required)), properties


def _is_explicit_non_object_response_schema(schema: Mapping[str, object]) -> bool:
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        return raw_type != "object"
    if isinstance(raw_type, Sequence) and not isinstance(raw_type, str | bytes):
        string_types = {item for item in raw_type if isinstance(item, str)}
        return bool(string_types) and "object" not in string_types
    return False


def _merge_response_property_schema(
    existing: object,
    candidate: object,
    *,
    field_name: str,
    schema_components: Mapping[str, object],
    context: str,
    depth: int,
    budget: _TraversalBudget,
) -> object:
    if existing is _MISSING or existing == candidate:
        return candidate if existing is _MISSING else existing

    existing_schema = _ensure_mapping(existing, f"{context} property {field_name!r}")
    candidate_schema = _ensure_mapping(candidate, f"{context} property {field_name!r}")
    existing_enum = _response_property_enum_value(
        existing_schema,
        schema_components=schema_components,
        context=f"{context} property {field_name!r}",
        depth=depth,
        budget=budget,
    )
    candidate_enum = _response_property_enum_value(
        candidate_schema,
        schema_components=schema_components,
        context=f"{context} property {field_name!r}",
        depth=depth,
        budget=budget,
    )
    if (
        existing_enum is not _MISSING
        and candidate_enum is not _MISSING
        and existing_enum != candidate_enum
    ):
        msg = f"{context} conflicting allOf property schema for {field_name!r}"
        raise OpenApiCompilationError(msg)
    existing_kind = _response_property_schema_kind(
        existing_schema,
        schema_components=schema_components,
        context=f"{context} property {field_name!r}",
        depth=depth,
        budget=budget,
    )
    candidate_kind = _response_property_schema_kind(
        candidate_schema,
        schema_components=schema_components,
        context=f"{context} property {field_name!r}",
        depth=depth,
        budget=budget,
    )
    if _response_property_schema_kinds_conflict(existing_kind, candidate_kind):
        msg = f"{context} conflicting allOf property schema for {field_name!r}"
        raise OpenApiCompilationError(msg)
    # Keep both assertion-relevant schemas so nested required fields from
    # overlapping allOf properties merge through the normal allOf path.
    return {"allOf": [existing_schema, candidate_schema]}


def _response_property_schema_kind(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
    composition_refs: tuple[str, ...] = (),
) -> str | None:
    budget = budget or _TraversalBudget()
    _check_openapi_schema_budget(depth=depth, budget=budget, context=context)
    composition_refs = _response_schema_composition_refs(
        schema,
        context=context,
        seen_refs=composition_refs,
    )
    schema = _resolve_response_schema_ref(
        schema,
        schema_components=schema_components,
        context=context,
    )
    kinds = [_response_property_schema_direct_kind(schema)]
    raw_all_of = schema.get("allOf")
    if raw_all_of is not None:
        if not isinstance(raw_all_of, Sequence) or isinstance(raw_all_of, str | bytes):
            msg = f"{context} allOf must be an array"
            raise OpenApiCompilationError(msg)
        for index, raw_member in enumerate(raw_all_of):
            member = _ensure_mapping(raw_member, f"{context} allOf member {index}")
            kinds.append(
                _response_property_schema_kind(
                    member,
                    schema_components=schema_components,
                    context=f"{context} allOf member {index}",
                    depth=depth + 1,
                    budget=budget,
                    composition_refs=composition_refs,
                )
            )
    return _merge_response_property_schema_kinds(kinds, context=context)


def _response_property_schema_direct_kind(schema: Mapping[str, object]) -> str | None:
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        return raw_type
    if "required" in schema or "properties" in schema:
        return "object"
    enum_value = _first_enum_value(schema)
    if enum_value is _MISSING:
        return None
    return _response_schema_value_kind(enum_value)


def _response_schema_value_kind(value: object) -> str:
    return (
        "null"
        if value is None
        else "boolean"
        if isinstance(value, bool)
        else "integer"
        if isinstance(value, int)
        else "number"
        if isinstance(value, float)
        else "string"
    )


def _merge_response_property_schema_kinds(
    kinds: Sequence[str | None],
    *,
    context: str,
) -> str | None:
    concrete_kinds = {kind for kind in kinds if kind is not None}
    if not concrete_kinds:
        return None
    if concrete_kinds <= {"integer", "number"}:
        return "number" if "number" in concrete_kinds else "integer"
    if len(concrete_kinds) == 1:
        return next(iter(concrete_kinds))
    msg = f"{context} conflicting allOf property schema"
    raise OpenApiCompilationError(msg)


def _response_property_schema_kinds_conflict(
    existing_kind: str | None,
    candidate_kind: str | None,
) -> bool:
    if existing_kind is None or candidate_kind is None:
        return False
    if existing_kind == candidate_kind:
        return False
    return {existing_kind, candidate_kind} != {"integer", "number"}


def _response_property_enum_value(
    schema: Mapping[str, object],
    *,
    schema_components: Mapping[str, object],
    context: str,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> object:
    budget = budget or _TraversalBudget()
    _check_openapi_schema_budget(depth=depth, budget=budget, context=context)
    schema = _resolve_response_schema_ref(
        schema,
        schema_components=schema_components,
        context=context,
    )
    if "oneOf" in schema or "anyOf" in schema:
        msg = f"{context} unsupported response schema composition"
        raise OpenApiCompilationError(msg)

    enum_value = _first_enum_value(schema)
    raw_all_of = schema.get("allOf")
    if raw_all_of is None:
        return enum_value
    if not isinstance(raw_all_of, Sequence) or isinstance(raw_all_of, str | bytes):
        msg = f"{context} allOf must be an array"
        raise OpenApiCompilationError(msg)

    for index, raw_member in enumerate(raw_all_of):
        member = _ensure_mapping(raw_member, f"{context} allOf member {index}")
        member_enum = _response_property_enum_value(
            member,
            schema_components=schema_components,
            context=f"{context} allOf member {index}",
            depth=depth + 1,
            budget=budget,
        )
        if member_enum is _MISSING:
            continue
        if enum_value is _MISSING:
            enum_value = member_enum
        elif enum_value != member_enum:
            msg = f"{context} conflicting allOf property schema"
            raise OpenApiCompilationError(msg)
    return enum_value


def _response_schema_composition_refs(
    schema: Mapping[str, object],
    *,
    context: str,
    seen_refs: tuple[str, ...],
) -> tuple[str, ...]:
    raw_ref = schema.get("$ref")
    if raw_ref is None:
        return seen_refs
    if not isinstance(raw_ref, str):
        return seen_refs
    if raw_ref in seen_refs:
        msg = f"{context} cyclic response schema composition {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    return (*seen_refs, raw_ref)


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


def _jsonpath_for_field(field_name: str) -> str:
    return "$" + _jsonpath_field_segment(field_name)


def _jsonpath_for_fields(field_names: tuple[str, ...]) -> str:
    if len(field_names) == 1:
        return _jsonpath_for_field(field_names[0])
    return "$" + "".join(_jsonpath_field_segment(field_name) for field_name in field_names)


def _jsonpath_field_segment(field_name: str) -> str:
    if _JSONPATH_FIELD_RE.fullmatch(field_name) is not None:
        return f".{field_name}"
    if _is_safe_jsonpath_bracket_field(field_name):
        return f"['{field_name}']"
    msg = f"OpenAPI JSONPath field is not supported yet: {field_name!r}"
    raise OpenApiCompilationError(msg)


def _is_safe_jsonpath_bracket_field(field_name: str) -> bool:
    return (
        bool(field_name)
        and "'" not in field_name
        and '"' not in field_name
        and "\\" not in field_name
        and not _has_control(field_name)
        and not _has_hurl_template_delimiter(field_name)
    )


def _is_safe_openapi_path(value: str) -> bool:
    return (
        value.startswith("/")
        and not _has_control(value)
        and not any(char.isspace() for char in value)
    )
