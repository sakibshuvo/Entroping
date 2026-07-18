import pytest

from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl_with_report,
)


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
