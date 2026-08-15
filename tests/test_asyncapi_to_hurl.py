import hashlib
import shutil
from pathlib import Path
from typing import Literal, cast

import pytest
import yaml

from entroping.bridge.asyncapi_to_hurl import (
    AsyncapiHurlCompilationError,
    compile_asyncapi_webhook_to_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
ASYNCAPI_SPEC = REPO_ROOT / "examples" / "asyncapi-events" / "contracts" / "orders.asyncapi.yaml"
HTTP_WEBHOOK_ASYNCAPI = """\
asyncapi: 2.6.0
channels:
  /orders:
    bindings:
      http: {}
    publish:
      bindings:
        http:
          method: POST
"""


def _deep_asyncapi_yaml(collection_count: int) -> str:
    lines = ["asyncapi: 2.6.0", "channels:"]
    indent = ""
    for index in range(collection_count):
        indent += "  "
        lines.append(f"{indent}level_{index}:")
    lines.append(f"{indent}  publish: {{}}")
    return "\n".join(lines) + "\n"


def _large_asyncapi_yaml(channel_count: int) -> str:
    channels = "\n".join(f"  channel_{index}: {{}}" for index in range(channel_count))
    return f"asyncapi: 2.6.0\nchannels:\n{channels}\n"


def _aliased_asyncapi_yaml(alias_count: int) -> str:
    aliases = "\n".join(f"  alias_{index}: *operation" for index in range(alias_count))
    return f"asyncapi: 2.6.0\nchannels:\n  operation: &operation\n    publish: {{}}\n{aliases}\n"


def _nested_mapping_asyncapi_yaml(entry_count: int) -> str:
    entries = "\n".join(f"  entry_{index}: {{value: item}}" for index in range(entry_count))
    return f"asyncapi: 2.6.0\nchannels:\n  operation:\n    publish: {{}}\n{entries}\n"


def _syntactic_limit_asyncapi_yaml(entry_count: int) -> str:
    entries = "\n".join(f"  entry_{index}: {{}}" for index in range(entry_count))
    return f"asyncapi: 2.6.0\nchannels:\n  operation:\n    publish: {{}}\n{entries}\n"


def test_compile_asyncapi_webhook_to_hurl_preserves_baseline_bytes() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="https://webhooks.example.test/order-events",
    )

    assert generated.relative_path == (
        "tests/generated/asyncapi-webhooks-example-test-order-events-smoke.hurl"
    )
    assert hashlib.sha256(generated.content.encode("utf-8")).hexdigest() == (
        "012b96d1950f8cb06d65babdaee91f096e73c03b63bdf4fd259bcdbe89f25db3"
    )


def test_compile_asyncapi_webhook_to_hurl_compiles_selected_http_publish_operation() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        HTTP_WEBHOOK_ASYNCAPI,
        target_url="https://webhooks.example.test/base?ignored=true",
        channel="/orders",
        operation="publish",
    )

    assert generated.relative_path == (
        "tests/generated/asyncapi-webhooks-example-test-orders-smoke.hurl"
    )
    assert generated.content == (
        "# entroping: tags=smoke,asyncapi,webhook\n"
        "# entroping: source=asyncapi\n"
        "# entroping: target_origin=https://webhooks.example.test\n"
        "# entroping: channel=/orders\n"
        "# entroping: operation=publish\n"
        "# entroping: scaffold=http-webhook-operation\n"
        "\n"
        "POST https://webhooks.example.test/orders\n"
        "Content-Type: application/json\n"
        "{\n"
        '  "entroping": "asyncapi-webhook-smoke"\n'
        "}\n"
        "HTTP 202\n"
    )


def test_compile_asyncapi_webhook_to_hurl_compiles_selected_http_subscribe_operation() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        HTTP_WEBHOOK_ASYNCAPI.replace("publish", "subscribe").replace("POST", "GET"),
        target_url="https://webhooks.example.test/base?ignored=true#fragment",
        channel="/orders",
        operation="subscribe",
    )

    assert "GET https://webhooks.example.test/orders\n" in generated.content
    assert "Content-Type:" not in generated.content
    assert '"entroping":' not in generated.content
    assert "/base" not in generated.content
    assert "ignored=true" not in generated.content
    assert "fragment" not in generated.content


