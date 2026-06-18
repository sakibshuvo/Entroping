"""Validation helpers for traffic that claims to be redacted."""

from urllib.parse import parse_qsl, unquote, urlsplit

from entroping.models.secrets import (
    REDACTED,
    contains_secret_like_value,
    is_sensitive_header_name,
    is_sensitive_key,
)
from entroping.models.traffic import TrafficBody, TrafficExchange


def redacted_traffic_violation_summary(exchange: TrafficExchange) -> str | None:
    """Return a value-free summary when a redacted exchange still looks unsafe."""

    locations = _redacted_traffic_violation_locations(exchange)
    if not locations:
        return None
    return "unredacted secret-like traffic content in " + ", ".join(locations)


def _redacted_traffic_violation_locations(exchange: TrafficExchange) -> tuple[str, ...]:
    locations: list[str] = []
    locations.extend(_url_violation_locations(exchange.request.url, location="request.url"))
    locations.extend(
        _header_violation_locations(exchange.request.headers, location="request.headers")
    )
    locations.extend(_body_violation_locations(exchange.request.body, location="request.body"))
    if exchange.response is not None:
        locations.extend(
            _header_violation_locations(
                exchange.response.headers,
                location="response.headers",
            )
        )
        locations.extend(
            _body_violation_locations(exchange.response.body, location="response.body")
        )
    return tuple(dict.fromkeys(locations))


def _url_violation_locations(url: str, *, location: str) -> tuple[str, ...]:
    parsed = urlsplit(url)
    locations: list[str] = []
    if "@" in parsed.netloc:
        locations.append(f"{location}.userinfo")
    if any(_path_segment_looks_secret(segment) for segment in parsed.path.split("/")):
        locations.append(f"{location}.path")
    if any(_query_pair_looks_secret(key, value) for key, value in _query_pairs(parsed.query)):
        locations.append(f"{location}.query")
    return tuple(locations)


def _query_pairs(query: str) -> tuple[tuple[str, str], ...]:
    return tuple(parse_qsl(query, keep_blank_values=True))


def _query_pair_looks_secret(key: str, value: str) -> bool:
    if is_sensitive_key(key):
        return value != REDACTED
    return contains_secret_like_value(value)


def _path_segment_looks_secret(segment: str) -> bool:
    decoded = unquote(segment)
    return bool(decoded and decoded != REDACTED and contains_secret_like_value(decoded))


def _header_violation_locations(
    headers: dict[str, str],
    *,
    location: str,
) -> tuple[str, ...]:
    if any(_header_value_looks_secret(name, value) for name, value in headers.items()):
        return (location,)
    return ()


def _header_value_looks_secret(name: str, value: str) -> bool:
    if is_sensitive_header_name(name):
        return value != REDACTED
    return contains_secret_like_value(value)


def _body_violation_locations(
    body: TrafficBody | None,
    *,
    location: str,
) -> tuple[str, ...]:
    if body is not None and body.text is not None and contains_secret_like_value(body.text):
        return (location,)
    return ()
