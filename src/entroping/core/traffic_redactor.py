"""Redaction pipeline for Eye traffic before local persistence."""

import json
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from entroping.models.secrets import (
    REDACTED,
    is_sensitive_header_name,
    is_sensitive_key,
    redact_secret_like_values,
)
from entroping.models.traffic import (
    DEFAULT_REDACTION_CONFIDENCE,
    RedactionConfidence,
    TrafficBody,
    TrafficExchange,
    TrafficRequest,
    TrafficResponse,
)

DEFAULT_MAX_BODY_CHARS = 4096
_BODY_REDACTION_SCAN_EXTRA_CHARS = 512
_MULTIPART_BODY_SUMMARY_TEMPLATE = "[REDACTED {content_type} body]"
_OPAQUE_HEX_VALUE_RE = re.compile(r"(?<![A-Fa-f0-9])[A-Fa-f0-9]{48,}(?![A-Fa-f0-9])")
_REDACTED_PATH_SEGMENT = quote(REDACTED, safe="")


def redact_traffic_exchange(
    exchange: TrafficExchange,
    *,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> TrafficExchange:
    """Return a copy of ``exchange`` safe for local persistence."""

    if max_body_chars <= 0:
        msg = "max_body_chars must be positive"
        raise ValueError(msg)

    redacted_request = _redact_request(
        exchange.request,
        max_body_chars=max_body_chars,
    )
    redacted_response = (
        _redact_response(exchange.response, max_body_chars=max_body_chars)
        if exchange.response is not None
        else None
    )

    return TrafficExchange(
        captured_at=exchange.captured_at,
        duration_ms=exchange.duration_ms,
        request=redacted_request,
        response=redacted_response,
        redacted=True,
        redaction_confidence=_combine_redaction_confidence(
            redacted_request.body,
            redacted_response.body if redacted_response is not None else None,
        ),
    )


def _redact_request(request: TrafficRequest, *, max_body_chars: int) -> TrafficRequest:
    redacted_body, _ = _redact_body(request.body, max_body_chars=max_body_chars)
    return TrafficRequest(
        method=request.method,
        url=_redact_url(request.url),
        headers=_redact_headers(request.headers),
        body=redacted_body,
    )


def _redact_response(response: TrafficResponse, *, max_body_chars: int) -> TrafficResponse:
    redacted_body, _ = _redact_body(response.body, max_body_chars=max_body_chars)
    return TrafficResponse(
        status_code=response.status_code,
        headers=_redact_headers(response.headers),
        body=redacted_body,
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
    return urlunsplit((parsed.scheme, netloc, _redact_path(parsed.path), query, ""))


def _redact_path(path: str) -> str:
    return "/".join(_redact_path_segment(segment) for segment in path.split("/"))


def _redact_path_segment(segment: str) -> str:
    if not segment:
        return segment
    decoded = unquote(segment)
    if _redact_text(decoded) != decoded:
        return _REDACTED_PATH_SEGMENT
    return segment


def _redact_body(
    body: TrafficBody | None,
    *,
    max_body_chars: int,
) -> tuple[TrafficBody | None, RedactionConfidence]:
    if body is None:
        return None, DEFAULT_REDACTION_CONFIDENCE
    if body.text is None:
        return body.model_copy(update={"truncated": body.truncated}), DEFAULT_REDACTION_CONFIDENCE

    content_type = (body.content_type or "").split(";", maxsplit=1)[0].lower().strip()
    if _is_multipart_content_type(content_type):
        return TrafficBody(
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            text=_MULTIPART_BODY_SUMMARY_TEMPLATE.format(content_type=content_type),
            truncated=True,
            redaction_confidence="low",
        ), "low"

    text_for_redaction, input_truncated = _bounded_body_text(
        body.text,
        max_body_chars=max_body_chars,
    )
    redacted_text = (
        _redact_json_body(text_for_redaction)
        if _is_json_content_type(content_type)
        else _redact_plain_text_body(text_for_redaction)
    )
    redaction_confidence: RedactionConfidence = "low"
    if _is_json_content_type(content_type):
        redaction_confidence = _redact_json_body_confidence(text_for_redaction)

    truncated = (
        body.truncated
        or input_truncated
        or len(body.text) > max_body_chars
        or len(redacted_text) > max_body_chars
    )
    if len(redacted_text) > max_body_chars:
        redacted_text = redacted_text[:max_body_chars]

    return TrafficBody(
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        text=redacted_text,
        redaction_confidence=redaction_confidence,
        truncated=truncated,
    ), redaction_confidence


def _bounded_body_text(text: str, *, max_body_chars: int) -> tuple[str, bool]:
    scan_limit = max_body_chars + _BODY_REDACTION_SCAN_EXTRA_CHARS
    if len(text) <= scan_limit:
        return text, False
    return text[:scan_limit], True


def _redact_json_body(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _redact_text(text)
    return json.dumps(_redact_json_value(parsed), separators=(",", ":"), sort_keys=True)


def _redact_json_body_confidence(text: str) -> RedactionConfidence:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return "low"
    return "high"


def _combine_redaction_confidence(
    request_body: TrafficBody | None,
    response_body: TrafficBody | None,
) -> RedactionConfidence:
    if (
        request_body is not None
        and request_body.redaction_confidence == "low"
        or response_body is not None
        and response_body.redaction_confidence == "low"
    ):
        return "low"
    return DEFAULT_REDACTION_CONFIDENCE


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


def _redact_plain_text_body(text: str) -> str:
    return _redact_text(text).rstrip()


def _redact_text(text: str) -> str:
    return _OPAQUE_HEX_VALUE_RE.sub(REDACTED, redact_secret_like_values(text))


def _is_json_content_type(content_type: str) -> bool:
    return content_type == "application/json" or content_type.endswith("+json")


def _is_multipart_content_type(content_type: str) -> bool:
    return content_type.startswith("multipart/")
