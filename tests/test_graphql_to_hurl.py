import shutil
from pathlib import Path

import pytest

from entroping.bridge.graphql_to_hurl import (
    GraphqlHurlCompilationError,
    compile_graphql_sdl_to_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHQL_SCHEMA = REPO_ROOT / "examples" / "graphql-api" / "schema.graphql"


def test_compile_graphql_sdl_to_hurl_generates_deterministic_smoke_scaffold() -> None:
    generated = compile_graphql_sdl_to_hurl(
        GRAPHQL_SCHEMA.read_text(encoding="utf-8"),
        target_url="https://api.example.test/graphql",
    )

    assert generated.relative_path == "tests/generated/graphql-api-example-test-graphql-smoke.hurl"
    assert generated.content == (
        "# entroping: tags=smoke,graphql\n"
        "# entroping: source=graphql-sdl\n"
        "# entroping: target_origin=https://api.example.test\n"
        "# entroping: operation_categories=mutation,query\n"
        "# entroping: scaffold=typename-smoke\n"
        "\n"
        "POST https://api.example.test/graphql\n"
        "Content-Type: application/json\n"
        "{\n"
        '  "query": "query EntropingSmoke { __typename }"\n'
        "}\n"
        "HTTP 200\n"
        "[Asserts]\n"
        'jsonpath "$.errors" not exists\n'
    )
    assert "user(id:" not in generated.content
    assert "updatePlan" not in generated.content
    assert "Ada Lovelace" not in generated.content
    assert parse_hurl_metadata(generated.content).tags == frozenset({"smoke", "graphql"})
    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "POST"
    assert exchange.url == "https://api.example.test/graphql"


def test_compile_graphql_sdl_to_hurl_accepts_local_fixture_target() -> None:
    generated = compile_graphql_sdl_to_hurl(
        GRAPHQL_SCHEMA.read_text(encoding="utf-8"),
        target_url="http://127.0.0.1:18082/graphql",
    )

    assert "POST http://127.0.0.1:18082/graphql\n" in generated.content
    assert "# entroping: target_origin=http://127.0.0.1:18082\n" in generated.content


def test_compile_graphql_sdl_to_hurl_ignores_empty_operation_blocks() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Mutation {}\ntype Query { viewer: String }",
        target_url="https://api.example.test/graphql",
    )

    assert "# entroping: operation_categories=query\n" in generated.content


def test_compile_graphql_sdl_to_hurl_requires_query_root() -> None:
    with pytest.raises(GraphqlHurlCompilationError, match="at least one Query field"):
        compile_graphql_sdl_to_hurl(
            "type Mutation { updatePlan(id: ID!): Boolean }",
            target_url="https://api.example.test/graphql",
        )


@pytest.mark.parametrize(
    ("schema_sdl", "message"),
    [
        ("", "GraphQL SDL is required"),
        ("type Query { viewer: String }\x00", "disallowed control characters"),
        ("type Query { token: String = \"sk-proj-secret123\" }", "secret-like"),
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_unsafe_schema_input(
    schema_sdl: str,
    message: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError, match=message):
        compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
        )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("", "GraphQL target URL is required"),
        ("ftp://api.example.test/graphql", "scheme must be http or https"),
        ("https://user:pass@api.example.test/graphql", "must not contain credentials"),
        ("https://api.example.test/graphql#fragment", "must not contain a fragment"),
        ("https://api.example.test/graphql\x00", "contains control characters"),
        ("https://api.example.test/has space", "must not contain whitespace"),
        ("https://api.example.test/{{secret}}", "contains Hurl template delimiters"),
        ("https://api.example.test:abc/graphql", "contains an invalid port"),
        ("https:///graphql", "must include a host"),
        ("https://api.example.test/graphql?api_key=placeholder", "sensitive query key"),
        ("https://api.example.test/graphql?ready=sk-proj-secret123", "secret-like"),
        ("https://api.example.test/sk-proj-secret123", "secret-like"),
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_unsafe_targets(
    target_url: str,
    message: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError, match=message):
        compile_graphql_sdl_to_hurl(
            "type Query { viewer: String }",
            target_url=target_url,
        )


def test_compile_graphql_sdl_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_graphql_sdl_to_hurl(
        GRAPHQL_SCHEMA.read_text(encoding="utf-8"),
        target_url="https://api.example.test/graphql",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
