"""Owner-authorized descriptor reads for sensitive local evidence."""

from __future__ import annotations

import errno
import os
import stat
from contextlib import ExitStack
from pathlib import Path

from entroping.core.evidence_common import (
    local_evidence_read_error_summary,
    read_bounded_local_evidence_bytes_from_descriptor,
    register_local_evidence_descriptor,
    supports_no_follow_tree_open,
)

__all__ = [
    "read_bounded_local_evidence_bytes_from_descriptor",
    "read_owner_only_local_evidence_artifact_bytes",
]


def read_owner_only_local_evidence_artifact_bytes(
    path: Path,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    """Read owner-only evidence from one stable no-follow descriptor tree."""

    if not supports_no_follow_tree_open():
        return None, "authorization unsupported"
    try:
        with ExitStack() as descriptor_stack:
            root, parts = _parent_descriptor_parts(path)
            directory_descriptor = register_local_evidence_descriptor(
                descriptor_stack,
                os.open(root, os.O_RDONLY | os.O_DIRECTORY),
            )
            for part in parts:
                directory_descriptor = register_local_evidence_descriptor(
                    descriptor_stack,
                    os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_descriptor,
                    ),
                )
            file_descriptor = register_local_evidence_descriptor(
                descriptor_stack,
                os.open(
                    path.name,
                    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=directory_descriptor,
                ),
            )
            return _read_authorized_descriptor(
                directory_descriptor,
                file_descriptor,
                path.name,
                max_bytes=max_bytes,
            )
    except OSError as exc:
        return None, local_evidence_read_error_summary(exc)


def _parent_descriptor_parts(path: Path) -> tuple[str, tuple[str, ...]]:
    """Split a parent path into its descriptor-open root and components."""

    parent = path.parent
    if parent.is_absolute():
        parts = parent.parts[1:]
        root = parent.anchor
    else:
        parts = parent.parts
        root = "."
    if any(part == ".." for part in parts):
        raise OSError(errno.EINVAL, "parent traversal is not allowed")
    return root, parts


def _read_authorized_descriptor(
    directory_descriptor: int,
    file_descriptor: int,
    name: str,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    before = _authorization_snapshot(directory_descriptor, file_descriptor, name)
    if not _authorized(*before):
        return None, "authorization failed"
    raw, read_error = read_bounded_local_evidence_bytes_from_descriptor(
        file_descriptor,
        max_bytes=max_bytes,
    )
    if raw is None:
        return None, read_error
    after = _authorization_snapshot(directory_descriptor, file_descriptor, name)
    if _authorization_changed(before=before, after=after):
        return None, "authorization changed"
    return raw, ""


def _authorization_snapshot(
    directory_descriptor: int,
    file_descriptor: int,
    name: str,
) -> tuple[os.stat_result, os.stat_result, os.stat_result]:
    return (
        os.fstat(directory_descriptor),
        os.fstat(file_descriptor),
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False),
    )


def _authorized(
    parent_status: os.stat_result,
    descriptor_status: os.stat_result,
    path_status: os.stat_result,
) -> bool:
    return (
        _owner_authorized_directory(parent_status)
        and _owner_authorized_file(descriptor_status)
        and _same_file(descriptor_status, path_status)
    )


def _owner_authorized_directory(status: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(status.st_mode)
        and status.st_uid == os.geteuid()
        and status.st_mode & 0o022 == 0
    )


def _owner_authorized_file(status: os.stat_result) -> bool:
    return (
        stat.S_ISREG(status.st_mode)
        and status.st_uid == os.geteuid()
        and status.st_mode & 0o077 == 0
    )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _authorization_changed(
    *,
    before: tuple[os.stat_result, os.stat_result, os.stat_result],
    after: tuple[os.stat_result, os.stat_result, os.stat_result],
) -> bool:
    parent_before, descriptor_before, path_before = before
    parent_after, descriptor_after, path_after = after
    return (
        _stable_snapshot(parent_before) != _stable_snapshot(parent_after)
        or _stable_snapshot(descriptor_before) != _stable_snapshot(descriptor_after)
        or _stable_snapshot(path_before) != _stable_snapshot(path_after)
        or not _same_file(descriptor_after, path_after)
        or not _authorized(parent_after, descriptor_after, path_after)
    )


def _stable_snapshot(status: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_uid,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )
