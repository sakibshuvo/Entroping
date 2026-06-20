"""Tests for shared local evidence artifact safety helpers."""

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_metadata_text,
    safe_evidence_text,
)


def test_local_evidence_artifact_cap_is_100_mib() -> None:
    assert LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES == 100 * 1024 * 1024


def test_safe_evidence_text_redacts_and_normalizes_ascii_controls() -> None:
    text = safe_evidence_text("Authorization: Bearer live-token\r\nnext\tvalue\x00tail")

    assert text == "Authorization: [REDACTED] next value tail"


def test_safe_evidence_metadata_text_preserves_spacing_but_strips_line_breaks() -> None:
    text = safe_evidence_metadata_text("token=live-secret\r\nnext")

    assert text == "token=[REDACTED]  next"


def test_contains_unredacted_evidence_secret_ignores_redacted_inline_code_fence() -> None:
    assert contains_unredacted_evidence_secret("token=[REDACTED]`") is False
    assert contains_unredacted_evidence_secret("token=live-secret") is True
