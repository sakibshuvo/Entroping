"""Tests for Eye traffic redaction before persistence."""

from datetime import UTC, datetime

import pytest

from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _raw_exchange() -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=42,
        request=TrafficRequest(
            method="POST",
            url="https://api.example.test/checkout?access_token=query-secret&cart_id=cart-1",
            headers={
                "Authorization": "Bearer header-secret",
                "Cookie": "session_id=cookie-secret",
                "Content-Type": "application/json",
                "X-Request-ID": "req-123",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=69,
                text='{"password":"body-secret","cart_id":"cart-1","nested":{"api_key":"key-secret"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=200,
            headers={
                "Set-Cookie": "session_id=response-cookie",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=42,
                text='{"token":"response-token","ok":true}',
            ),
        ),
    )


def test_redactor_removes_headers_query_params_and_json_secret_fields() -> None:
    redacted = redact_traffic_exchange(_raw_exchange())

    serialized = redacted.model_dump_json()
    assert redacted.redacted is True
    assert redacted.request.url == "https://api.example.test/checkout?access_token=%5BREDACTED%5D&cart_id=cart-1"
    assert redacted.request.headers["Authorization"] == "[REDACTED]"
    assert redacted.request.headers["Cookie"] == "[REDACTED]"
    assert redacted.response is not None
    assert redacted.response.headers["Set-Cookie"] == "[REDACTED]"
    assert "body-secret" not in serialized
    assert "key-secret" not in serialized
    assert "response-token" not in serialized
    assert "header-secret" not in serialized
    assert "cookie-secret" not in serialized
    request_body = redacted.request.body
    assert request_body is not None
    assert request_body.text is not None
    assert '"password":"[REDACTED]"' in request_body.text
    assert '"api_key":"[REDACTED]"' in request_body.text


def test_redactor_treats_json_subtype_bodies_as_structured_json() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"Content-Type": "application/problem+json"},
                    "body": TrafficBody(
                        content_type="application/problem+json",
                        size_bytes=31,
                        text='{"token":"problem-secret","ok":true}',
                    ),
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    serialized = redacted.model_dump_json()
    assert "problem-secret" not in serialized
    assert redacted.request.body is not None
    assert redacted.request.body.text is not None
    assert '"token":"[REDACTED]"' in redacted.request.body.text


def test_redactor_rejects_non_positive_body_limit() -> None:
    with pytest.raises(ValueError, match="max_body_chars must be positive"):
        redact_traffic_exchange(_raw_exchange(), max_body_chars=0)


def test_redactor_preserves_non_text_body_metadata() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"Content-Type": "application/octet-stream"},
                    "body": TrafficBody(
                        content_type="application/octet-stream",
                        size_bytes=128,
                        text=None,
                        truncated=True,
                    ),
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    assert redacted.request.body is not None
    assert redacted.request.body.text is None
    assert redacted.request.body.truncated is True
    assert redacted.request.body.content_type == "application/octet-stream"


def test_redactor_preserves_absent_bodies() -> None:
    base = _raw_exchange()
    assert base.response is not None
    exchange = base.model_copy(
        update={
            "request": base.request.model_copy(update={"body": None}),
            "response": base.response.model_copy(update={"body": None}),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    assert redacted.request.body is None
    assert redacted.response is not None
    assert redacted.response.body is None


def test_redactor_falls_back_to_text_redaction_for_invalid_json() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "body": TrafficBody(
                        content_type="application/json",
                        size_bytes=32,
                        text='{"token":"broken-secret"',
                    ),
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    assert redacted.request.body is not None
    assert redacted.request.body.text == '{"token":"[REDACTED]"'
    assert "broken-secret" not in redacted.model_dump_json()


def test_redactor_redacts_secret_values_inside_json_arrays() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "body": TrafficBody(
                        content_type="application/json",
                        size_bytes=96,
                        text='[{"token":"array-secret"},"Bearer inline-secret",{"ok":true}]',
                    ),
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    assert redacted.request.body is not None
    assert redacted.request.body.text == (
        '[{"token":"[REDACTED]"},"Bearer [REDACTED]",{"ok":true}]'
    )
    assert "array-secret" not in redacted.model_dump_json()
    assert "inline-secret" not in redacted.model_dump_json()


def test_redactor_redacts_token_shaped_values_in_non_sensitive_fields() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"X-Request-ID": "req-sk-proj-live-secret"},
                    "body": TrafficBody(
                        content_type="application/json",
                        size_bytes=64,
                        text='{"note":"sk-proj-live-secret","safe":"ok"}',
                    ),
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    serialized = redacted.model_dump_json()
    assert "sk-proj-live-secret" not in serialized
    assert redacted.request.headers["X-Request-ID"] == "req-[REDACTED]"
    assert redacted.request.body is not None
    assert redacted.request.body.text == '{"note":"[REDACTED]","safe":"ok"}'


def test_redactor_removes_url_userinfo_credentials() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "url": "https://user:pass@example.test/checkout?token=query-secret",
                },
            ),
        },
    )

    redacted = redact_traffic_exchange(exchange)

    assert redacted.request.url == "https://example.test/checkout?token=%5BREDACTED%5D"
    assert redacted.request.host == "example.test"
    assert "user:pass" not in redacted.model_dump_json()


def test_redactor_bounds_text_body_summaries() -> None:
    exchange = _raw_exchange().model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"Content-Type": "text/plain"},
                    "body": TrafficBody(
                        content_type="text/plain",
                        size_bytes=64,
                        text="token=secret-value " + ("a" * 64),
                    ),
                }
            )
        }
    )

    redacted = redact_traffic_exchange(exchange, max_body_chars=16)

    request_body = redacted.request.body
    assert request_body is not None
    assert request_body.text == "token=[REDACTED]"
    assert request_body.truncated is True
    assert "secret-value" not in redacted.model_dump_json()


def test_traffic_models_reject_control_characters_in_boundaries() -> None:
    with pytest.raises(ValueError, match="must not contain control characters"):
        TrafficRequest(method="GET", url="https://example.test/\nnext", headers={}, body=None)

    with pytest.raises(ValueError, match="header names"):
        TrafficRequest(
            method="GET",
            url="https://example.test/",
            headers={"Bad\nName": "x"},
            body=None,
        )
