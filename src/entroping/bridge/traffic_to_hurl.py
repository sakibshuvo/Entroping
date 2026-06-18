"""Traffic-to-Hurl compiler boundary.

This module will convert redacted, normalized traffic sessions into Hurl test
models. It must not own proxy capture, SQLite persistence, or report writing.
"""

import json
import math
import re
from base64 import b64encode
from dataclasses import dataclass

from entroping.bridge.traffic_sessions import TrafficSessionCandidate, TrafficSessionRecord
from entroping.models.secrets import REDACTED, is_sensitive_key
from entroping.models.traffic import TrafficBody, TrafficResponse

_SAFE_FILE_STEM_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_HTTP_METHOD_TOKEN_RE = re.compile(r"^[A-Z]+(?:-[A-Z]+)*$")
_HTTP_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_JSONPATH_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HURL_REQUEST_LINE_RE = re.compile(
    r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE)\s+\S+(?:\s+.*)?$",
)
_HURL_RESPONSE_LINE_RE = re.compile(r"^HTTP\s+\S+")
_HURL_SECTION_LINES = frozenset(
    {
        "[Asserts]",
        "[BasicAuth]",
        "[Captures]",
        "[Cookies]",
        "[FormParams]",
        "[MultipartFormData]",
        "[Options]",
        "[QueryStringParams]",
    }
)
_HOP_BY_HOP_REQUEST_HEADERS = frozenset(
    {
        "accept-encoding",
        "connection",
        "content-length",
        "host",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_TEXTUAL_CONTENT_TYPES = frozenset(
    {
        "application/graphql",
        "application/json",
        "application/problem+json",
        "application/x-ndjson",
        "application/x-www-form-urlencoded",
        "application/xml",
    }
)
_VOLATILE_KEY_PARTS = (
    "timestamp",
    "created_at",
    "updated_at",
    "deleted_at",
    "expires_at",
    "uuid",
)


class TrafficHurlCompilationError(ValueError):
    """Raised when a traffic session cannot be compiled into safe Hurl."""


@dataclass(frozen=True, slots=True)
class GeneratedTrafficHurlFile:
    """Generated traffic Hurl content plus its deterministic repository path."""

    relative_path: str
    content: str


def compile_traffic_session_to_hurl(
    session: TrafficSessionCandidate,
    *,
    golden: bool,
) -> GeneratedTrafficHurlFile:
    """Compile a filtered redacted traffic session into one Hurl file."""

    if not session.records:
        msg = f"traffic session {session.name!r} contains no traffic records"
        raise TrafficHurlCompilationError(msg)

    lines = [
        "# entroping: tags=traffic,freeze",
        "# entroping: source=traffic",
        f"# entroping: session={session.name}",
    ]
    if session.target_origin is not None:
        lines.append(f"# entroping: target={session.target_origin}")
    lines.append("")

    for index, record in enumerate(session.records):
        if index > 0:
            lines.append("")
        lines.extend(_render_record(record, golden=golden))

    lines.append("")
    return GeneratedTrafficHurlFile(
        relative_path=f"tests/generated/{_safe_file_stem(session.name)}.hurl",
        content="\n".join(lines),
    )


def _render_record(record: TrafficSessionRecord, *, golden: bool) -> list[str]:
    exchange = record.exchange
    if not exchange.redacted:
        msg = "traffic-to-Hurl compilation requires redacted traffic"
        raise TrafficHurlCompilationError(msg)
    if exchange.response is None:
        msg = "traffic-to-Hurl compilation requires response records"
        raise TrafficHurlCompilationError(msg)

    method = _safe_request_method(exchange.request.method)
    lines = [
        f"# entroping: role={record.role}",
        f"# entroping: captured_at={exchange.captured_at.isoformat()}",
        f"{method} {_safe_hurl_line_value(exchange.request.url, 'request URL')}",
    ]
    lines.extend(_render_request_headers(exchange.request.headers))
    request_body = _request_body_text(exchange.request.body)
    if request_body is not None:
        lines.extend(_safe_body_lines(request_body))
    lines.append(f"HTTP {exchange.response.status_code}")

    assertions = _golden_assertions(exchange.response) if golden else []
    if assertions:
        lines.append("[Asserts]")
        lines.extend(assertions)
    return lines


def _render_request_headers(headers: dict[str, str]) -> list[str]:
    rendered: list[str] = []
    for name, value in headers.items():
        safe_name = _safe_header_name(name)
        if safe_name.lower() in _HOP_BY_HOP_REQUEST_HEADERS:
            continue
        rendered.append(
            f"{safe_name}: {_safe_hurl_line_value(value, f'header {safe_name!r}')}"
        )
    return rendered


def _request_body_text(body: TrafficBody | None) -> str | None:
    if body is None or body.text is None:
        return None
    if not _is_textual_content_type(body.content_type):
        return None
    return body.text


def _safe_body_lines(text: str) -> list[str]:
    if _has_hurl_template_delimiter(text):
        msg = "traffic body contains Hurl template delimiters"
        raise TrafficHurlCompilationError(msg)
    if _contains_hurl_structural_line(text):
        return _base64_body_lines(text)
    return text.splitlines() or [""]


def _contains_hurl_structural_line(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if (
            _HURL_REQUEST_LINE_RE.fullmatch(stripped)
            or _HURL_RESPONSE_LINE_RE.fullmatch(stripped)
            or stripped.startswith("#")
            or _is_hurl_section_line(stripped)
        ):
            return True
    return False


def _is_hurl_section_line(line: str) -> bool:
    return line in _HURL_SECTION_LINES


def _base64_body_lines(text: str) -> list[str]:
    encoded = b64encode(text.encode("utf-8")).decode("ascii")
    return [f"base64,{encoded};"]


def _golden_assertions(response: TrafficResponse) -> list[str]:
    assertions: list[str] = []
    content_type = _header_value(response.headers, "content-type")
    if content_type is not None and _is_textual_content_type(content_type):
        media_type = _media_type(content_type)
        assertions.append(f'header "Content-Type" contains "{media_type}"')

    body = response.body
    if (
        body is None
        or body.text is None
        or _media_type(body.content_type or "") != "application/json"
    ):
        return assertions

    try:
        parsed = json.loads(body.text)
    except json.JSONDecodeError:
        return assertions
    if not isinstance(parsed, dict):
        return assertions

    for key, value in parsed.items():
        key_text = str(key)
        if not _is_stable_json_assertion(key_text, value):
            continue
        assertions.append(f'jsonpath "$.{key_text}" == {_hurl_json_literal(value)}')
    return assertions


def _is_stable_json_assertion(key: str, value: object) -> bool:
    normalized = key.lower().replace("-", "_")
    if _JSONPATH_FIELD_RE.fullmatch(key) is None:
        return False
    if (
        normalized == "id"
        or normalized.endswith("_id")
        or is_sensitive_key(key)
        or any(part in normalized for part in _VOLATILE_KEY_PARTS)
    ):
        return False
    if not isinstance(value, str | int | float | bool):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return not (
        isinstance(value, str)
        and (
            value == REDACTED
            or _contains_control(value)
            or _has_hurl_template_delimiter(value)
        )
    )


def _hurl_json_literal(value: str | int | float | bool) -> str:
    return json.dumps(value, allow_nan=False)


def _header_value(headers: dict[str, str], name: str) -> str | None:
    normalized = name.lower()
    for header_name, value in headers.items():
        if header_name.lower() == normalized:
            return value
    return None


def _is_textual_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = _media_type(content_type)
    return (
        media_type.startswith("text/")
        or media_type in _TEXTUAL_CONTENT_TYPES
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )


def _media_type(content_type: str) -> str:
    return content_type.split(";", maxsplit=1)[0].lower().strip()


def _safe_file_stem(name: str) -> str:
    stem = _SAFE_FILE_STEM_RE.sub("_", name.strip()).strip("._-")
    if not stem:
        msg = "traffic session name does not produce a safe Hurl filename"
        raise TrafficHurlCompilationError(msg)
    return stem


def _safe_request_method(value: str) -> str:
    if _contains_control(value):
        msg = "request method contains control characters"
        raise TrafficHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "request method contains Hurl template delimiters"
        raise TrafficHurlCompilationError(msg)
    method = value.strip().upper()
    if _HTTP_METHOD_TOKEN_RE.fullmatch(method) is None:
        msg = "request method must be an HTTP token"
        raise TrafficHurlCompilationError(msg)
    return method


def _safe_header_name(value: str) -> str:
    if _contains_control(value):
        msg = "header name contains control characters"
        raise TrafficHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "header name contains Hurl template delimiters"
        raise TrafficHurlCompilationError(msg)
    if _HTTP_HEADER_NAME_RE.fullmatch(value) is None:
        msg = "header name must be an HTTP token"
        raise TrafficHurlCompilationError(msg)
    return value


def _safe_hurl_line_value(value: str, context: str) -> str:
    if _contains_control(value):
        msg = f"{context} contains control characters"
        raise TrafficHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = f"{context} contains Hurl template delimiters"
        raise TrafficHurlCompilationError(msg)
    return value


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
