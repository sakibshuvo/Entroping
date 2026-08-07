import pytest
from openapi_to_hurl_test_helpers import (
    _compile_single_operation,
    _deep_json_value,
    _deep_required_object_schema,
    _ok_operation,
    _oversized_openapi_string,
)

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError, compile_openapi_to_hurl


def _wide_json_value() -> list[dict[str, int]]:
    return [{"index": index} for index in range(10_001)]


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


def test_compile_openapi_rejects_top_level_response_control_jsonpath_field_names() -> None:
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
                                        "required": ["bad\nname"],
                                        "properties": {
                                            "bad\nname": {"type": "string"},
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

    with pytest.raises(OpenApiCompilationError, match="JSONPath field"):
        compile_openapi_to_hurl(document, tags=frozenset())


@pytest.mark.parametrize(
    "field_name",
    [
        "bad'name",
        'bad"name',
        "bad\\name",
        "bad{{name",
        "bad\tname",
    ],
)
def test_compile_openapi_rejects_nested_unsafe_jsonpath_field_names(
    field_name: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/account": {
                "get": {
                    "operationId": "getAccount",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["data"],
                                        "properties": {
                                            "data": {
                                                "type": "object",
                                                "required": [field_name],
                                                "properties": {
                                                    field_name: {"type": "string"},
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
        },
    }

    with pytest.raises(OpenApiCompilationError, match="JSONPath field"):
        compile_openapi_to_hurl(document, tags=frozenset())


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
        (
            {
                "operationId": "bad",
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id"],
                                    "properties": {"id": None},
                                },
                            },
                        },
                    },
                },
            },
            "schema for 'id' must be a mapping",
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


def test_compile_openapi_rejects_excessively_deep_schema_rendering() -> None:
    operation: dict[str, object] = {
        "operationId": "createDeepSchema",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": _deep_required_object_schema(80),
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="schema depth exceeds"):
        _compile_single_operation(operation, path="/deep", method="post")


def test_compile_openapi_rejects_unbounded_schema_string_generation() -> None:
    operation: dict[str, object] = {
        "operationId": "createHugeString",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string", "minLength": 1_000_000}},
                    },
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="string length exceeds"):
        _compile_single_operation(operation, path="/huge-string", method="post")


def test_compile_openapi_rejects_unbounded_boundary_string_generation() -> None:
    operation: dict[str, object] = {
        "operationId": "createHugeBoundaryString",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string", "maxLength": 1_000_000}},
                    },
                },
            },
        },
        "responses": {
            "201": {"description": "created"},
            "422": {"description": "validation failed"},
        },
    }

    with pytest.raises(OpenApiCompilationError, match="string length exceeds"):
        _compile_single_operation(operation, path="/huge-boundary", method="post")


@pytest.mark.parametrize(
    ("literal_name", "literal_value"),
    (
        ("example", _oversized_openapi_string()),
        ("default", _oversized_openapi_string()),
        ("const", _oversized_openapi_string()),
    ),
)
def test_compile_openapi_rejects_oversized_schema_literal_strings(
    literal_name: str,
    literal_value: str,
) -> None:
    operation: dict[str, object] = {
        "operationId": "createHugeLiteral",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {
                                "type": "string",
                                literal_name: literal_value,
                            },
                        },
                    },
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="string length exceeds"):
        _compile_single_operation(operation, path="/huge-literal", method="post")


def test_compile_openapi_rejects_excessively_deep_schema_examples() -> None:
    operation: dict[str, object] = {
        "operationId": "createDeepExample",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["payload"],
                        "properties": {"payload": {"example": _deep_json_value(80)}},
                    },
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="JSON depth exceeds"):
        _compile_single_operation(operation, path="/deep-example", method="post")


def test_compile_openapi_rejects_more_than_ten_thousand_schema_nodes() -> None:
    operation: dict[str, object] = {
        "operationId": "createWideSchema",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": [f"field_{index}" for index in range(10_001)],
                        "properties": {
                            f"field_{index}": {"type": "string"}
                            for index in range(10_001)
                        },
                    },
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="schema traversal exceeds"):
        _compile_single_operation(operation, path="/wide-schema", method="post")


def test_compile_openapi_rejects_more_than_ten_thousand_json_nodes() -> None:
    operation: dict[str, object] = {
        "operationId": "createWideExample",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["payload"],
                        "properties": {"payload": {"example": _wide_json_value()}},
                    },
                },
            },
        },
        "responses": {"201": {"description": "created"}},
    }

    with pytest.raises(OpenApiCompilationError, match="JSON traversal exceeds"):
        _compile_single_operation(operation, path="/wide-example", method="post")


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
