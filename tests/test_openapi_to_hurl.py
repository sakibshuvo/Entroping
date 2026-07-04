"""Unit tests for deterministic OpenAPI-to-Hurl compilation."""

import importlib
from pathlib import Path
from typing import cast

import pytest

from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl,
    compile_openapi_to_hurl_with_report,
)
from entroping.core.run_safety import evaluate_run_safety
from entroping.models.hurl import HurlTest, parse_hurl_exchanges, parse_hurl_metadata


def test_openapi_to_hurl_package_exposes_compatibility_surface() -> None:
    compiler_module = importlib.import_module("entroping.bridge.openapi_to_hurl.compiler")
    parameters_module = importlib.import_module("entroping.bridge.openapi_to_hurl.parameters")

    assert openapi_compiler.compile_openapi_to_hurl is compiler_module.compile_openapi_to_hurl
    assert openapi_compiler.OpenApiCompilationError is compiler_module.OpenApiCompilationError
    assert openapi_compiler._OpenApiParameter is compiler_module._OpenApiParameter  # noqa: SLF001
    assert openapi_compiler._TraversalBudget is compiler_module._TraversalBudget  # noqa: SLF001
    assert openapi_compiler._render_request_target is parameters_module._render_request_target  # noqa: SLF001
    assert openapi_compiler._render_parameter_headers is parameters_module._render_parameter_headers  # noqa: SLF001
    assert openapi_compiler._validate_path_template is parameters_module._validate_path_template  # noqa: SLF001
    with pytest.raises(
        AttributeError,
        match=r"module 'entroping\.bridge\.openapi_to_hurl' has no attribute '_missing'",
    ):
        missing_attribute = "_missing"
        getattr(openapi_compiler, missing_attribute)


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


def _deep_required_object_schema(depth: int) -> dict[str, object]:
    schema: dict[str, object] = {"type": "string"}
    for index in range(depth):
        field = f"child_{index}"
        schema = {
            "type": "object",
            "required": [field],
            "properties": {field: schema},
        }
    return schema


def _deep_json_value(depth: int) -> dict[str, object]:
    value: dict[str, object] = {"leaf": "ok"}
    for index in range(depth):
        value = {f"child_{index}": value}
    return value


def _oversized_openapi_string() -> str:
    return "x" * (openapi_compiler._MAX_OPENAPI_GENERATED_STRING_LENGTH + 1)  # noqa: SLF001


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


