"""OpenAPI-to-Hurl compiler boundary.

This module owns only OpenAPI operation/schema translation. It must not call
LLMs, invoke Hurl, write files directly, or apply merge behavior.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_JSONPATH_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class OpenApiCompilationError(ValueError):
    """Raised when an OpenAPI document cannot be compiled into Hurl content."""


@dataclass(frozen=True)
class GeneratedHurlFile:
    """Generated Hurl file content plus its deterministic repository path."""

    relative_path: str
    content: str


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
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
) -> str:
    status, response_schema = _select_response(operation)
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        f"# entroping: operation_id={operation_id}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{path}",
    ]

    request_schema = _json_request_schema(operation)
    if request_schema is not None:
        lines.append("Content-Type: application/json")
        lines.extend(json.dumps(_example_for_schema(request_schema), indent=2).splitlines())

    lines.append(f"HTTP {status}")
    assertions = _response_assertions(response_schema)
    if assertions:
        lines.append("[Asserts]")
        lines.extend(assertions)
    lines.append("")
    return "\n".join(lines)


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
    schema_type = schema.get("type")
    enum_value = _first_enum_value(schema)
    if enum_value is not None:
        return enum_value
    if schema_type == "object":
        properties = _ensure_mapping(schema.get("properties", {}), "OpenAPI object properties")
        required = _string_sequence(schema.get("required"), "OpenAPI object required")
        return {
            field_name: _example_for_schema(
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
    return "\n" in value or "\r" in value


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
