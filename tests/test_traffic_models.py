"""Validation tests for traffic domain models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def test_traffic_body_rejects_control_characters_in_content_type() -> None:
    with pytest.raises(ValidationError, match="content type"):
        TrafficBody(content_type="application/json\nx", size_bytes=1)


@pytest.mark.parametrize("method", ["", "GE\nT", "POST1"])
def test_traffic_request_rejects_invalid_http_method(method: str) -> None:
    with pytest.raises(ValidationError, match="HTTP method"):
        TrafficRequest(method=method, url="https://api.example.test/checkout")


@pytest.mark.parametrize("url", ["ftp://api.example.test/checkout", "https://api.example.test/\n"])
def test_traffic_request_rejects_invalid_url(url: str) -> None:
    with pytest.raises(ValidationError, match="URL"):
        TrafficRequest(method="GET", url=url)


def test_traffic_exchange_requires_timezone_aware_capture_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TrafficExchange(
            captured_at=datetime(2026, 5, 30, 12, 0),
            request=TrafficRequest(method="GET", url="https://api.example.test/checkout"),
            response=TrafficResponse(status_code=200),
        )


@pytest.mark.parametrize(
    "headers",
    [
        {"Bad:Name": "ok"},
        {"X-Test": "bad\nvalue"},
    ],
)
def test_traffic_headers_reject_invalid_names_and_values(headers: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="header"):
        TrafficRequest(method="GET", url="https://api.example.test/checkout", headers=headers)


def test_traffic_headers_allow_tabs_in_values() -> None:
    request = TrafficRequest(
        method="GET",
        url="https://api.example.test/checkout",
        headers={"X-Trace": "trace\tsegment"},
    )

    assert request.headers == {"X-Trace": "trace\tsegment"}
