"""Tests for auditing captured traffic routes against OpenAPI."""

import json

import pytest

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
from entroping.bridge.traffic_openapi_audit import (
    TrafficOpenApiAuditError,
    audit_traffic_routes_against_openapi,
    render_traffic_openapi_markdown,
    traffic_openapi_report_to_dict,
)
from entroping.bridge.traffic_to_graph import TrafficDependencyGraph, TrafficDependencyRoute


def _route(
    *,
    method: str,
    path_template: str,
    call_count: int = 1,
    failure_count: int = 0,
) -> TrafficDependencyRoute:
    return TrafficDependencyRoute(
        destination_host="api.example.test",
        method=method,
        path_template=path_template,
        call_count=call_count,
        failure_count=failure_count,
        latency_min_ms=None,
        latency_average_ms=None,
        latency_max_ms=None,
    )


def test_traffic_openapi_audit_reports_documented_undocumented_and_spec_only_routes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
            "/orders/{order_id}": {
                "get": {
                    "operationId": "getOrder",
                    "responses": {"200": {"description": "ok"}},
                },
            },
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    graph = TrafficDependencyGraph(
        source_label="client",
        routes=(
            _route(method="GET", path_template="/health"),
            _route(method="GET", path_template="/orders/{id}", call_count=2),
            _route(method="DELETE", path_template="/internal-debug", failure_count=1),
        ),
    )

    report = audit_traffic_routes_against_openapi(document, graph)

    assert not report.passed
    assert [(row.method, row.path_template, row.operation_ids) for row in report.documented] == [
        ("GET", "/health", ("getHealth",)),
        ("GET", "/orders/{id}", ("getOrder",)),
    ]
    assert [(row.method, row.path_template) for row in report.undocumented] == [
        ("DELETE", "/internal-debug"),
    ]
    assert [(row.method, row.path_template, row.operation_id) for row in report.spec_only] == [
        ("POST", "/checkout", "createCheckout"),
    ]

    payload = traffic_openapi_report_to_dict(report)
    assert payload["summary"] == {
        "documented_routes": 2,
        "undocumented_routes": 1,
        "spec_only_routes": 1,
    }
    assert payload["undocumented_routes"] == [
        {
            "method": "DELETE",
            "path_template": "/internal-debug",
            "call_count": 1,
            "failure_count": 1,
        }
    ]
    assert "DELETE /internal-debug" in render_traffic_openapi_markdown(report)


def test_traffic_openapi_audit_strips_query_fragments_and_does_not_report_values() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    graph = TrafficDependencyGraph(
        source_label="client",
        routes=(
            TrafficDependencyRoute(
                destination_host="user:live-secret@api.example.test",
                method="POST",
                path_template="/checkout?token=live-secret#frag",
                call_count=1,
                failure_count=0,
                latency_min_ms=10,
                latency_average_ms=10,
                latency_max_ms=10,
            ),
        ),
    )

    report = audit_traffic_routes_against_openapi(document, graph)

    assert report.passed
    assert report.documented[0].path_template == "/checkout"
    serialized = json.dumps(traffic_openapi_report_to_dict(report), sort_keys=True)
    markdown = render_traffic_openapi_markdown(report)
    assert "live-secret" not in serialized
    assert "live-secret" not in markdown
    assert "token" not in serialized
    assert "token" not in markdown
    assert "?" not in serialized
    assert "?" not in markdown


def test_traffic_openapi_audit_rejects_unsafe_route_shapes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    graph = TrafficDependencyGraph(
        source_label="client",
        routes=(
            _route(method="GET\nPOST", path_template="/health"),
        ),
    )

    with pytest.raises(TrafficOpenApiAuditError, match="traffic route method is unsafe"):
        audit_traffic_routes_against_openapi(document, graph)


def test_traffic_openapi_audit_accepts_root_fallback_ids_and_empty_paths() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
    }
    graph = TrafficDependencyGraph(
        source_label="client",
        routes=(
            _route(method="GET", path_template=""),
        ),
    )

    report = audit_traffic_routes_against_openapi(document, graph)

    assert report.passed
    assert report.documented[0].path_template == "/"
    assert report.documented[0].operation_ids == ("get_root",)


@pytest.mark.parametrize(
    ("document", "message"),
    (
        ({"openapi": "3.1.0"}, "paths mapping"),
        (
            {"openapi": "3.1.0", "paths": {"health": {}}},
            "absolute path strings",
        ),
        (
            {"openapi": "3.1.0", "paths": {"/health": "bad"}},
            "OpenAPI path '/health' must be a mapping",
        ),
        (
            {"openapi": "3.1.0", "paths": {"/health": {"summary": "ignored"}}},
            "supported HTTP operations",
        ),
        (
            {
                "openapi": "3.1.0",
                "paths": {
                    "/one": {"get": {"operationId": "same", "responses": {"200": {}}}},
                    "/two": {"get": {"operationId": "same", "responses": {"200": {}}}},
                },
            },
            "operationId must be unique",
        ),
        (
            {
                "openapi": "3.1.0",
                "paths": {
                    "/health": {"get": {"operationId": "get\nHealth", "responses": {"200": {}}}},
                },
            },
            "operationId is not safe",
        ),
        ({"openapi": "3.1.0", "paths": {1: {}}}, "paths keys must be strings"),
    ),
)
def test_traffic_openapi_audit_rejects_malformed_openapi_documents(
    document: dict[str, object],
    message: str,
) -> None:
    graph = TrafficDependencyGraph(
        source_label="client",
        routes=(_route(method="GET", path_template="/health"),),
    )

    with pytest.raises(OpenApiCompilationError, match=message):
        audit_traffic_routes_against_openapi(document, graph)


@pytest.mark.parametrize(
    ("route", "message"),
    (
        (_route(method="TRACE", path_template="/health", call_count=-1), "counts"),
        (_route(method="GET", path_template="health"), "path template is unsafe"),
        (_route(method="GET", path_template="/bad\npath"), "path template is unsafe"),
        (_route(method="BREW", path_template="/health"), "method is unsafe"),
        (_route(method="", path_template="/health"), "method is unsafe"),
    ),
)
def test_traffic_openapi_audit_rejects_unsafe_route_details(
    route: TrafficDependencyRoute,
    message: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    graph = TrafficDependencyGraph(source_label="client", routes=(route,))

    with pytest.raises(TrafficOpenApiAuditError, match=message):
        audit_traffic_routes_against_openapi(document, graph)
