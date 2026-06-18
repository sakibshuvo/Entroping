"""Tests for value-free validation of redacted traffic records."""

from datetime import UTC, datetime

from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse
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
