"""Pure WireMock mapping compilation from redacted traffic sessions."""

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from entroping.bridge.traffic_sessions import TrafficSessionCandidate, TrafficSessionRecord
from entroping.models.secrets import REDACTED, is_sensitive_key
from entroping.models.traffic import TrafficBody, TrafficResponse
from entroping.models.traffic_redaction import redacted_traffic_violation_summary

_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authenticate",
        "proxy-authorization",
        "set-cookie",
        "www-authenticate",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
    }
)
_HOP_BY_HOP_RESPONSE_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
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
        "text/html",
        "text/plain",
        "text/xml",
    }
)


class TrafficWireMockCompilationError(ValueError):
    """Raised when redacted traffic cannot be compiled into WireMock mappings."""


@dataclass(frozen=True, slots=True)
class GeneratedWireMockMapping:
    """Generated WireMock mapping content plus its deterministic repository path."""

    relative_path: str
    content: str


def compile_traffic_session_to_wiremock(
    session: TrafficSessionCandidate,
    *,
    service: str,
) -> tuple[GeneratedWireMockMapping, ...]:
    """Compile selected redacted traffic records into WireMock mapping JSON files."""

    if not session.records:
        msg = f"traffic session {session.name!r} contains no traffic records"
        raise TrafficWireMockCompilationError(msg)

    safe_service = _validate_safe_stem(service, field="mock service")
    safe_session = _validate_safe_stem(session.name, field="traffic session name")
    selected = [record for record in session.records if _matches_service(record, safe_service)]
    if not selected:
        msg = f"No traffic records matched mock service {safe_service!r}"
        raise TrafficWireMockCompilationError(msg)

    return tuple(
        GeneratedWireMockMapping(
            relative_path=f"mocks/{safe_service}/{safe_session}-{index:03d}.json",
            content=_mapping_content(record),
        )
        for index, record in enumerate(selected, start=1)
    )


def _mapping_content(record: TrafficSessionRecord) -> str:
    exchange = record.exchange
    if not exchange.redacted:
        msg = "traffic-to-WireMock compilation requires redacted traffic"
        raise TrafficWireMockCompilationError(msg)
    violation_summary = redacted_traffic_violation_summary(exchange)
    if violation_summary is not None:
        raise TrafficWireMockCompilationError(violation_summary)
    if exchange.response is None:
        msg = "traffic-to-WireMock compilation requires response records"
        raise TrafficWireMockCompilationError(msg)

    parsed = urlsplit(exchange.request.url)
    payload: dict[str, object] = {
        "request": _request_mapping(
            method=exchange.request.method,
            path=parsed.path,
            query=parsed.query,
        ),
        "response": _response_mapping(exchange.response),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _request_mapping(*, method: str, path: str, query: str) -> dict[str, object]:
    safe_path = path or "/"
    pairs = tuple(parse_qsl(query, keep_blank_values=True))
    if pairs and _requires_exact_url_match(pairs):
        return {"method": method, "url": f"{safe_path}?{query}"}

    payload: dict[str, object] = {"method": method, "urlPath": safe_path}
    query_parameters = _query_parameter_matchers(pairs)
    if query_parameters:
        payload["queryParameters"] = query_parameters
    return payload


def _query_parameter_matchers(
    pairs: tuple[tuple[str, str], ...],
) -> dict[str, dict[str, str]]:
    matchers: dict[str, dict[str, str]] = {}
    for key, value in pairs:
        if _requires_value_free_query_match(key, value):
            matchers[key] = {"matches": ".+"}
            continue
        if key not in matchers:
            matchers[key] = {"equalTo": value}
    return matchers


def _requires_exact_url_match(pairs: tuple[tuple[str, str], ...]) -> bool:
    if any(_requires_value_free_query_match(key, value) for key, value in pairs):
        return False

    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            return True
        seen.add(key)
    return False


def _requires_value_free_query_match(key: str, value: str) -> bool:
    return is_sensitive_key(key) or value == REDACTED


def _response_mapping(response: TrafficResponse) -> dict[str, object]:
    payload: dict[str, object] = {"status": response.status_code}
    headers = _safe_response_headers(response.headers)
    if headers:
        payload["headers"] = headers

    body = _body_payload(response.body)
    if body is not None:
        key, value = body
        payload[key] = value
    return payload


def _safe_response_headers(headers: dict[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized in _SENSITIVE_HEADER_NAMES or normalized in _HOP_BY_HOP_RESPONSE_HEADERS:
            continue
        if value == REDACTED:
            continue
        rendered[name] = value
    return rendered


def _body_payload(body: TrafficBody | None) -> tuple[str, object] | None:
    if body is None or body.text is None or not _is_textual_content_type(body.content_type):
        return None

    if _media_type(body.content_type or "") == "application/json":
        try:
            return "jsonBody", json.loads(body.text)
        except json.JSONDecodeError:
            return "body", body.text
    return "body", body.text


def _matches_service(record: TrafficSessionRecord, safe_service: str) -> bool:
    host = urlsplit(record.exchange.request.url).netloc.lower()
    if host == safe_service:
        return True
    first_label = host.split(".", maxsplit=1)[0]
    return "." not in safe_service and first_label == safe_service


def _validate_safe_stem(value: str, *, field: str) -> str:
    safe = value.strip().lower()
    if not safe:
        msg = f"{field} must not be empty"
        raise TrafficWireMockCompilationError(msg)
    if _contains_control(safe):
        msg = f"{field} must not contain control characters"
        raise TrafficWireMockCompilationError(msg)
    if "/" in safe or "\\" in safe or ".." in safe or safe.startswith("."):
        msg = f"{field} must be a safe file stem"
        raise TrafficWireMockCompilationError(msg)
    if _SAFE_STEM_RE.fullmatch(safe) is None:
        msg = f"{field} must contain only letters, numbers, dots, dashes, or underscores"
        raise TrafficWireMockCompilationError(msg)
    return safe


def _is_textual_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = _media_type(content_type)
    return media_type in _TEXTUAL_CONTENT_TYPES or media_type.startswith("text/")


def _media_type(content_type: str) -> str:
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
