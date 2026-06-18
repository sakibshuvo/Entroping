"""Safety helper tests for Brain prompt and provider boundaries."""

from entroping.brain.safety import (
    contains_secret_like_value,
    has_disallowed_control,
    redact_secret_like_values,
)


def test_contains_secret_like_value_ignores_empty_header_values() -> None:
    assert contains_secret_like_value("Authorization:    ") is False


def test_contains_secret_like_value_ignores_already_redacted_values() -> None:
    assert contains_secret_like_value("token=[REDACTED]") is False


def test_contains_secret_like_value_detects_literal_auth_headers() -> None:
    assert contains_secret_like_value("Authorization: Bearer live-token") is True


def test_contains_secret_like_value_detects_literal_cookie_values() -> None:
    assert contains_secret_like_value("Cookie: session=live-session") is True


def test_contains_secret_like_value_ignores_templated_cookie_values() -> None:
    assert contains_secret_like_value("Cookie: session={{session_id}}; api=[REDACTED]") is False


def test_redact_secret_like_values_preserves_templated_header_values() -> None:
    assert redact_secret_like_values("Authorization: {{token}}") == "Authorization: {{token}}"


def test_redact_secret_like_values_preserves_templated_key_values() -> None:
    assert redact_secret_like_values("token={{api_token}}") == "token={{api_token}}"


def test_safety_helpers_detect_and_redact_real_secret_shapes() -> None:
    text = "Authorization: Bearer live-token\napi_key=live-key\nsk-proj-secret"

    assert contains_secret_like_value(text) is True
    redacted = redact_secret_like_values(text)

    assert "live-token" not in redacted
    assert "live-key" not in redacted
    assert "sk-proj-secret" not in redacted
    assert "Authorization: [REDACTED]" in redacted
    assert "api_key=[REDACTED]" in redacted


def test_safety_helpers_detect_and_redact_sensitive_data_shapes() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    text = "\n".join(
        [
            f"opaque={jwt}",
            "blob=QWxhZGRpbjpPcGVuU2VzYW1lMTIzNDU2Nzg5MA==",
            "card=4111 1111 1111 1111",
            "ssn=123-45-6789",
            "email=alice@example.test",
        ],
    )

    assert contains_secret_like_value(text) is True
    redacted = redact_secret_like_values(text)

    assert "eyJhbGci" not in redacted
    assert "QWxhZGRp" not in redacted
    assert "4111" not in redacted
    assert "123-45" not in redacted
    assert "alice@example" not in redacted
    assert redacted.count("[REDACTED]") == 5


def test_has_disallowed_control_allows_markdown_whitespace_only() -> None:
    assert has_disallowed_control("line one\nline two\tok\r") is False
    assert has_disallowed_control("bad\x00value") is True
