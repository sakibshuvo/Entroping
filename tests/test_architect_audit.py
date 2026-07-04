"""Unit tests for deterministic Architect audit coverage."""

from pathlib import Path

import pytest

from entroping.bridge.openapi_audit import (
    OPENAPI_AUDIT_SCHEMA_VERSION,
    audit_openapi_coverage,
    audit_report_to_dict,
    render_audit_markdown,
)
from entroping.bridge.openapi_diff import audit_openapi_breaking_changes
from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
from entroping.bridge.traffic_openapi_audit import (
    TrafficOpenApiAuditReport,
    TrafficUndocumentedRoute,
)
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest


def test_audit_openapi_coverage_reports_missing_operations() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
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
    covered = HurlTest(
        path=Path("tests/generated/get_health.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )
    unrelated = HurlTest(
        path=Path("tests/manual_checkout.hurl"),
        metadata=HurlMetadata(meta={"operation_id": "createCheckout"}),
    )

    report = audit_openapi_coverage(document, [covered, unrelated])

    assert report.total_operations == 2
    assert report.covered_operations == 1
    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["createCheckout"]
    assert audit_report_to_dict(report)["status"] == "fail"
    assert "createCheckout" in render_audit_markdown(report)


def test_audit_openapi_coverage_reports_operation_matrix_and_stale_references() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {"201": {"description": "created"}},
                },
            },
            "/orders/{order_id}": {
                "get": {
                    "operationId": "getOrder",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    health = HurlTest(
        path=Path("tests/generated/get_health.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )
    order_generated = HurlTest(
        path=Path("tests/generated/get_order.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getOrder"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/orders/123", path="/orders/123"),),
    )
    order_manual = HurlTest(
        path=Path("tests/manual/get_order_smoke.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getOrder"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/orders/456", path="/orders/456"),),
    )
    stale = HurlTest(
        path=Path("tests/generated/delete_order.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "deleteOrder"}),
        exchanges=(
            HurlExchange(method="DELETE", url="{{base_url}}/orders/123", path="/orders/123"),
        ),
    )

    report = audit_openapi_coverage(
        document,
        [health, order_manual, stale, order_generated],
    )

    assert report.covered_operations == 2
    assert report.missing_operations == 1
    assert [(row.operation_id, row.status, row.test_paths) for row in report.operation_matrix] == [
        ("getHealth", "covered", ("tests/generated/get_health.hurl",)),
        ("createCheckout", "uncovered", ()),
        (
            "getOrder",
            "ambiguous",
            ("tests/generated/get_order.hurl", "tests/manual/get_order_smoke.hurl"),
        ),
    ]
    assert report.stale_references[0].operation_id == "deleteOrder"
    assert report.stale_references[0].test_path == "tests/generated/delete_order.hurl"

    payload = audit_report_to_dict(report)
    assert payload["schema_version"] == OPENAPI_AUDIT_SCHEMA_VERSION
    summary = payload["summary"]
    matrix = payload["operation_matrix"]
    stale_references = payload["stale_references"]
    assert isinstance(summary, dict)
    assert isinstance(matrix, list)
    assert isinstance(stale_references, list)
    assert summary["ambiguous_operations"] == 1
    assert summary["stale_references"] == 1
    assert matrix[2] == {
        "operation_id": "getOrder",
        "method": "GET",
        "path": "/orders/{order_id}",
        "status": "ambiguous",
        "tests": ["tests/generated/get_order.hurl", "tests/manual/get_order_smoke.hurl"],
        "negative_tests": [],
        "auth_negative_tests": [],
        "validation_negative_tests": [],
    }
    assert stale_references == [
        {
            "operation_id": "deleteOrder",
            "test_path": "tests/generated/delete_order.hurl",
        }
    ]
    markdown = render_audit_markdown(report)
    assert "## Operation Coverage Matrix" in markdown
    assert "| getOrder | GET | /orders/{order_id} | ambiguous |" in markdown
    assert "## Stale OpenAPI References" in markdown


def test_audit_openapi_coverage_does_not_leak_external_absolute_paths(tmp_path: Path) -> None:
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
    outside_path = tmp_path.parent / "outside_health.hurl"
    covered = HurlTest(
        path=outside_path,
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )

    report = audit_openapi_coverage(document, [covered], project_root=tmp_path)

    assert report.operation_matrix[0].test_paths == ("outside_health.hurl",)

    bridge_report = audit_openapi_coverage(document, [covered])
    assert bridge_report.operation_matrix[0].test_paths == (outside_path.as_posix(),)


def test_audit_openapi_coverage_passes_when_all_operations_are_covered() -> None:
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
    covered = HurlTest(
        path=Path("tests/generated/get_health.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )

    report = audit_openapi_coverage(document, [covered])

    assert report.total_operations == 1
    assert report.covered_operations == 1
    assert report.missing_operations == 0
    assert report.findings == ()
    assert audit_report_to_dict(report)["status"] == "pass"
    assert "No OpenAPI coverage gaps found." in render_audit_markdown(report)


def test_audit_openapi_coverage_does_not_count_metadata_without_hurl_exchange() -> None:
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
    metadata_only = HurlTest(
        path=Path("tests/generated/get_health.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "getHealth"}),
    )

    report = audit_openapi_coverage(document, [metadata_only])

    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["getHealth"]


def test_audit_openapi_coverage_does_not_count_spoofed_operation_metadata() -> None:
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
    spoofed = HurlTest(
        path=Path("tests/generated/create_checkout.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "createCheckout"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )

    report = audit_openapi_coverage(document, [spoofed])

    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["createCheckout"]


def test_audit_openapi_coverage_does_not_count_negative_tests_as_positive() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {
                        "201": {"description": "created"},
                        "400": {"description": "bad request"},
                    },
                },
            },
        },
    }
    negative = HurlTest(
        path=Path("tests/generated/negative/create_checkout_malformed_json.hurl"),
        metadata=HurlMetadata(
            tags=frozenset({"generated", "negative", "malformed-json"}),
            meta={
                "source": "openapi",
                "generation": "negative-path-fuzzing",
                "operation_id": "createCheckout",
                "negative_category": "malformed-json",
                "severity": "medium",
            },
        ),
        exchanges=(HurlExchange(method="POST", url="{{base_url}}/checkout", path="/checkout"),),
    )

    report = audit_openapi_coverage(document, [negative])

    assert report.covered_operations == 0
    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["createCheckout"]
    assert report.operation_matrix[0].status == "uncovered"
    assert report.operation_matrix[0].test_paths == ()
    assert report.operation_matrix[0].negative_test_paths == (
        "tests/generated/negative/create_checkout_malformed_json.hurl",
    )
    payload = audit_report_to_dict(report)
    matrix = payload["operation_matrix"]
    assert isinstance(matrix, list)
    first_row = matrix[0]
    assert isinstance(first_row, dict)
    assert first_row["tests"] == []
    assert first_row["negative_tests"] == [
        "tests/generated/negative/create_checkout_malformed_json.hurl",
    ]
    markdown = render_audit_markdown(report)
    assert "| createCheckout | POST | /checkout | uncovered | - |" in markdown
    assert "tests/generated/negative/create_checkout_malformed_json.hurl" in markdown


def test_audit_openapi_coverage_does_not_count_auth_negative_tests_as_positive() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/secure": {
                "get": {
                    "operationId": "getSecure",
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }
    auth_negative = HurlTest(
        path=Path("tests/generated/security/get_secure_invalid_auth.hurl"),
        metadata=HurlMetadata(
            tags=frozenset({"generated", "security"}),
            meta={
                "source": "openapi",
                "operation_id": "getSecure",
                "negative_category": "invalid-auth",
                "severity": "high",
            },
        ),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/secure", path="/secure"),),
    )

    report = audit_openapi_coverage(document, [auth_negative])

    assert report.covered_operations == 0
    assert report.missing_operations == 1
    assert report.operation_matrix[0].test_paths == ()
    assert report.operation_matrix[0].negative_test_paths == (
        "tests/generated/security/get_secure_invalid_auth.hurl",
    )


def test_audit_openapi_coverage_classifies_negative_evidence_by_family() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {
                        "201": {"description": "created"},
                        "400": {"description": "bad request"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }
    positive = HurlTest(
        path=Path("tests/generated/create_checkout.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "createCheckout"}),
        exchanges=(HurlExchange(method="POST", url="{{base_url}}/checkout", path="/checkout"),),
    )
    auth_negative = HurlTest(
        path=Path("tests/generated/security/create_checkout_invalid_auth.hurl"),
        metadata=HurlMetadata(
            tags=frozenset({"generated", "negative", "auth", "invalid-auth"}),
            meta={
                "source": "openapi",
                "operation_id": "createCheckout",
                "negative_category": "invalid-auth",
                "severity": "high",
            },
        ),
        exchanges=(HurlExchange(method="POST", url="{{base_url}}/checkout", path="/checkout"),),
    )
    validation_negative = HurlTest(
        path=Path("tests/generated/negative/create_checkout_malformed_json.hurl"),
        metadata=HurlMetadata(
            tags=frozenset({"generated", "negative", "malformed-json"}),
            meta={
                "source": "openapi",
                "generation": "negative-path-fuzzing",
                "operation_id": "createCheckout",
                "negative_category": "malformed-json",
                "severity": "medium",
            },
        ),
        exchanges=(HurlExchange(method="POST", url="{{base_url}}/checkout", path="/checkout"),),
    )

    report = audit_openapi_coverage(document, [positive, validation_negative, auth_negative])

    payload = audit_report_to_dict(report)
    summary = payload["summary"]
    matrix = payload["operation_matrix"]
    assert isinstance(summary, dict)
    assert isinstance(matrix, list)
    assert summary["happy_path_covered_operations"] == 1
    assert summary["auth_negative_covered_operations"] == 1
    assert summary["validation_negative_covered_operations"] == 1
    row = matrix[0]
    assert isinstance(row, dict)
    assert row["tests"] == ["tests/generated/create_checkout.hurl"]
    assert row["negative_tests"] == [
        "tests/generated/negative/create_checkout_malformed_json.hurl",
        "tests/generated/security/create_checkout_invalid_auth.hurl",
    ]
    assert row["auth_negative_tests"] == [
        "tests/generated/security/create_checkout_invalid_auth.hurl",
    ]
    assert row["validation_negative_tests"] == [
        "tests/generated/negative/create_checkout_malformed_json.hurl",
    ]
    markdown = render_audit_markdown(report)
    assert "Auth Negative Tests" in markdown
    assert "Validation Negative Tests" in markdown


def test_audit_openapi_coverage_enumerates_default_response_operations() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/fallback": {
                "get": {
                    "operationId": "getFallback",
                    "responses": {"default": {"description": "fallback"}},
                },
            },
        },
    }

    report = audit_openapi_coverage(document, [])

    assert report.total_operations == 1
    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["getFallback"]


def test_audit_openapi_coverage_matches_fallback_ids_root_and_path_templates() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/": {"get": {"responses": {"200": {"description": "ok"}}}},
            "/users/{user_id}": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
    }
    root = HurlTest(
        path=Path("tests/generated/get_root.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "get_root"}),
        exchanges=(HurlExchange(method="get", url="{{base_url}}/", path="/"),),
    )
    templated = HurlTest(
        path=Path("tests/generated/get_users_user_id.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "get_users_user_id"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/users/123", path="/users/123"),),
    )

    report = audit_openapi_coverage(document, [root, templated])

    assert report.passed
    assert report.covered_operations == 2


def test_audit_openapi_coverage_ignores_missing_and_unknown_operation_metadata() -> None:
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
    missing_operation_id = HurlTest(
        path=Path("tests/generated/missing.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )
    unknown_operation_id = HurlTest(
        path=Path("tests/generated/unknown.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "unknown"}),
        exchanges=(HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),),
    )

    report = audit_openapi_coverage(document, [missing_operation_id, unknown_operation_id])

    assert report.missing_operations == 1
    assert [finding.operation_id for finding in report.findings] == ["getHealth"]


def test_audit_openapi_coverage_rejects_malformed_documents() -> None:
    cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"openapi": "3.1.0"}, "paths mapping"),
        ({"openapi": "3.1.0", "paths": {"health": {}}}, "absolute path strings"),
        ({"openapi": "3.1.0", "paths": {"/health": "bad"}}, "must be a mapping"),
        (
            {"openapi": "3.1.0", "paths": {"/health": {"summary": "ignored"}}},
            "supported HTTP operations",
        ),
        (
            {"openapi": "3.1.0", "paths": {"/health": {"get": "bad"}}},
            "OpenAPI operation 'get' /health must be a mapping",
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
                    "/health": {
                        "get": {"operationId": "get\nHealth", "responses": {"200": {}}},
                    },
                },
            },
            "operationId is not safe",
        ),
        ({"openapi": "3.1.0", "paths": {1: {}}}, "paths keys must be strings"),
    )

    for document, expected_error in cases:
        with pytest.raises(OpenApiCompilationError, match=expected_error):
            audit_openapi_coverage(document, [])


def test_render_audit_markdown_escapes_table_cells() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health|checks<svg>": {
                "get": {
                    "operationId": "get|Health<img>",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    markdown = render_audit_markdown(audit_openapi_coverage(document, []))

    assert "get\\|Health&lt;img&gt;" in markdown
    assert "/health\\|checks&lt;svg&gt;" in markdown
    assert "<img>" not in markdown
    assert "<svg>" not in markdown


def test_render_audit_markdown_includes_traffic_route_section() -> None:
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
    report = audit_openapi_coverage(
        document,
        [],
        traffic_routes=TrafficOpenApiAuditReport(
            documented=(),
            undocumented=(
                TrafficUndocumentedRoute(
                    method="POST",
                    path_template="/debug",
                    call_count=1,
                    failure_count=0,
                ),
            ),
            spec_only=(),
        ),
    )

    markdown = render_audit_markdown(report)

    assert "## Traffic vs OpenAPI Routes" in markdown
    assert "POST /debug" in markdown


def test_openapi_breaking_diff_links_only_openapi_operation_metadata() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/legacy": {
                "delete": {
                    "operationId": "deleteLegacy",
                    "responses": {"204": {"description": "deleted"}},
                },
            },
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    current: dict[str, object] = {
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
    linked = HurlTest(
        path=Path("tests/generated/delete_legacy.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi", "operation_id": "deleteLegacy"}),
        exchanges=(HurlExchange(method="DELETE", url="{{base_url}}/legacy", path="/legacy"),),
    )
    ignored_manual = HurlTest(
        path=Path("tests/manual/delete_legacy.hurl"),
        metadata=HurlMetadata(meta={"operation_id": "deleteLegacy"}),
    )
    ignored_missing_operation = HurlTest(
        path=Path("tests/generated/missing_meta.hurl"),
        metadata=HurlMetadata(meta={"source": "openapi"}),
    )

    report = audit_openapi_coverage(
        current,
        [linked, ignored_manual, ignored_missing_operation],
        openapi_diff=audit_openapi_breaking_changes(base, current, base_ref="HEAD"),
    )

    assert report.openapi_diff is not None
    assert report.openapi_diff.findings[0].test_paths == ("tests/generated/delete_legacy.hurl",)
    assert "openapi_diff" in audit_report_to_dict(report)
    assert "## OpenAPI Breaking-Change Diff" in render_audit_markdown(report)
