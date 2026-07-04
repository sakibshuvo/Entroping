import shutil

import pytest

from entroping.bridge.target_to_hurl import (
    TargetHurlCompilationError,
    compile_target_url_to_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata


def test_compile_target_url_to_hurl_generates_deterministic_get_probe() -> None:
    generated = compile_target_url_to_hurl("https://api.example.test/health?ready=true")

    assert generated.relative_path == "tests/generated/target-api-example-test-health.hurl"
    assert generated.content == (
        "# entroping: tags=target,smoke\n"
        "# entroping: source=target-url\n"
        "# entroping: target_origin=https://api.example.test\n"
        "\n"
        "GET https://api.example.test/health?ready=true\n"
        "HTTP 200\n"
    )
    assert parse_hurl_metadata(generated.content).tags == frozenset({"target", "smoke"})
    assert parse_hurl_exchanges(generated.content)[0].url == (
        "https://api.example.test/health?ready=true"
    )


def test_compile_target_url_to_hurl_accepts_explicit_safe_method() -> None:
    generated = compile_target_url_to_hurl(
        "https://api.example.test/ready",
        method="HEAD",
    )

    assert "HEAD https://api.example.test/ready\nHTTP 200\n" in generated.content


def test_compile_target_url_to_hurl_keeps_explicit_port() -> None:
    generated = compile_target_url_to_hurl("https://api.example.test:8443/health")

    assert generated.content == (
        "# entroping: tags=target,smoke\n"
        "# entroping: source=target-url\n"
        "# entroping: target_origin=https://api.example.test:8443\n"
        "\n"
        "GET https://api.example.test:8443/health\n"
        "HTTP 200\n"
    )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("", "target URL is required"),
        ("ftp://api.example.test/health", "target URL scheme must be http or https"),
        ("https://user:pass@api.example.test/health", "must not contain credentials"),
        ("https://api.example.test/health#fragment", "must not contain a fragment"),
        ("https://api.example.test/health\x00", "contains control characters"),
        ("https://api.example.test/has space", "must not contain whitespace"),
        ("https://api.example.test/{{secret}}", "contains Hurl template delimiters"),
        ("https://api.example.test:abc/health", "contains an invalid port"),
        ("https:///health", "must include a host"),
        ("https://api.example.test/health?api_key=placeholder", "sensitive query key"),
        ("https://api.example.test/health?ready=sk-proj-secret123", "secret-like"),
        ("https://api.example.test/sk-proj-secret123", "secret-like"),
    ],
)
def test_compile_target_url_to_hurl_rejects_unsafe_targets(
    target_url: str,
    message: str,
) -> None:
    with pytest.raises(TargetHurlCompilationError, match=message):
        compile_target_url_to_hurl(target_url)


@pytest.mark.parametrize("method", ["POST", "DELETE", "GET /admin", "GE\x00T"])
def test_compile_target_url_to_hurl_rejects_unsafe_methods(method: str) -> None:
    with pytest.raises(TargetHurlCompilationError):
        compile_target_url_to_hurl("https://api.example.test/health", method=method)


def test_compile_target_url_to_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_target_url_to_hurl("https://api.example.test/health")

    validate_hurl_content(generated.content, display_path=generated.relative_path)
