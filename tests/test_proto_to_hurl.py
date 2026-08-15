import shutil
from pathlib import Path
from time import perf_counter

import pytest

from entroping.bridge.proto_to_hurl import (
    ProtoHurlCompilationError,
    _http_option_parts,
    compile_proto_http_transcoding_to_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTO_CONTRACT = REPO_ROOT / "examples" / "grpc-transcoding" / "contracts" / "orders.proto"


def test_compile_proto_http_transcoding_to_hurl_generates_deterministic_smoke_scaffold() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/v1/orders/entroping-smoke",
    )

    assert generated.relative_path == (
        "tests/generated/grpc-api-example-test-v1-orders-entroping-smoke-smoke.hurl"
    )
    assert generated.content == (
        "# entroping: tags=smoke,grpc,transcoding\n"
        "# entroping: source=proto\n"
        "# entroping: target_origin=https://api.example.test\n"
        "# entroping: rpc_count=2\n"
        "# entroping: http_rule_count=2\n"
        "# entroping: scaffold=http-transcoding-smoke\n"
        "# entroping: native_grpc_streaming=future\n"
        "\n"
        "GET https://api.example.test/v1/orders/entroping-smoke\n"
        "Accept: application/json\n"
        "HTTP 200\n"
    )
    assert "OrderService" not in generated.content
    assert "GetOrder" not in generated.content
    assert "CreateOrder" not in generated.content
    assert "/v1/orders/{id}" not in generated.content
    assert parse_hurl_metadata(generated.content).tags == frozenset(
        {"smoke", "grpc", "transcoding"}
    )
    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "GET"
    assert exchange.url == "https://api.example.test/v1/orders/entroping-smoke"


def test_compile_proto_http_transcoding_to_hurl_selects_unique_get_rule() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/ignored-target-path",
        rpc_name="GetOrder",
    )

    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "GET"
    assert exchange.url == "https://api.example.test/v1/orders/entroping"
    assert "# entroping: rpc_count=2\n" in generated.content
    assert "# entroping: http_rule_count=2\n" in generated.content
    assert "GET https://api.example.test/v1/orders/entroping\n" in generated.content
    assert "{id}" not in generated.content


def test_compile_proto_http_transcoding_to_hurl_selects_post_rule_with_body_star() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/ignored-target-path",
        rpc_name="CreateOrder",
    )

    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "POST"
    assert exchange.url == "https://api.example.test/v1/orders"
    assert '{\n  "entroping": "grpc-http-transcoding-smoke"\n}\n' in generated.content


@pytest.mark.parametrize("trailing_token", ["trailing_token", "[one, two]", "{ nested: true }"])
def test_compile_proto_http_transcoding_to_hurl_rejects_unsupported_option_tokens(
    trailing_token: str,
) -> None:
    proto_text = f"""
    service Orders {{
      rpc GetOrder(M) returns (R) {{
        option (google.api.http) = {{
          get: "/v1/orders"
          {trailing_token}
        }};
      }}
    }}
    """

    with pytest.raises(ProtoHurlCompilationError, match="unsupported or malformed"):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test",
            rpc_name="GetOrder",
        )


def test_compile_proto_http_transcoding_to_hurl_scans_large_option_linearly() -> None:
    repeated_fields = " ".join('get: "/v1/orders"' for _ in range(20_000))
    proto_text = f"""
    service Orders {{
      rpc GetOrder(M) returns (R) {{
        option (google.api.http) = {{ {repeated_fields} }};
      }}
    }}
    """

    started = perf_counter()
    with pytest.raises(ProtoHurlCompilationError, match="duplicate bindings"):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test",
            rpc_name="GetOrder",
        )

    assert perf_counter() - started < 1.5


def test_compile_proto_http_transcoding_to_hurl_field_parsing_scales_linearly() -> None:
    def elapsed_for_field_count(field_count: int) -> float:
        repeated_fields = " ".join('get: "/v1/orders"' for _ in range(field_count))
        proto_text = f"""
        service Orders {{
          rpc GetOrder(M) returns (R) {{
            option (google.api.http) = {{ {repeated_fields} }};
          }}
        }}
        """
        started = perf_counter()
        with pytest.raises(ProtoHurlCompilationError, match="duplicate bindings"):
            compile_proto_http_transcoding_to_hurl(
                proto_text,
                target_url="https://api.example.test",
                rpc_name="GetOrder",
            )
        return perf_counter() - started

    small = elapsed_for_field_count(2_000)
    large = elapsed_for_field_count(40_000)

    assert large < small * 22


