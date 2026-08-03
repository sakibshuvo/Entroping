"""Direct tests for owner-authorized local evidence reads."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

import pytest

from entroping.core import owner_only_evidence


def _owner_only_file(tmp_path: Path, content: bytes = b"evidence") -> Path:
    parent = tmp_path / "private"
    parent.mkdir()
    os.chmod(parent, 0o700)
    target = parent / "receipt.json"
    _ = target.write_bytes(content)
    os.chmod(target, 0o600)
    return target


def test_owner_only_reader_returns_bytes_from_stable_descriptor(tmp_path: Path) -> None:
    path = _owner_only_file(tmp_path)

    raw, error = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        path, max_bytes=32
    )

    assert raw == b"evidence"
    assert error == ""


def test_owner_only_reader_rejects_unsupported_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _owner_only_file(tmp_path)
    monkeypatch.setattr(owner_only_evidence, "supports_no_follow_tree_open", lambda: False)

    raw, error = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        path, max_bytes=32
    )

    assert raw is None
    assert error == "authorization unsupported"


def test_owner_only_reader_rejects_permissive_mode_and_oversize(tmp_path: Path) -> None:
    permissive = _owner_only_file(tmp_path)
    os.chmod(permissive, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    unauthorized = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        permissive, max_bytes=32
    )
    os.chmod(permissive, 0o600)
    oversized = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        permissive, max_bytes=1
    )

    assert unauthorized == (None, "authorization failed")
    assert oversized == (None, "artifact exceeds 1 bytes")


def test_owner_only_reader_closes_descriptor_when_registration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _owner_only_file(tmp_path)
    original_close = os.close
    closed: list[int] = []

    def track_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    def fail_callback(
        self: ExitStack,
        callback: Callable[..., object],
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        del self, callback, args, kwargs
        raise MemoryError("registration failed")

    monkeypatch.setattr(os, "close", track_close)
    monkeypatch.setattr(ExitStack, "callback", fail_callback)

    with pytest.raises(MemoryError, match="registration failed"):
        _ = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(path, max_bytes=32)

    assert len(closed) == 1


def test_owner_only_reader_supports_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absolute = _owner_only_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    raw, error = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        Path("private") / absolute.name, max_bytes=32
    )

    assert raw == b"evidence"
    assert error == ""


def test_owner_only_reader_rejects_parent_traversal_and_missing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "private"
    private.mkdir()
    os.chmod(private, 0o700)
    monkeypatch.chdir(private)

    traversal = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        Path("..") / "receipt.json", max_bytes=32
    )
    missing = owner_only_evidence.read_owner_only_local_evidence_artifact_bytes(
        Path("missing.json"), max_bytes=32
    )

    assert traversal == (None, "unreadable")
    assert missing == (None, "unreadable")
