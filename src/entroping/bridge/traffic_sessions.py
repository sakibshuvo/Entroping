"""Pure traffic filtering and session candidate transformations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse
from entroping.models.traffic_redaction import redacted_traffic_violation_summary

TrafficRecordRole = Literal["target", "dependency", "observed"]

STATIC_ASSET_EXTENSIONS = frozenset(
    {
        ".css",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".map",
        ".png",
        ".svg",
        ".ttf",
        ".webp",
        ".woff",
        ".woff2",
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


class TrafficSessionError(ValueError):
    """Raised when redacted traffic cannot be converted into a session candidate."""


@dataclass(frozen=True, slots=True)
class TrafficSessionRecord:
    """One filtered traffic record with its role in the observed flow."""

    exchange: TrafficExchange
    role: TrafficRecordRole


@dataclass(frozen=True, slots=True)
class TrafficSessionCandidate:
    """Ordered, filtered traffic records ready for freeze or map compilation."""

    name: str
    target_origin: str | None
    records: tuple[TrafficSessionRecord, ...]


def build_traffic_session_candidate(
    exchanges: Iterable[TrafficExchange],
    *,
    name: str,
    target_url: str | None,
) -> TrafficSessionCandidate:
    """Filter redacted traffic and return an ordered session candidate."""

    candidate_name = _validate_name(name)
    target_origin = _origin(target_url) if target_url is not None else None

    indexed_records: list[tuple[datetime, int, TrafficSessionRecord]] = []
    for index, exchange in enumerate(exchanges):
        if not exchange.redacted:
            msg = "requires redacted traffic"
            raise TrafficSessionError(msg)
        violation_summary = redacted_traffic_violation_summary(exchange)
        if violation_summary is not None:
            raise TrafficSessionError(violation_summary)
        if _is_static_asset(exchange):
            continue

        sanitized = _omit_binary_body_text(exchange)
        indexed_records.append(
            (
                sanitized.captured_at,
                index,
                TrafficSessionRecord(
                    exchange=sanitized,
                    role=_role_for(sanitized.request.url, target_origin),
                ),
            )
        )

    indexed_records.sort(key=lambda item: (item[0], item[1]))
    return TrafficSessionCandidate(
        name=candidate_name,
        target_origin=target_origin,
        records=tuple(item[2] for item in indexed_records),
    )


def _validate_name(name: str) -> str:
    value = name.strip()
    if not value:
        msg = "traffic session name must not be empty"
        raise TrafficSessionError(msg)
    if _contains_control(value):
        msg = "traffic session name must not contain control characters"
        raise TrafficSessionError(msg)
    return value


def _origin(url: str) -> str:
    if _contains_control(url):
        msg = "target_url must not contain control characters"
        raise TrafficSessionError(msg)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = "target_url must be an absolute http or https URL"
        raise TrafficSessionError(msg)
    return f"{parsed.scheme}://{parsed.netloc}"


def _role_for(url: str, target_origin: str | None) -> TrafficRecordRole:
    if target_origin is None:
        return "observed"
    return "target" if _origin(url) == target_origin else "dependency"


def _is_static_asset(exchange: TrafficExchange) -> bool:
    path = urlsplit(exchange.request.url).path.lower()
    return any(path.endswith(extension) for extension in STATIC_ASSET_EXTENSIONS)


def _omit_binary_body_text(exchange: TrafficExchange) -> TrafficExchange:
    request = _omit_request_binary_body_text(exchange.request)
    response = (
        _omit_response_binary_body_text(exchange.response)
        if exchange.response is not None
        else None
    )
    if request == exchange.request and response == exchange.response:
        return exchange
    return exchange.model_copy(update={"request": request, "response": response})


def _omit_request_binary_body_text(request: TrafficRequest) -> TrafficRequest:
    body = _omit_binary_text(request.body)
    if body == request.body:
        return request
    return request.model_copy(update={"body": body})


def _omit_response_binary_body_text(response: TrafficResponse) -> TrafficResponse:
    body = _omit_binary_text(response.body)
    if body == response.body:
        return response
    return response.model_copy(update={"body": body})


def _omit_binary_text(body: TrafficBody | None) -> TrafficBody | None:
    if body is None or body.text is None or _is_textual_content_type(body.content_type):
        return body
    return body.model_copy(update={"text": None})


def _is_textual_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", maxsplit=1)[0].lower().strip()
    return (
        media_type.startswith("text/")
        or media_type in _TEXTUAL_CONTENT_TYPES
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
