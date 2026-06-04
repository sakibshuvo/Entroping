"""Unit tests for deterministic OpenAPI-to-Hurl compilation."""

import pytest

from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
)


def _compile_single_operation(
    operation: dict[str, object],
    *,
    path: str = "/health",
    method: str = "get",
    tags: frozenset[str] = frozenset(),
) -> str:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {path: {method: operation}},
    }
    return compile_openapi_to_hurl(document, tags=tags)[0].content


def _ok_operation(operation_id: str = "getHealth") -> dict[str, object]:
    return {
        "operationId": operation_id,
        "responses": {"200": {"description": "ok"}},
    }


def test_compile_openapi_generates_deterministic_hurl_files() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "Checkout API", "version": "0.1.0"},
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["status"],
                                        "properties": {
                                            "status": {"type": "string", "enum": ["ok"]},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["cart_id"],
                                    "properties": {
                                        "cart_id": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["id", "status"],
                                        "properties": {
                                            "id": {"type": "string"},
                                            "status": {
                                                "type": "string",
                                                "enum": ["accepted"],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    generated = compile_openapi_to_hurl(document, tags=frozenset({"smoke"}))

    assert [item.relative_path for item in generated] == [
        "tests/generated/get_health.hurl",
        "tests/generated/create_checkout.hurl",
    ]
    health = generated[0].content
    assert "# entroping: tags=generated,smoke" in health
    assert "# entroping: source=openapi" in health
    assert "# entroping: operation_id=getHealth" in health
    assert "GET {{base_url}}/health" in health
    assert "HTTP 200" in health
    assert 'jsonpath "$.status" exists' in health
    assert 'jsonpath "$.status" == "ok"' in health

    checkout = generated[1].content
    assert "# entroping: operation_id=createCheckout" in checkout
    assert "POST {{base_url}}/checkout" in checkout
    assert "Content-Type: application/json" in checkout
    assert '"cart_id": "string"' in checkout
    assert "HTTP 201" in checkout
    assert 'jsonpath "$.id" exists' in checkout
    assert 'jsonpath "$.status" == "accepted"' in checkout


def test_compile_openapi_can_filter_to_selected_operation_ids() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": _ok_operation("getHealth")},
            "/checkout": {"post": _ok_operation("createCheckout")},
            "/refunds": {"post": _ok_operation("createRefund")},
        },
    }

    generated = compile_openapi_to_hurl(
        document,
        tags=frozenset({"smoke"}),
        operation_ids=frozenset({"createCheckout", "createRefund"}),
    )

    assert [item.relative_path for item in generated] == [
        "tests/generated/create_checkout.hurl",
        "tests/generated/create_refund.hurl",
    ]
    assert all("# entroping: tags=generated,smoke" in item.content for item in generated)
    assert "getHealth" not in "\n".join(item.content for item in generated)


def test_compile_openapi_rejects_selected_operation_ids_that_match_nothing() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": _ok_operation("getHealth")}},
    }

    with pytest.raises(OpenApiCompilationError, match="selected operations"):
        compile_openapi_to_hurl(
            document,
            tags=frozenset(),
            operation_ids=frozenset({"createCheckout"}),
        )


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


def test_compile_openapi_rejects_missing_paths_mapping() -> None:
    with pytest.raises(
        OpenApiCompilationError,
        match="OpenAPI document must contain a paths mapping",
    ):
        compile_openapi_to_hurl({"openapi": "3.1.0"}, tags=frozenset())


def test_compile_openapi_rejects_duplicate_generated_hurl_paths() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/one": {"get": _ok_operation("get user")},
            "/two": {"get": _ok_operation("get_user")},
        },
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_documents_without_supported_operations() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"summary": "not an operation"}},
    }

    with pytest.raises(OpenApiCompilationError, match="supported HTTP operations"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_control_characters_in_metadata_values() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "get\nHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="operationId"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_whitespace_in_paths() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/bad path": {
                "get": {
                    "operationId": "getBadPath",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="absolute path strings"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_non_mapping_path_items_and_operations() -> None:
    bad_path_item: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": "not-a-path-item"},
    }
    bad_operation: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": "not-an-operation"}},
    }

    with pytest.raises(OpenApiCompilationError, match="OpenAPI path '/health' must be a mapping"):
        compile_openapi_to_hurl(bad_path_item, tags=frozenset())
    with pytest.raises(OpenApiCompilationError, match="OpenAPI operation 'get' /health"):
        compile_openapi_to_hurl(bad_operation, tags=frozenset())


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


def test_compile_openapi_rejects_control_characters_in_parameter_values() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "parameters": [
                        {
                            "name": "X-Request-Id",
                            "in": "header",
                            "schema": {"type": "string", "default": "req\t123"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="control characters"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_hurl_template_delimiters_in_parameter_values() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "parameters": [
                        {
                            "name": "Authorization",
                            "in": "header",
                            "schema": {"type": "string", "default": "Bearer {{token}}"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="Hurl template delimiters"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_hurl_template_delimiters_in_schema_examples() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["cart_id"],
                                    "properties": {
                                        "cart_id": {
                                            "type": "string",
                                            "example": "{{cart_id}}",
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="Hurl template delimiters"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_secret_like_fallback_variable_names() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/leak/{AWS_SECRET_ACCESS_KEY}": {
                "get": {
                    "operationId": "leakSecret",
                    "parameters": [
                        {
                            "name": "AWS_SECRET_ACCESS_KEY",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="secret-like fallback variable"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_hurl_template_delimiters_in_json_object_keys() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["{{secret}}"],
                                    "properties": {
                                        "{{secret}}": {
                                            "type": "string",
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="JSON object key"):
        compile_openapi_to_hurl(document, tags=frozenset())


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


def test_compile_openapi_rejects_non_finite_schema_examples() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount"],
                                    "properties": {
                                        "amount": {
                                            "type": "number",
                                            "default": float("nan"),
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="finite"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_unsafe_jsonpath_field_names() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ['bad"name'],
                                        "properties": {'bad"name': {"type": "string"}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="JSONPath field"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_renders_request_and_response_schema_fallbacks() -> None:
    operation: dict[str, object] = {
        "operationId": "createSchemaExample",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": [
                            "items",
                            "count",
                            "ok",
                            "name",
                            "nothing",
                            "empty_examples",
                            "mapped_example",
                            "metadata_only_example",
                            "empty_object",
                        ],
                        "properties": {
                            "items": {"type": "array"},
                            "count": {"type": "integer"},
                            "ok": {"type": "boolean"},
                            "name": {},
                            "nothing": {"example": None},
                            "empty_examples": {"examples": []},
                            "mapped_example": {
                                "examples": {
                                    "skipped": {"summary": "metadata only"},
                                    "chosen": {"value": ["a", {"b": True}]},
                                },
                            },
                            "metadata_only_example": {
                                "examples": {"skipped": {"summary": "metadata only"}},
                            },
                            "empty_object": {"type": "object", "required": []},
                        },
                    },
                },
            },
        },
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["id", "loose", "mode", "missing"],
                            "properties": {
                                "id": {"type": "string", "enum": ["evt-1"]},
                                "loose": {"type": "string", "enum": [None, {}]},
                                "mode": {"type": "string", "enum": "manual"},
                            },
                        },
                    },
                },
            },
        },
    }

    content = _compile_single_operation(operation, path="/schemas", method="post")

    assert '"items": []' in content
    assert '"count": 0' in content
    assert '"ok": false' in content
    assert '"name": "string"' in content
    assert '"nothing": null' in content
    assert '"empty_examples": "string"' in content
    assert '"mapped_example": [\n    "a",' in content
    assert '"metadata_only_example": "string"' in content
    assert '"empty_object": {}' in content
    assert 'jsonpath "$.id" == "evt-1"' in content
    assert 'jsonpath "$.loose" exists' in content
    assert 'jsonpath "$.mode" exists' in content
    assert 'jsonpath "$.mode" ==' not in content
    assert 'jsonpath "$.missing" exists' in content


def test_compile_openapi_selects_lowest_numeric_response_when_no_success_status() -> None:
    operation: dict[str, object] = {
        "operationId": "getMissing",
        "responses": {
            "default": {"description": "fallback"},
            "404": {"description": "not found"},
            "500": {"description": "server error"},
        },
    }

    content = _compile_single_operation(operation)

    assert "HTTP 404" in content


def test_compile_openapi_renders_operation_id_fallback_and_empty_json_content_shapes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {}},
                        },
                    },
                },
            },
            "/empty-asserts": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": [],
                                        "properties": {},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "/no-required": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {}},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    generated = compile_openapi_to_hurl(document, tags=frozenset())

    assert [item.relative_path for item in generated] == [
        "tests/generated/get_root.hurl",
        "tests/generated/get_empty_asserts.hurl",
        "tests/generated/get_no_required.hurl",
    ]
    assert "# entroping: operation_id=get_root" in generated[0].content
    assert "[Asserts]" not in generated[0].content
    assert "[Asserts]" not in generated[1].content
    assert "[Asserts]" not in generated[2].content


