import shutil
from pathlib import Path
from time import perf_counter

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


def test_compile_graphql_sdl_to_hurl_selects_unique_query_field() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: String }",
        target_url="https://api.example.test/graphql",
        query_field="viewer",
    )

    assert generated.content == (
        "# entroping: tags=smoke,graphql\n"
        "# entroping: source=graphql-sdl\n"
        "# entroping: target_origin=https://api.example.test\n"
        "# entroping: operation_categories=query\n"
        "# entroping: scaffold=typename-smoke\n"
        "\n"
        "POST https://api.example.test/graphql\n"
        "Content-Type: application/json\n"
        "{\n"
        '  "query": "query EntropingSmoke { viewer }"\n'
        "}\n"
        "HTTP 200\n"
        "[Asserts]\n"
        'jsonpath "$.errors" not exists\n'
    )


def test_compile_graphql_sdl_to_hurl_selects_field_from_query_extension() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: String } extend type Query { health: String }",
        target_url="https://api.example.test/graphql",
        query_field="health",
    )

    assert '"query": "query EntropingSmoke { health }"' in generated.content


@pytest.mark.parametrize("query_field", ["viewer", None])
def test_compile_graphql_sdl_to_hurl_rejects_query_header_without_its_own_body(
    query_field: str | None,
) -> None:
    schema_sdl = "type Query implements Missing type Mutation { viewer: String }"

    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field=query_field,
        )

    assert "Missing" not in str(error.value)
    assert "viewer" not in str(error.value)
    assert "Traceback" not in str(error.value)


@pytest.mark.parametrize(
    "schema_sdl",
    [
        "type Query implements Node & Named { viewer: String }",
        "type Query implements & Node & Named { viewer: String }",
        "type Query @root { viewer: String }",
        'type Query @root(label: "query") { viewer: String }',
        'type Query implements Node @root(label: "query") { viewer: String }',
    ],
)
def test_compile_graphql_sdl_to_hurl_accepts_valid_query_header_neighbors(
    schema_sdl: str,
) -> None:
    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field="viewer",
    )

    assert '"query": "query EntropingSmoke { viewer }"' in generated.content


@pytest.mark.parametrize(
    "schema_sdl",
    [
        "type Query implements & { viewer: String }",
        "type Query implements Node & { viewer: String }",
        "type Query @ { viewer: String }",
        "type Query implements Node implements Named { viewer: String }",
        "type Query @root implements Node { viewer: String }",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_malformed_query_header_grammar(
    schema_sdl: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="viewer",
        )

    assert "viewer" not in str(error.value)
    assert "Traceback" not in str(error.value)


@pytest.mark.parametrize(
    "field_definition",
    [
        "viewer: String extra",
        "viewer: String !!",
        "viewer: [String]!!",
        "viewer: String ! extra",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_selected_field_trailing_syntax(
    field_definition: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            f"type Query {{ {field_definition} }}",
            target_url="https://api.example.test/graphql",
            query_field="viewer",
        )

    assert "viewer" not in str(error.value)
    assert "Traceback" not in str(error.value)


@pytest.mark.parametrize("directive_value", ["{ ghost: VALUE }", "[{ ghost: VALUE }]"])
def test_compile_graphql_sdl_to_hurl_ignores_type_directive_object_literals(
    directive_value: str,
) -> None:
    schema_sdl = f"""
    directive @root(arg: Config) on OBJECT
    input Config {{ ghost: Mode }}
    enum Mode {{ VALUE }}
    type Query @root(arg: {directive_value}) {{ health: String }}
    """

    with pytest.raises(GraphqlHurlCompilationError, match="query_field"):
        compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="ghost",
        )
    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )

    assert '"query": "query EntropingSmoke { health }"' in generated.content


@pytest.mark.parametrize("default_value", ["{ ghost: VALUE }", "[{ ghost: VALUE }]"])
def test_compile_graphql_sdl_to_hurl_selects_field_after_nested_argument_default(
    default_value: str,
) -> None:
    schema_sdl = (
        f"input Input {{ ghost: Mode }} enum Mode {{ VALUE }} "
        f"type Query {{ other(filter: Input = {default_value}): String health: String }} "
        "type Mutation { update: String }"
    )

    with pytest.raises(GraphqlHurlCompilationError, match="query_field"):
        compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="ghost",
        )
    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )

    assert "# entroping: operation_categories=mutation,query\n" in generated.content
    assert '"query": "query EntropingSmoke { health }"' in generated.content