def test_compile_asyncapi_webhook_to_hurl_never_materializes_selected_payload_metadata() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        HTTP_WEBHOOK_ASYNCAPI
        + "      message:\n"
        + "        name: OrderPayload\n"
        + "        payload:\n"
        + "          type: object\n"
        + "          example: payload-marker\n",
        target_url="https://webhooks.example.test",
        channel="/orders",
        operation="publish",
    )

    assert '"entroping": "asyncapi-webhook-smoke"' in generated.content
    assert "OrderPayload" not in generated.content
    assert "payload-marker" not in generated.content


@pytest.mark.parametrize(
    ("channel", "operation"),
    [
        (None, "publish"),
        ("/orders", None),
        ("", "publish"),
        ("orders", "publish"),
        ("/orders//items", "publish"),
        ("/orders/../items", "publish"),
        ("/orders%2Fitems", "publish"),
        ("/orders?query=yes", "publish"),
        ("/orders#fragment", "publish"),
        ("/orders/{id}", "publish"),
        ("/sk-proj-secret123", "publish"),
        ("/\ud800", "publish"),
        ("/orders", "receive"),
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_invalid_selector_pairs(
    channel: str | None,
    operation: str | None,
) -> None:
    with pytest.raises(AsyncapiHurlCompilationError) as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            HTTP_WEBHOOK_ASYNCAPI,
            target_url="https://webhooks.example.test",
            channel=channel,
            operation=cast(Literal["publish", "subscribe"] | None, operation),
        )

    assert str(exc_info.value) in {
        "AsyncAPI webhook selection is invalid",
        "AsyncAPI webhook channel is invalid",
    }
    assert "sk-proj-secret123" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("asyncapi_yaml", "expected_error"),
    [
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("asyncapi: 2.6.0", "asyncapi: 3.0.0"),
            "AsyncAPI webhook selection requires an AsyncAPI 2.x document",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("asyncapi: 2.6.0", "asyncapi: 3.0.0\nasyncapi: 2.6.0"),
            "AsyncAPI webhook selection requires an AsyncAPI 2.x document",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("http: {}", "ws: {}"),
            "AsyncAPI webhook channel binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("http: {}", "http:\n        type: request"),
            "AsyncAPI webhook channel binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("method: POST", "method: CONNECT"),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "method: POST", "method: POST\n          bindingVersion: 0.2.0"
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("method: POST", "method: POST\n          query: {}"),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace("method: POST", "message: {}"),
            "AsyncAPI webhook operation binding is invalid",
        ),
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_unsupported_selected_bindings(
    asyncapi_yaml: str,
    expected_error: str,
) -> None:
    with pytest.raises(AsyncapiHurlCompilationError, match=f"^{expected_error}$") as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test",
            channel="/orders",
            operation="publish",
        )

    assert "request" not in str(exc_info.value)
    assert "CONNECT" not in str(exc_info.value)


