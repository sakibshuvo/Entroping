"""Unit tests for deterministic OpenAPI-to-Hurl compilation."""

from pathlib import Path

import pytest
from openapi_to_hurl_test_helpers import _compile_single_operation, _ok_operation

from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
    compile_openapi_to_hurl_with_report,
)
from entroping.core.run_safety import evaluate_run_safety
from entroping.models.hurl import HurlTest, parse_hurl_exchanges, parse_hurl_metadata


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


def test_compile_openapi_treats_vendor_json_media_types_as_json() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/events": {
                "post": {
                    "operationId": "createEvent",
                    "requestBody": {
                        "content": {
                            "application/vnd.entroping.event+json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["event_type"],
                                    "properties": {
                                        "event_type": {
                                            "type": "string",
                                            "default": "checkout.created",
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
                                "application/problem+json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["status"],
                                        "properties": {
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

    generated = compile_openapi_to_hurl(document, tags=frozenset())

    content = generated[0].content
    assert "Content-Type: application/vnd.entroping.event+json" in content
    assert '"event_type": "checkout.created"' in content
    assert "HTTP 201" in content
    assert 'jsonpath "$.status" exists' in content
    assert 'jsonpath "$.status" == "accepted"' in content


def test_compile_openapi_prefers_exact_application_json_over_vendor_json() -> None:
    operation: dict[str, object] = {
        "operationId": "createPriority",
        "requestBody": {
            "content": {
                "application/vnd.entroping.priority+json": {
                    "schema": {
                        "type": "object",
                        "required": ["source"],
                        "properties": {"source": {"type": "string", "default": "vendor"}},
                    },
                },
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["source"],
                        "properties": {"source": {"type": "string", "default": "exact"}},
                    },
                },
            },
        },
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "application/vnd.entroping.response+json": {
                        "schema": {
                            "type": "object",
                            "required": ["mode"],
                            "properties": {"mode": {"type": "string", "enum": ["vendor"]}},
                        },
                    },
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["mode"],
                            "properties": {"mode": {"type": "string", "enum": ["exact"]}},
                        },
                    },
                },
            },
        },
    }

    content = _compile_single_operation(operation, path="/priority", method="post")

    assert "Content-Type: application/json" in content
    assert "Content-Type: application/vnd.entroping.priority+json" not in content
    assert '"source": "exact"' in content
    assert '"source": "vendor"' not in content
    assert 'jsonpath "$.mode" == "exact"' in content
    assert 'jsonpath "$.mode" == "vendor"' not in content


def test_compile_openapi_matches_json_media_types_case_insensitively() -> None:
    operation: dict[str, object] = {
        "operationId": "createCaseInsensitive",
        "requestBody": {
            "content": {
                "Application/Vnd.Entroping.Case+JSON": {
                    "schema": {
                        "type": "object",
                        "required": ["source"],
                        "properties": {
                            "source": {"type": "string", "default": "upper"},
                        },
                    },
                },
            },
        },
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "Application/JSON": {
                        "schema": {
                            "type": "object",
                            "required": ["mode"],
                            "properties": {"mode": {"type": "string", "enum": ["exact"]}},
                        },
                    },
                },
            },
        },
    }

    content = _compile_single_operation(operation, path="/case", method="post")

    assert "Content-Type: Application/Vnd.Entroping.Case+JSON" in content
    assert '"source": "upper"' in content
    assert 'jsonpath "$.mode" == "exact"' in content


def test_compile_openapi_selects_vendor_json_media_type_deterministically() -> None:
    operation: dict[str, object] = {
        "operationId": "createMultiVendor",
        "requestBody": {
            "content": {
                "application/vnd.zed+json": {
                    "schema": {
                        "type": "object",
                        "required": ["source"],
                        "properties": {"source": {"type": "string", "default": "zed"}},
                    },
                },
                "application/problem+json": {
                    "schema": {
                        "type": "object",
                        "required": ["source"],
                        "properties": {"source": {"type": "string", "default": "problem"}},
                    },
                },
            },
        },
        "responses": {"200": {"description": "ok"}},
    }

    content = _compile_single_operation(operation, path="/multi-vendor", method="post")

    assert "Content-Type: application/problem+json" in content
    assert "Content-Type: application/vnd.zed+json" not in content
    assert '"source": "problem"' in content
    assert '"source": "zed"' not in content


def test_compile_openapi_does_not_guess_unsupported_non_json_media_types() -> None:
    operation: dict[str, object] = {
        "operationId": "createXml",
        "requestBody": {
            "content": {
                "application/xml": {"schema": {"type": "object", "required": ["id"]}},
                "text/json": {"schema": {"type": "object", "required": ["id"]}},
            },
        },
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "application/xml": {"schema": {"type": "object", "required": ["id"]}},
                    "text/json": {"schema": {"type": "object", "required": ["id"]}},
                },
            },
        },
    }

    content = _compile_single_operation(operation, path="/xml", method="post")

    assert "Content-Type:" not in content
    assert '"id":' not in content
    assert "[Asserts]" not in content


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


def test_compile_openapi_generates_bounded_negative_path_corpus_with_safety_metadata() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/accounts/{account_id}/checkouts": {
                "post": {
                    "operationId": "createAccountCheckout",
                    "parameters": [
                        {
                            "name": "account_id",
                            "in": "path",
                            "example": "acct-001",
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "quantity"],
                                    "properties": {
                                        "email": {
                                            "type": "string",
                                            "minLength": 3,
                                        },
                                        "quantity": {
                                            "type": "integer",
                                            "minimum": 1,
                                            "maximum": 5,
                                        },
                                        "coupon": {"type": "string"},
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

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"checkout"}))

    assert [item.relative_path for item in result.files] == [
        "tests/generated/create_account_checkout.hurl",
        "tests/generated/negative/create_account_checkout_malformed_json.hurl",
        "tests/generated/negative/create_account_checkout_schema_violations.hurl",
        "tests/generated/negative/create_account_checkout_boundary_values.hurl",
        "tests/generated/negative/create_account_checkout_sqli_like_strings.hurl",
        "tests/generated/negative/create_account_checkout_idor_path_variants.hurl",
    ]
    negative_files = result.files[1:]
    joined = "\n---\n".join(item.content for item in negative_files)
    for category in (
        "malformed-json",
        "schema-violations",
        "boundary-values",
        "sqli-like-strings",
        "idor-path-variants",
    ):
        assert f"# entroping: negative_category={category}" in joined
        matching = [
            item
            for item in negative_files
            if f"# entroping: negative_category={category}" in item.content
        ]
        assert len(matching) == 1
        assert parse_hurl_metadata(matching[0].content).tags >= frozenset(
            {"checkout", "generated", "negative", category}
        )

    assert "# entroping: severity=medium" in joined
    assert "# entroping: severity=high" in joined
    assert "# entroping: safety=destructive" in joined
    assert "HTTP 400" in joined
    assert '"email": "xx"' in joined
    assert '"quantity": 0' in joined
    assert "\"coupon\": \"' OR '1'='1\"" in joined
    assert "POST {{base_url}}/accounts/acct-other/checkouts" in joined

    generated_tests = [
        HurlTest(
            path=Path(item.relative_path),
            metadata=parse_hurl_metadata(item.content, source=Path(item.relative_path)),
            exchanges=parse_hurl_exchanges(item.content),
        )
        for item in negative_files
    ]
    safety = evaluate_run_safety(
        generated_tests,
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )
    assert len(safety.blocks) == len(negative_files)
    assert {block.evidence.blocked_reason for block in safety.blocks} == {
        "destructive tests are blocked in protected environments"
    }


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
