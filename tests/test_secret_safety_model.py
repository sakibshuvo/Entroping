"""Shared credential safety primitive tests."""

from entroping.models.secrets import (
    REDACTED,
    contains_secret_like_value,
    is_sensitive_key,
    redact_secret_like_values,
)


def test_shared_secret_helpers_redact_common_literal_credentials() -> None:
    openai_token = "sk-proj-" + ("a" * 24)
    github_token = "github_pat_" + ("b" * 32)
    text = "\n".join(
        [
            "Authorization: Bearer live-token",
            "Cookie: session_id=live-session",
            f"note={openai_token}",
            f'{{"metadata":"{github_token}"}}',
        ]
    )

    redacted = redact_secret_like_values(text)

    assert contains_secret_like_value(text) is True
    assert "live-token" not in redacted
    assert "live-session" not in redacted
    assert openai_token not in redacted
    assert github_token not in redacted
    assert REDACTED in redacted


def test_shared_secret_helpers_preserve_harmless_token_shape_placeholders() -> None:
    text = "\n".join(
        [
            "Docs mention ghp_example as a placeholder.",
            "Use github_pat_example in tutorials, not production.",
            "The Hugging Face prefix hf_model is not a token.",
            "Bearer docs is ordinary prose.",
        ]
    )

    assert contains_secret_like_value(text) is False
    assert redact_secret_like_values(text) == text


def test_shared_secret_helpers_preserve_non_luhn_digit_groups() -> None:
    text = "reference=1111 1111 1111 1111"

    assert contains_secret_like_value(text) is False
    assert redact_secret_like_values(text) == text


def test_shared_secret_helpers_preserve_templates_and_redacted_values() -> None:
    text = "Authorization: Bearer {{api_token}}\ntoken=[REDACTED]"

    assert contains_secret_like_value(text) is False
    assert redact_secret_like_values(text) == text


def test_shared_secret_helpers_redact_csrf_token_key_values() -> None:
    text = "csrf_token=live-csrf-secret\nx-csrf-token=header-csrf-secret"

    redacted = redact_secret_like_values(text)

    assert contains_secret_like_value(text) is True
    assert "live-csrf-secret" not in redacted
    assert "header-csrf-secret" not in redacted
    assert "csrf_token=[REDACTED]" in redacted
    assert "x-csrf-token=[REDACTED]" in redacted


def test_shared_sensitive_key_matching_covers_http_and_payload_names() -> None:
    assert is_sensitive_key("X-API-Key") is True
    assert is_sensitive_key("refresh-token") is True
    assert is_sensitive_key("customer_id") is False