def test_compile_openapi_rejects_response_and_json_content_shape_errors() -> None:
    cases: tuple[tuple[dict[str, object], str], ...] = (
        (
            {"operationId": "bad", "responses": {"default": {"description": "fallback"}}},
            "at least one numeric response status",
        ),
        (
            {"operationId": "bad", "responses": {"200": "ok"}},
            "OpenAPI response 200 must be a mapping",
        ),
        (
            {
                "operationId": "bad",
                "requestBody": "json",
                "responses": {"200": {"description": "ok"}},
            },
            "OpenAPI requestBody must be a mapping",
        ),
        (
            {
                "operationId": "bad",
                "requestBody": {"content": "json"},
                "responses": {"200": {"description": "ok"}},
            },
            "OpenAPI content must be a mapping",
        ),
        (
            {
                "operationId": "bad",
                "requestBody": {"content": {"application/json": "json"}},
                "responses": {"200": {"description": "ok"}},
            },
            "OpenAPI application/json content must be a mapping",
        ),
        (
            {
                "operationId": "bad",
                "requestBody": {"content": {"application/json": {"schema": "json"}}},
                "responses": {"200": {"description": "ok"}},
            },
            "OpenAPI JSON schema must be a mapping",
        ),
        (
            {
                "operationId": "bad",
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {"application/json": {"schema": {"required": "id"}}},
                    },
                },
            },
            "OpenAPI schema required must be a list of strings",
        ),
    )

    for operation, expected_error in cases:
        with pytest.raises(OpenApiCompilationError, match=expected_error):
            _compile_single_operation(operation)


