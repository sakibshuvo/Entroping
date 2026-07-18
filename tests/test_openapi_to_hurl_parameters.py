import pytest
from openapi_to_hurl_test_helpers import _compile_single_operation, _ok_operation

from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
    compile_openapi_to_hurl_with_report,
)
from entroping.models.hurl import parse_hurl_metadata


def test_compile_openapi_generates_missing_required_parameter_negatives() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [
                        {
                            "name": "customer_id",
                            "in": "query",
                            "required": True,
                            "example": "cust_1",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "example": 1,
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "X-Tenant",
                            "in": "header",
                            "required": True,
                            "example": "tenant_1",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "session_id",
                            "in": "cookie",
                            "required": True,
                            "example": "sess_1",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "ok"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"orders"}))
    files = {item.relative_path: item.content for item in result.files}

    query_negative = files[
        "tests/generated/negative/list_orders_missing_required_query_customer_id.hurl"
    ]
    header_negative = files[
        "tests/generated/negative/list_orders_missing_required_header_x_tenant.hurl"
    ]
    cookie_negative = files[
        "tests/generated/negative/list_orders_missing_required_cookie_session_id.hurl"
    ]

    assert "# entroping: negative_category=missing-required-parameter" in query_negative
    assert "GET {{base_url}}/orders?page=1" in query_negative
    assert "customer_id=" not in query_negative
    assert "X-Tenant: tenant_1" in query_negative
    assert "Cookie: session_id=sess_1" in query_negative
    assert "HTTP 422" in query_negative
    assert parse_hurl_metadata(query_negative).tags >= frozenset(
        {"orders", "generated", "negative", "missing-required-parameter"}
    )

    assert "GET {{base_url}}/orders?customer_id=cust_1&page=1" in header_negative
    assert "X-Tenant:" not in header_negative
    assert "Cookie: session_id=sess_1" in header_negative
    assert "HTTP 422" in header_negative

    assert "GET {{base_url}}/orders?customer_id=cust_1&page=1" in cookie_negative
    assert "X-Tenant: tenant_1" in cookie_negative
    assert "Cookie:" not in cookie_negative
    assert "HTTP 422" in cookie_negative


