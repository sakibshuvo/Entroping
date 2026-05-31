"""Shared credential safety primitive tests."""

from entroping.models.secrets import (
    REDACTED,
    contains_secret_like_value,
    is_sensitive_key,
    redact_secret_like_values,
)


def test_shared_secret_helpers_redact_common_literal_credentials() -> None:
    text = "\n".join(
        [
            "Authorization: Bearer live-token",
            "Cookie: session_id=live-session",
            "note=sk-proj-live-secret",
            '{"metadata":"github_pat_live_secret"}',
        ]
    )

    redacted = redact_secret_like_values(text)

    assert contains_secret_like_value(text) is True
    assert "live-token" not in redacted
    assert "live-session" not in redacted
    assert "sk-proj-live-secret" not in redacted
    assert "github_pat_live_secret" not in redacted
    assert REDACTED in redacted


def test_shared_secret_helpers_preserve_templates_and_redacted_values() -> None:
    text = "Authorization: Bearer {{api_token}}\ntoken=[REDACTED]"

    assert contains_secret_like_value(text) is False
    assert redact_secret_like_values(text) == text


def test_shared_sensitive_key_matching_covers_http_and_payload_names() -> None:
    assert is_sensitive_key("X-API-Key") is True
    assert is_sensitive_key("refresh-token") is True
    assert is_sensitive_key("customer_id") is False
