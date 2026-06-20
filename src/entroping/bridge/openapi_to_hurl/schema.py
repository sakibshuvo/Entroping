"""Schema traversal and example generation for OpenAPI-to-Hurl compilation."""

import math
from collections.abc import Mapping, Sequence

from entroping.bridge.openapi_to_hurl.models import (
    _MISSING,
    OpenApiCompilationError,
    _TraversalBudget,
)
from entroping.bridge.openapi_to_hurl.validation import (
    _ensure_mapping,
    _has_control,
    _has_hurl_template_delimiter,
    _string_sequence,
    _validate_json_object_key,
)

_MAX_OPENAPI_SCHEMA_DEPTH = 64
_MAX_OPENAPI_SCHEMA_NODES = 10_000
_MAX_OPENAPI_JSON_DEPTH = 64
_MAX_OPENAPI_JSON_NODES = 10_000
_MAX_OPENAPI_GENERATED_STRING_LENGTH = 4096


def _first_enum_value(schema: Mapping[str, object]) -> object:
    raw_enum = schema.get("enum")
    if not isinstance(raw_enum, Sequence) or isinstance(raw_enum, str | bytes):
        return _MISSING
    for value in raw_enum:
        if value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            continue
        if isinstance(value, str):
            if _has_control(value) or _has_hurl_template_delimiter(value):
                continue
            return value
        if isinstance(value, int | float | bool):
            return value
    return _MISSING


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
        minimum = _finite_numeric_bound(schema.get("minimum"))
        if minimum is not None:
            return int(minimum) if schema_type == "integer" else minimum
        maximum = _finite_numeric_bound(schema.get("maximum"))
        if maximum is not None:
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
    if enum_value is not _MISSING:
        return enum_value
    return _MISSING


def _finite_numeric_bound(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


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
