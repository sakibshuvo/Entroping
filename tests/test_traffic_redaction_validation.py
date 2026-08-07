"""Tests for value-free validation of redacted traffic records."""

from datetime import UTC, datetime

from entroping.models.traffic import (
    TrafficBody,
    TrafficExchange,
    TrafficRequest,
    TrafficResponse,
)
from entroping.models.traffic_redaction import redacted_traffic_violation_summary


def _exchange(url: str) -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        request=TrafficRequest(method="GET", url=url, headers={}, body=None),
        response=TrafficResponse(status_code=200),
        redacted=True,
    )


def test_redacted_traffic_validation_reports_userinfo_without_values() -> None:
    summary = redacted_traffic_violation_summary(
        _exchange("https://user:pass@example.test/checkout")
    )

    assert summary == "unredacted secret-like traffic content in request.url.userinfo"
    assert "user:pass" not in summary


def test_redacted_traffic_validation_reports_secret_like_non_sensitive_query_value() -> None:
    token = "sk-proj-" + ("a" * 24)
    summary = redacted_traffic_violation_summary(
        _exchange(f"https://example.test/checkout?state={token}")
    )

    assert summary == "unredacted secret-like traffic content in request.url.query"
    assert token not in summary


def test_redacted_traffic_validation_reports_short_credential_body_without_values() -> None:
    raw_value = "123456"
    exchange = _exchange("https://example.test/checkout").model_copy(
        update={
            "request": TrafficRequest(
                method="POST",
                url="https://example.test/checkout",
                headers={"Content-Type": "application/json"},
                body=TrafficBody(
                    content_type="application/json",
                    size_bytes=48,
                    text=f'{{"OTP":{raw_value},"status":"ready"}}',
                ),
            )
        }
    )

    summary = redacted_traffic_violation_summary(exchange)

    assert summary == "unredacted secret-like traffic content in request.body"
    assert raw_value not in summary
