"""Redaction pipeline for Eye traffic before local persistence."""

import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from entroping.models.secrets import (
    REDACTED,
    is_sensitive_header_name,
    is_sensitive_key,
    redact_secret_like_values,
)
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

DEFAULT_MAX_BODY_CHARS = 4096


def redact_traffic_exchange(
    exchange: TrafficExchange,
    *,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> TrafficExchange:
    """Return a copy of ``exchange`` safe for local persistence."""

    if max_body_chars <= 0:
        msg = "max_body_chars must be positive"
        raise ValueError(msg)

    return TrafficExchange(
        captured_at=exchange.captured_at,
        duration_ms=exchange.duration_ms,
        request=_redact_request(exchange.request, max_body_chars=max_body_chars),
        response=(
            _redact_response(exchange.response, max_body_chars=max_body_chars)
            if exchange.response is not None
            else None
        ),
        redacted=True,
    )


def _redact_request(request: TrafficRequest, *, max_body_chars: int) -> TrafficRequest:
    return TrafficRequest(
        method=request.method,
        url=_redact_url(request.url),
        headers=_redact_headers(request.headers),
        body=_redact_body(request.body, max_body_chars=max_body_chars),
    )


def _redact_response(response: TrafficResponse, *, max_body_chars: int) -> TrafficResponse:
    return TrafficResponse(
        status_code=response.status_code,
        headers=_redact_headers(response.headers),
        body=_redact_body(response.body, max_body_chars=max_body_chars),
    )


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if is_sensitive_header_name(name):
            redacted[name] = REDACTED
        else:
            redacted[name] = _redact_text(value)
    return redacted


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    query = urlencode(
        [
            (key, REDACTED if is_sensitive_key(key) else _redact_text(value))
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ],
        doseq=True,
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def _redact_body(body: TrafficBody | None, *, max_body_chars: int) -> TrafficBody | None:
    if body is None:
        return None
    if body.text is None:
        return body.model_copy(update={"truncated": body.truncated})

    content_type = (body.content_type or "").split(";", maxsplit=1)[0].lower().strip()
    redacted_text = (
        _redact_json_body(body.text)
        if _is_json_content_type(content_type)
        else _redact_plain_text_body(body.text, max_body_chars=max_body_chars)
    )
    truncated = (
        body.truncated or len(body.text) > max_body_chars or len(redacted_text) > max_body_chars
    )
    if len(redacted_text) > max_body_chars:
        redacted_text = redacted_text[:max_body_chars]

    return TrafficBody(
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        text=redacted_text,
        truncated=truncated,
    )


def _redact_json_body(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _redact_text(text)
    return json.dumps(_redact_json_value(parsed), separators=(",", ":"), sort_keys=True)


def _redact_json_value(value: object, *, key: str | None = None) -> object:
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for item_key, item_value in value.items():
            key_text = str(item_key)
            redacted[key_text] = _redact_json_value(item_value, key=key_text)
        return redacted
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_plain_text_body(text: str, *, max_body_chars: int) -> str:
    truncated_source = text[:max_body_chars]
    return _redact_text(truncated_source).rstrip()


def _redact_text(text: str) -> str:
    return redact_secret_like_values(text)


def _is_json_content_type(content_type: str) -> bool:
    return content_type == "application/json" or content_type.endswith("+json")
