import shutil
from pathlib import Path

import pytest

from entroping.bridge.proto_to_hurl import (
    ProtoHurlCompilationError,
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
            +
            '''
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
'''
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
        ("syntax = \"proto3\";\x00", "control characters"),
        ("service Secrets { string token = 1 [default = \"sk-proj-secret123\"]; }", "secret-like"),
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