@pytest.mark.parametrize(
    "asyncapi_yaml",
    [
        HTTP_WEBHOOK_ASYNCAPI.replace(
            "  /orders:\n",
            "  /orders:\n"
            "    bindings:\n"
            "      http: {}\n"
            "    publish:\n"
            "      bindings:\n"
            "        http:\n"
            "          method: POST\n"
            "  /orders:\n",
        ),
        HTTP_WEBHOOK_ASYNCAPI.replace(
            "          method: POST\n",
            "          method: POST\n"
            "    publish:\n"
            "      bindings:\n"
            "        http:\n"
            "          method: POST\n",
        ),
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_duplicate_selected_channel_or_operation(
    asyncapi_yaml: str,
) -> None:
    with pytest.raises(
        AsyncapiHurlCompilationError,
        match="^AsyncAPI selected channel operation is invalid$",
    ):
        _ = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test",
            channel="/orders",
            operation="publish",
        )


@pytest.mark.parametrize("resource_error", [MemoryError, RecursionError, yaml.YAMLError])
def test_selected_compiler_normalizes_yaml_compose_errors_without_artifact(
    resource_error: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_compose(*_args: object, **_kwargs: object) -> object:
        raise resource_error("compose-input-marker")

    monkeypatch.setattr(yaml, "compose", raise_compose)
    expected = (
        "Invalid AsyncAPI YAML"
        if resource_error is yaml.YAMLError
        else "AsyncAPI YAML exceeds resource limits"
    )

    with pytest.raises(AsyncapiHurlCompilationError, match=f"^{expected}$") as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            HTTP_WEBHOOK_ASYNCAPI,
            target_url="https://webhooks.example.test",
            channel="/orders",
            operation="publish",
        )

    assert "compose-input-marker" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("asyncapi_yaml", "expected_error"),
    [
        (
            "asyncapi: 2.6.0\n"
            "channels:\n"
            "  /other: {publish: {}}\n"
            "channels:\n"
            "  /orders: {publish: {}}\n",
            "AsyncAPI selected channel operation is invalid",
        ),
        (
            "asyncapi: 2.6.0\nchannels:\n  /orders: []\n",
            "AsyncAPI selected channel operation is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "        http:\n          method: POST",
                "        http: []",
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "      bindings:\n        http:\n          method: POST",
                "      bindings: []",
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "          method: POST",
                "          method: {}",
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "          method: POST\n",
                "          method: POST\n          method: GET\n",
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "          method: POST\n",
                "          method: POST\n"
                "          bindingVersion: 0.3.0\n"
                "          bindingVersion: 0.3.0\n",
            ),
            "AsyncAPI webhook operation binding is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "    bindings:\n      http: {}\n",
                "    bindings:\n      http: {}\n    bindings:\n      http: {}\n",
            ),
            "AsyncAPI selected channel operation is invalid",
        ),
        (
            HTTP_WEBHOOK_ASYNCAPI.replace(
                "      http: {}\n",
                "      http: {}\n      http: {}\n",
            ),
            "AsyncAPI selected channel operation is invalid",
        ),
    ],
)
def test_selected_compiler_rejects_public_yaml_binding_shapes_without_artifact(
    asyncapi_yaml: str,
    expected_error: str,
) -> None:
    with pytest.raises(AsyncapiHurlCompilationError, match=f"^{expected_error}$"):
        _ = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test",
            channel="/orders",
            operation="publish",
        )


def test_compile_asyncapi_webhook_to_hurl_rejects_missing_selected_operation() -> None:
    with pytest.raises(
        AsyncapiHurlCompilationError,
        match="^AsyncAPI selected channel operation is invalid$",
    ):
        _ = compile_asyncapi_webhook_to_hurl(
            HTTP_WEBHOOK_ASYNCAPI,
            target_url="https://webhooks.example.test",
            channel="/orders",
            operation="subscribe",
        )


def test_compile_asyncapi_webhook_to_hurl_accepts_exact_http_binding_version() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        HTTP_WEBHOOK_ASYNCAPI.replace(
            "method: POST", "method: PUT\n          bindingVersion: 0.3.0"
        ),
        target_url="https://webhooks.example.test",
        channel="/orders",
        operation="publish",
    )

    assert "PUT https://webhooks.example.test/orders\n" in generated.content


@pytest.mark.parametrize(
    "target_url",
    [
        "",
        "https://webhooks.example.test/base?token=selection-marker",
        "https://webhooks.example.test/sk-proj-secret123",
        "https://webhooks.example.test/{{selection-marker}}",
        "ftp://webhooks.example.test/orders",
        "https://user:pass@webhooks.example.test/orders",
        "https://webhooks.example.test:abc/orders",
        "https:///orders",
        "https://webhooks.example.test/orders?token=",
        "https://webhooks.example.test/orders?token=selection-marker",
        'https://evil.com"x',
        "https://example.com|evil",
        "https://example.com<evil",
        "https://example.com>evil",
        r"https://example.com\evil",
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_unsafe_selected_target_without_echoing_input(
    target_url: str,
) -> None:
    with pytest.raises(
        AsyncapiHurlCompilationError,
        match="^AsyncAPI webhook target URL is invalid$",
    ) as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            HTTP_WEBHOOK_ASYNCAPI,
            target_url=target_url,
            channel="/orders",
            operation="publish",
        )

    assert "selection-marker" not in str(exc_info.value)
    assert "sk-proj-secret123" not in str(exc_info.value)
    assert "evil" not in str(exc_info.value)


def test_compile_asyncapi_webhook_accepts_scalar_yaml_anchor() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        (
            "asyncapi: 2.6.0\n"
            "info:\n"
            "  title: &document_title Orders\n"
            "  description: *document_title\n"
            "channels:\n"
            "  order.created:\n"
            "    publish: {}\n"
        ),
        target_url="https://webhooks.example.test/order-events",
    )

    assert "# entroping: operation_count=1\n" in generated.content


