import os
import stat as stat_module
from pathlib import Path
from types import SimpleNamespace

import pytest

import entroping.core.evidence_common as evidence_common


def test_read_local_evidence_artifact_bytes_uses_best_effort_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    _ = path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence_common, "supports_no_follow_tree_open", lambda: False)

    raw_bytes, error = evidence_common.read_local_evidence_artifact_bytes(path)

    assert raw_bytes == b"{}"
    assert error == ""


def test_read_local_evidence_artifact_bytes_best_effort_rejects_stat_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    _ = path.write_text("{}", encoding="utf-8")
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
    _ = path.write_text("{}", encoding="utf-8")
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
