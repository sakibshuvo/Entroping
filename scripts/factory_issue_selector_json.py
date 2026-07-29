from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from scripts.factory_issue_selector_models import JsonObject, JsonValue

_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class JsonBoundaryError(ValueError):
    pass


def decode_json(raw: str | bytes) -> JsonValue:
    try:
        json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        return _JSON_VALUE_ADAPTER.validate_json(raw, strict=True)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValidationError) as exc:
        raise JsonBoundaryError("invalid JSON") from exc


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise JsonBoundaryError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> float:
    raise JsonBoundaryError(f"invalid JSON constant: {value}")
