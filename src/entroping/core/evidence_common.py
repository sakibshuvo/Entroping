"""Shared safety helpers for local evidence artifacts."""

from typing import Final

from entroping.models.secrets import contains_secret_like_value, redact_secret_like_values

LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES: Final = 100 * 1024 * 1024
_ASCII_CONTROL_CHAR_TRANSLATION: Final = {code: " " for code in range(32)}


def safe_evidence_text(value: str) -> str:
    """Redact and normalize report text that is rendered as compact evidence."""

    sanitized = redact_secret_like_values(value).translate(_ASCII_CONTROL_CHAR_TRANSLATION)
    return " ".join(sanitized.split())


def safe_evidence_metadata_text(value: str) -> str:
    """Redact metadata text while preserving non-line-break spacing."""

    return redact_secret_like_values(value).replace("\r", " ").replace("\n", " ")


def contains_unredacted_evidence_secret(value: str) -> bool:
    """Return whether evidence text still contains a secret-like value.

    Markdown inline-code fences can trail an already-redacted marker.
    """

    normalized = value.replace("[REDACTED]`", "[REDACTED]")
    return contains_secret_like_value(normalized)
