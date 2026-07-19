from typing import cast

import pytest
from openapi_to_hurl_test_helpers import _compile_single_operation, _oversized_openapi_string

from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
    compile_openapi_to_hurl_with_report,
)
from entroping.models.hurl import parse_hurl_metadata


def test_compile_openapi_uses_vendor_json_for_schema_negative_generation() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/patches": {
                "patch": {
                    "operationId": "patchResource",
                    "requestBody": {
                        "content": {
                            "application/merge-patch+json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string", "minLength": 3},
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "200": {"description": "ok"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"patch"}))

    assert [item.relative_path for item in result.files] == [
        "tests/generated/patch_resource.hurl",
        "tests/generated/negative/patch_resource_malformed_json.hurl",
        "tests/generated/negative/patch_resource_schema_violations.hurl",
        "tests/generated/negative/patch_resource_boundary_values.hurl",
        "tests/generated/negative/patch_resource_sqli_like_strings.hurl",
    ]
    assert all(
        "Content-Type: application/merge-patch+json" in item.content for item in result.files
    )


def test_compile_openapi_generates_invalid_enum_negative_for_body_and_query_fields() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shipments": {
                "post": {
                    "operationId": "createShipment",
                    "parameters": [
                        {
                            "name": "region",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["us", "eu"]},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": ["standard", "express"],
                                        },
                                        "priority": {
                                            "type": "integer",
                                            "enum": [1, 2],
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"shipments"}))
    enum_negative = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/negative/create_shipment_invalid_enum_values.hurl"
    )

    assert "# entroping: negative_category=invalid-enum-values" in enum_negative.content
    assert "POST {{base_url}}/shipments?region=entroping_invalid_enum" in enum_negative.content
    assert '"mode": "entroping_invalid_enum"' in enum_negative.content
    assert '"priority": "entroping_invalid_enum"' in enum_negative.content
    assert "HTTP 422" in enum_negative.content
    assert parse_hurl_metadata(enum_negative.content).tags >= frozenset(
        {"shipments", "generated", "negative", "invalid-enum-values"}
    )