def test_compile_proto_http_transcoding_to_hurl_rejects_an_unsafe_generated_filename() -> None:
    declared_path = "/" + ("orders-" * 60)
    proto_text = f"""
    service Orders {{
      rpc GetOrder(M) returns (R) {{
        option (google.api.http) = {{ get: "{declared_path}" }};
      }}
    }}
    """

    with pytest.raises(ProtoHurlCompilationError, match="filename") as error:
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test",
            rpc_name="GetOrder",
        )

    assert declared_path not in str(error.value)


@pytest.mark.parametrize(
    ("method", "body", "expected_body"),
    [("put", 'body: "*"', True), ("patch", 'body: "*"', True), ("delete", "", False)],
)
def test_compile_proto_http_transcoding_to_hurl_supports_declared_method_body_policy(
    method: str,
    body: str,
    expected_body: bool,
) -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        f"""
        service Orders {{
          rpc UpdateOrder(M) returns (R) {{
            option (google.api.http) = {{ {method}: "/v1/orders/{{id}}" {body} }};
          }}
        }}
        """,
        target_url="https://api.example.test/ignored-target-path",
        rpc_name="UpdateOrder",
    )

    assert f"{method.upper()} https://api.example.test/v1/orders/entroping\n" in generated.content
    assert ("Content-Type: application/json\n" in generated.content) is expected_body


def test_compile_proto_http_transcoding_to_hurl_preserves_omitted_selector_bytes() -> None:
    proto_text = PROTO_CONTRACT.read_text(encoding="utf-8")

    omitted = compile_proto_http_transcoding_to_hurl(
        proto_text,
        target_url="https://api.example.test/v1/orders/entroping-smoke",
    )
    explicit_none = compile_proto_http_transcoding_to_hurl(
        proto_text,
        target_url="https://api.example.test/v1/orders/entroping-smoke",
        rpc_name=None,
    )

    assert explicit_none == omitted


@pytest.mark.parametrize(
    "rpc_name",
    ["", "Get Order", "GetOrder/extra", "sk-proj-secret123", "sk_proj_secret123", "x" * 129],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unsafe_rpc_selector(
    rpc_name: str,
) -> None:
    with pytest.raises(ProtoHurlCompilationError, match="rpc_name selector") as error:
        compile_proto_http_transcoding_to_hurl(
            PROTO_CONTRACT.read_text(encoding="utf-8"),
            target_url="https://api.example.test/orders",
            rpc_name=rpc_name,
        )

    if rpc_name:
        assert rpc_name not in str(error.value)


@pytest.mark.parametrize(
    ("proto_text", "rpc_name", "message"),
    [
        (
            "service Orders { rpc Missing(M) returns (R); }",
            "Missing",
            "primary google.api.http rule",
        ),
        (
            "service Orders { rpc GetOrder(M) returns (R); rpc GetOrder(M) returns (R); }",
            "GetOrder",
            "exactly one RPC",
        ),
        (
            "service Orders { rpc GetOrder(stream M) returns (R) {} }",
            "GetOrder",
            "unary RPC",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = {
                  get: "/v1/orders"
                  additional_bindings: { get: "/v1/other" }
                };
              }
            }
            """,
            "GetOrder",
            "unsupported or duplicate bindings",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { custom: { kind: "HEAD" path: "/v1/orders" } };
              }
            }
            """,
            "GetOrder",
            "unsupported or duplicate bindings",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { post: "/v1/orders" };
              }
            }
            """,
            "GetOrder",
            "requires body star",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: "/v1/orders" body: "field" };
              }
            }
            """,
            "GetOrder",
            "forbids a body",
        ),
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unsupported_selected_rules(
    proto_text: str,
    rpc_name: str,
    message: str,
) -> None:
    with pytest.raises(ProtoHurlCompilationError, match=message):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test/orders",
            rpc_name=rpc_name,
        )


