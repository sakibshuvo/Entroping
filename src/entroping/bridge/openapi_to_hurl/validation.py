"""Shared validation helpers for OpenAPI-to-Hurl compilation."""

from collections.abc import Mapping, Sequence

from entroping.bridge.openapi_to_hurl.models import OpenApiCompilationError


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
