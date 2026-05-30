"""Unit tests for deterministic Architect audit coverage."""

from pathlib import Path

import pytest

from entroping.bridge.openapi_audit import (
    audit_openapi_coverage,
    audit_report_to_dict,
    render_audit_markdown,
)
from entroping.bridge.openapi_to_hurl import OpenApiCompilationError
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
