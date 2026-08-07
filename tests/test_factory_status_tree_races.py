from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_status_filesystem import collect_queue, collect_retention  # noqa: E402


@pytest.mark.parametrize("surface", ("queue", "retention"))
def test_tree_walk_remains_bound_to_validated_directory_descriptor(
    tmp_path: Path, monkeypatch: MonkeyPatch, surface: str
) -> None:
    """Replacing a walked pathname cannot redirect traversal to a new tree."""

    if surface == "queue":
        walked = tmp_path / ".entroping" / "ai-jobs" / "queued"
    else:
        walked = tmp_path / ".entroping" / "factory-logs"
        policy_dir = tmp_path / "docs" / "meta"
        policy_dir.mkdir(parents=True)
        (policy_dir / "factory-retention-policy.example.json").write_bytes(
            (REPO_ROOT / "docs" / "meta" / "factory-retention-policy.example.json").read_bytes()
        )
    walked.mkdir(parents=True)
    (walked / "original.json").write_text("metadata", encoding="utf-8")
    original_inode = walked.stat().st_ino
    moved = walked.with_name(f"{walked.name}-opened")
    original_scandir = os.scandir

    def scan_descriptor(path: int) -> Iterator[os.DirEntry[str]]:
        return original_scandir(path)

    swapped = False

    def swap_before_scan(path: int) -> Iterator[os.DirEntry[str]]:
        nonlocal swapped
        if not swapped and os.fstat(path).st_ino == original_inode:
            os.replace(walked, moved)
            walked.mkdir()
            os.symlink(tmp_path / "outside", walked / "replacement.json")
            swapped = True
        return scan_descriptor(path)

    monkeypatch.setattr(os, "scandir", swap_before_scan)

    if surface == "queue":
        queue_result, _ = collect_queue(tmp_path, [])
        assert queue_result.queued == 1
    else:
        retention_result, _ = collect_retention(tmp_path, [])
        factory_log = next(
            item for item in retention_result.classes if item.artifact_class == "factory_log"
        )
        assert factory_log.count == 1
    assert swapped is True


def test_queue_rejects_hardlink_swapped_after_path_stat(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A regular queue entry swapped after path stat is rejected from its bound descriptor."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    job = queued / "job.json"
    job.write_text("original", encoding="utf-8")
    replacement = tmp_path / "replacement.json"
    replacement.write_text("replacement", encoding="utf-8")
    os.link(replacement, tmp_path / "replacement-alias.json")
    original_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o600,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if not swapped and os.fsdecode(path) == job.name and dir_fd is not None:
            job.unlink()
            os.link(replacement, job)
            swapped = True
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_before_open)

    queue, reasons = collect_queue(tmp_path, [])

    assert swapped is True
    assert queue.status == "unsafe"
    assert reasons == ("queue-unsafe",)