def test_compile_asyncapi_webhook_to_hurl_generates_deterministic_smoke_scaffold() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="https://webhooks.example.test/order-events",
    )

    assert generated.relative_path == (
        "tests/generated/asyncapi-webhooks-example-test-order-events-smoke.hurl"
    )
    assert generated.content == (
        "# entroping: tags=smoke,asyncapi,webhook\n"
        "# entroping: source=asyncapi\n"
        "# entroping: target_origin=https://webhooks.example.test\n"
        "# entroping: operation_count=2\n"
        "# entroping: scaffold=webhook-ack-smoke\n"
        "\n"
        "POST https://webhooks.example.test/order-events\n"
        "Content-Type: application/json\n"
        "{\n"
        '  "entroping": "asyncapi-webhook-smoke"\n'
        "}\n"
        "HTTP 202\n"
    )
    assert "order.created.v1" not in generated.content
    assert "OrderCreated" not in generated.content
    assert "customer_email" not in generated.content
    assert "example-marker" not in generated.content
    assert parse_hurl_metadata(generated.content).tags == frozenset(
        {"smoke", "asyncapi", "webhook"}
    )
    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "POST"
    assert exchange.url == "https://webhooks.example.test/order-events"


def test_compile_asyncapi_webhook_to_hurl_accepts_local_fixture_target() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="http://127.0.0.1:18084/webhooks/orders",
    )

    assert "POST http://127.0.0.1:18084/webhooks/orders\n" in generated.content
    assert "# entroping: target_origin=http://127.0.0.1:18084\n" in generated.content


def test_compile_asyncapi_webhook_to_hurl_preserves_non_sensitive_target_query() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="https://webhooks.example.test/order-events?ready=1",
    )

    assert "POST https://webhooks.example.test/order-events?ready=1\n" in generated.content


def test_compile_asyncapi_webhook_to_hurl_ignores_sparse_channel_entries() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        (
            "asyncapi: 2.6.0\n"
            "channels:\n"
            "  order.created: disabled\n"
            "  order.cancelled:\n"
            "    publish: {}\n"
        ),
        target_url="https://webhooks.example.test/order-events",
    )

    assert "# entroping: operation_count=1\n" in generated.content


@pytest.mark.parametrize(
    ("case_name", "asyncapi_yaml"),
    [
        (
            "recursive-alias",
            "\n".join(
                (
                    "asyncapi: 2.6.0",
                    "channels: &recursive_marker",
                    "  recursive_marker: *recursive_marker",
                    "",
                )
            ),
        ),
        ("depth", _deep_asyncapi_yaml(130)),
        ("nodes", _large_asyncapi_yaml(5_001)),
        ("alias-expansion", _aliased_asyncapi_yaml(3_000)),
    ],
)
def test_compile_asyncapi_webhook_rejects_yaml_resource_boundaries_before_construction(
    case_name: str,
    asyncapi_yaml: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_constructed(_content: str) -> object:
        raise AssertionError(f"safe_load constructed {case_name} input")

    monkeypatch.setattr(yaml, "safe_load", fail_if_constructed)

    with pytest.raises(
        AsyncapiHurlCompilationError,
        match="^AsyncAPI YAML exceeds resource limits$",
    ) as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test/order-events",
        )

    assert case_name not in str(exc_info.value)
    assert "recursive_marker" not in str(exc_info.value)


