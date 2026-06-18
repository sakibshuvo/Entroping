"""Tests for compiling redacted traffic into WireMock-compatible mappings."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from entroping.bridge.traffic_sessions import TrafficSessionRecord, build_traffic_session_candidate
from entroping.bridge.traffic_to_wiremock import (
    TrafficWireMockCompilationError,
    compile_traffic_session_to_wiremock,
)
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

BASE_TIME = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _exchange(
    *,
    method: str = "POST",
    url: str = "https://payments.example.test/charge?token=%5BREDACTED%5D",
    status_code: int = 201,
    response_body: str | None = '{"approved":true,"token":"[REDACTED]"}',
    response_content_type: str | None = "application/json",
    response_headers: dict[str, str] | None = None,
    offset_seconds: int = 0,
    redacted: bool = True,
) -> TrafficExchange:
    headers = (
        {
            "Content-Type": response_content_type,
            "Set-Cookie": "[REDACTED]",
        }
        if response_content_type is not None
        else {"Set-Cookie": "[REDACTED]"}
    )
    if response_headers is not None:
        headers.update(response_headers)

    return TrafficExchange(
        captured_at=BASE_TIME + timedelta(seconds=offset_seconds),
        duration_ms=40,
        request=TrafficRequest(
            method=method,
            url=url,
            headers={"Authorization": "[REDACTED]", "Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=26,
                text='{"token":"[REDACTED]"}',
            ),
        ),
        response=TrafficResponse(
            status_code=status_code,
            headers=headers,
            body=(
                TrafficBody(
                    content_type=response_content_type,
                    size_bytes=len(response_body),
                    text=response_body,
                )
                if response_body is not None
                else None
            ),
        ),
        redacted=redacted,
    )


def test_compile_traffic_session_to_wiremock_selects_service_and_omits_request_secrets() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(url="https://api.example.test/checkout", status_code=200),
            _exchange(),
        ],
        name="refund_flow",
        target_url="https://api.example.test",
    )

    mappings = compile_traffic_session_to_wiremock(session, service="payments")

    assert len(mappings) == 1
    generated = mappings[0]
    assert generated.relative_path == "mocks/payments/refund_flow-001.json"
    payload = json.loads(generated.content)
    assert payload["request"] == {
        "method": "POST",
        "queryParameters": {"token": {"matches": ".+"}},
        "urlPath": "/charge",
    }
    assert payload["response"]["status"] == 201
    assert payload["response"]["headers"] == {"Content-Type": "application/json"}
    assert payload["response"]["jsonBody"] == {"approved": True, "token": "[REDACTED]"}
    assert "Authorization" not in generated.content
    assert "secret" not in generated.content
    assert "token=%5BREDACTED%5D" not in generated.content
    assert '"equalTo": "[REDACTED]"' not in generated.content


def test_compile_traffic_session_to_wiremock_adds_query_parameter_matchers() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url=(
                    "https://payments.example.test/charge"
                    "?tenant=north&mode=live&token=%5BREDACTED%5D"
                ),
                status_code=200,
            )
        ],
        name="query_flow",
        target_url=None,
    )

    mappings = compile_traffic_session_to_wiremock(session, service="payments")

    payload = json.loads(mappings[0].content)
    assert payload["request"] == {
        "method": "GET",
        "queryParameters": {
            "mode": {"equalTo": "live"},
            "tenant": {"equalTo": "north"},
            "token": {"matches": ".+"},
        },
        "urlPath": "/charge",
    }
    assert "token=%5BREDACTED%5D" not in mappings[0].content
    assert '"equalTo": "[REDACTED]"' not in mappings[0].content


def test_compile_traffic_session_to_wiremock_uses_exact_url_for_repeated_safe_query_keys() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url="https://payments.example.test/search?tag=fraud&tag=refund",
                status_code=200,
            )
        ],
        name="repeated_query_flow",
        target_url=None,
    )

    mappings = compile_traffic_session_to_wiremock(session, service="payments")

    payload = json.loads(mappings[0].content)
    assert payload["request"] == {
        "method": "GET",
        "url": "/search?tag=fraud&tag=refund",
    }


def test_compile_traffic_session_to_wiremock_matches_exact_host_and_escapes_json() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url='https://payments.example.test/quote"path',
                status_code=502,
                response_body="dependency failed",
            )
        ],
        name="quote.flow",
        target_url=None,
    )

    mappings = compile_traffic_session_to_wiremock(
        session,
        service="payments.example.test",
    )

    payload = json.loads(mappings[0].content)
    assert payload["request"] == {"method": "GET", "urlPath": '/quote"path'}
    assert payload["response"]["status"] == 502
    assert payload["response"]["body"] == "dependency failed"


def test_compile_traffic_session_to_wiremock_rejects_no_match_and_unsafe_inputs() -> None:
    session = build_traffic_session_candidate([_exchange()], name="refund_flow", target_url=None)

    with pytest.raises(TrafficWireMockCompilationError, match="No traffic records matched"):
        compile_traffic_session_to_wiremock(session, service="shipping")
    with pytest.raises(TrafficWireMockCompilationError, match="mock service"):
        compile_traffic_session_to_wiremock(session, service="../payments")


def test_compile_traffic_session_to_wiremock_rejects_empty_or_unredacted_sessions() -> None:
    empty = build_traffic_session_candidate([], name="empty", target_url=None)
    safe = build_traffic_session_candidate([_exchange()], name="safe", target_url=None)
    safe_record = safe.records[0]
    unsafe_session = safe.__class__(
        name=safe.name,
        target_origin=safe.target_origin,
        records=(
            TrafficSessionRecord(
                exchange=safe_record.exchange.model_copy(update={"redacted": False}),
                role="observed",
            ),
        ),
    )

    with pytest.raises(TrafficWireMockCompilationError, match="contains no traffic records"):
        compile_traffic_session_to_wiremock(empty, service="payments")
    with pytest.raises(TrafficWireMockCompilationError, match="requires redacted traffic"):
        compile_traffic_session_to_wiremock(unsafe_session, service="payments")


def test_compile_traffic_session_to_wiremock_rejects_secret_like_content() -> None:
    token = "sk-proj-" + ("a" * 24)
    unsafe_exchange = _exchange(response_body=f'{{"token":"{token}"}}')
    unsafe_session = build_traffic_session_candidate([], name="unsafe", target_url=None).__class__(
        name="unsafe",
        target_origin=None,
        records=(TrafficSessionRecord(exchange=unsafe_exchange, role="observed"),),
    )

    with pytest.raises(
        TrafficWireMockCompilationError,
        match="unredacted secret-like traffic content",
    ) as exc:
        compile_traffic_session_to_wiremock(unsafe_session, service="payments")

    assert token not in str(exc.value)


def test_compile_traffic_session_to_wiremock_rejects_records_without_response() -> None:
    safe = build_traffic_session_candidate([_exchange()], name="safe", target_url=None)
    safe_record = safe.records[0]
    missing_response = safe_record.exchange.model_copy(update={"response": None})
    session = safe.__class__(
        name=safe.name,
        target_origin=safe.target_origin,
        records=(TrafficSessionRecord(exchange=missing_response, role="observed"),),
    )

    with pytest.raises(TrafficWireMockCompilationError, match="requires response records"):
        compile_traffic_session_to_wiremock(session, service="payments")


def test_compile_traffic_session_to_wiremock_omits_redacted_headers_and_empty_body() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                response_body=None,
                response_headers={
                    "X-Trace": "[REDACTED]",
                    "Transfer-Encoding": "chunked",
                },
            )
        ],
        name="headers",
        target_url=None,
    )

    generated = compile_traffic_session_to_wiremock(session, service="payments")[0]
    payload = json.loads(generated.content)

    assert payload["response"] == {
        "headers": {"Content-Type": "application/json"},
        "status": 201,
    }
    assert "X-Trace" not in payload["response"]["headers"]
    assert "Transfer-Encoding" not in payload["response"]["headers"]


def test_compile_traffic_session_to_wiremock_renders_textual_body() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                response_body="dependency failed",
                response_content_type="text/plain; charset=utf-8",
            )
        ],
        name="plain_text",
        target_url=None,
    )

    generated = compile_traffic_session_to_wiremock(session, service="payments")[0]
    payload = json.loads(generated.content)

    assert payload["response"]["body"] == "dependency failed"


def test_compile_traffic_session_to_wiremock_omits_unknown_content_type_body() -> None:
    session = TrafficSessionRecord(
        exchange=_exchange(
            response_body="opaque body",
            response_content_type=None,
        ),
        role="observed",
    )
    candidate = build_traffic_session_candidate([], name="unknown", target_url=None).__class__(
        name="unknown",
        target_origin=None,
        records=(session,),
    )

    generated = compile_traffic_session_to_wiremock(candidate, service="payments")[0]
    payload = json.loads(generated.content)

    assert payload["response"] == {"status": 201}


@pytest.mark.parametrize(
    ("service", "message"),
    [
        (" ", "mock service must not be empty"),
        ("pay\nments", "mock service must not contain control characters"),
        (".payments", "mock service must be a safe file stem"),
        ("pay ments!", "mock service must contain only letters"),
    ],
)
def test_compile_traffic_session_to_wiremock_rejects_invalid_service_stems(
    service: str,
    message: str,
) -> None:
    session = build_traffic_session_candidate([_exchange()], name="refund_flow", target_url=None)

    with pytest.raises(TrafficWireMockCompilationError, match=message):
        compile_traffic_session_to_wiremock(session, service=service)
