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
class _OpenApiParameter:
    """Normalized OpenAPI parameter data used by the pure compiler."""

    name: str
    location: str
    variable_name: str
    example_value: str | int | float | bool | None


def compile_openapi_to_hurl(
    document: Mapping[str, object],
    *,
    tags: frozenset[str],
) -> tuple[GeneratedHurlFile, ...]:
    """Compile supported OpenAPI operations into deterministic Hurl files."""

    paths = _mapping_field(document, "paths", "OpenAPI document must contain a paths mapping")
    generated: list[GeneratedHurlFile] = []
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
            relative_path = f"tests/generated/{_slugify_operation_id(operation_id)}.hurl"
            if relative_path in used_paths:
                msg = f"OpenAPI operations compile to duplicate Hurl path: {relative_path}"
                raise OpenApiCompilationError(msg)
            used_paths.add(relative_path)

            generated.append(
                GeneratedHurlFile(
                    relative_path=relative_path,
                    content=_render_operation(
                        method=method.upper(),
                        path=raw_path,
                        path_item=path_item,
                        operation=operation,
                        operation_id=operation_id,
                        tags=tags,
                    ),
                ),
            )

    if not generated:
        msg = "OpenAPI document does not contain supported HTTP operations"
        raise OpenApiCompilationError(msg)
    return tuple(generated)


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
    value = _parameter_example_value(parameter, schema_mapping, context=context)
    return _OpenApiParameter(
        name=name,
        location=location,
        variable_name=_variable_name(name),
        example_value=value,
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
    context: str,
) -> str | int | float | bool | None:
    value = parameter.get("example", _MISSING)
    if value is _MISSING:
        value = _schema_preferred_value(schema, context=f"{context} schema")
    if value is _MISSING or value is None:
        return None
    return _ensure_scalar_parameter_value(value, context=context)


def _ensure_scalar_parameter_value(
    value: object,
    *,
    context: str,
) -> str | int | float | bool:
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
) -> str:
    path_parameters = {
        parameter.name: parameter for parameter in parameters if parameter.location == "path"
    }

    def replace_path_parameter(match: re.Match[str]) -> str:
        raw_name = match.group(1)
        parameter = path_parameters.get(raw_name)
        if parameter is None:
            return f"{{{{{_variable_name(raw_name)}}}}}"
        if parameter.example_value is None:
            return f"{{{{{parameter.variable_name}}}}}"
        return _url_component(parameter.example_value)

    rendered_path = _PATH_PARAMETER_RE.sub(replace_path_parameter, path)
    query_parts = [
        f"{_url_component(parameter.name)}={_parameter_value_token(parameter, url_component=True)}"
        for parameter in parameters
        if parameter.location == "query"
    ]
    if not query_parts:
        return rendered_path
    return f"{rendered_path}?{'&'.join(query_parts)}"


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
    if url_component:
        return _url_component(parameter.example_value)
    return _scalar_to_text(parameter.example_value)


def _url_component(value: str | int | float | bool) -> str:
    return quote(_scalar_to_text(value), safe="-._~")


def _scalar_to_text(value: str | int | float | bool) -> str:
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


def _example_for_schema(schema: Mapping[str, object]) -> object:
    preferred = _schema_preferred_value(schema, context="OpenAPI schema")
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
                _ensure_mapping(properties.get(field_name, {}), f"schema for {field_name!r}")
            )
            for field_name in required
        }
    if schema_type == "array":
        return []
    if schema_type in {"integer", "number"}:
        return 0
    if schema_type == "boolean":
        return False
    return "string"


def _schema_preferred_value(schema: Mapping[str, object], *, context: str) -> object:
    if "example" in schema:
        return _ensure_json_value(schema["example"], context=f"{context} example")

    examples_value = schema.get("examples", _MISSING)
    if examples_value is not _MISSING:
        extracted = _first_example_value(examples_value, context=f"{context} examples")
        if extracted is not _MISSING:
            return extracted

    if "default" in schema:
        return _ensure_json_value(schema["default"], context=f"{context} default")
    if "const" in schema:
        return _ensure_json_value(schema["const"], context=f"{context} const")

    enum_value = _first_enum_value(schema)
    if enum_value is not None:
        return enum_value
    return _MISSING


def _first_example_value(value: object, *, context: str) -> object:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            return _ensure_json_value(item, context=context)
        return _MISSING
    if isinstance(value, Mapping):
        normalized = _ensure_mapping(value, context)
        for item in normalized.values():
            example = _ensure_mapping(item, f"{context} item")
            if "value" in example:
                return _ensure_json_value(example["value"], context=context)
        return _MISSING
    msg = f"{context} must be a list or mapping"
    raise OpenApiCompilationError(msg)


def _ensure_json_value(value: object, *, context: str) -> object:
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
        return [_ensure_json_value(item, context=context) for item in value]
    if isinstance(value, Mapping):
        normalized = _ensure_mapping(value, context)
        return {
            _validate_json_object_key(key, context=context): _ensure_json_value(
                item,
                context=f"{context}.{key}",
            )
            for key, item in normalized.items()
        }
    msg = f"{context} must be JSON-compatible"
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
