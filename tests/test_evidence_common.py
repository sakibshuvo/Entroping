"""Tests for shared local evidence artifact safety helpers."""

import errno
import os
import stat as stat_module
from pathlib import Path
from types import SimpleNamespace

import pytest

import entroping.core.evidence_common as evidence_common
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_metadata_text,
    safe_evidence_text,
)


def test_local_evidence_artifact_cap_is_100_mib() -> None:
    assert LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES == 100 * 1024 * 1024


def test_append_local_evidence_descriptor_closes_on_append_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed_descriptors: list[int] = []

    class FailingDescriptors(list[int]):
        def append(self, descriptor: int) -> None:
            raise RuntimeError("append failed")

    monkeypatch.setattr(os, "close", closed_descriptors.append)

    with pytest.raises(RuntimeError, match="append failed"):
        evidence_common.append_local_evidence_descriptor(FailingDescriptors(), 123)

    assert closed_descriptors == [123]


def test_safe_evidence_text_redacts_and_normalizes_ascii_controls() -> None:
    text = safe_evidence_text("Authorization: Bearer live-token\r\nnext\tvalue\x00tail")

    assert text == "Authorization: [REDACTED] next value tail"


def test_safe_evidence_metadata_text_preserves_spacing_but_strips_line_breaks() -> None:
    text = safe_evidence_metadata_text("token=live-secret\r\nnext")

    assert text == "token=[REDACTED]  next"


def test_contains_unredacted_evidence_secret_ignores_redacted_inline_code_fence() -> None:
    assert contains_unredacted_evidence_secret("token=[REDACTED]`") is False
    assert contains_unredacted_evidence_secret("token=live-secret") is True


def test_read_local_evidence_artifact_bytes_rejects_final_symlink(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    source = tmp_path / "source.json"
    os.symlink(target, source)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(source)

    assert raw_bytes is None
    assert error == "symlinked path component"


def test_read_local_evidence_artifact_bytes_rejects_parent_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.json").write_text("{}", encoding="utf-8")
    linked_parent = tmp_path / "linked"
    os.symlink(outside, linked_parent)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(
        linked_parent / "source.json"
    )

    assert raw_bytes is None
    assert error == "symlinked path component"


def test_read_local_evidence_artifact_bytes_reads_relative_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "source.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(
        Path("nested") / "source.json"
    )

    assert raw_bytes == b"{}"
    assert error == ""


def test_read_local_evidence_artifact_bytes_rejects_parent_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "source.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(
        Path("nested") / ".." / "source.json"
    )

    assert raw_bytes is None
    assert error == "unreadable"


def test_read_local_evidence_artifact_bytes_uses_best_effort_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence_common, "supports_no_follow_tree_open", lambda: False)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(path)

    assert raw_bytes == b"{}"
    assert error == ""


def test_read_local_evidence_artifact_bytes_best_effort_rejects_stat_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    path.write_text("{}", encoding="utf-8")
    real_fstat = os.fstat

    def mismatched_fstat(file_descriptor: int) -> SimpleNamespace:
        original = real_fstat(file_descriptor)
        return SimpleNamespace(
            st_mode=original.st_mode,
            st_size=original.st_size,
            st_dev=original.st_dev + 1,
            st_ino=original.st_ino + 1,
        )

    monkeypatch.setattr(os, "fstat", mismatched_fstat)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes_best_effort(path)

    assert raw_bytes is None
    assert error == "unreadable"


def test_read_local_evidence_artifact_bytes_no_follow_reports_os_errors(
    tmp_path: Path,
) -> None:
    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes_no_follow(
        tmp_path / "reports" / "missing.json"
    )

    assert raw_bytes is None
    assert error == "unreadable"


def test_read_local_evidence_artifact_bytes_no_follow_closes_opened_parent_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_descriptors: list[tuple[int, str, int | None]] = []
    closed_descriptors: list[int] = []

    def fake_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        del flags, mode
        name = os.fspath(path)
        if name == "blocked":
            raise OSError(errno.EACCES, "blocked")
        descriptor = 100 + len(opened_descriptors)
        opened_descriptors.append((descriptor, name, dir_fd))
        return descriptor

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", closed_descriptors.append)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes_no_follow(
        Path("reports") / "blocked" / "artifact.json"
    )

    assert raw_bytes is None
    assert error == "unreadable"
    assert opened_descriptors == [(100, ".", None), (101, "reports", 100)]
    assert closed_descriptors == [101, 100]


def test_read_local_evidence_artifact_bytes_best_effort_reports_os_errors(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes_best_effort(
        missing
    )

    assert raw_bytes is None
    assert error == "unreadable"


def test_read_local_evidence_artifact_bytes_best_effort_rejects_non_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    path.write_text("{}", encoding="utf-8")
    real_s_isreg = stat_module.S_ISREG

    def fake_s_isreg(mode: int) -> bool:
        if mode == path.stat(follow_symlinks=False).st_mode:
            return False
        return real_s_isreg(mode)

    monkeypatch.setattr(stat_module, "S_ISREG", fake_s_isreg)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes_best_effort(
        path
    )

    assert raw_bytes is None
    assert error == "not a file"


def test_read_bounded_local_evidence_bytes_from_descriptor_rejects_non_file(
    tmp_path: Path,
) -> None:
    directory_descriptor = os.open(tmp_path, os.O_RDONLY)
    try:
        raw_bytes, error = (
            evidence_common.read_bounded_local_evidence_bytes_from_descriptor(
                directory_descriptor
            )
        )
    finally:
        os.close(directory_descriptor)

    assert raw_bytes is None
    assert error == "not a file"


def test_read_bounded_local_evidence_bytes_from_descriptor_detects_growth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    path.write_text("abcdef", encoding="utf-8")
    real_fstat = os.fstat

    def small_fstat(file_descriptor: int) -> SimpleNamespace:
        original = real_fstat(file_descriptor)
        return SimpleNamespace(
            st_mode=original.st_mode,
            st_size=1,
            st_dev=original.st_dev,
            st_ino=original.st_ino,
        )

    monkeypatch.setattr(os, "fstat", small_fstat)
    file_descriptor = os.open(path, os.O_RDONLY)
    try:
        raw_bytes, error = (
            evidence_common.read_bounded_local_evidence_bytes_from_descriptor(
                file_descriptor,
                max_bytes=1,
            )
        )
    finally:
        os.close(file_descriptor)

    assert raw_bytes is None
    assert "exceeds" in error


def test_local_evidence_read_error_summaries() -> None:
    assert (
        evidence_common.local_evidence_read_error_summary(
            OSError(errno.ELOOP, "too many links")
        )
        == "symlinked path component"
    )
    assert (
        evidence_common.local_evidence_read_error_summary(
            OSError(errno.ENOTDIR, "not directory")
        )
        == "symlinked path component"
    )
    assert (
        evidence_common.local_evidence_read_error_summary(
            OSError(errno.EISDIR, "directory")
        )
        == "not a file"
    )
    assert (
        evidence_common.local_evidence_read_error_summary(OSError(errno.EPERM, "denied"))
        == "unreadable"
    )
