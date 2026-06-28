from pathlib import Path

import pytest

from entroping.core.bounded_read import BoundedReadError, read_text_bounded


def test_read_text_bounded_rejects_non_positive_byte_limit(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("ok", encoding="utf-8")

    with pytest.raises(BoundedReadError, match="byte limit must be positive"):
        read_text_bounded(artifact, max_bytes=0, label="artifact")


def test_read_text_bounded_wraps_os_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(BoundedReadError, match="Could not read artifact"):
        read_text_bounded(missing, max_bytes=8, label="artifact")


def test_read_text_bounded_wraps_utf8_decode_errors(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_bytes(b"\xff")

    with pytest.raises(BoundedReadError, match="Could not decode artifact"):
        read_text_bounded(artifact, max_bytes=8, label="artifact")