@pytest.mark.parametrize("resource_error", [MemoryError, RecursionError])
def test_compile_asyncapi_webhook_normalizes_yaml_resource_errors_without_content(
    resource_error: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_resource_error(_content: str) -> object:
        raise resource_error("resource-input-marker")

    monkeypatch.setattr(yaml, "safe_load", raise_resource_error)

    with pytest.raises(
        AsyncapiHurlCompilationError,
        match="^AsyncAPI YAML exceeds resource limits$",
    ) as exc_info:
        _ = compile_asyncapi_webhook_to_hurl(
            "asyncapi: 2.6.0\nchannels:\n  order.created:\n    publish: {}\n",
            target_url="https://webhooks.example.test/order-events",
        )

    assert "resource-input-marker" not in str(exc_info.value)


def test_compile_asyncapi_webhook_accepts_nested_mapping_below_syntactic_limit() -> None:
    generated = compile_asyncapi_webhook_to_hurl(
        _nested_mapping_asyncapi_yaml(2_000),
        target_url="https://webhooks.example.test",
    )

    assert "operation_count=1" in generated.content


@pytest.mark.parametrize(
    ("asyncapi_yaml", "should_compile"),
    [
        (_syntactic_limit_asyncapi_yaml(4_995), True),
        (_syntactic_limit_asyncapi_yaml(4_996), False),
        (_aliased_asyncapi_yaml(2_497), True),
        (_aliased_asyncapi_yaml(2_498), False),
    ],
)
def test_compile_asyncapi_webhook_enforces_adjacent_yaml_resource_limits(
    asyncapi_yaml: str,
    should_compile: bool,
) -> None:
    if should_compile:
        generated = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test",
        )
        assert "operation_count=" in generated.content
    else:
        with pytest.raises(
            AsyncapiHurlCompilationError,
            match="^AsyncAPI YAML exceeds resource limits$",
        ) as exc_info:
            _ = compile_asyncapi_webhook_to_hurl(
                asyncapi_yaml,
                target_url="https://webhooks.example.test",
            )
        assert "resource-input-marker" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("asyncapi_yaml", "message"),
    [
        ("", "AsyncAPI document is required"),
        ("asyncapi: 2.6.0\nchannels:\n  order.created: {}\x00", "control characters"),
        ("asyncapi: 2.6.0\ninfo:\n  token: sk-proj-secret123\n", "secret-like"),
        ("{not yaml: [}\n", "Invalid AsyncAPI YAML"),
        ("[]\n", "AsyncAPI document must be a mapping"),
        ("info:\n  title: Missing version\nchannels: {}\n", "must declare an asyncapi version"),
        ("asyncapi: 2.6.0\n", "must define a channels mapping"),
        ("asyncapi: 2.6.0\nchannels: []\n", "must define a channels mapping"),
        (
            "asyncapi: 2.6.0\nchannels:\n  order.created:\n    description: missing operation\n",
            "at least one publish or subscribe operation",
        ),
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_unsupported_or_unsafe_documents(
    asyncapi_yaml: str,
    message: str,
) -> None:
    with pytest.raises(AsyncapiHurlCompilationError, match=message):
        _ = compile_asyncapi_webhook_to_hurl(
            asyncapi_yaml,
            target_url="https://webhooks.example.test/order-events",
        )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("", "AsyncAPI webhook target URL is required"),
        ("ftp://webhooks.example.test/order-events", "scheme must be http or https"),
        ("https://user:pass@webhooks.example.test/order-events", "must not contain credentials"),
        ("https://webhooks.example.test/order-events#fragment", "must not contain a fragment"),
        ("https://webhooks.example.test/order-events\x00", "contains control characters"),
        ("https://webhooks.example.test/has space", "must not contain whitespace"),
        ("https://webhooks.example.test/{{secret}}", "contains Hurl template delimiters"),
        ("https://webhooks.example.test:abc/order-events", "contains an invalid port"),
        ("https:///order-events", "must include a host"),
        ("https://webhooks.example.test/order-events?token=placeholder", "sensitive query key"),
        ("https://webhooks.example.test/order-events?ready=sk-proj-secret123", "secret-like"),
        ("https://webhooks.example.test/sk-proj-secret123", "secret-like"),
    ],
)
def test_compile_asyncapi_webhook_to_hurl_rejects_unsafe_targets(
    target_url: str,
    message: str,
) -> None:
    with pytest.raises(AsyncapiHurlCompilationError, match=message):
        _ = compile_asyncapi_webhook_to_hurl(
            "asyncapi: 2.6.0\nchannels:\n  order.created:\n    publish: {}\n",
            target_url=target_url,
        )


def test_compile_asyncapi_webhook_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    omitted_generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="https://webhooks.example.test/order-events",
    )
    selected_generated = compile_asyncapi_webhook_to_hurl(
        HTTP_WEBHOOK_ASYNCAPI,
        target_url="https://webhooks.example.test",
        channel="/orders",
        operation="publish",
    )

    validate_hurl_content(
        omitted_generated.content,
        display_path=omitted_generated.relative_path,
    )
    validate_hurl_content(
        selected_generated.content,
        display_path=selected_generated.relative_path,
    )
