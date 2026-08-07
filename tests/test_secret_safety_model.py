"""Shared credential safety primitive tests."""

import pytest

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


def test_contains_secret_like_value_normalizes_markdown_redacted_marker() -> None:
    assert contains_secret_like_value("token=[REDACTED]`") is False
    assert contains_secret_like_value("token=[REDACTED]") is False


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


@pytest.mark.parametrize(
    "key",
    [
        "OTP",
        "otp-code",
        "pin_code",
        "passCode",
        "verification.code",
        "Verification-Code",
        "recoveryCode",
    ],
)
def test_shared_sensitive_key_matching_covers_short_credential_variants(
    key: str,
) -> None:
    assert is_sensitive_key(key) is True


@pytest.mark.parametrize("key", ["quantity", "count", "status", "status_code", "pinpoint"])
def test_shared_sensitive_key_matching_rejects_benign_similar_names(key: str) -> None:
    assert is_sensitive_key(key) is False


def test_shared_secret_helpers_redact_short_credentials_and_preserve_placeholders() -> None:
    text = "\n".join(
        [
            "OTP=otp-probe-value",
            "pin-code: pin-probe-value",
            "Verification_Code=verification-probe-value",
            "recoveryCode=recovery-probe-value",
            "quantity=731944",
            "status_code=200",
            "otp={{otp}}",
            "pin-code=[REDACTED]",
        ]
    )

    redacted = redact_secret_like_values(text)

    assert contains_secret_like_value(text) is True
    for raw_value in (
        "otp-probe-value",
        "pin-probe-value",
        "verification-probe-value",
        "recovery-probe-value",
    ):
        assert raw_value not in redacted
    assert "quantity=731944" in redacted
    assert "status_code=200" in redacted
    assert "otp={{otp}}" in redacted
    assert "pin-code=[REDACTED]" in redacted
    assert redacted.count(REDACTED) == 5


@pytest.mark.parametrize(
    ("text", "expected", "contains_secret"),
    [
        ('{"OTP":"{{otp}}"}', '{"OTP":"{{otp}}"}', False),
        ('{"verificationCode":"[REDACTED]"}', '{"verificationCode":"[REDACTED]"}', False),
        ('{"OTP":"otp-json-literal"}', '{"OTP":"[REDACTED]"}', True),
        ('{"pin":123456}', '{"pin":"[REDACTED]"}', True),
    ],
)
def test_json_short_credentials_preserve_placeholders_and_redact_literals(
    text: str,
    expected: str,
    contains_secret: bool,
) -> None:
    assert redact_secret_like_values(text) == expected
    assert contains_secret_like_value(text) is contains_secret
