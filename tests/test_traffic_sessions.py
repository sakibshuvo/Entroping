"""Tests for pure traffic filtering and session candidate building."""

from datetime import UTC, datetime, timedelta

import pytest

from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
    build_traffic_session_candidate,
)
from entroping.models.traffic import (
    TrafficBody,
    TrafficExchange,
    TrafficRequest,
    TrafficResponse,
)

BASE_TIME = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _exchange(
    *,
    url: str,
    status_code: int = 200,
    offset_seconds: int = 0,
    content_type: str | None = "application/json",
    body_text: str | None = '{"ok":true}',
    redacted: bool = True,
) -> TrafficExchange:
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["Content-Type"] = content_type

    return TrafficExchange(
        captured_at=BASE_TIME + timedelta(seconds=offset_seconds),
        duration_ms=25,
        request=TrafficRequest(
            method="GET",
            url=url,
            headers=headers,
            body=TrafficBody(content_type=content_type, size_bytes=0, text=body_text),
        ),
        response=TrafficResponse(
            status_code=status_code,
            headers=headers,
            body=TrafficBody(content_type=content_type, size_bytes=0, text=body_text),
        ),
        redacted=redacted,
    )


def test_session_filters_static_assets_and_retains_failed_api_calls() -> None:
    static_asset = _exchange(
        url="https://api.example.test/assets/app.js",
        status_code=200,
        offset_seconds=0,
    )
    failed_target = _exchange(
        url="https://api.example.test/checkout",
        status_code=500,
        offset_seconds=1,
    )
    dependency = _exchange(
        url="https://payments.example.test/charge",
        status_code=201,
        offset_seconds=2,
    )

    candidate = build_traffic_session_candidate(
        [static_asset, failed_target, dependency],
        name="checkout_flow",
        target_url="https://api.example.test",
    )

    assert candidate.name == "checkout_flow"
    assert candidate.target_origin == "https://api.example.test"
    assert [item.exchange.request.path for item in candidate.records] == ["/checkout", "/charge"]
    statuses: list[int] = []
    for item in candidate.records:
        response = item.exchange.response
        assert response is not None
        statuses.append(response.status_code)
    assert statuses == [500, 201]
    assert [item.role for item in candidate.records] == ["target", "dependency"]


def test_session_orders_by_capture_time_and_handles_empty_state() -> None:
    latest = _exchange(url="https://api.example.test/latest", offset_seconds=30)
    earliest = _exchange(url="https://api.example.test/earliest", offset_seconds=10)
    middle = _exchange(url="https://api.example.test/middle", offset_seconds=20)

    candidate = build_traffic_session_candidate(
        [latest, earliest, middle],
        name="ordered",
        target_url="https://api.example.test",
    )
    empty = build_traffic_session_candidate([], name="empty", target_url=None)

    assert [item.exchange.request.path for item in candidate.records] == [
        "/earliest",
        "/middle",
        "/latest",
    ]
    assert empty.name == "empty"
    assert empty.target_origin is None
    assert empty.records == ()


def test_session_without_target_marks_records_as_observed() -> None:
    candidate = build_traffic_session_candidate(
        [_exchange(url="https://api.example.test/checkout")],
        name="observed",
        target_url=None,
    )

    assert candidate.target_origin is None
    assert [item.role for item in candidate.records] == ["observed"]


def test_session_omits_binary_body_text_without_mutating_source() -> None:
    binary = _exchange(
        url="https://api.example.test/download",
        content_type="application/octet-stream",
        body_text="raw-binary-summary",
    )

    candidate = build_traffic_session_candidate(
        [binary],
        name="download",
        target_url="https://api.example.test",
    )

    request_body = candidate.records[0].exchange.request.body
    response = candidate.records[0].exchange.response
    assert request_body is not None
    assert request_body.text is None
    assert response is not None
    assert response.body is not None
    assert response.body.text is None
    assert binary.request.body is not None
    assert binary.request.body.text == "raw-binary-summary"


def test_session_requires_redacted_traffic() -> None:
    with pytest.raises(TrafficSessionError, match="requires redacted traffic"):
        build_traffic_session_candidate(
            [_exchange(url="https://api.example.test/checkout", redacted=False)],
            name="unsafe",
            target_url="https://api.example.test",
        )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("  ", "traffic session name must not be empty"),
        ("bad\nname", "traffic session name must not contain control characters"),
    ],
)
def test_session_rejects_invalid_names(name: str, message: str) -> None:
    with pytest.raises(TrafficSessionError, match=message):
        build_traffic_session_candidate(
            [_exchange(url="https://api.example.test/checkout")],
            name=name,
            target_url="https://api.example.test",
        )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("https://api.example.test\n", "target_url must not contain control characters"),
        ("ftp://api.example.test", "target_url must be an absolute http or https URL"),
        ("api.example.test", "target_url must be an absolute http or https URL"),
    ],
)
def test_session_rejects_invalid_target_urls(target_url: str, message: str) -> None:
    with pytest.raises(TrafficSessionError, match=message):
        build_traffic_session_candidate(
            [_exchange(url="https://api.example.test/checkout")],
            name="checkout",
            target_url=target_url,
        )


def test_session_omits_body_text_when_content_type_is_unknown() -> None:
    unknown_body_type = _exchange(
        url="https://api.example.test/download",
        content_type=None,
        body_text="opaque-body-summary",
    )

    candidate = build_traffic_session_candidate(
        [unknown_body_type],
        name="download",
        target_url="https://api.example.test",
    )

    request_body = candidate.records[0].exchange.request.body
    response = candidate.records[0].exchange.response
    assert request_body is not None
    assert request_body.text is None
    assert response is not None
    assert response.body is not None
    assert response.body.text is None
