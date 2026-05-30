"""Unit tests for deterministic OpenAPI-to-Hurl compilation."""

import pytest

from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
)


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
