"""Pure OpenAPI operation-change detection."""

from typing import cast

import pytest

from entroping.bridge import openapi_diff as openapi_diff_bridge
from entroping.bridge.openapi_diff import (
    audit_openapi_breaking_changes,
    breaking_diff_report_to_dict,
    detect_openapi_operation_changes,
    render_breaking_diff_markdown,
)
from entroping.bridge.openapi_to_hurl import OpenApiCompilationError


def _operation(operation_id: str, *, status: str = "200") -> dict[str, object]:
    return {"operationId": operation_id, "responses": {status: {"description": "ok"}}}


def _object_schema(*, required: list[str], properties: dict[str, object]) -> dict[str, object]:
    return {"type": "object", "required": required, "properties": properties}


def _deep_json_value(depth: int) -> dict[str, object]:
    value: dict[str, object] = {"leaf": "ok"}
    for index in range(depth):
        value = {f"child_{index}": value}
    return value


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


def test_audit_openapi_breaking_changes_reports_removed_and_added_operations() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": _operation("getHealth")},
            "/legacy": {"delete": _operation("deleteLegacy", status="204")},
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": _operation("getHealth")},
            "/refunds": {"post": _operation("createRefund", status="202")},
        },
    }

    report = audit_openapi_breaking_changes(base, current, base_ref="HEAD")

    assert report.passed is False
    assert [
        (finding.code, finding.severity, finding.operation_id, finding.method, finding.path)
        for finding in report.findings
    ] == [
        ("OPENAPI_OPERATION_ADDED", "info", "createRefund", "POST", "/refunds"),
        ("OPENAPI_OPERATION_REMOVED", "error", "deleteLegacy", "DELETE", "/legacy"),
    ]
    assert report.summary == {
        "added": 1,
        "modified": 0,
        "renamed": 0,
        "removed": 1,
        "unchanged": 1,
        "breaking_findings": 1,
        "warnings": 0,
        "informational": 1,
    }


def test_audit_openapi_breaking_changes_reports_required_request_changes() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "parameters": [
                        {"name": "idempotency-key", "in": "header", "required": False},
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": _object_schema(
                                    required=["sku"],
                                    properties={"sku": {"type": "string"}},
                                ),
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "parameters": [
                        {"name": "idempotency-key", "in": "header", "required": True},
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _object_schema(
                                    required=["sku", "quantity"],
                                    properties={
                                        "sku": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                    },
                                ),
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.severity, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_REQUIRED_PARAMETER_ADDED", "error", ("header:idempotency-key",)),
        ("OPENAPI_REQUIRED_BODY_ADDED", "error", ()),
        ("OPENAPI_REQUIRED_BODY_FIELD_ADDED", "error", ("quantity",)),
    ]


def test_audit_openapi_breaking_changes_reports_status_and_response_shape_changes() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {
                        "201": {
                            "description": "created",
                            "content": {
                                "application/json": {
                                    "schema": _object_schema(
                                        required=["id", "status"],
                                        properties={
                                            "id": {"type": "string"},
                                            "status": {"type": "string"},
                                            "total": {"type": "number"},
                                        },
                                    ),
                                },
                            },
                        },
                        "400": {
                            "description": "bad request",
                            "content": {
                                "application/json": {
                                    "schema": _object_schema(
                                        required=["id", "status"],
                                        properties={
                                            "id": {"type": "string"},
                                            "status": {"type": "string"},
                                            "total": {"type": "number"},
                                        },
                                    ),
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "responses": {
                        "202": {"description": "accepted"},
                        "400": {
                            "description": "bad request",
                            "content": {
                                "application/json": {
                                    "schema": _object_schema(
                                        required=["id"],
                                        properties={
                                            "id": {"type": "integer"},
                                            "total": {"type": "number"},
                                        },
                                    ),
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.severity, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_RESPONSE_STATUS_ADDED", "info", ("202",)),
        ("OPENAPI_RESPONSE_STATUS_REMOVED", "error", ("201",)),
        ("OPENAPI_RESPONSE_REQUIRED_FIELD_REMOVED", "error", ("400:application/json:status",)),
        ("OPENAPI_RESPONSE_FIELD_REMOVED", "error", ("400:application/json:status",)),
        ("OPENAPI_RESPONSE_FIELD_TYPE_CHANGED", "error", ("400:application/json:id",)),
    ]


def test_audit_openapi_breaking_changes_reports_unsupported_constructs() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/OrderList"}},
                            },
                        },
                    },
                },
            },
        },
    }
    current = base

    report = audit_openapi_breaking_changes(base, current)

    assert report.passed is True
    assert [
        (finding.code, finding.severity, finding.operation_id)
        for finding in report.findings
    ] == [("OPENAPI_RESPONSE_SCHEMA_UNANALYZED", "warning", "listOrders")]


