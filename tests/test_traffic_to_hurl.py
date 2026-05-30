"""Tests for compiling redacted traffic sessions into Hurl content."""

from datetime import UTC, datetime

import pytest

from entroping.bridge.traffic_sessions import build_traffic_session_candidate
from entroping.bridge.traffic_to_hurl import (
    TrafficHurlCompilationError,
    compile_traffic_session_to_hurl,
)
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _exchange(
    *,
    method: str = "POST",
    url: str = "https://api.example.test/checkout",
    request_body: str | None = '{"cart_id":"cart-1","password":"[REDACTED]"}',
    response_body: str | None = '{"id":"ord_123","status":"accepted","token":"[REDACTED]"}',
    content_type: str = "application/json",
    redacted: bool = True,
) -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method=method,
            url=url,
            headers={
                "Authorization": "[REDACTED]",
                "Content-Type": content_type,
                "Host": "api.example.test",
            },
            body=TrafficBody(
                content_type=content_type,
                size_bytes=len(request_body or ""),
                text=request_body,
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": content_type},
            body=TrafficBody(
                content_type=content_type,
                size_bytes=len(response_body or ""),
                text=response_body,
            ),
        ),
        redacted=redacted,
    )


def test_compile_traffic_session_generates_hurl_with_metadata_and_golden_assertions() -> None:
    session = build_traffic_session_candidate(
        [_exchange()],
        name="checkout_flow",
        target_url="https://api.example.test",
    )

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert generated.relative_path == "tests/generated/checkout_flow.hurl"
    assert "# entroping: tags=traffic,freeze" in generated.content
    assert "# entroping: source=traffic" in generated.content
    assert "# entroping: session=checkout_flow" in generated.content
    assert "# entroping: target=https://api.example.test" in generated.content
    assert "# entroping: role=target" in generated.content
    assert "POST https://api.example.test/checkout" in generated.content
    assert "Authorization: [REDACTED]" in generated.content
    assert "Host:" not in generated.content
    assert '"password":"[REDACTED]"' in generated.content
    assert "HTTP 201" in generated.content
    assert "[Asserts]" in generated.content
    assert 'header "Content-Type" contains "application/json"' in generated.content
    assert 'jsonpath "$.status" == "accepted"' in generated.content
    assert "$.id" not in generated.content
    assert "$.token" not in generated.content
    assert "ord_123" not in generated.content


def test_compile_traffic_session_omits_binary_body_text_and_raw_secrets() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                url="https://api.example.test/download",
                request_body="raw-binary-secret",
                response_body="raw-binary-response-secret",
                content_type="application/octet-stream",
            )
        ],
        name="download",
        target_url="https://api.example.test",
    )

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert "raw-binary-secret" not in generated.content
    assert "raw-binary-response-secret" not in generated.content
    assert "application/octet-stream" in generated.content
    assert "[Asserts]" not in generated.content


def test_compile_traffic_session_skips_non_finite_golden_values() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                response_body='{"score":NaN,"status":"accepted"}',
            )
        ],
        name="score",
        target_url="https://api.example.test",
    )

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert "$.score" not in generated.content
    assert 'jsonpath "$.status" == "accepted"' in generated.content


def test_compile_traffic_session_rejects_empty_session() -> None:
    session = build_traffic_session_candidate([], name="empty", target_url=None)

    with pytest.raises(TrafficHurlCompilationError, match="contains no traffic records"):
        compile_traffic_session_to_hurl(session, golden=False)


def test_compile_traffic_session_rejects_unredacted_records() -> None:
    session = build_traffic_session_candidate([], name="unsafe", target_url=None)
    unsafe_record = build_traffic_session_candidate(
        [_exchange(redacted=True)],
        name="safe",
        target_url=None,
    ).records[0]
    unsafe_exchange = unsafe_record.exchange.model_copy(update={"redacted": False})
    unsafe_session = session.__class__(
        name="unsafe",
        target_origin=None,
        records=(unsafe_record.__class__(exchange=unsafe_exchange, role="observed"),),
    )

    with pytest.raises(TrafficHurlCompilationError, match="requires redacted traffic"):
        compile_traffic_session_to_hurl(unsafe_session, golden=False)