@pytest.mark.parametrize(
    "description",
    [
        r'''"""description with escaped triple quote: \""" and a fake field
        ghost: String
        """''',
        r'''"""description with a backslash \\ before \""" and a fake field
        ghost: String
        """''',
        r'''"""description with adjacent backslashes \\""" and a fake field
        ghost: String
        """''',
        '''"""description with a fake field
        ghost: String
        """''',
    ],
)
def test_compile_graphql_sdl_to_hurl_ignores_block_string_description_fields(
    description: str,
) -> None:
    schema_sdl = f"type Query {{\n{description}\nhealth: String\n}}"
    baseline = compile_graphql_sdl_to_hurl(
        "type Query { health: String }",
        target_url="https://api.example.test/graphql",
    )

    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="ghost",
        )
    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )
    omitted = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
    )

    assert "ghost" not in str(error.value)
    assert "Traceback" not in str(error.value)
    assert '"query": "query EntropingSmoke { ghost }"' not in generated.content
    assert '"query": "query EntropingSmoke { health }"' in generated.content
    assert omitted == baseline


@pytest.mark.parametrize(
    ("description", "query_field"),
    [
        ('"""description with a fake field\nghost: String', "ghost"),
        ('"""description with a fake field\nghost: String', "health"),
        (r'"""description with escaped triple quote: \"""\nghost: String', "ghost"),
        (r'"""description with escaped triple quote: \"""\nghost: String', "health"),
        (
            r'"""description with a backslash \\ before \"""\nghost: String',
            "ghost",
        ),
        (
            r'"""description with a backslash \\ before \"""\nghost: String',
            "health",
        ),
        (r'"""description with adjacent backslashes \\"""\nghost: String', "ghost"),
        (r'"""description with adjacent backslashes \\"""\nghost: String', "health"),
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_unterminated_block_string_content_free(
    description: str,
    query_field: str,
) -> None:
    schema_sdl = f"type Query {{\n{description}\nhealth: String\n}}"

    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field=query_field,
        )

    assert "ghost" not in str(error.value)
    assert "Traceback" not in str(error.value)


def test_compile_graphql_sdl_to_hurl_bounds_escaped_block_string_scanning() -> None:
    schema_sdl = 'type Query {\n"""' + (r'\"""' * 20_000) + "\nghost: String\nhealth: String\n}"
    started_at = perf_counter()

    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="ghost",
        )

    assert "ghost" not in str(error.value)
    assert perf_counter() - started_at < 2.0


def test_compile_graphql_sdl_to_hurl_scales_for_argument_list_fields() -> None:
    small_schema = (
        "type Query { "
        + " ".join(f"field{number}(values: [String]): String" for number in range(2_000))
        + " health: String }"
    )
    large_schema = (
        "type Query { "
        + " ".join(f"field{number}(values: [String]): String" for number in range(8_000))
        + " health: String }"
    )

    small_started_at = perf_counter()
    small_generated = compile_graphql_sdl_to_hurl(
        small_schema,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )
    small_elapsed = perf_counter() - small_started_at
    large_started_at = perf_counter()
    large_generated = compile_graphql_sdl_to_hurl(
        large_schema,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )
    large_elapsed = perf_counter() - large_started_at

    assert '"query": "query EntropingSmoke { health }"' in small_generated.content
    assert '"query": "query EntropingSmoke { health }"' in large_generated.content
    assert large_elapsed < (small_elapsed * 8) + 0.1


def test_compile_graphql_sdl_to_hurl_ignores_block_markers_in_comments_and_strings() -> None:
    schema_sdl = '''
    directive @root(label: String) on OBJECT
    type Query @root(label: "quoted") {
      # """ not a block string
      health: String
    }
    '''

    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field="health",
    )

    assert '"query": "query EntropingSmoke { health }"' in generated.content


def test_compile_graphql_sdl_to_hurl_rejects_malformed_type_directive_content_free() -> None:
    schema_sdl = "type Query @root(arg: { ghost: VALUE } { health: String }"

    with pytest.raises(GraphqlHurlCompilationError) as error:
        compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="health",
        )

    assert "ghost" not in str(error.value)


@pytest.mark.parametrize(
    "schema_sdl",
    [
        "type Query { viewer(argument: String }",
        "type Query { viewer(argument: String) }",
        "type Query { viewer: [String }",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_unclosed_selected_field_syntax(
    schema_sdl: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="viewer",
        )

    assert "viewer" not in str(error.value)


@pytest.mark.parametrize(
    "schema_sdl",
    [
        "type Query { health: }",
        "type Query { health(): }",
        "type Query { health: ! }",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_empty_selected_return_type_content_free(
    schema_sdl: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="health",
        )

    assert "health" not in str(error.value)
    assert "Traceback" not in str(error.value)


def test_compile_graphql_sdl_to_hurl_rejects_unclosed_preceding_selected_syntax() -> None:
    with pytest.raises(GraphqlHurlCompilationError) as error:
        _ = compile_graphql_sdl_to_hurl(
            "input Broken { type Query { viewer: String }",
            target_url="https://api.example.test/graphql",
            query_field="viewer",
        )

    assert "Broken" not in str(error.value)


def test_compile_graphql_sdl_to_hurl_selects_list_return_field() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: [String]! }",
        target_url="https://api.example.test/graphql",
        query_field="viewer",
    )

    assert '"query": "query EntropingSmoke { viewer }"' in generated.content


def test_compile_graphql_sdl_to_hurl_omitted_selector_deduplicates_legacy_categories() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: String } type Query { health: String }",
        target_url="https://api.example.test/graphql",
    )

    assert "# entroping: operation_categories=query\n" in generated.content