def test_compile_openapi_missing_required_parameter_negatives_need_validation_response() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [
                        {
                            "name": "customer_id",
                            "in": "query",
                            "required": True,
                            "example": "cust_1",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == ["tests/generated/list_orders.hurl"]


def test_compile_openapi_missing_required_parameter_negative_preserves_json_body() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "post": {
                    "operationId": "createOrder",
                    "parameters": [
                        {
                            "name": "X-Tenant",
                            "in": "header",
                            "required": True,
                            "example": "tenant_1",
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["sku"],
                                    "properties": {"sku": {"type": "string"}},
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "400": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())
    missing_header = next(
        item
        for item in result.files
        if item.relative_path
        == "tests/generated/negative/create_order_missing_required_header_x_tenant.hurl"
    )

    assert "POST {{base_url}}/orders" in missing_header.content
    assert "X-Tenant:" not in missing_header.content
    assert "Content-Type: application/json" in missing_header.content
    assert '"sku": "string"' in missing_header.content
    assert "HTTP 400" in missing_header.content


def test_compile_openapi_rejects_non_boolean_parameter_required() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [
                        {
                            "name": "customer_id",
                            "in": "query",
                            "required": "true",
                            "example": "cust_1",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="parameter required must be a boolean"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_duplicate_missing_required_generated_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def duplicate_missing_required_file(**_: object) -> tuple[openapi_compiler.GeneratedHurlFile]:
        return (
            openapi_compiler.GeneratedHurlFile(
                relative_path="tests/generated/list_orders.hurl",
                content="GET {{base_url}}/duplicate\nHTTP 422\n",
            ),
        )

    monkeypatch.setattr(
        openapi_compiler,
        "_missing_required_parameter_negative_files",
        duplicate_missing_required_file,
    )

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/orders": {"get": _ok_operation("listOrders")}},
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_generates_numeric_boundary_negative_for_path_and_query() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits/{level}": {
                "get": {
                    "operationId": "getLimit",
                    "parameters": [
                        {
                            "name": "level",
                            "in": "path",
                            "required": True,
                            "example": 9,
                            "schema": {"type": "integer", "exclusiveMaximum": 10},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "example": 5,
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        {
                            "name": "score",
                            "in": "query",
                            "example": 2.5,
                            "schema": {"type": "number", "exclusiveMinimum": 1.5},
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "example": 1,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "ok"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"limits"}))
    boundary = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/negative/get_limit_numeric_boundary_values.hurl"
    )

    assert "# entroping: negative_category=numeric-boundary-values" in boundary.content
    assert "GET {{base_url}}/limits/10?limit=0&score=1.5&page=1" in boundary.content
    assert "HTTP 422" in boundary.content
    assert parse_hurl_metadata(boundary.content).tags >= frozenset(
        {"limits", "generated", "negative", "numeric-boundary-values"}
    )


def test_compile_openapi_numeric_boundary_parameter_negative_preserves_json_body() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "parameters": [
                        {
                            "name": "count",
                            "in": "query",
                            "example": 10,
                            "schema": {"type": "integer", "maximum": 10},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["sku"],
                                    "properties": {"sku": {"type": "string"}},
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "400": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())
    expected_path = "tests/generated/negative/create_limit_numeric_boundary_values.hurl"
    boundary = next(
        item for item in result.files if item.relative_path == expected_path
    )

    assert "POST {{base_url}}/limits?count=11" in boundary.content
    assert "Content-Type: application/json" in boundary.content
    assert '"sku": "string"' in boundary.content
    assert "HTTP 400" in boundary.content


def test_compile_openapi_rejects_duplicate_numeric_boundary_generated_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def duplicate_numeric_boundary_file(**_: object) -> tuple[openapi_compiler.GeneratedHurlFile]:
        return (
            openapi_compiler.GeneratedHurlFile(
                relative_path="tests/generated/list_orders.hurl",
                content="GET {{base_url}}/duplicate\nHTTP 422\n",
            ),
        )

    monkeypatch.setattr(
        openapi_compiler,
        "_numeric_boundary_parameter_negative_files",
        duplicate_numeric_boundary_file,
    )

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/orders": {"get": _ok_operation("listOrders")}},
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_idor_variants_preserve_scalar_path_types() -> None:
    missing_example = object()

    def idor_operation(
        operation_id: str,
        parameter_schema: dict[str, object],
        *,
        example: object = missing_example,
    ) -> dict[str, object]:
        parameter: dict[str, object] = {
            "name": "value",
            "in": "path",
            "schema": parameter_schema,
        }
        if example is not missing_example:
            parameter["example"] = example
        return {
            "operationId": operation_id,
            "parameters": [parameter],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {"name": {"type": "string"}},
                        },
                    },
                },
            },
            "responses": {
                "201": {"description": "created"},
                "400": {"description": "validation failed"},
            },
        }

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/flags/{value}": {
                "post": idor_operation("createFlag", {"type": "boolean"}, example=True)
            },
            "/counters/{value}": {
                "post": idor_operation("createCounter", {"type": "integer"}, example=42)
            },
            "/ratios/{value}": {
                "post": idor_operation("createRatio", {"type": "number"}, example=1.5)
            },
            "/slugs/{value}": {
                "post": idor_operation("createSlug", {"type": "string"}, example="customer")
            },
            "/fallback/{value}": {
                "post": idor_operation("createFallback", {"type": "string"})
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())
    idor_contents = [
        item.content
        for item in result.files
        if item.relative_path.endswith("_idor_path_variants.hurl")
    ]

    assert len(idor_contents) == 5
    joined = "\n---\n".join(idor_contents)
    assert "POST {{base_url}}/flags/false" in joined
    assert "POST {{base_url}}/counters/43" in joined
    assert "POST {{base_url}}/ratios/2.5" in joined
    assert "POST {{base_url}}/slugs/customer-other" in joined
    assert "POST {{base_url}}/fallback/entroping-other" in joined


def test_compile_openapi_renders_parameters_and_schema_examples() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders/{order_id}/events/{event-id}": {
                "parameters": [
                    {
                        "name": "order_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "tenant",
                        "in": "query",
                        "schema": {"type": "string", "default": "north"},
                    },
                ],
                "post": {
                    "operationId": "createOrderEvent",
                    "parameters": [
                        {
                            "name": "event-id",
                            "in": "path",
                            "required": True,
                            "example": "evt-001",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["accepted", "pending"]},
                        },
                        {
                            "name": "X-Request-Id",
                            "in": "header",
                            "schema": {"type": "string", "default": "req-123"},
                        },
                        {
                            "name": "session_id",
                            "in": "cookie",
                            "schema": {"type": "string", "default": "demo-session"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["source", "retry", "priority", "payload"],
                                    "properties": {
                                        "source": {
                                            "type": "string",
                                            "example": "mobile",
                                        },
                                        "retry": {
                                            "type": "boolean",
                                            "default": True,
                                        },
                                        "priority": {
                                            "const": "high",
                                        },
                                        "payload": {
                                            "type": "object",
                                            "examples": [{"kind": "refund"}],
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {"202": {"description": "accepted"}},
                },
            },
        },
    }

    generated = compile_openapi_to_hurl(document, tags=frozenset({"orders"}))

    assert len(generated) == 1
    content = generated[0].content
    assert "# entroping: path=/orders/{order_id}/events/{event-id}" in content
    assert (
        "POST {{base_url}}/orders/{{order_id}}/events/evt-001"
        "?tenant=north&status=accepted"
    ) in content
    assert "X-Request-Id: req-123" in content
    assert "Cookie: session_id=demo-session" in content
    assert '"source": "mobile"' in content
    assert '"retry": true' in content
    assert '"priority": "high"' in content
    assert '"payload": {\n    "kind": "refund"\n  }' in content
    assert "HTTP 202" in content


def test_compile_openapi_resolves_reusable_parameter_refs() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "parameters": {
                "OrderId": {
                    "name": "order_id",
                    "in": "path",
                    "required": True,
                    "example": "ord-123",
                    "schema": {"type": "string"},
                },
                "Tenant": {
                    "name": "X-Tenant",
                    "in": "header",
                    "schema": {"type": "string", "default": "north"},
                },
                "Include": {
                    "name": "include",
                    "in": "query",
                    "schema": {"type": "string", "enum": ["events"]},
                },
            },
        },
        "paths": {
            "/orders/{order_id}": {
                "parameters": [{"$ref": "#/components/parameters/OrderId"}],
                "get": {
                    "operationId": "getOrder",
                    "parameters": [
                        {"$ref": "#/components/parameters/Tenant"},
                        {"$ref": "#/components/parameters/Include"},
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset({"orders"}))[0].content

    assert "GET {{base_url}}/orders/ord-123?include=events" in content
    assert "X-Tenant: north" in content


def test_compile_openapi_resolves_escaped_parameter_ref_names() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "parameters": {
                "Tenant/Id~V1": {
                    "name": "X-Tenant",
                    "in": "header",
                    "schema": {"type": "string", "default": "north"},
                },
            },
        },
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [{"$ref": "#/components/parameters/Tenant~1Id~0V1"}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert "X-Tenant: north" in content


def test_compile_openapi_resolves_transitive_parameter_refs() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "parameters": {
                "Outer": {"$ref": "#/components/parameters/Middle"},
                "Middle": {"$ref": "#/components/parameters/Tenant"},
                "Tenant": {
                    "name": "tenant",
                    "in": "query",
                    "schema": {"type": "string", "default": "north"},
                },
            },
        },
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [{"$ref": "#/components/parameters/Outer"}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert "GET {{base_url}}/orders?tenant=north" in content


@pytest.mark.parametrize(
    ("parameter", "expected_error"),
    [
        ({"$ref": "common.yaml#/components/parameters/Tenant"}, "only local parameter refs"),
        ({"$ref": "#/components/schemas/Tenant"}, "unsupported parameter ref"),
        ({"$ref": 1}, "parameter ref must be a string"),
        ({"$ref": "#/components/parameters/Missing"}, "unknown parameter ref"),
        ({"$ref": "#/components/parameters/Tenant", "name": "tenant"}, "sibling fields"),
        ({"$ref": "#/components/parameters/"}, "malformed parameter ref"),
        ({"$ref": "#/components/parameters/Tenant/Id"}, "malformed parameter ref"),
        ({"$ref": "#/components/parameters/Bad~2Name"}, "malformed parameter ref"),
        ({"$ref": "#/components/parameters/Bad~"}, "malformed parameter ref"),
    ],
)
def test_compile_openapi_rejects_unsupported_parameter_refs(
    parameter: dict[str, object],
    expected_error: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "parameters": {
                "Tenant": {
                    "name": "X-Tenant",
                    "in": "header",
                    "schema": {"type": "string", "default": "north"},
                },
            },
        },
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [parameter],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match=expected_error):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_non_mapping_parameter_ref_targets() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"parameters": {"Tenant": "not-a-parameter"}},
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [{"$ref": "#/components/parameters/Tenant"}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="parameter ref target"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_malformed_parameter_components() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"parameters": ["not-a-map"]},
        "paths": {"/orders": {"get": _ok_operation("listOrders")}},
    }

    with pytest.raises(OpenApiCompilationError, match="OpenAPI components parameters"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_cyclic_parameter_refs() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "parameters": {
                "Tenant": {"$ref": "#/components/parameters/Loop"},
                "Loop": {"$ref": "#/components/parameters/Tenant"},
            },
        },
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [{"$ref": "#/components/parameters/Tenant"}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="cyclic parameter ref"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_deep_parameter_ref_chains() -> None:
    parameter_components: dict[str, object] = {
        f"Param{index}": {"$ref": f"#/components/parameters/Param{index + 1}"}
        for index in range(70)
    }
    parameter_components["Param70"] = {
        "name": "X-Tenant",
        "in": "header",
        "schema": {"type": "string", "default": "north"},
    }
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"parameters": parameter_components},
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [{"$ref": "#/components/parameters/Param0"}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="parameter ref depth"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_unsafe_parameter_definitions() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "parameters": [
                        {
                            "name": "X-Bad\nHeader",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="parameter name"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_unsupported_parameter_locations() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "parameters": [
                        {
                            "name": "debug",
                            "in": "body",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="parameter location"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_malformed_parameter_collections() -> None:
    path_parameters_not_list: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"parameters": {"name": "debug"}, "get": _ok_operation()}},
    }
    operation_parameter_not_mapping: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": ["debug"],
        "responses": {"200": {"description": "ok"}},
    }

    with pytest.raises(OpenApiCompilationError, match="parameters must be a list"):
        compile_openapi_to_hurl(path_parameters_not_list, tags=frozenset())
    with pytest.raises(OpenApiCompilationError, match="parameter 0 must be a mapping"):
        _compile_single_operation(operation_parameter_not_mapping)


def test_compile_openapi_rejects_parameter_name_location_schema_and_value_shapes() -> None:
    missing_name: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"in": "query", "schema": {"type": "string"}}],
        "responses": {"200": {"description": "ok"}},
    }
    bad_location_type: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": 1, "schema": {"type": "string"}}],
        "responses": {"200": {"description": "ok"}},
    }
    unsafe_header_token: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "Bad Header", "in": "header", "schema": {"type": "string"}}],
        "responses": {"200": {"description": "ok"}},
    }
    bad_schema: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": "query", "schema": "string"}],
        "responses": {"200": {"description": "ok"}},
    }
    non_scalar_example: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": "query", "example": ["yes"]}],
        "responses": {"200": {"description": "ok"}},
    }
    control_example: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": "query", "example": "yes\tplease"}],
        "responses": {"200": {"description": "ok"}},
    }
    template_example: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": "query", "example": "{{debug}}"}],
        "responses": {"200": {"description": "ok"}},
    }
    non_finite_example: dict[str, object] = {
        "operationId": "getHealth",
        "parameters": [{"name": "debug", "in": "query", "example": float("inf")}],
        "responses": {"200": {"description": "ok"}},
    }

    cases: tuple[tuple[dict[str, object], str], ...] = (
        (missing_name, "parameter name must be a non-empty string"),
        (bad_location_type, "parameter location must be one of"),
        (unsafe_header_token, "not safe for header"),
        (bad_schema, "parameter 0 schema must be a mapping"),
        (non_scalar_example, "must be a scalar"),
        (control_example, "contains control characters"),
        (template_example, "contains Hurl template delimiters"),
        (non_finite_example, "must be finite"),
    )
    for operation, expected_error in cases:
        with pytest.raises(OpenApiCompilationError, match=expected_error):
            _compile_single_operation(operation)


