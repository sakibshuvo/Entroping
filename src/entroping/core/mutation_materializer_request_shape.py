"""Bounded request-shape transforms for reviewed Hurl mutations."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Final, TypedDict

from entroping.core import mutation_materializer_hurl_requests as _hurl_requests
from entroping.core import mutation_materializer_io as _io
from entroping.models.secrets import contains_secret_like_value, has_disallowed_control

MutationMaterializerError = _io.MutationMaterializerError
JsonScalar = None | bool | int | float | str
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_CORPUS: Final[dict[str, tuple[JsonScalar, ...]]] = {
    "string": ("", " ", "x" * 256),
    "number": (-1, 0, 2_147_483_647),
    "boolean": (False, True),
    "null": ("", 0, False),
}


class RequestShapeSelector(TypedDict):
    request_ordinal: int
    json_pointer: str
    corpus_id: str


@dataclass(frozen=True, slots=True)
class _JsonScalarSpan:
    value: JsonScalar
    start: int
    end: int


def selector_types_valid(selector: dict[str, JsonValue]) -> bool:
    return (
        type(selector.get("request_ordinal")) is int
        and type(selector.get("json_pointer")) is str
        and type(selector.get("corpus_id")) is str
    )


def _reject(condition: bool, error: str) -> None:
    if condition:
        raise MutationMaterializerError(error)


def validate_selector(selector: RequestShapeSelector) -> RequestShapeSelector:
    _reject(
        set(selector) != {"request_ordinal", "json_pointer", "corpus_id"},
        "category selector keys are invalid",
    )
    request_ordinal = selector["request_ordinal"]
    json_pointer_value = selector["json_pointer"]
    corpus_id_value = selector["corpus_id"]
    _reject(request_ordinal < 0 or request_ordinal > 9_999, "request ordinal is invalid")
    json_pointer = _manifest_text(json_pointer_value)
    _reject(
        not json_pointer.startswith("/") or len(json_pointer.encode("utf-8")) > 1_024,
        "JSON pointer is invalid",
    )
    _validate_json_pointer_escapes(json_pointer)
    corpus_id = _manifest_text(corpus_id_value)
    _reject(corpus_id != "request-shape-v1", "request-shape corpus is unsupported")
    return {
        "request_ordinal": request_ordinal,
        "json_pointer": json_pointer,
        "corpus_id": corpus_id,
    }


def materialize_request_shape(
    content: str,
    selector: RequestShapeSelector,
    reviewed_seed: int,
) -> str:
    body_start, body_end = _hurl_requests.locate_request_json_body(
        content, selector["request_ordinal"]
    )
    body = content[body_start:body_end]
    pointer = tuple(
        part.replace("~1", "/").replace("~0", "~")
        for part in selector["json_pointer"].split("/")[1:]
    )
    scalar = _find_json_scalar_span(body, pointer)
    replacement = _scalar_replacement(scalar.value, reviewed_seed)
    return content[: body_start + scalar.start] + replacement + content[body_start + scalar.end :]


def _manifest_text(value: str) -> str:
    _reject(
        unicodedata.normalize("NFC", value) != value or has_disallowed_control(value),
        "manifest text is not normalized",
    )
    _reject(contains_secret_like_value(value), "manifest contains unsafe text")
    return value


def _validate_json_pointer_escapes(pointer: str) -> None:
    for segment in pointer.split("/")[1:]:
        index = 0
        while index < len(segment):
            if segment[index] != "~":
                index += 1
                continue
            _reject(
                index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"},
                "JSON pointer is invalid",
            )
            index += 2


def _new_json_decoder() -> json.JSONDecoder:
    return json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_json_constant,
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise MutationMaterializerError("request body contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> JsonValue:
    raise MutationMaterializerError("request body is not valid JSON")


def _decode_json_value(
    content: str,
    start: int,
    decoder: json.JSONDecoder | None = None,
) -> tuple[JsonValue, int]:
    try:
        return (decoder or _new_json_decoder()).raw_decode(content, start)
    except MutationMaterializerError:
        raise
    except (TypeError, ValueError) as exc:
        raise MutationMaterializerError("request body is not valid JSON") from exc


def _skip_json_whitespace(content: str, index: int) -> int:
    while index < len(content) and content[index] in " \t\r\n":
        index += 1
    return index


def _json_scalar_kind(value: JsonScalar) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in {int, float}:
        return "number"
    if type(value) is str:
        return "string"
    raise MutationMaterializerError("request-shape target is not a JSON scalar")


def _scalar_replacement(value: JsonScalar, reviewed_seed: int) -> str:
    kind = _json_scalar_kind(value)
    candidates = tuple(
        candidate
        for candidate in _CORPUS[kind]
        if not (_json_scalar_kind(candidate) == kind and candidate == value)
    )
    _reject(not candidates, "request-shape corpus has no replacement")
    replacement = candidates[reviewed_seed % len(candidates)]
    return json.dumps(replacement, ensure_ascii=False, separators=(",", ":"))


def _find_json_scalar_span(content: str, pointer: tuple[str, ...]) -> _JsonScalarSpan:
    start = _skip_json_whitespace(content, 0)
    root, end = _decode_json_value(content, start)
    _reject(content[end:].strip() != "", "request body contains multiple JSON values")
    if not pointer:
        if isinstance(root, (dict, list)):
            raise MutationMaterializerError("request-shape target must be a JSON scalar")
        _, scalar_end = _decode_json_value(content, start)
        return _JsonScalarSpan(root, start, scalar_end)
    current_start = start
    current_value = root
    for segment in pointer:
        current_value, current_start = _find_json_child(
            content, current_start, current_value, segment
        )
    if isinstance(current_value, (dict, list)):
        raise MutationMaterializerError("request-shape target must be a JSON scalar")
    _, scalar_end = _decode_json_value(content, current_start)
    return _JsonScalarSpan(current_value, current_start, scalar_end)


def _find_json_child(
    content: str,
    start: int,
    value: JsonValue,
    segment: str,
) -> tuple[JsonValue, int]:
    if isinstance(value, dict):
        return _find_json_object_child(content, start, value, segment)
    if not isinstance(value, list):
        raise MutationMaterializerError("request-shape JSON pointer target is missing")
    return _find_json_array_child(content, start, value, segment)


def _json_container_start(content: str, start: int, opening: str) -> int:
    cursor = _skip_json_whitespace(content, start)
    _reject(cursor >= len(content) or content[cursor] != opening, "request body is not valid JSON")
    return _skip_json_whitespace(content, cursor + 1)


def _json_object_key(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise MutationMaterializerError("request body is not valid JSON")
    return value


def _find_json_object_child(
    content: str,
    start: int,
    value: dict[str, JsonValue],
    target: str,
) -> tuple[JsonValue, int]:
    cursor = _json_container_start(content, start, "{")
    decoder = _new_json_decoder()
    while cursor < len(content) and content[cursor] != "}":
        raw_key, key_end = _decode_json_value(content, cursor, decoder)
        key = _json_object_key(raw_key)
        cursor = _skip_json_whitespace(content, key_end)
        _reject(
            cursor >= len(content) or content[cursor] != ":",
            "request body is not valid JSON",
        )
        child_start = _skip_json_whitespace(content, cursor + 1)
        if key == target:
            return value[key], child_start
        _, child_end = _decode_json_value(content, child_start, decoder)
        cursor = _json_child_separator(content, child_end, "}")
    raise MutationMaterializerError("request-shape JSON pointer target is missing")


def _find_json_array_child(
    content: str,
    start: int,
    value: list[JsonValue],
    segment: str,
) -> tuple[JsonValue, int]:
    target = _array_target(segment)
    cursor = _json_container_start(content, start, "[")
    decoder = _new_json_decoder()
    current = 0
    while cursor < len(content) and content[cursor] != "]":
        if current == target:
            return value[current], cursor
        _, child_end = _decode_json_value(content, cursor, decoder)
        cursor = _json_child_separator(content, child_end, "]")
        current += 1
    raise MutationMaterializerError("request-shape JSON pointer target is missing")


def _json_child_separator(content: str, end: int, closing: str) -> int:
    cursor = _skip_json_whitespace(content, end)
    if cursor < len(content) and content[cursor] == ",":
        return _skip_json_whitespace(content, cursor + 1)
    _reject(cursor >= len(content) or content[cursor] != closing, "request body is not valid JSON")
    return cursor


def _array_target(segment: str) -> int:
    _reject(
        not segment
        or (segment != "0" and segment.startswith("0"))
        or not segment.isascii()
        or not segment.isdecimal(),
        "request-shape JSON pointer target is missing",
    )
    return int(segment)