def test_audit_openapi_breaking_changes_rejects_malformed_specs() -> None:
    with pytest.raises(OpenApiCompilationError, match="responses must be a mapping"):
        audit_openapi_breaking_changes(
            {
                "openapi": "3.1.0",
                "paths": {"/bad": {"get": {"operationId": "getBad", "responses": []}}},
            },
            {
                "openapi": "3.1.0",
                "paths": {"/bad": {"get": _operation("getBad")}},
            },
        )


def test_breaking_diff_json_and_markdown_escape_output() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/unsafe|path": {"get": _operation("getUnsafe|<script>")}},
    }
    current: dict[str, object] = {"openapi": "3.1.0", "paths": {}}

    report = audit_openapi_breaking_changes(base, current, base_ref="feature/<unsafe>")
    payload = breaking_diff_report_to_dict(report)
    markdown = render_breaking_diff_markdown(report)
    findings = cast("list[dict[str, object]]", payload["findings"])

    assert payload["schema_version"] == "entroping.openapi-breaking-diff.v1"
    assert payload["base_ref"] == "feature/<unsafe>"
    assert findings[0]["operation_id"] == "getUnsafe|<script>"
    assert "getUnsafe\\|&lt;script&gt;" in markdown
    assert "/unsafe\\|path" in markdown
    assert "feature/&lt;unsafe&gt;" in markdown


def test_breaking_diff_markdown_reports_no_changes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": _operation("getHealth")}},
    }

    markdown = render_breaking_diff_markdown(audit_openapi_breaking_changes(document, document))

    assert "No OpenAPI operation changes found." in markdown


def test_audit_openapi_breaking_changes_reports_renamed_and_generic_modified() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {"get": _operation("listOrdersOld")},
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary": "old",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {"get": _operation("listOrders")},
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary": "new",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.severity, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_OPERATION_RENAMED", "warning", ("listOrdersOld",)),
        ("OPENAPI_OPERATION_MODIFIED", "warning", ()),
    ]


def test_audit_openapi_breaking_changes_reports_method_and_path_changes() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/orders": {"get": _operation("listOrders")}},
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/v2/orders": {"post": _operation("listOrders")}},
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_METHOD_CHANGED", ("GET->POST",)),
        ("OPENAPI_PATH_CHANGED", ("/orders->/v2/orders",)),
    ]


def test_audit_openapi_breaking_changes_reports_removed_required_inputs() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "parameters": [
                        {"name": "tenant", "in": "query", "required": True},
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _object_schema(
                                    required=["sku"],
                                    properties={"sku": {"type": "string"}},
                                ),
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {"required": False},
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.severity, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_REQUIRED_PARAMETER_REMOVED", "info", ("query:tenant",)),
        ("OPENAPI_REQUIRED_BODY_REMOVED", "info", ()),
        ("OPENAPI_REQUIRED_BODY_FIELD_REMOVED", "info", ("sku",)),
    ]


