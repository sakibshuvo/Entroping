import shutil
from pathlib import Path

import pytest

from entroping.bridge.asyncapi_to_hurl import (
    AsyncapiHurlCompilationError,
    compile_asyncapi_webhook_to_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
ASYNCAPI_SPEC = REPO_ROOT / "examples" / "asyncapi-events" / "contracts" / "orders.asyncapi.yaml"


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
        compile_asyncapi_webhook_to_hurl(
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
        compile_asyncapi_webhook_to_hurl(
            "asyncapi: 2.6.0\nchannels:\n  order.created:\n    publish: {}\n",
            target_url=target_url,
        )


def test_compile_asyncapi_webhook_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_asyncapi_webhook_to_hurl(
        ASYNCAPI_SPEC.read_text(encoding="utf-8"),
        target_url="https://webhooks.example.test/order-events",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
