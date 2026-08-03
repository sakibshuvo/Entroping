from __future__ import annotations

import builtins
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO

import pytest
from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_status import collect_factory_status  # noqa: E402
from scripts.factory_status_filesystem import collect_queue as status_collect_queue  # noqa: E402
from scripts.factory_status_models import QueueStatus  # noqa: E402


def _deny_payload_reads(monkeypatch: MonkeyPatch, payload: Path) -> None:
    """Instrument every public content-read seam while preserving metadata access."""

    original_open = builtins.open
    original_path_open = Path.open
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes
    original_os_open = os.open

    def is_payload(value: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> bool:
        decoded = os.fsdecode(value)
        return decoded in {str(payload), payload.name}

    def reject_open(
        file: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        closefd: bool = True,
        opener: Callable[[str, int], int] | None = None,
    ) -> IO[str] | IO[bytes]:
        if is_payload(file):
            raise AssertionError("status attempted to read queue payload")
        return original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    def reject_path_open(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[str] | IO[bytes]:
        if self == payload:
            raise AssertionError("status attempted to read queue payload")
        return original_path_open(self, mode, buffering, encoding, errors, newline)

    def reject_read_text(self: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if self == payload:
            raise AssertionError("status attempted to read queue payload")
        return original_read_text(self, encoding=encoding, errors=errors)

    def reject_read_bytes(self: Path) -> bytes:
        if self == payload:
            raise AssertionError("status attempted to read queue payload")
        return original_read_bytes(self)

    def reject_os_open(
        file: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if is_payload(file):
            raise AssertionError("status attempted to read queue payload")
        if dir_fd is None:
            return original_os_open(file, flags, mode)
        return original_os_open(file, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(builtins, "open", reject_open)
    monkeypatch.setattr(Path, "open", reject_path_open)
    monkeypatch.setattr(Path, "read_text", reject_read_text)
    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    monkeypatch.setattr(os, "open", reject_os_open)


def test_queue_payload_file_is_never_read_through_any_content_seam(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Queue status uses metadata only, even when every content reader rejects the canary."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    payload = queued / "job.json"
    payload.write_text("secret-canary", encoding="utf-8")
    _deny_payload_reads(monkeypatch, payload)

    report = collect_factory_status(tmp_path)

    assert report.queue.queued == 1


def test_status_never_invokes_provider_or_test_execution(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Status is a local projection and cannot trigger network or subprocess work."""

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("status attempted network access")

    def reject_process(*args: object, **kwargs: object) -> None:
        raise AssertionError("status attempted subprocess execution")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(subprocess, "run", reject_process)

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"


@pytest.mark.parametrize("kind", ("hardlink", "special"))
def test_queue_rejects_unsafe_non_payload_entries(tmp_path: Path, kind: str) -> None:
    """Hardlinks and special entries are invalid queue metadata boundaries."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    candidate = queued / "job.json"
    if kind == "hardlink":
        source = tmp_path / "source.json"
        source.write_text("payload", encoding="utf-8")
        os.link(source, candidate)
    else:
        os.mkfifo(candidate)

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.queue.status == "unsafe"


def test_retention_pressure_pauses_status(tmp_path: Path) -> None:
    """A managed retention root above its trusted ceiling is a paused state."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    policy = json.loads(
        (REPO_ROOT / "docs" / "meta" / "factory-retention-policy.example.json").read_text(
            encoding="utf-8"
        )
    )
    policy["class_policies"][4]["byte_ceiling"] = 1
    (policy_dir / "factory-retention-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    journal = tmp_path / ".entroping" / "retention-journal"
    journal.mkdir(parents=True)
    (journal / "entry.json").write_bytes(b"xx")

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"
    assert "retention-pressure" in report.reason_codes


def test_changed_metadata_between_collections_is_unsafe(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A moving status snapshot cannot be represented as stable authority."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    job = queued / "job.json"
    job.write_text("first", encoding="utf-8")
    collect_queue = status_collect_queue
    calls = 0

    def move_after_first_queue(
        root: Path, fingerprints: list[tuple[str, int, int, int]]
    ) -> tuple[QueueStatus, tuple[str, ...]]:
        nonlocal calls
        result = collect_queue(root, fingerprints)
        calls += 1
        if calls == 1:
            job.write_text("second", encoding="utf-8")
        return result

    monkeypatch.setattr("scripts.factory_status.collect_queue", move_after_first_queue)

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.snapshot_consistency == "changed"
