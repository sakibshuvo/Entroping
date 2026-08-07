"""Bounded response evidence reconstruction for Hurl structured output."""

import base64
from collections.abc import Mapping, Sequence

from entroping.core.hurl_structured import HurlStructuredReportError

_STRUCTURED_RESPONSE_BODY_LIMIT_BYTES = 256 * 1024
_STRUCTURED_RESPONSE_HEADERS = frozenset({"cache-control", "content-type", "vary"})


def structured_response_output(
    entries: Sequence[Mapping[object, object]],
    capture_names: Sequence[str],
) -> bytes | None:
    """Validate response fields and reconstruct stable public response bytes."""

    response_status, response_headers, reserved_capture_values = _response_evidence(
        entries,
        capture_names,
    )
    _validate_capture_set(capture_names, response_status, reserved_capture_values)
    response_body = _decode_body(_last_capture(capture_names, reserved_capture_values))
    return _render_response(response_status, response_headers, response_body)


def _response_evidence(
    entries: Sequence[Mapping[object, object]],
    capture_names: Sequence[str],
) -> tuple[int | None, tuple[tuple[str, str], ...], dict[str, str]]:
    response_status: int | None = None
    response_headers: tuple[tuple[str, str], ...] = ()
    reserved_capture_values: dict[str, str] = {}
    for entry in entries:
        calls_status, calls_headers = _structured_calls(entry.get("calls"))
        if calls_status is not None:
            response_status = calls_status
            response_headers = calls_headers
        _structured_captures(
            entry.get("captures"),
            capture_names=capture_names,
            reserved_capture_values=reserved_capture_values,
        )
    return response_status, response_headers, reserved_capture_values


def _structured_calls(
    raw_calls: object,
) -> tuple[int | None, tuple[tuple[str, str], ...]]:
    if not isinstance(raw_calls, list):
        raise HurlStructuredReportError
    responses = tuple(_parse_call(call) for call in raw_calls)
    return responses[-1] if responses else (None, ())


def _parse_call(raw_call: object) -> tuple[int, tuple[tuple[str, str], ...]]:
    call = _require_mapping(raw_call)
    response = _require_mapping(call.get("response"))
    status_code = _response_status(response.get("status"))
    return status_code, _structured_headers(response.get("headers"))


def _response_status(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 100 <= value <= 599:
        raise HurlStructuredReportError
    return value


def _structured_headers(raw_headers: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw_headers, list):
        raise HurlStructuredReportError
    return tuple(
        _parse_header(raw_header)
        for raw_header in raw_headers
        if _is_kept_header(raw_header)
    )


def _is_kept_header(raw_header: object) -> bool:
    header = _require_mapping(raw_header)
    name = header.get("name")
    value = header.get("value")
    _validate_header_text(name, allow_empty=False)
    _validate_header_text(value, allow_empty=True)
    return str(name).lower() in _STRUCTURED_RESPONSE_HEADERS


def _parse_header(raw_header: object) -> tuple[str, str]:
    header = _require_mapping(raw_header)
    name = header.get("name")
    value = header.get("value")
    _validate_header_text(name, allow_empty=False)
    _validate_header_text(value, allow_empty=True)
    return str(name), str(value)


def _validate_header_text(value: object, *, allow_empty: bool) -> None:
    if not isinstance(value, str):
        raise HurlStructuredReportError
    if _empty_header_text(value, allow_empty) or _has_header_break(value):
        raise HurlStructuredReportError


def _empty_header_text(value: str, allow_empty: bool) -> bool:
    return not allow_empty and not value


def _has_header_break(value: str) -> bool:
    return any(character in value for character in "\r\n")


def _structured_captures(
    raw_captures: object,
    *,
    capture_names: Sequence[str],
    reserved_capture_values: dict[str, str],
) -> None:
    if not isinstance(raw_captures, list):
        raise HurlStructuredReportError
    for capture in raw_captures:
        name, value = _capture_parts(capture)
        _retain_capture(
            name,
            value,
            capture_names=capture_names,
            reserved_capture_values=reserved_capture_values,
        )


def _retain_capture(
    name: str,
    value: object,
    *,
    capture_names: Sequence[str],
    reserved_capture_values: dict[str, str],
) -> None:
    if name not in capture_names:
        return
    if not isinstance(value, str) or name in reserved_capture_values:
        raise HurlStructuredReportError
    reserved_capture_values[name] = value


def _capture_parts(raw_capture: object) -> tuple[str, object]:
    capture = _require_mapping(raw_capture)
    name = capture.get("name")
    if not isinstance(name, str):
        raise HurlStructuredReportError
    return name, capture.get("value")


def _validate_capture_set(
    capture_names: Sequence[str],
    response_status: int | None,
    reserved_capture_values: Mapping[str, str],
) -> None:
    if tuple(reserved_capture_values) != tuple(capture_names):
        raise HurlStructuredReportError
    if capture_names and response_status is None:
        raise HurlStructuredReportError


def _last_capture(
    capture_names: Sequence[str],
    reserved_capture_values: Mapping[str, str],
) -> str | None:
    return reserved_capture_values[capture_names[-1]] if capture_names else None


def _decode_body(value: str | None) -> bytes | None:
    if value is None:
        return None
    try:
        body = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise HurlStructuredReportError from exc
    if len(body) > _STRUCTURED_RESPONSE_BODY_LIMIT_BYTES:
        raise HurlStructuredReportError
    return body


def _render_response(
    status: int | None,
    headers: Sequence[tuple[str, str]],
    body: bytes | None,
) -> bytes | None:
    if status is None:
        return body
    response = [f"HTTP/1.1 {status}\n".encode()]
    response.extend(f"{name}: {value}\n".encode() for name, value in headers)
    response.append(b"\n")
    if body is not None:
        response.append(body)
    return b"".join(response)


def _require_mapping(value: object) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise HurlStructuredReportError
    return value