def test_compile_openapi_rejects_schema_required_and_property_shape_errors() -> None:
    required_not_string: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "required": ["id", ""], "properties": {}},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    properties_not_mapping: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "required": ["id"], "properties": []},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    property_schema_not_mapping: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {"id": "string"},
                    },
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    control_key: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["bad\nkey"],
                        "properties": {"bad\nkey": {"type": "string"}},
                    },
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }

    cases: tuple[tuple[dict[str, object], str], ...] = (
        (required_not_string, "must contain only non-empty strings"),
        (properties_not_mapping, "OpenAPI object properties must be a mapping"),
        (property_schema_not_mapping, "schema for 'id' must be a mapping"),
        (control_key, "JSON object key contains control characters"),
    )
    for operation, expected_error in cases:
        with pytest.raises(OpenApiCompilationError, match=expected_error):
            _compile_single_operation(operation, path="/bad", method="post")


def test_compile_openapi_rejects_invalid_schema_examples_defaults_and_keys() -> None:
    invalid_examples_type: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "examples": 1},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    examples_item_not_mapping: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"examples": {"one": "not-a-mapping"}},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    non_string_object_key: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"default": {1: "bad"}},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }
    non_json_default: dict[str, object] = {
        "operationId": "bad",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"default": object()},
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }

    cases: tuple[tuple[dict[str, object], str], ...] = (
        (invalid_examples_type, "must be a list or mapping"),
        (examples_item_not_mapping, "OpenAPI schema examples item must be a mapping"),
        (non_string_object_key, "keys must be strings"),
        (non_json_default, "must be JSON-compatible"),
    )
    for operation, expected_error in cases:
        with pytest.raises(OpenApiCompilationError, match=expected_error):
            _compile_single_operation(operation, path="/bad", method="post")


def test_compile_openapi_rejects_operation_ids_and_tags_that_break_generated_metadata() -> None:
    with pytest.raises(OpenApiCompilationError, match="safe file name"):
        _compile_single_operation(
            {"operationId": "!!!", "responses": {"200": {"description": "ok"}}},
        )
    with pytest.raises(OpenApiCompilationError, match="tags must not be empty"):
        _compile_single_operation(_ok_operation(), tags=frozenset({""}))
    with pytest.raises(OpenApiCompilationError, match="tag is not safe"):
        _compile_single_operation(_ok_operation(), tags=frozenset({"smoke,prod"}))