def test_compile_openapi_rejects_parameter_variable_name_collisions() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "listOrders",
                    "parameters": [
                        {
                            "name": "foo-bar",
                            "in": "query",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "foo_bar",
                            "in": "query",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="fallback variable"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_renders_parameter_overrides_fallbacks_and_scalars() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/orders/{order_id}/{missing-id}/{123}": {
                "parameters": [
                    {"name": "order_id", "in": "path", "schema": {"type": "string"}},
                    {"name": "flag", "in": "query", "schema": {"type": "boolean", "default": True}},
                    {"name": "n", "in": "query", "schema": {"type": "integer", "default": 5}},
                ],
                "get": {
                    "operationId": "getOrderFallbacks",
                    "parameters": [
                        {
                            "name": "order_id",
                            "in": "path",
                            "example": "ord 42",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "ratio",
                            "in": "query",
                            "schema": {"type": "number", "default": 1.5},
                        },
                        {
                            "name": "X-Debug",
                            "in": "header",
                            "schema": {"type": "boolean", "default": False},
                        },
                        {"name": "cid", "in": "cookie", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"text/plain": {"schema": {"type": "string"}}},
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert (
        "GET {{base_url}}/orders/ord%2042/{{missing_id}}/{{param_123}}"
        "?flag=true&n=5&ratio=1.5"
    ) in content
    assert "X-Debug: false" in content
    assert "Cookie: cid={{cid}}" in content
    assert "[Asserts]" not in content


def test_compile_openapi_renders_form_exploded_array_query_defaults() -> None:
    operation: dict[str, object] = {
        "operationId": "searchOrders",
        "parameters": [
            {
                "name": "tag",
                "in": "query",
                "schema": {"type": "array", "items": {"type": "string"}, "default": ["a", "b"]},
            },
        ],
        "responses": {"200": {"description": "ok"}},
    }

    content = _compile_single_operation(operation, path="/orders/search")

    assert "GET {{base_url}}/orders/search?tag=a&tag=b" in content


def test_compile_openapi_renders_form_non_exploded_array_query_examples() -> None:
    operation: dict[str, object] = {
        "operationId": "searchOrders",
        "parameters": [
            {
                "name": "color",
                "in": "query",
                "style": "form",
                "explode": False,
                "example": ["red blue", "green"],
                "schema": {"type": "array", "items": {"type": "string"}},
            },
        ],
        "responses": {"200": {"description": "ok"}},
    }

    content = _compile_single_operation(operation, path="/orders/search")

    assert "GET {{base_url}}/orders/search?color=red%20blue,green" in content


@pytest.mark.parametrize(
    ("parameter", "expected_error"),
    [
        (
            {
                "name": "tag",
                "in": "query",
                "style": "pipeDelimited",
                "schema": {"type": "array", "items": {"type": "string"}, "default": ["a", "b"]},
            },
            "array query parameter style",
        ),
        (
            {
                "name": "X-Tags",
                "in": "header",
                "schema": {"type": "array", "items": {"type": "string"}, "default": ["a", "b"]},
            },
            "array parameter examples/defaults are only supported for query parameters",
        ),
        (
            {
                "name": "tag",
                "in": "query",
                "schema": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "array query parameter example/default must contain at least one item",
        ),
        (
            {
                "name": "tag",
                "in": "query",
                "schema": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": "not-a-list",
                },
            },
            "array query parameter example/default must be a list",
        ),
        (
            {
                "name": "tag",
                "in": "query",
                "style": 1,
                "schema": {"type": "array", "items": {"type": "string"}, "default": ["a"]},
            },
            "parameter style must be a string",
        ),
        (
            {
                "name": "tag",
                "in": "query",
                "explode": "true",
                "schema": {"type": "array", "items": {"type": "string"}, "default": ["a"]},
            },
            "parameter explode must be a boolean",
        ),
    ],
)
def test_compile_openapi_rejects_unsupported_array_query_parameters(
    parameter: dict[str, object],
    expected_error: str,
) -> None:
    operation: dict[str, object] = {
        "operationId": "searchOrders",
        "parameters": [parameter],
        "responses": {"200": {"description": "ok"}},
    }

    with pytest.raises(OpenApiCompilationError, match=expected_error):
        _compile_single_operation(operation, path="/orders/search")


def test_compile_openapi_defensively_rejects_array_values_outside_query_rendering() -> None:
    path_parameter = openapi_compiler._OpenApiParameter(  # noqa: SLF001
        name="order_id",
        location="path",
        variable_name="order_id",
        example_value=("ord_1", "ord_2"),
        style="simple",
        explode=False,
    )
    header_parameter = openapi_compiler._OpenApiParameter(  # noqa: SLF001
        name="X-Tags",
        location="header",
        variable_name="X_Tags",
        example_value=("a", "b"),
        style="simple",
        explode=False,
    )

    with pytest.raises(OpenApiCompilationError, match="array parameter values"):
        openapi_compiler._render_request_target(  # noqa: SLF001
            "/orders/{order_id}",
            (path_parameter,),
        )
    with pytest.raises(OpenApiCompilationError, match="array parameter values"):
        openapi_compiler._render_parameter_headers((header_parameter,))  # noqa: SLF001


def test_compile_openapi_rejects_malformed_path_templates_and_unsafe_path_variables() -> None:
    malformed: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/orders/{order_id": {"get": _ok_operation()}},
    }
    unsafe_variable: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/orders/{!!!}": {"get": _ok_operation()}},
    }

    with pytest.raises(OpenApiCompilationError, match="malformed parameter braces"):
        compile_openapi_to_hurl(malformed, tags=frozenset())
    with pytest.raises(OpenApiCompilationError, match="safe variable name"):
        compile_openapi_to_hurl(unsafe_variable, tags=frozenset())


def test_compile_openapi_defensive_path_template_validation_rejects_control_names() -> None:
    with pytest.raises(OpenApiCompilationError, match="control characters"):
        openapi_compiler._validate_path_template("/orders/{bad\nid}")  # noqa: SLF001