def test_audit_openapi_breaking_changes_handles_optional_schema_shapes() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shape": {
                "get": {
                    "operationId": "getShape",
                    "requestBody": {"content": {"text/plain": {}}},
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "text/plain": {},
                                "application/json": {
                                    "schema": {
                                        "type": ["object", "null"],
                                        "properties": {"id": {}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shape": {
                "get": {
                    "operationId": "getShape",
                    "requestBody": {"content": {"application/json": {}}},
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["id"],
                                        "properties": {"id": {"type": "string"}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.evidence)
        for finding in report.findings
    ] == [
        ("OPENAPI_RESPONSE_SCHEMA_TYPE_CHANGED", ("200:application/json:schema",)),
        ("OPENAPI_RESPONSE_FIELD_TYPE_CHANGED", ("200:application/json:id",)),
    ]


def test_audit_openapi_breaking_changes_skips_unanalyzable_response_shapes() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shape": {
                "get": {
                    "operationId": "getShape",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": {"$ref": "#/Thing"}}},
                        },
                    },
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shape": {
                "get": {
                    "operationId": "getShape",
                    "summary": "changed",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "text/plain": {},
                                "application/json": {},
                            },
                        },
                        "204": {"description": "empty", "content": {"text/plain": {}}},
                    },
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert [
        (finding.code, finding.severity)
        for finding in report.findings
    ] == [("OPENAPI_RESPONSE_STATUS_ADDED", "info")]


def test_audit_openapi_breaking_changes_rejects_malformed_parameters() -> None:
    cases: tuple[tuple[dict[str, object], str], ...] = (
        (
            {
                "openapi": "3.1.0",
                "paths": {
                    "/bad": {
                        "get": {
                            "operationId": "getBad",
                            "parameters": "tenant",
                            "responses": {"200": {"description": "ok"}},
                        },
                    },
                },
            },
            "parameters.*must be a list",
        ),
        (
            {
                "openapi": "3.1.0",
                "paths": {
                    "/bad": {
                        "get": {
                            "operationId": "getBad",
                            "parameters": [{"in": "query", "required": True}],
                            "responses": {"200": {"description": "ok"}},
                        },
                    },
                },
            },
            "needs a name",
        ),
        (
            {
                "openapi": "3.1.0",
                "paths": {
                    "/bad": {
                        "get": {
                            "operationId": "getBad",
                            "parameters": [{"name": "tenant", "required": True}],
                            "responses": {"200": {"description": "ok"}},
                        },
                    },
                },
            },
            "needs a location",
        ),
    )

    for current, expected in cases:
        with pytest.raises(OpenApiCompilationError, match=expected):
            audit_openapi_breaking_changes(
                {
                    "openapi": "3.1.0",
                    "paths": {
                        "/bad": {"get": {"operationId": "getBad", "responses": {}}},
                    },
                },
                current,
            )


def test_audit_openapi_breaking_changes_ignores_parameter_refs() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "parameters": [{"$ref": "#/components/parameters/Tenant"}],
                "get": {
                    "operationId": "listOrders",
                    "summary": "old",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "parameters": [{"$ref": "#/components/parameters/Tenant"}],
                "get": {
                    "operationId": "listOrders",
                    "summary": "new",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert report.findings[0].code == "OPENAPI_OPERATION_MODIFIED"


def test_audit_openapi_breaking_changes_allows_modified_operations_without_responses() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": {"operationId": "getHealth", "summary": "old"}}},
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": {"operationId": "getHealth", "summary": "new"}}},
    }

    report = audit_openapi_breaking_changes(base, current)

    assert report.findings[0].code == "OPENAPI_OPERATION_MODIFIED"


def test_audit_openapi_breaking_changes_allows_request_body_refs() -> None:
    base: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {"$ref": "#/components/requestBodies/Checkout"},
                    "summary": "old",
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {"$ref": "#/components/requestBodies/Checkout"},
                    "summary": "new",
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    report = audit_openapi_breaking_changes(base, current)

    assert report.findings[0].code == "OPENAPI_OPERATION_MODIFIED"


def test_audit_openapi_breaking_changes_rejects_excessively_deep_operation_payloads() -> None:
    base = {"openapi": "3.1.0", "paths": {"/health": {"get": _operation("getHealth")}}}
    current: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "x-entroping-deep": _deep_json_value(80),
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="JSON depth exceeds"):
        audit_openapi_breaking_changes(base, current)


def test_audit_openapi_breaking_changes_budget_helper_rejects_node_exhaustion() -> None:
    budget = openapi_diff_bridge._JsonTraversalBudget(  # noqa: SLF001
        nodes=openapi_diff_bridge._MAX_OPENAPI_JSON_NODES,  # noqa: SLF001
    )

    with pytest.raises(OpenApiCompilationError, match="JSON traversal exceeds"):
        openapi_diff_bridge._check_openapi_json_budget(  # noqa: SLF001
            depth=0,
            budget=budget,
            context="GET /health operation",
        )


def test_audit_openapi_breaking_changes_rejects_malformed_schema_shapes() -> None:
    cases: tuple[tuple[dict[str, object], str], ...] = (
        (
            {
                "type": "object",
                "required": "id",
                "properties": {"id": {"type": "string"}},
            },
            "required must be a list",
        ),
        (
            {
                "type": "object",
                "required": [1],
                "properties": {"id": {"type": "string"}},
            },
            "required field 0 must be a string",
        ),
        (
            {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": ["string", 1]}},
            },
            "type entry 1 must be a string",
        ),
        (
            {
                "type": {"not": "valid"},
                "properties": {"id": {"type": "string"}},
            },
            "type must be a string or string list",
        ),
    )

    for schema, expected in cases:
        with pytest.raises(OpenApiCompilationError, match=expected):
            audit_openapi_breaking_changes(
                {
                    "openapi": "3.1.0",
                    "paths": {
                        "/bad": {
                            "get": {
                                "operationId": "getBad",
                                "responses": {
                                    "200": {
                                        "description": "ok",
                                        "content": {"application/json": {"schema": {}}},
                                    },
                                },
                            },
                        },
                    },
                },
                {
                    "openapi": "3.1.0",
                    "paths": {
                        "/bad": {
                            "get": {
                                "operationId": "getBad",
                                "responses": {
                                    "200": {
                                        "description": "ok",
                                        "content": {"application/json": {"schema": schema}},
                                    },
                                },
                            },
                        },
                    },
                },
            )
