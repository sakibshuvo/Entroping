from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from scripts.factory_retention_fs import RetentionFsError, open_relative_directory

from .factory_status_errors import FactoryStatusError

type Fingerprints = list[tuple[str, int, int, int]]

QUEUE_STATES = ("queued", "running", "completed", "failed")
MAX_ENTRIES = 10_000
MAX_DEPTH = 64


@dataclass(slots=True)
class TraversalBudget:
    remaining: int = MAX_ENTRIES

    def consume(self) -> None:
        if self.remaining <= 0:
            raise FactoryStatusError("entry limit exceeded")
        self.remaining -= 1


def scan_queue(root: Path, fingerprints: Fingerprints) -> tuple[dict[str, int], int]:
    """Validate the fixed queue layout through bound directory descriptors."""

    counts = {state: 0 for state in QUEUE_STATES}
    try:
        with open_relative_directory(root, (".entroping", "ai-jobs")) as directory:
            invalid = _scan_queue_directory(
                directory,
                (".entroping", "ai-jobs"),
                fingerprints,
                counts,
                state=None,
                depth=0,
                budget=TraversalBudget(),
            )
    except (OSError, RetentionFsError) as exc:
        raise FactoryStatusError("queue traversal is unsafe") from exc
    return counts, invalid


def scan_retention(
    root: Path,
    parts: tuple[str, ...],
    fingerprints: Fingerprints,
    totals: list[int],
    budget: TraversalBudget,
) -> None:
    """Accumulate retention metadata through bound directory descriptors."""

    try:
        with open_relative_directory(root, parts) as directory:
            _scan_retention_directory(
                directory, parts, fingerprints, totals, depth=0, budget=budget
            )
    except (OSError, RetentionFsError) as exc:
        raise FactoryStatusError("retention traversal is unsafe") from exc


def _scan_queue_directory(
    directory: int,
    parts: tuple[str, ...],
    fingerprints: Fingerprints,
    counts: dict[str, int],
    *,
    state: str | None,
    depth: int,
    budget: TraversalBudget,
) -> int:
    _check_depth(depth)
    invalid = 0
    for name in _names(directory, budget):
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            bound = _regular_metadata(directory, name)
            _fingerprint((*parts, name), bound, fingerprints)
            if state is not None and depth == 1 and name.endswith(".json"):
                counts[state] += 1
            else:
                invalid += 1
            continue
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory(directory, name, metadata)
            try:
                child_state = name if depth == 0 and name in counts else state
                expected = depth == 0 and name in counts
                invalid += 0 if expected else 1
                invalid += _scan_queue_directory(
                    child,
                    (*parts, name),
                    fingerprints,
                    counts,
                    state=child_state,
                    depth=depth + 1,
                    budget=budget,
                )
            finally:
                os.close(child)
            continue
        raise FactoryStatusError("queue contains a symlink or special file")
    return invalid


def _scan_retention_directory(
    directory: int,
    parts: tuple[str, ...],
    fingerprints: Fingerprints,
    totals: list[int],
    *,
    depth: int,
    budget: TraversalBudget,
) -> None:
    _check_depth(depth)
    for name in _names(directory, budget):
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            bound = _regular_metadata(directory, name)
            _fingerprint((*parts, name), bound, fingerprints)
            totals[0] += 1
            totals[1] += bound.st_size
            continue
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory(directory, name, metadata)
            try:
                _scan_retention_directory(
                    child,
                    (*parts, name),
                    fingerprints,
                    totals,
                    depth=depth + 1,
                    budget=budget,
                )
            finally:
                os.close(child)
            continue
        raise FactoryStatusError("retention contains a symlink or special file")


def _names(directory: int, budget: TraversalBudget) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            budget.consume()
            names.append(entry.name)
    return tuple(sorted(names))


def _open_directory(parent: int, name: str, expected: os.stat_result) -> int:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent,
    )
    actual = os.fstat(descriptor)
    if not stat.S_ISDIR(actual.st_mode) or _entry_identity(actual) != _entry_identity(expected):
        os.close(descriptor)
        raise FactoryStatusError("directory changed during traversal")
    return descriptor


def _regular_metadata(parent: int, name: str) -> os.stat_result:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        dir_fd=parent,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise FactoryStatusError("unsafe regular metadata file")
        return metadata
    finally:
        os.close(descriptor)


def _fingerprint(
    parts: tuple[str, ...],
    metadata: os.stat_result,
    fingerprints: Fingerprints,
) -> None:
    relative = Path(*parts).as_posix()
    fingerprints.append((relative, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns))


def _entry_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _check_depth(depth: int) -> None:
    if depth > MAX_DEPTH:
        raise FactoryStatusError("path depth exceeded")
