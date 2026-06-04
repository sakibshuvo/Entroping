"""Pure OpenAPI operation-change detection."""

from typing import cast

import pytest

from entroping.bridge.openapi_diff import detect_openapi_operation_changes
from entroping.bridge.openapi_to_hurl import OpenApiCompilationError


def _operation(operation_id: str, *, status: str = "200") -> dict[str, object]:
    return {"operationId": operation_id, "responses": {status: {"description": "ok"}}}


def test_detect_openapi_operation_changes_classifies_added_modified_renamed_and_removed() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": _operation("getHealth")},
            "/checkout": {"post": _operation("createCheckout")},
            "/orders": {"get": _operation("listOrdersOld")},
            "/legacy": {"delete": _operation("deleteLegacy")},
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": _operation("getHealth")},
            "/checkout": {"post": _operation("createCheckout", status="201")},
            "/orders": {"get": _operation("listOrders")},
            "/refunds": {"post": _operation("createRefund")},
        },
    }

    changes = detect_openapi_operation_changes(base, current)

    assert [
        (change.change_type, change.operation_id, change.previous_operation_id)
        for change in changes.items
    ] == [
        ("modified", "createCheckout", None),
        ("renamed", "listOrders", "listOrdersOld"),
        ("added", "createRefund", None),
        ("removed", "deleteLegacy", None),
    ]
    assert changes.generation_operation_ids == (
        "createCheckout",
        "listOrders",
        "createRefund",
    )
    assert changes.summary == {
        "added": 1,
        "modified": 1,
        "renamed": 1,
        "removed": 1,
        "unchanged": 1,
    }


def test_detect_openapi_operation_changes_reports_no_changes_for_identical_specs() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": _operation("getHealth")}},
    }

    changes = detect_openapi_operation_changes(document, document)

    assert changes.items == ()
    assert changes.generation_operation_ids == ()
    assert changes.summary == {
        "added": 0,
        "modified": 0,
        "renamed": 0,
        "removed": 0,
        "unchanged": 1,
    }


def test_detect_openapi_operation_changes_handles_fallback_ids_and_non_operation_fields() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/": {
                "summary": "root path",
                "parameters": [{"name": "tenant", "in": "query"}],
                "get": {"x-throttle": 1.5, "responses": {"200": {"description": "ok"}}},
            },
        },
    }

    changes = detect_openapi_operation_changes(document, document)

    assert changes.items == ()
    assert changes.summary["unchanged"] == 1


def test_detect_openapi_operation_changes_rejects_duplicate_operation_ids() -> None:
    duplicate: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/one": {"get": _operation("getThing")},
            "/two": {"get": _operation("getThing")},
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/one": {"get": _operation("getThing")}},
    }

    with pytest.raises(OpenApiCompilationError, match="operationId must be unique"):
        detect_openapi_operation_changes(duplicate, current)


def test_detect_openapi_operation_changes_rejects_malformed_documents() -> None:
    cases: tuple[tuple[dict[object, object], str], ...] = (
        ({"openapi": "3.1.0"}, "paths mapping"),
        ({"paths": {"bad": {"get": _operation("getBad")}}}, "absolute path"),
        ({"paths": {"/bad": "not-a-path-item"}}, "must be a mapping"),
        ({"paths": {"/bad": {"get": "not-an-operation"}}}, "must be a mapping"),
        ({"paths": {"/bad": {"get": {"operationId": "bad\nid"}}}}, "operationId"),
        ({"paths": {"/bad": {"get": {1: "bad-key"}}}}, "keys must be strings"),
        ({"paths": {"/bad": {"get": {"summary": "bad\nsummary"}}}}, "control"),
        ({"paths": {"/bad": {"get": {"x": float("nan")}}}}, "finite"),
        ({"paths": {"/bad": {"get": {"x": object()}}}}, "JSON-compatible"),
    )

    for document, expected in cases:
        with pytest.raises(OpenApiCompilationError, match=expected):
            detect_openapi_operation_changes(cast("dict[str, object]", document), {"paths": {}})
