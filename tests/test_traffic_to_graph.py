"""Tests for compiling redacted traffic into dependency graph exports."""

from datetime import UTC, datetime, timedelta

import pytest

from entroping.bridge.traffic_sessions import TrafficSessionRecord, build_traffic_session_candidate
from entroping.bridge.traffic_to_graph import (
    TrafficGraphCompilationError,
    compile_traffic_dependency_graph,
    render_dependency_graph_dot,
    render_dependency_graph_markdown,
    render_dependency_graph_mermaid,
)
from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse

BASE_TIME = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _exchange(
    *,
    method: str,
    url: str,
    status_code: int = 200,
    duration_ms: int | None = 100,
    offset_seconds: int = 0,
    redacted: bool = True,
) -> TrafficExchange:
    return TrafficExchange(
        captured_at=BASE_TIME + timedelta(seconds=offset_seconds),
        duration_ms=duration_ms,
        request=TrafficRequest(method=method, url=url),
        response=TrafficResponse(status_code=status_code),
        redacted=redacted,
    )


def test_compile_traffic_dependency_graph_aggregates_routes_and_latency() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url="https://api.example.test/orders/123",
                status_code=200,
                duration_ms=120,
            ),
            _exchange(
                method="GET",
                url="https://api.example.test/orders/456",
                status_code=503,
                duration_ms=240,
                offset_seconds=1,
            ),
            _exchange(
                method="POST",
                url="https://payments.example.test/charge",
                status_code=201,
                duration_ms=None,
                offset_seconds=2,
            ),
        ],
        name="checkout",
        target_url=None,
    )

    graph = compile_traffic_dependency_graph(session)

    assert graph.source_label == "client"
    assert len(graph.routes) == 2
    orders = graph.routes[0]
    assert orders.destination_host == "api.example.test"
    assert orders.method == "GET"
    assert orders.path_template == "/orders/{id}"
    assert orders.call_count == 2
    assert orders.failure_count == 1
    assert orders.latency_min_ms == 120
    assert orders.latency_average_ms == 180
    assert orders.latency_max_ms == 240
    payments = graph.routes[1]
    assert payments.destination_host == "payments.example.test"
    assert payments.method == "POST"
    assert payments.path_template == "/charge"
    assert payments.call_count == 1
    assert payments.failure_count == 0
    assert payments.latency_min_ms is None
    assert payments.latency_average_ms is None
    assert payments.latency_max_ms is None


def test_render_dependency_graph_exports_escape_traffic_labels() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url='https://api.example.test/path|break"quote<node>',
            )
        ],
        name="dangerous",
        target_url=None,
    )
    graph = compile_traffic_dependency_graph(session)

    mermaid = render_dependency_graph_mermaid(graph)
    markdown = render_dependency_graph_markdown(graph)
    dot = render_dependency_graph_dot(graph)

    assert mermaid.startswith("flowchart LR")
    assert 'path|break"quote<node>' not in mermaid
    assert 'path|break"quote<node>' not in markdown
    assert 'path|break"quote<node>' not in dot
    assert "GET /path/break&quot;quote&lt;node&gt;" in mermaid
    assert "/path\\|break&quot;quote&lt;node&gt;" in markdown
    assert r"GET /path|break\"quote<node>" in dot


def test_render_dependency_graph_outputs_route_statistics() -> None:
    session = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url="https://api.example.test/orders/123?token=%5BREDACTED%5D",
                status_code=500,
                duration_ms=99,
            )
        ],
        name="redacted",
        target_url=None,
    )
    graph = compile_traffic_dependency_graph(session)

    mermaid = render_dependency_graph_mermaid(graph)
    markdown = render_dependency_graph_markdown(graph)
    dot = render_dependency_graph_dot(graph)

    assert "token" not in mermaid
    assert "token" not in markdown
    assert "token" not in dot
    assert "calls=1" in mermaid
    assert "failures=1" in mermaid
    assert "99ms avg" in mermaid
    assert "| api.example.test | GET | /orders/{id} | 1 | 1 | 99 | 99 | 99 |" in markdown
    assert "calls=1, failures=1, avg=99ms" in dot


def test_compile_traffic_dependency_graph_rejects_empty_or_unredacted_sessions() -> None:
    empty = build_traffic_session_candidate([], name="empty", target_url=None)
    unsafe = build_traffic_session_candidate([], name="unsafe", target_url=None)
    unsafe_record = build_traffic_session_candidate(
        [
            _exchange(
                method="GET",
                url="https://api.example.test/unsafe",
                redacted=True,
            )
        ],
        name="safe_before_mutation",
        target_url=None,
    ).records[0]
    unsafe_session = unsafe.__class__(
        name=unsafe.name,
        target_origin=unsafe.target_origin,
        records=(
            TrafficSessionRecord(
                exchange=unsafe_record.exchange.model_copy(update={"redacted": False}),
                role="observed",
            ),
        ),
    )

    with pytest.raises(TrafficGraphCompilationError, match="contains no traffic records"):
        compile_traffic_dependency_graph(empty)
    with pytest.raises(TrafficGraphCompilationError, match="requires redacted traffic"):
        compile_traffic_dependency_graph(unsafe_session)
