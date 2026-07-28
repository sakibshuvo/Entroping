from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

MAX_METADATA_BYTES = 1_048_576
MAX_DIRECTORY_ENTRIES = 10_000
MAX_SNAPSHOT_ENTRIES = 100_000
MAX_SNAPSHOT_BYTES = 8_589_934_592
MAX_POLICY_TOTAL_BYTES = MAX_SNAPSHOT_BYTES // 2
MAX_SNAPSHOT_DEPTH = 64


class RetentionFsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FsSnapshot:
    kind: str
    byte_size: int
    mtime_ns: int
    sha256: str


@dataclass(slots=True)
class SnapshotBudget:
    max_entries: int = MAX_SNAPSHOT_ENTRIES
    max_bytes: int = MAX_SNAPSHOT_BYTES
    max_depth: int = MAX_SNAPSHOT_DEPTH
    entries: int = 0
    bytes: int = 0

    def consume(self, *, byte_size: int, depth: int) -> None:
        if depth > self.max_depth:
            raise RetentionFsError("managed artifact exceeds snapshot depth limit")
        if self.entries >= self.max_entries:
            raise RetentionFsError("managed inventory exceeds snapshot entry limit")
        if byte_size < 0 or self.bytes > self.max_bytes - byte_size:
            raise RetentionFsError("managed inventory exceeds snapshot byte limit")
        self.entries += 1
        self.bytes += byte_size


@contextmanager
def open_relative_directory(
    repo_root: Path,
    parts: tuple[str, ...],
    *,
    create: bool = False,
) -> Generator[int, None, None]:
    invalid_component = any(
        not part or part in {".", ".."} or Path(part).name != part for part in parts
    )
    if invalid_component:
        raise RetentionFsError("directory path contains an invalid component")
    flags = os.O_RDONLY | _directory_flag() | _nofollow_flag()
    descriptors: list[int] = []
    try:
        current = os.open(repo_root, flags)
        descriptors.append(current)
        for part in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=current)
            child = os.open(part, flags, dir_fd=current)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                raise RetentionFsError("managed path component is not a directory")
            descriptors.append(child)
            current = child
    except OSError as exc:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise RetentionFsError(
            "could not open managed directory without following symlinks"
        ) from exc
    try:
        yield current
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def list_names(directory_fd: int) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if len(names) >= MAX_DIRECTORY_ENTRIES:
                raise RetentionFsError("managed directory exceeds entry limit")
            _validate_name(entry.name)
            names.append(entry.name)
    return tuple(sorted(names))


def path_exists(repo_root: Path, parts: tuple[str, ...]) -> bool:
    try:
        _ = os.stat(repo_root.joinpath(*parts), follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def entry_snapshot(
    directory_fd: int,
    name: str,
    *,
    budget: SnapshotBudget | None = None,
) -> FsSnapshot:
    return _entry_snapshot(
        directory_fd,
        name,
        budget=budget or SnapshotBudget(),
        depth=0,
    )


def _entry_snapshot(
    directory_fd: int,
    name: str,
    *,
    budget: SnapshotBudget,
    depth: int,
) -> FsSnapshot:
    _validate_name(name)
    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if stat.S_ISREG(metadata.st_mode):
        budget.consume(byte_size=metadata.st_size, depth=depth)
        return _regular_snapshot(directory_fd, name, expected_size=metadata.st_size)
    if stat.S_ISDIR(metadata.st_mode):
        budget.consume(byte_size=0, depth=depth)
        return _directory_snapshot(directory_fd, name, budget=budget, depth=depth)
    raise RetentionFsError("managed entry is a symlink or special file")


def read_bounded_regular(
    directory_fd: int,
    name: str,
    *,
    limit: int = MAX_METADATA_BYTES,
) -> bytes:
    _validate_name(name)
    try:
        descriptor = _open_regular(directory_fd, name)
    except OSError as exc:
        raise RetentionFsError("managed metadata file must be regular and non-symlink") from exc
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_size > limit:
            raise RetentionFsError("metadata file exceeds the bounded read limit")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > limit:
            raise RetentionFsError("metadata file exceeds the bounded read limit")
        return payload
    finally:
        os.close(descriptor)


def _regular_snapshot(directory_fd: int, name: str, *, expected_size: int) -> FsSnapshot:
    descriptor = _open_regular(directory_fd, name)
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_size != expected_size:
            raise RetentionFsError("managed file changed during snapshot")
        digest = hashlib.sha256()
        bytes_read = 0
        while chunk := os.read(descriptor, min(65_536, expected_size - bytes_read + 1)):
            bytes_read += len(chunk)
            if bytes_read > expected_size:
                raise RetentionFsError("managed file changed during snapshot")
            digest.update(chunk)
        if bytes_read != expected_size:
            raise RetentionFsError("managed file changed during snapshot")
        return FsSnapshot(
            kind="file",
            byte_size=expected_size,
            mtime_ns=metadata.st_mtime_ns,
            sha256=digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


def _directory_snapshot(
    directory_fd: int,
    name: str,
    *,
    budget: SnapshotBudget,
    depth: int,
) -> FsSnapshot:
    flags = os.O_RDONLY | _directory_flag() | _nofollow_flag()
    child_fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        metadata = os.fstat(child_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RetentionFsError("managed entry is not a directory")
        digest = hashlib.sha256()
        size = 0
        newest_mtime = metadata.st_mtime_ns
        for child_name in list_names(child_fd):
            child = _entry_snapshot(
                child_fd,
                child_name,
                budget=budget,
                depth=depth + 1,
            )
            digest.update(child.kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(child_name.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\0")
            digest.update(child.sha256.encode("ascii"))
            size += child.byte_size
            newest_mtime = max(newest_mtime, child.mtime_ns)
        return FsSnapshot(
            kind="directory",
            byte_size=size,
            mtime_ns=newest_mtime,
            sha256=digest.hexdigest(),
        )
    finally:
        os.close(child_fd)


def _open_regular(directory_fd: int, name: str) -> int:
    flags = os.O_RDONLY | _nofollow_flag() | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(name, flags, dir_fd=directory_fd)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RetentionFsError("managed entry is not a regular file")
    return descriptor


def _validate_name(name: str) -> None:
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise RetentionFsError("managed entry name is invalid")


def _nofollow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _directory_flag() -> int:
    return getattr(os, "O_DIRECTORY", 0)
