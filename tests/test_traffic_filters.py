"""Tests for redacted traffic capture filters."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from entroping.core.traffic_filters import (
    TrafficCaptureFilters,
    TrafficFilterError,
    filter_traffic_exchanges,
)
from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse


def _exchange(
    *,
    method: str,
    url: str,
    redacted: bool = True,
) -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        request=TrafficRequest(method=method, url=url),
        response=TrafficResponse(status_code=200),
        redacted=redacted,
    )


def test_filters_include_by_host_method_and_path_prefix_without_query_values() -> None:
    exchanges = (
        _exchange(method="GET", url="https://api.example.test/checkout?token=live-secret"),
        _exchange(method="POST", url="https://api.example.test/checkout"),
        _exchange(method="GET", url="https://payments.example.test/checkout"),
        _exchange(method="GET", url="https://api.example.test/orders"),
    )

    filtered = filter_traffic_exchanges(
        exchanges,
        TrafficCaptureFilters(
            include_hosts=("api.example.test",),
            include_methods=("get",),
            include_paths=("/checkout",),
        ),
    )

    assert [exchange.request.url for exchange in filtered] == [
        "https://api.example.test/checkout?token=live-secret"
    ]


def test_filters_apply_exclusion_precedence_and_path_globs() -> None:
    exchanges = (
        _exchange(method="GET", url="https://api.example.test/checkout"),
        _exchange(method="GET", url="https://api.example.test/checkout/internal/health"),
        _exchange(method="DELETE", url="https://api.example.test/checkout/ord_123"),
    )

    filtered = filter_traffic_exchanges(
        exchanges,
        TrafficCaptureFilters(
            include_hosts=("api.example.test",),
            include_paths=("/checkout",),
            exclude_methods=("delete",),
            exclude_paths=("/checkout/internal/*",),
        ),
    )

    assert [exchange.request.path for exchange in filtered] == ["/checkout"]


def test_filters_reject_unredacted_records_before_matching() -> None:
    with pytest.raises(TrafficFilterError, match="requires redacted traffic"):
        filter_traffic_exchanges(
            (_exchange(method="GET", url="https://api.example.test/checkout", redacted=False),),
            TrafficCaptureFilters(include_hosts=("api.example.test",)),
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: TrafficCaptureFilters(include_hosts=("https://api.example.test",)), "host"),
        (lambda: TrafficCaptureFilters(include_hosts=("api.example.test/path",)), "host"),
        (lambda: TrafficCaptureFilters(include_hosts=("api.example.test\n",)), "host"),
        (lambda: TrafficCaptureFilters(include_methods=("GET\n",)), "method"),
        (lambda: TrafficCaptureFilters(include_methods=("bad method",)), "method"),
        (lambda: TrafficCaptureFilters(include_paths=("checkout",)), "path"),
        (lambda: TrafficCaptureFilters(include_paths=("/checkout\n",)), "path"),
        (lambda: TrafficCaptureFilters(include_paths=("/checkout?token=secret",)), "path"),
        (lambda: TrafficCaptureFilters(exclude_paths=("https://api.example.test/x",)), "path"),
    ],
)
def test_filters_reject_unsafe_filter_values(
    factory: Callable[[], TrafficCaptureFilters],
    message: str,
) -> None:
    with pytest.raises(TrafficFilterError, match=message):
        factory()


def test_empty_filters_preserve_input_order() -> None:
    first = _exchange(method="GET", url="https://api.example.test/first")
    second = _exchange(method="GET", url="https://api.example.test/second")

    assert filter_traffic_exchanges((first, second), TrafficCaptureFilters()) == (first, second)


def test_filter_paths_do_not_match_query_strings() -> None:
    exchange = _exchange(method="GET", url="https://api.example.test/checkout?flow=internal")

    assert filter_traffic_exchanges(
        (exchange,),
        TrafficCaptureFilters(include_paths=("/checkout",)),
    ) == (exchange,)
    with pytest.raises(TrafficFilterError, match="path"):
        TrafficCaptureFilters(include_paths=("/checkout?flow=internal",))
