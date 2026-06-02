"""Response fingerprint extraction for run reports."""

import json
import re
from collections.abc import Mapping

_HTTP_STATUS_RE = re.compile(r"^HTTP(?:/\S+)?\s+(?P<status>\d{3})(?:\s+.*)?$")
_HEADER_RE = re.compile(r"^(?P<name>[!#$%&'*+\-.^_`|~0-9A-Za-z]+):\s*(?P<value>.*)$")
_STABLE_RESPONSE_HEADERS = frozenset({"cache-control", "content-type", "vary"})


def _extract_response_fingerprint(
    stdout: str,
) -> tuple[int | None, tuple[tuple[str, str], ...], tuple[str, ...]]:
    status_code: int | None = None
    headers: tuple[tuple[str, str], ...] = ()
    body_text = stdout.strip()
    lines = stdout.splitlines()

    for index, line in enumerate(lines):
        status_match = _HTTP_STATUS_RE.fullmatch(line.strip())
        if status_match is None:
            continue
        status_code = int(status_match.group("status"))
        headers, body_text = _parse_response_lines(lines[index + 1 :])
        break

    body_shape = _json_body_shape(body_text)
    return status_code, headers, body_shape


def _parse_response_lines(lines: list[str]) -> tuple[tuple[tuple[str, str], ...], str]:
    raw_headers: dict[str, str] = {}
    body_start = len(lines)
    for index, line in enumerate(lines):
        if not line.strip():
            body_start = index + 1
            break
        header_match = _HEADER_RE.fullmatch(line)
        if header_match is None:
            body_start = index
            break
        name = header_match.group("name").strip().lower()
        value = header_match.group("value").strip()
        if name in _STABLE_RESPONSE_HEADERS and value and "[REDACTED]" not in value:
            raw_headers[name] = value

    headers = tuple(sorted(raw_headers.items()))
    return headers, "\n".join(lines[body_start:]).strip()


def _json_body_shape(body_text: str) -> tuple[str, ...]:
    if not body_text:
        return ()
    try:
        document = json.loads(body_text)
    except json.JSONDecodeError:
        return ()
    return tuple(_walk_json_shape(document, "$"))


def _walk_json_shape(value: object, path: str) -> list[str]:
    entries = [f"{path}:{_json_type(value)}"]
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            if not isinstance(key, str) or not key or _has_control_character(key):
                continue
            entries.extend(_walk_json_shape(value[key], f"{path}.{_shape_key(key)}"))
    elif isinstance(value, list) and value:
        entries.extend(_walk_json_shape(value[0], f"{path}[]"))
    return entries


def _json_type(value: object) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    return "string"


def _shape_key(key: str) -> str:
    return key.replace("\\", "\\\\").replace(".", "\\.")


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 for character in value)


def _serialized_response_status(response: object) -> int | None:
    if not isinstance(response, Mapping):
        return None
    status_code = response.get("status_code")
    if type(status_code) is int:
        return status_code
    return None


def _serialized_response_headers(response: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(response, Mapping):
        return ()
    raw_headers = response.get("headers")
    if not isinstance(raw_headers, Mapping):
        return ()
    normalized: dict[str, str] = {}
    for raw_name, raw_value in raw_headers.items():
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            continue
        name = raw_name.strip().lower()
        value = raw_value.strip()
        if name in _STABLE_RESPONSE_HEADERS and value and "[REDACTED]" not in value:
            normalized[name] = value
    return tuple(sorted(normalized.items()))


def _serialized_response_body_shape(response: object) -> tuple[str, ...]:
    if not isinstance(response, Mapping):
        return ()
    raw_shape = response.get("body_shape")
    if not isinstance(raw_shape, list):
        return ()
    shape = {
        item
        for item in raw_shape
        if isinstance(item, str) and item.strip() and not _has_control_character(item)
    }
    return tuple(sorted(shape, key=_body_shape_sort_key))


def _body_shape_sort_key(item: str) -> tuple[int, str]:
    return (0 if item.startswith("$:") else 1, item)