def test_compile_openapi_invalid_enum_negative_handles_path_suffix_and_skips_params() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shipments/{kind}": {
                "post": {
                    "operationId": "createShipmentByKind",
                    "parameters": [
                        {
                            "name": "kind",
                            "in": "path",
                            "schema": {
                                "type": "string",
                                "enum": ["entroping_invalid_enum"],
                            },
                        },
                        {
                            "name": "X-Mode",
                            "in": "header",
                            "schema": {"type": "string", "enum": ["strict"]},
                        },
                        {
                            "name": "tags",
                            "in": "query",
                            "example": ["fast"],
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {"mode": {"type": "string"}},
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
    enum_negative = next(
        item
        for item in result.files
        if item.relative_path
        == "tests/generated/negative/create_shipment_by_kind_invalid_enum_values.hurl"
    )

    assert (
        "POST {{base_url}}/shipments/entroping_invalid_enum_2?tags=fast"
        in enum_negative.content
    )
    assert '"mode": "string"' in enum_negative.content
    assert "X-Mode" not in enum_negative.content


def test_compile_openapi_skips_invalid_enum_negative_without_validation_response() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/shipments": {
                "post": {
                    "operationId": "createShipment",
                    "parameters": [
                        {
                            "name": "region",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["us", "eu"]},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": ["standard", "express"],
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == ["tests/generated/create_shipment.hurl"]


def test_compile_openapi_generates_only_malformed_negative_for_non_object_schema() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/bulk": {
                "post": {
                    "operationId": "createBulk",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "responses": {
                        "202": {"description": "accepted"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == [
        "tests/generated/create_bulk.hurl",
        "tests/generated/negative/create_bulk_malformed_json.hurl",
    ]
    negative_content = result.files[1].content
    assert "# entroping: negative_category=malformed-json" in negative_content
    assert '`{"entroping_malformed":`' in negative_content
    assert "HTTP 422" in negative_content


def test_compile_openapi_skips_inapplicable_object_negative_cases_without_guessing() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/payload": {
                "post": {
                    "operationId": "createPayload",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "example": "unexpected"},
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

    assert [item.relative_path for item in result.files] == [
        "tests/generated/create_payload.hurl",
        "tests/generated/negative/create_payload_malformed_json.hurl",
    ]
    assert "# entroping: negative_category=schema-violations" not in result.files[1].content
    assert "# entroping: negative_category=boundary-values" not in result.files[1].content
    assert "# entroping: negative_category=sqli-like-strings" not in result.files[1].content
    assert '"unexpected"' in result.files[0].content


def test_compile_openapi_negative_boundaries_use_maximum_constraints() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["code", "level"],
                                    "properties": {
                                        "code": {"type": "string", "maxLength": 2},
                                        "level": {"type": "integer", "maximum": 10},
                                    },
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
    boundary = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/negative/create_limit_boundary_values.hurl"
    )

    assert '"code": "xx"' in result.files[0].content
    assert '"level": 10' in result.files[0].content
    assert '"code": "xxx"' in boundary.content
    assert '"level": 11' in boundary.content


def test_compile_openapi_negative_boundaries_use_exclusive_numeric_constraints() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["count", "score"],
                                    "properties": {
                                        "count": {
                                            "type": "integer",
                                            "exclusiveMaximum": 10,
                                        },
                                        "score": {
                                            "type": "number",
                                            "exclusiveMinimum": 1.5,
                                        },
                                    },
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
    boundary = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/negative/create_limit_boundary_values.hurl"
    )

    assert '"count": 10' in boundary.content
    assert '"score": 1.5' in boundary.content


def test_compile_openapi_skips_ambiguous_integer_numeric_boundaries() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "count": {"type": "integer", "minimum": 1.5},
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "422": {"description": "validation failed"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == [
        "tests/generated/create_limit.hurl",
        "tests/generated/negative/create_limit_malformed_json.hurl",
    ]


def test_compile_openapi_skips_non_finite_numeric_bounds_in_negative_generation() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["count", "score", "threshold"],
                                    "properties": {
                                        "count": {
                                            "type": "integer",
                                            "minimum": float("-inf"),
                                            "maximum": 10,
                                        },
                                        "score": {
                                            "type": "number",
                                            "minimum": float("nan"),
                                            "maximum": float("inf"),
                                        },
                                        "threshold": {
                                            "type": "number",
                                            "minimum": 1.5,
                                            "maximum": float("nan"),
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "422": {"description": "invalid"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    joined = "\n".join(item.content for item in result.files)
    assert "NaN" not in joined
    assert "Infinity" not in joined
    boundary = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/negative/create_limit_boundary_values.hurl"
    )
    assert '"count": 11' in boundary.content
    assert '"score": 0' in boundary.content
    assert '"threshold": 0.5' in boundary.content


def test_compile_openapi_skips_non_finite_enum_values_before_rendering() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["level"],
                                    "properties": {
                                        "level": {
                                            "type": "number",
                                            "enum": [float("nan"), float("inf"), 2.5],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "number",
                                                "enum": [
                                                    float("-inf"),
                                                    float("nan"),
                                                    3.5,
                                                ],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "422": {"description": "invalid"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    joined = "\n".join(item.content for item in result.files)
    assert "NaN" not in joined
    assert "Infinity" not in joined
    assert '"level": 2.5' in result.files[0].content
    assert 'jsonpath "$.status" == 3.5' in result.files[0].content


def test_compile_openapi_falls_back_when_enums_have_no_finite_values() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/limits": {
                "post": {
                    "operationId": "createLimit",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["level"],
                                    "properties": {
                                        "level": {
                                            "type": "number",
                                            "enum": [
                                                float("nan"),
                                                float("inf"),
                                                float("-inf"),
                                            ],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "number",
                                                "enum": [
                                                    float("inf"),
                                                    float("-inf"),
                                                    float("nan"),
                                                ],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "422": {"description": "invalid"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    joined = "\n".join(item.content for item in result.files)
    assert "NaN" not in joined
    assert "Infinity" not in joined
    assert '"level": 0' in result.files[0].content
    assert 'jsonpath "$.status" exists' in result.files[0].content
    assert 'jsonpath "$.status" ==' not in result.files[0].content


def test_compile_openapi_skips_unsafe_enum_strings_before_rendering() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/modes": {
                "post": {
                    "operationId": "createMode",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": ["{{unsafe_token}}", "safe-mode"],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "enum": ["bad\nvalue", "accepted"],
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    content = result.files[0].content
    assert "{{unsafe_token}}" not in content
    assert "bad\nvalue" not in content
    assert "bad\\nvalue" not in content
    assert '"mode": "safe-mode"' in content
    assert 'jsonpath "$.status" == "accepted"' in content


def test_compile_openapi_falls_back_when_enum_strings_are_all_unsafe() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/modes": {
                "post": {
                    "operationId": "createMode",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": ["{{unsafe_token}}", "bad\nvalue"],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "enum": ["bad\nvalue", "{{unsafe_token}}"],
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    content = result.files[0].content
    assert "{{unsafe_token}}" not in content
    assert "bad\nvalue" not in content
    assert "bad\\nvalue" not in content
    assert '"mode": "string"' in content
    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.status" ==' not in content


def test_compile_openapi_skips_oversized_enum_strings_before_rendering() -> None:
    oversized = _oversized_openapi_string()
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/modes": {
                "post": {
                    "operationId": "createMode",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": [oversized, "safe-mode"],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "enum": [oversized, "accepted"],
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    content = result.files[0].content
    assert oversized not in content
    assert '"mode": "safe-mode"' in content
    assert 'jsonpath "$.status" == "accepted"' in content


def test_compile_openapi_falls_back_when_enum_strings_are_all_oversized() -> None:
    oversized = _oversized_openapi_string()
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/modes": {
                "post": {
                    "operationId": "createMode",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {"type": "string", "enum": [oversized]},
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {"type": "string", "enum": [oversized]},
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    content = result.files[0].content
    assert oversized not in content
    assert '"mode": "string"' in content
    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.status" ==' not in content


def test_compile_openapi_renders_null_enum_values_before_fallbacks() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/modes": {
                "post": {
                    "operationId": "createMode",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["mode"],
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": [{}, None, "safe-mode"],
                                        },
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "enum": [[], None, "accepted"],
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    content = result.files[0].content
    assert '"mode": null' in content
    assert '"mode": "safe-mode"' not in content
    assert 'jsonpath "$.status" == null' in content
    assert 'jsonpath "$.status" == "accepted"' not in content


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
    assert 'jsonpath "$.loose" == null' in content
    assert 'jsonpath "$.mode" exists' in content
    assert 'jsonpath "$.mode" ==' not in content
    assert 'jsonpath "$.missing" exists' in content


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array", "items": {"type": "object", "required": ["id"]}},
        {"type": "string"},
        {"type": ["null", "string"]},
    ],
)
def test_compile_openapi_skips_non_object_response_schema_assertions(
    schema: dict[str, object],
) -> None:
    operation: dict[str, object] = {
        "operationId": "getHealth",
        "responses": {
            "200": {
                "description": "ok",
                "content": {"application/json": {"schema": schema}},
            },
        },
    }

    content = _compile_single_operation(operation)

    assert "[Asserts]" not in content
    assert "jsonpath" not in content


@pytest.mark.parametrize(
    "schema",
    [
        {
            "type": "array",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        },
        {"type": "string", "required": ["id"]},
        {"type": ["null", "string"], "properties": {"id": {"type": "string"}}},
    ],
)
def test_compile_openapi_rejects_object_assertion_fields_on_non_object_response_schemas(
    schema: dict[str, object],
) -> None:
    operation: dict[str, object] = {
        "operationId": "getHealth",
        "responses": {
            "200": {
                "description": "ok",
                "content": {"application/json": {"schema": schema}},
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="non-object response schema"):
        _compile_single_operation(operation)


def test_compile_openapi_resolves_response_schema_refs_before_assertions() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "required": ["status", "mode"],
                    "properties": {
                        "status": {"$ref": "#/components/schemas/Status"},
                        "mode": {"type": "string"},
                    },
                },
                "Status": {"type": "string", "enum": ["ok"]},
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    generated = compile_openapi_to_hurl(document, tags=frozenset())

    assert len(generated) == 1
    content = generated[0].content
    assert "[Asserts]" in content
    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.status" == "ok"' in content
    assert 'jsonpath "$.mode" exists' in content


def test_compile_openapi_generates_nested_required_response_assertions() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Envelope": {
                    "type": "object",
                    "required": ["data"],
                    "properties": {
                        "data": {"$ref": "#/components/schemas/Account"},
                    },
                },
                "Account": {
                    "type": "object",
                    "required": ["id", "state", "owner"],
                    "properties": {
                        "id": {"type": "string", "enum": ["acct-1"]},
                        "state": {"allOf": [{"type": "string"}, {"enum": ["active"]}]},
                        "owner": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string", "enum": ["Ada"]},
                            },
                        },
                    },
                },
            },
        },
        "paths": {
            "/account": {
                "get": {
                    "operationId": "getAccount",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Envelope"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.data" exists' in content
    assert 'jsonpath "$.data.id" exists' in content
    assert 'jsonpath "$.data.id" == "acct-1"' in content
    assert 'jsonpath "$.data.state" == "active"' in content
    assert 'jsonpath "$.data.owner" exists' in content
    assert 'jsonpath "$.data.owner.name" == "Ada"' in content


def test_compile_openapi_generates_bracket_jsonpath_response_assertions() -> None:
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
                                        "required": [
                                            "123field",
                                            "a.b",
                                            "display name",
                                            "user-name",
                                            "data-root",
                                        ],
                                        "properties": {
                                            "123field": {
                                                "type": "string",
                                                "enum": ["leading"],
                                            },
                                            "a.b": {"type": "string"},
                                            "display name": {"type": "string"},
                                            "user-name": {
                                                "type": "string",
                                                "enum": ["Ada"],
                                            },
                                            "data-root": {
                                                "type": "object",
                                                "required": ["child.value"],
                                                "properties": {
                                                    "child.value": {
                                                        "type": "string",
                                                        "enum": ["ok"],
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
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$[\'123field\']" exists' in content
    assert 'jsonpath "$[\'123field\']" == "leading"' in content
    assert 'jsonpath "$[\'a.b\']" exists' in content
    assert 'jsonpath "$[\'display name\']" exists' in content
    assert 'jsonpath "$[\'user-name\']" exists' in content
    assert 'jsonpath "$[\'user-name\']" == "Ada"' in content
    assert 'jsonpath "$[\'data-root\']" exists' in content
    assert 'jsonpath "$[\'data-root\'][\'child.value\']" exists' in content
    assert 'jsonpath "$[\'data-root\'][\'child.value\']" == "ok"' in content


def test_compile_openapi_merges_nested_assertions_from_overlapping_all_of() -> None:
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
                                        "allOf": [
                                            {
                                                "type": "object",
                                                "required": ["payload"],
                                                "properties": {
                                                    "payload": {
                                                        "type": "object",
                                                        "required": ["id"],
                                                        "properties": {
                                                            "id": {
                                                                "type": "string",
                                                                "enum": ["acct-1"],
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                            {
                                                "type": "object",
                                                "required": ["payload"],
                                                "properties": {
                                                    "payload": {
                                                        "type": "object",
                                                        "required": ["state"],
                                                        "properties": {
                                                            "state": {
                                                                "type": "string",
                                                                "enum": ["active"],
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.payload" exists' in content
    assert 'jsonpath "$.payload.id" == "acct-1"' in content
    assert 'jsonpath "$.payload.state" == "active"' in content


def test_compile_openapi_rejects_incompatible_overlapping_all_of_property_shapes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/status": {
                "get": {
                    "operationId": "getStatus",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "allOf": [
                                            {
                                                "type": "object",
                                                "required": ["status"],
                                                "properties": {
                                                    "status": {
                                                        "type": "string",
                                                        "enum": ["ok"],
                                                    },
                                                },
                                                    },
                                            {
                                                "type": "object",
                                                "required": ["status"],
                                                "properties": {
                                                    "status": {
                                                        "required": ["code"],
                                                        "properties": {
                                                            "code": {"type": "string"},
                                                        },
                                                    },
                                                },
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="conflicting allOf property schema"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_preserves_compatible_overlapping_all_of_property_shapes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/status": {
                "get": {
                    "operationId": "getStatus",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "allOf": [
                                            {
                                                "type": "object",
                                                "required": ["status", "count"],
                                                "properties": {
                                                    "status": {"description": "first"},
                                                    "count": {"type": "integer"},
                                                },
                                            },
                                            {
                                                "type": "object",
                                                "required": ["status", "count"],
                                                "properties": {
                                                    "status": {"description": "second"},
                                                    "count": {"type": "number"},
                                                },
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.count" exists' in content


def test_compile_openapi_rejects_nested_response_schema_ref_cycles() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "required": ["child"],
                    "properties": {
                        "child": {"$ref": "#/components/schemas/Node"},
                    },
                },
            },
        },
        "paths": {
            "/node": {
                "get": {
                    "operationId": "getNode",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="cyclic response schema ref"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_nested_property_all_of_ref_cycles() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Loop": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Loop"},
                    ],
                },
            },
        },
        "paths": {
            "/status": {
                "get": {
                    "operationId": "getStatus",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["status"],
                                        "properties": {
                                            "status": {
                                                "allOf": [
                                                    {"$ref": "#/components/schemas/Loop"},
                                                ],
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

    with pytest.raises(OpenApiCompilationError, match="cyclic response schema composition"):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_resolves_escaped_response_schema_ref_names() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Health/Response~V1": {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"type": "string", "enum": ["ok"]}},
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Health~1Response~0V1"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.status" == "ok"' in content


def test_compile_openapi_resolves_transitive_response_schema_refs() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Outer": {"$ref": "#/components/schemas/Middle"},
                "Middle": {"$ref": "#/components/schemas/Inner"},
                "Inner": {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"type": "string", "enum": ["ok"]}},
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Outer"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.status" == "ok"' in content


def test_compile_openapi_merges_all_of_response_schema_assertions() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "HealthResponse": {
                    "allOf": [
                        {
                            "type": "object",
                            "required": ["status"],
                            "properties": {
                                "status": {"type": "string", "enum": ["ok"]},
                                "kind": {"type": "string"},
                            },
                        },
                        {"$ref": "#/components/schemas/HealthDetails"},
                    ],
                },
                "HealthDetails": {
                    "type": "object",
                    "required": ["mode", "kind"],
                    "properties": {
                        "mode": {"allOf": [{"type": "string"}, {"enum": ["live"]}]},
                        "kind": {"type": "string", "enum": ["health"]},
                        "status": {
                            "type": "string",
                            "description": "same response field with extra metadata",
                            "enum": ["ok"],
                        },
                    },
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.status" == "ok"' in content
    assert 'jsonpath "$.mode" exists' in content
    assert 'jsonpath "$.mode" == "live"' in content
    assert 'jsonpath "$.kind" == "health"' in content


def test_compile_openapi_merges_root_and_all_of_response_assertions() -> None:
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
                                        "required": ["status"],
                                        "properties": {
                                            "status": {"type": "string", "enum": ["ok"]},
                                        },
                                        "allOf": [
                                            {
                                                "type": "object",
                                                "required": ["mode"],
                                                "properties": {"mode": {"type": "string"}},
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    content = compile_openapi_to_hurl(document, tags=frozenset())[0].content

    assert 'jsonpath "$.status" == "ok"' in content
    assert 'jsonpath "$.mode" exists' in content


@pytest.mark.parametrize("composition_key", ["oneOf", "anyOf"])
def test_compile_openapi_rejects_ambiguous_response_schema_composition(
    composition_key: str,
) -> None:
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
                                        composition_key: [
                                            {
                                                "type": "object",
                                                "required": ["status"],
                                                "properties": {
                                                    "status": {"type": "string"},
                                                },
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="unsupported response schema composition"):
        compile_openapi_to_hurl(document, tags=frozenset())


@pytest.mark.parametrize(
    ("schema", "expected_error"),
    [
        ({"allOf": "not-a-sequence"}, "OpenAPI response schema allOf must be an array"),
        ({"allOf": ["not-a-schema"]}, "OpenAPI response schema allOf member 0"),
        (
            {
                "allOf": [
                    {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"type": "string", "enum": ["ok"]}},
                    },
                    {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"type": "string", "enum": ["fail"]}},
                    },
                ],
            },
            "conflicting allOf property schema",
        ),
        (
            {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {"oneOf": [{"type": "string", "enum": ["ok"]}]},
                },
            },
            "unsupported response schema composition",
        ),
        (
            {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {"allOf": "not-a-sequence"},
                },
            },
            "schema for 'status' allOf must be an array",
        ),
        (
            {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {
                        "allOf": [
                            {"type": "string", "enum": ["ok"]},
                            {"type": "string", "enum": ["fail"]},
                        ],
                    },
                },
            },
            "schema for 'status' conflicting allOf property schema",
        ),
        (
            {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {
                        "allOf": [
                            {"type": "string", "enum": ["ok"]},
                            {
                                "type": "object",
                                "required": ["code"],
                                "properties": {"code": {"type": "string"}},
                            },
                        ],
                    },
                },
            },
            "schema for 'status' conflicting allOf property schema",
        ),
        (
            {
                "allOf": [
                    {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"type": "string"}},
                    },
                    {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"allOf": "not-a-sequence"}},
                    },
                ],
            },
            "OpenAPI response schema property 'status' allOf must be an array",
        ),
    ],
)
def test_compile_openapi_rejects_unsafe_all_of_response_schemas(
    schema: dict[str, object],
    expected_error: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": schema}},
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match=expected_error):
        compile_openapi_to_hurl(document, tags=frozenset())


def test_compile_openapi_rejects_deep_response_schema_ref_chains() -> None:
    max_depth = cast(int, openapi_compiler._MAX_RESPONSE_SCHEMA_REF_DEPTH)  # noqa: SLF001
    schema_components: dict[str, object] = {
        f"Schema{index}": {"$ref": f"#/components/schemas/Schema{index + 1}"}
        for index in range(max_depth + 1)
    }
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"schemas": schema_components},
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Schema0"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="response schema ref depth"):
        compile_openapi_to_hurl(document, tags=frozenset())


@pytest.mark.parametrize(
    ("schema", "components", "expected_error"),
    (
        (
            {"$ref": "common.yaml#/components/schemas/HealthResponse"},
            {"HealthResponse": {"type": "object"}},
            "only local response schema refs",
        ),
        (
            {"$ref": "#/components/parameters/HealthResponse"},
            {"HealthResponse": {"type": "object"}},
            "unsupported response schema ref",
        ),
        (
            {"$ref": "#/components/schemas/Missing"},
            {"HealthResponse": {"type": "object"}},
            "unknown response schema ref",
        ),
        (
            {"$ref": "#/components/schemas/HealthResponse", "description": "ok"},
            {"HealthResponse": {"type": "object"}},
            "response schema ref must not define sibling fields",
        ),
        (
            {"$ref": "#/components/schemas/HealthResponse"},
            {"HealthResponse": "not-a-schema"},
            "response schema ref target",
        ),
        (
            {"$ref": "#/components/schemas/Loop"},
            {"Loop": {"$ref": "#/components/schemas/Loop"}},
            "cyclic response schema ref",
        ),
        (
            {"$ref": "#/components/schemas/"},
            {},
            "malformed response schema ref",
        ),
        (
            {"$ref": "#/components/schemas/Bad~2Name"},
            {},
            "malformed response schema ref",
        ),
        (
            {"$ref": "#/components/schemas/Bad~"},
            {},
            "malformed response schema ref",
        ),
        (
            {"$ref": 1},
            {},
            "response schema ref must be a string",
        ),
        (
            {"allOf": [{"$ref": 1}]},
            {},
            "response schema ref must be a string",
        ),
        (
            {"$ref": "#/components/schemas/Loop"},
            {"Loop": {"allOf": [{"$ref": "#/components/schemas/Loop"}]}},
            "cyclic response schema composition",
        ),
    ),
)
def test_compile_openapi_rejects_unsupported_response_schema_refs(
    schema: dict[str, object],
    components: dict[str, object],
    expected_error: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"schemas": components},
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": schema}},
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match=expected_error):
        compile_openapi_to_hurl(document, tags=frozenset())