def test_compile_openapi_generates_security_negative_tests_for_supported_schemes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "basicAuth": {"type": "http", "scheme": "basic"},
                "apiKeyHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                },
                "apiKeyQuery": {
                    "type": "apiKey",
                    "in": "query",
                    "name": "access_key",
                },
                "apiKeyCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session_id",
                },
            },
        },
        "paths": {
            "/accounts/{account_id}": {
                "get": {
                    "operationId": "getAccount",
                    "security": [
                        {
                            "bearerAuth": [],
                            "basicAuth": [],
                            "apiKeyHeader": [],
                            "apiKeyQuery": [],
                            "apiKeyCookie": [],
                        }
                    ],
                    "parameters": [
                        {
                            "name": "account_id",
                            "in": "path",
                            "example": "acct-001",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"security"}))

    assert result.security_findings == ()
    assert [item.relative_path for item in result.files] == [
        "tests/generated/get_account.hurl",
        "tests/generated/security/get_account_missing_auth.hurl",
        "tests/generated/security/get_account_invalid_bearer_auth.hurl",
        "tests/generated/security/get_account_invalid_basic_auth.hurl",
        "tests/generated/security/get_account_invalid_api_key_header.hurl",
        "tests/generated/security/get_account_invalid_api_key_query.hurl",
        "tests/generated/security/get_account_invalid_api_key_cookie.hurl",
    ]
    joined = "\n---\n".join(item.content for item in result.files)
    assert "# entroping: tags=auth,generated,invalid-auth,negative,security" in joined
    assert "# entroping: operation_id=getAccount" in joined
    assert "# entroping: negative_category=invalid-auth" in joined
    assert "# entroping: severity=high" in joined
    assert "# entroping: safety=read-only" in joined
    assert "# entroping: security=missing_auth" in joined
    assert "# entroping: security=invalid_auth" in joined
    assert "# entroping: security_scheme=bearerAuth" in joined
    assert "GET {{base_url}}/accounts/acct-001" in joined
    assert "Authorization: Bearer invalid-token" in joined
    assert "Authorization: Basic ZW50cm9waW5nOmludmFsaWQ=" in joined
    assert "X-API-Key: invalid-api-key" in joined
    assert "?access_key=invalid-api-key" in joined
    assert "Cookie: session_id=invalid-session" in joined
    assert "HTTP 401" in joined


def test_compile_openapi_merges_cookie_parameter_and_cookie_auth_negative() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                "sessionAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session_id",
                },
            },
        },
        "paths": {
            "/account": {
                "get": {
                    "operationId": "getAccount",
                    "security": [{"sessionAuth": []}],
                    "parameters": [
                        {
                            "name": "locale",
                            "in": "cookie",
                            "schema": {"type": "string", "default": "en-US"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"security"}))

    invalid_cookie_file = next(
        item
        for item in result.files
        if item.relative_path == "tests/generated/security/get_account_invalid_session_auth.hurl"
    )
    cookie_lines = [
        line for line in invalid_cookie_file.content.splitlines() if line.startswith("Cookie: ")
    ]
    assert cookie_lines == ["Cookie: locale=en-US; session_id=invalid-session"]


def test_compile_openapi_skips_auth_negatives_for_public_security_alternative() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
        },
        "paths": {
            "/catalog": {
                "get": {
                    "operationId": "getCatalog",
                    "security": [{}, {"bearerAuth": []}],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset({"catalog"}))

    assert result.security_findings == ()
    assert [item.relative_path for item in result.files] == [
        "tests/generated/get_catalog.hurl",
    ]
    assert "missing_auth" not in "\n".join(item.content for item in result.files)
    assert "invalid_auth" not in "\n".join(item.content for item in result.files)


@pytest.mark.parametrize(
    ("scheme_name", "expected_error"),
    [
        ("bearerAuth\n# entroping: safety=destructive", "control characters"),
        ("{{bearerAuth}}", "Hurl template delimiters"),
    ],
)
def test_compile_openapi_rejects_unsafe_security_scheme_names(
    scheme_name: str,
    expected_error: str,
) -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                scheme_name: {"type": "http", "scheme": "bearer"},
            },
        },
        "paths": {
            "/secret": {
                "get": {
                    "operationId": "getSecret",
                    "security": [{scheme_name: []}],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match=expected_error):
        compile_openapi_to_hurl_with_report(document, tags=frozenset())


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


def test_compile_openapi_rejects_duplicate_schema_negative_generated_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def duplicate_schema_negative_file(**_: object) -> tuple[openapi_compiler.GeneratedHurlFile]:
        return (
            openapi_compiler.GeneratedHurlFile(
                relative_path="tests/generated/get_health.hurl",
                content="GET {{base_url}}/duplicate\nHTTP 400\n",
            ),
        )

    monkeypatch.setattr(openapi_compiler, "_schema_negative_files", duplicate_schema_negative_file)

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {"/health": {"get": _ok_operation("getHealth")}},
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl_with_report(document, tags=frozenset())


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


def test_compile_openapi_reports_security_gaps_without_guessing() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "security": [{"oauth": []}],
        "components": {
            "securitySchemes": {
                "oauth": {
                    "type": "oauth2",
                    "flows": {},
                },
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
        },
        "paths": {
            "/oauth-only": {
                "get": {
                    "operationId": "getOauthOnly",
                    "responses": {"200": {"description": "ok"}, "401": {"description": "no"}},
                },
            },
            "/missing-response": {
                "get": {
                    "operationId": "getMissingResponse",
                    "security": [{"bearerAuth": []}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
            "/public": {
                "get": {
                    "operationId": "getPublic",
                    "security": [],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == [
        "tests/generated/get_oauth_only.hurl",
        "tests/generated/get_missing_response.hurl",
        "tests/generated/get_public.hurl",
    ]
    assert [
        (finding.operation_id, finding.scheme_name, finding.reason)
        for finding in result.security_findings
    ] == [
        ("getOauthOnly", "oauth", "unsupported security scheme type oauth2"),
        (
            "getMissingResponse",
            "bearerAuth",
            "missing explicit 401 or 403 response for auth-negative test",
        ),
    ]
    assert "invalid_bearer_auth" not in "\n".join(item.relative_path for item in result.files)


def test_compile_openapi_security_tests_render_body_403_and_deduplicate_schemes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": {
            "/checkout": {
                "post": {
                    "operationId": "createCheckout",
                    "security": [{"bearerAuth": []}, {"bearerAuth": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["cart_id"],
                                    "properties": {"cart_id": {"type": "string"}},
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "created"},
                        "403": {"description": "forbidden"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [item.relative_path for item in result.files] == [
        "tests/generated/create_checkout.hurl",
        "tests/generated/security/create_checkout_missing_auth.hurl",
        "tests/generated/security/create_checkout_invalid_bearer_auth.hurl",
    ]
    invalid_auth = result.files[2].content
    assert "Content-Type: application/json" in invalid_auth
    assert '"cart_id": "string"' in invalid_auth
    assert "HTTP 403" in invalid_auth


def test_compile_openapi_rejects_duplicate_security_generated_paths() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                "api key": {"type": "apiKey", "in": "header", "name": "X-One"},
                "api_key": {"type": "apiKey", "in": "header", "name": "X-Two"},
            },
        },
        "paths": {
            "/secret": {
                "get": {
                    "operationId": "getSecret",
                    "security": [{"api key": [], "api_key": []}],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl_with_report(document, tags=frozenset())


def test_compile_openapi_reports_missing_security_schemes_without_components() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {},
        "paths": {
            "/secret": {
                "get": {
                    "operationId": "getSecret",
                    "security": [{"missingAuth": []}],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [
        (finding.scheme_name, finding.reason) for finding in result.security_findings
    ] == [("missingAuth", "security scheme is not defined")]


def test_compile_openapi_reports_unsupported_security_scheme_shapes() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {
                "httpNoScheme": {"type": "http"},
                "digestAuth": {"type": "http", "scheme": "digest"},
                "apiKeyMissingName": {"type": "apiKey", "in": "header"},
                "apiKeyBody": {"type": "apiKey", "in": "body", "name": "token"},
            },
        },
        "paths": {
            "/secret": {
                "get": {
                    "operationId": "getSecret",
                    "security": [
                        {
                            "httpNoScheme": [],
                            "digestAuth": [],
                            "apiKeyMissingName": [],
                            "apiKeyBody": [],
                        }
                    ],
                    "responses": {
                        "200": {"description": "ok"},
                        "401": {"description": "unauthorized"},
                    },
                },
            },
        },
    }

    result = compile_openapi_to_hurl_with_report(document, tags=frozenset())

    assert [
        (finding.scheme_name, finding.reason) for finding in result.security_findings
    ] == [
        ("httpNoScheme", "http security scheme is missing a string scheme"),
        ("digestAuth", "unsupported http security scheme digest"),
        (
            "apiKeyMissingName",
            "apiKey security scheme requires string in and name fields",
        ),
        ("apiKeyBody", "unsupported apiKey location or name 'body'"),
    ]


def test_compile_openapi_rejects_malformed_security_requirements() -> None:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "security": "bad",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="security must be a list"):
        compile_openapi_to_hurl_with_report(document, tags=frozenset())


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
    assert 'jsonpath "$.loose" == null' in content
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


def test_compile_openapi_budget_helpers_reject_node_exhaustion() -> None:
    schema_budget = openapi_compiler._TraversalBudget(  # noqa: SLF001
        nodes=openapi_compiler._MAX_OPENAPI_SCHEMA_NODES,  # noqa: SLF001
    )
    with pytest.raises(OpenApiCompilationError, match="schema traversal exceeds"):
        openapi_compiler._check_openapi_schema_budget(  # noqa: SLF001
            depth=0,
            budget=schema_budget,
            context="OpenAPI schema",
        )

    json_budget = openapi_compiler._TraversalBudget(  # noqa: SLF001
        nodes=openapi_compiler._MAX_OPENAPI_JSON_NODES,  # noqa: SLF001
    )
    with pytest.raises(OpenApiCompilationError, match="JSON traversal exceeds"):
        openapi_compiler._check_openapi_json_budget(  # noqa: SLF001
            depth=0,
            budget=json_budget,
            context="OpenAPI schema example",
        )


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