def test_compile_graphql_sdl_to_hurl_preserves_safe_target_query() -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: String }",
        target_url="https://api.example.test/graphql?ready=true",
    )

    assert "POST https://api.example.test/graphql?ready=true\n" in generated.content


def test_compile_graphql_sdl_to_hurl_selected_output_validates_with_hurlfmt_when_available() -> (
    None
):
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_graphql_sdl_to_hurl(
        "type Query { health: String }",
        target_url="https://api.example.test/graphql",
        query_field="health",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)


@pytest.mark.parametrize(
    "schema_sdl",
    [
        "type Query { viewer: String } extend type Query { viewer: String }",
        "type Query { viewer(id: ID!): String }",
        "type Query { viewer: String @deprecated }",
        "type Mutation { viewer: String }",
        "type Subscription { viewer: String } type Query { health: String }",
        "extend type Query { viewer: String }",
        "type Query { viewer: String } type Query { health: String }",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_non_unique_query_field(
    schema_sdl: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError, match="query_field|canonical Query"):
        compile_graphql_sdl_to_hurl(
            schema_sdl,
            target_url="https://api.example.test/graphql",
            query_field="viewer",
        )


@pytest.mark.parametrize(
    "query_field",
    ["", "viewer name", "viewer\x00", "sk-proj-secret123", "a" * 129],
)
def test_compile_graphql_sdl_to_hurl_rejects_unsafe_query_field(
    query_field: str,
) -> None:
    with pytest.raises(GraphqlHurlCompilationError, match="query_field must be a GraphQL name"):
        compile_graphql_sdl_to_hurl(
            "type Query { viewer: String }",
            target_url="https://api.example.test/graphql",
            query_field=query_field,
        )


def test_compile_graphql_sdl_to_hurl_explicit_none_preserves_baseline_bytes() -> None:
    schema_sdl = GRAPHQL_SCHEMA.read_text(encoding="utf-8")

    omitted = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
    )
    explicit_none = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field=None,
    )

    assert explicit_none == omitted


def test_compile_graphql_sdl_to_hurl_omitted_nested_default_keeps_legacy_categories() -> None:
    schema_sdl = (
        "input Input { ghost: Mode } enum Mode { VALUE } "
        "type Query { health: String other(filter: Input = { ghost: VALUE }): String } "
        "type Mutation { update(filter: Input = { ghost: VALUE }): String }"
    )

    generated = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
    )
    explicit_none = compile_graphql_sdl_to_hurl(
        schema_sdl,
        target_url="https://api.example.test/graphql",
        query_field=None,
    )

    assert explicit_none == generated

    assert generated.content == (
        "# entroping: tags=smoke,graphql\n"
        "# entroping: source=graphql-sdl\n"
        "# entroping: target_origin=https://api.example.test\n"
        "# entroping: operation_categories=query\n"
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
        ('type Query { token: String = "sk-proj-secret123" }', "secret-like"),
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


@pytest.mark.parametrize(
    "target_url",
    [
        "https://api.example.test/graphql?ready=1",
        "http://127.0.0.1:18082/graphql",
        "http://[::1]:18082/graphql",
        "http://localhost/graphql",
    ],
)
def test_compile_graphql_sdl_to_hurl_accepts_safe_target_authorities(
    target_url: str,
) -> None:
    generated = compile_graphql_sdl_to_hurl(
        "type Query { viewer: String }",
        target_url=target_url,
    )

    assert f"POST {target_url}\n" in generated.content


@pytest.mark.parametrize(
    "target_url",
    [
        'https://api.example.test"attacker/graphql',
        "https://api.example.test|attacker/graphql",
        "https://api.example.test<attacker/graphql",
        "https://api.example.test>attacker/graphql",
        "https://api.example.test\\attacker/graphql",
        "https://api.example.test\x1fattacker/graphql",
        "https://api.example.test\x7fattacker/graphql",
        "https://api.example.test\tattacker/graphql",
    ],
)
def test_compile_graphql_sdl_to_hurl_rejects_unsafe_target_authorities(
    target_url: str,
) -> None:
    with pytest.raises(
        GraphqlHurlCompilationError,
        match="^GraphQL target URL contains unsafe authority characters$",
    ) as error:
        compile_graphql_sdl_to_hurl(
            "type Query { viewer: String }",
            target_url=target_url,
        )

    assert "attacker" not in str(error.value)


def test_compile_graphql_sdl_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_graphql_sdl_to_hurl(
        GRAPHQL_SCHEMA.read_text(encoding="utf-8"),
        target_url="https://api.example.test/graphql",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
