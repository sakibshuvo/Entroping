from pathlib import Path

import pytest

import entroping.hurl_source as hurl_source


def test_read_hurl_source_text_rejects_invalid_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "test.hurl"
    source.write_text("GET http://api.example.test/health\nHTTP 200\n", encoding="utf-8")
    monkeypatch.setattr(hurl_source, "HURL_SOURCE_MAX_BYTES", 0)

    with pytest.raises(
        hurl_source.HurlSourceTooLargeError,
        match="Hurl source byte limit must be positive",
    ):
        hurl_source.read_hurl_source_text(source)