@pytest.mark.parametrize(
    "option_fields",
    [
        'response_body: "order" get: "/v1/orders"',
        'get: "/v1/orders" response_body: "order"',
        'selector: "orders.v1" get: "/v1/orders"',
        'get: "/v1/orders" unknown: "metadata"',
        'unknown: { nested: "metadata" } get: "/v1/orders"',
        'post: "/v1/orders" body: "*" response_body: "order"',
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unknown_http_rule_fields(
    option_fields: str,
) -> None:
    proto_text = f"""
    service Orders {{
      rpc GetOrder(M) returns (R) {{
        option (google.api.http) = {{ {option_fields} }};
      }}
    }}
    """

    with pytest.raises(ProtoHurlCompilationError, match="unsupported or unknown fields"):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test/orders",
            rpc_name="GetOrder",
        )


@pytest.mark.parametrize(
    "path",
    [
        "v1/orders",
        "/v1/orders?ready=1",
        "/v1/orders#fragment",
        "/v1/orders/%7Bid%7D",
        "/v1/orders/{id=bad}",
        "/v1/../orders",
        "/v1/orders/{sk-proj-secret123}",
        "/v1/{bad/{id}",
        "/v1/{id}/{",
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unsafe_selected_paths(
    path: str,
) -> None:
    proto_text = f"""
    service Orders {{
      rpc GetOrder(M) returns (R) {{
        option (google.api.http) = {{ get: \"{path}\" }};
      }}
    }}
    """

    with pytest.raises(ProtoHurlCompilationError, match="path is unsafe|secret-like"):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test/orders",
            rpc_name="GetOrder",
        )


def test_compile_proto_http_transcoding_to_hurl_emits_json_body_for_mutating_rule() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        """
syntax = "proto3";
service Orders {
  rpc CreateOrder(CreateOrderRequest) returns (Order) {
    option (google.api.http) = {
      post: "/v1/orders"
      body: "*"
    };
  }
}
""",
        target_url="https://api.example.test/v1/orders",
    )

    assert "POST https://api.example.test/v1/orders\n" in generated.content
    assert "Content-Type: application/json\n" in generated.content
    assert '{\n  "entroping": "grpc-http-transcoding-smoke"\n}\n' in generated.content


@pytest.mark.parametrize(
    ("proto_text", "message"),
    [
        (
            "service Orders { rpc GetOrder(M) returns (R) {",
            "primary google.api.http rule",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = ;
              }
            }
            """,
            "malformed",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: "/v1/orders";
              }
            """,
            "primary google.api.http rule",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: "/v1/orders" };
                option (google.api.http) = { get: "/v1/other" };
              }
            }
            """,
            "one primary",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: };
              }
            }
            """,
            "invalid literal",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: path };
              }
            }
            """,
            "invalid literal",
        ),
        (
            """
            service Orders {
              rpc GetOrder(M) returns (R) {
                option (google.api.http) = { get: "unterminated };
              }
            }
            """,
            "invalid literal",
        ),
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_malformed_selected_rules(
    proto_text: str,
    message: str,
) -> None:
    with pytest.raises(ProtoHurlCompilationError, match=message):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test/orders",
            rpc_name="GetOrder",
        )


def test_http_option_parser_rejects_an_unclosed_option_body() -> None:
    with pytest.raises(ProtoHurlCompilationError, match="malformed"):
        _http_option_parts('option (google.api.http) = { get: "/v1/orders"')


def test_compile_proto_http_transcoding_to_hurl_ignores_selected_comments() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        """
        service Orders {
          rpc GetOrder(M) returns (R) {
            // option (google.api.http) = { post: "/wrong" };
            option (google.api.http) = {
              get: "/v1/orders"
            };
          }
        }
        """,
        target_url="https://api.example.test/orders",
        rpc_name="GetOrder",
    )

    assert "GET https://api.example.test/v1/orders\n" in generated.content


def test_compile_proto_http_transcoding_to_hurl_allows_non_sensitive_target_query() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/orders?ready=1",
    )

    assert "GET https://api.example.test/orders?ready=1\n" in generated.content


def test_compile_proto_http_transcoding_to_hurl_defaults_to_post_when_rule_has_no_verb() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        """
syntax = "proto3";
service Orders {
  rpc CreateOrder(CreateOrderRequest) returns (Order) {
    option (google.api.http) = {};
  }
}
""",
        target_url="https://api.example.test/v1/orders",
    )

    assert "POST https://api.example.test/v1/orders\n" in generated.content
    assert "# entroping: http_rule_count=1\n" in generated.content


def test_compile_proto_http_transcoding_to_hurl_keeps_ipv6_target_with_port() -> None:
    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="http://[::1]:18085/v1/orders/entroping-smoke",
    )

    assert "GET http://[::1]:18085/v1/orders/entroping-smoke\n" in generated.content
    assert "# entroping: target_origin=http://[::1]:18085\n" in generated.content


def test_compile_proto_http_transcoding_to_hurl_ignores_commented_and_string_rpcs() -> None:
    slash = "/"
    generated = compile_proto_http_transcoding_to_hurl(
        (
            f"{slash}{slash} rpc Commented(CommentedRequest) returns (CommentedResponse);\n"
            f"{slash}* rpc BlockCommented(BlockRequest) returns (BlockResponse); *{slash}\n"
            + """
syntax = "proto3";
service Orders {
  option deprecated = false;
  rpc GetOrder(GetOrderRequest) returns (Order) {
    option (google.api.http) = {
      get: "/v1/orders/{id}"
    };
  }
}
message Note {
  string example = 1 [json_name = "rpc NotADeclaration"];
}
"""
        ),
        target_url="https://api.example.test/v1/orders/entroping-smoke",
    )

    assert "# entroping: rpc_count=1\n" in generated.content
    assert "# entroping: http_rule_count=1\n" in generated.content
    assert "Commented" not in generated.content
    assert "NotADeclaration" not in generated.content


@pytest.mark.parametrize(
    ("proto_text", "message"),
    [
        ("", "proto document is required"),
        ('syntax = "proto3";\x00', "control characters"),
        ('service Secrets { string token = 1 [default = "sk-proj-secret123"]; }', "secret-like"),
        ("message OnlyData { string id = 1; }", "at least one rpc declaration"),
        (
            "service Orders {\n  rpc GetOrder(GetOrderRequest) returns (Order);\n}",
            "at least one google.api.http rule",
        ),
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unsupported_or_unsafe_documents(
    proto_text: str,
    message: str,
) -> None:
    with pytest.raises(ProtoHurlCompilationError, match=message):
        compile_proto_http_transcoding_to_hurl(
            proto_text,
            target_url="https://api.example.test/v1/orders/entroping-smoke",
        )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("", "gRPC HTTP target URL is required"),
        ("grpc://api.example.test/orders", "scheme must be http or https"),
        ("https://user:pass@api.example.test/v1/orders", "must not contain credentials"),
        ("https://api.example.test/v1/orders#fragment", "must not contain a fragment"),
        ("https://api.example.test/v1/orders\x00", "contains control characters"),
        ("https://api.example.test/has space", "must not contain whitespace"),
        ("https://api.example.test/{{secret}}", "contains Hurl template delimiters"),
        ("https://api.example.test:abc/v1/orders", "contains an invalid port"),
        ("https:///v1/orders", "must include a host"),
        ("https://api.example.test/v1/orders?token=placeholder", "sensitive query key"),
        ("https://api.example.test/v1/orders?ready=sk-proj-secret123", "secret-like"),
        ("https://api.example.test/sk-proj-secret123", "secret-like"),
    ],
)
def test_compile_proto_http_transcoding_to_hurl_rejects_unsafe_targets(
    target_url: str,
    message: str,
) -> None:
    with pytest.raises(ProtoHurlCompilationError, match=message):
        compile_proto_http_transcoding_to_hurl(
            """
syntax = "proto3";
service Orders {
  rpc GetOrder(GetOrderRequest) returns (Order) {
    option (google.api.http) = {
      get: "/v1/orders/{id}"
    };
  }
}
""",
            target_url=target_url,
        )


def test_compile_proto_http_transcoding_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/v1/orders/entroping-smoke",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)


def test_compile_proto_http_transcoding_to_hurl_selected_output_is_hurl_valid() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_proto_http_transcoding_to_hurl(
        PROTO_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://api.example.test/ignored-target-path",
        rpc_name="GetOrder",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
