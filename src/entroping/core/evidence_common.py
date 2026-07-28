"""Shared safety helpers for local evidence artifacts."""

import errno
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Final

from entroping.models.secrets import (
    contains_secret_like_value,
    normalize_redacted_marker,
    redact_secret_like_values,
)

LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES: Final = 100 * 1024 * 1024
_HAS_O_DIRECTORY: Final = hasattr(os, "O_DIRECTORY")
_HAS_O_NOFOLLOW: Final = hasattr(os, "O_NOFOLLOW")
_SUPPORTS_DIR_FD_OPEN: Final = os.open in os.supports_dir_fd
_ASCII_CONTROL_CHAR_TRANSLATION: Final = {code: " " for code in range(32)}


def safe_evidence_text(value: str) -> str:
    """Redact and normalize report text that is rendered as compact evidence."""

    sanitized = redact_secret_like_values(value).translate(_ASCII_CONTROL_CHAR_TRANSLATION)
    return " ".join(sanitized.split())


def safe_evidence_metadata_text(value: str) -> str:
    """Redact metadata text while preserving non-line-break spacing."""

    return redact_secret_like_values(value).replace("\r", " ").replace("\n", " ")


def contains_unredacted_evidence_secret(value: str) -> bool:
    """Return whether evidence text still contains a secret-like value.

    Markdown inline-code fences can trail an already-redacted marker.
    """

    return contains_secret_like_value(normalize_redacted_marker(value))


def read_local_evidence_artifact_bytes(
    path: Path,
    *,
    max_bytes: int = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
) -> tuple[bytes | None, str]:
    """Read a local artifact with a bounded descriptor-based no-follow policy."""

    if supports_no_follow_tree_open():
        return read_local_evidence_artifact_bytes_no_follow(path, max_bytes=max_bytes)
    return read_local_evidence_artifact_bytes_best_effort(path, max_bytes=max_bytes)


def supports_no_follow_tree_open() -> bool:
    """Return whether this runtime can open artifact files relative to a directory FD."""

    return _HAS_O_DIRECTORY and _HAS_O_NOFOLLOW and _SUPPORTS_DIR_FD_OPEN


def register_local_evidence_descriptor(
    descriptor_stack: ExitStack,
    descriptor: int,
) -> int:
    try:
        _ = descriptor_stack.callback(os.close, descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def append_local_evidence_descriptor(
    directory_descriptors: list[int],
    descriptor: int,
) -> None:
    try:
        directory_descriptors.append(descriptor)
    except BaseException:
        os.close(descriptor)
        raise


def read_local_evidence_artifact_bytes_no_follow(
    path: Path,
    *,
    max_bytes: int = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
) -> tuple[bytes | None, str]:
    """Read an artifact path without following parent or final symlink components."""

    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        parent = path.parent
        if parent.is_absolute():
            directory_descriptor = os.open(parent.anchor, os.O_RDONLY | os.O_DIRECTORY)
            directory_descriptors.append(directory_descriptor)
            parts = parent.parts[1:]
        else:
            directory_descriptor = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
            directory_descriptors.append(directory_descriptor)
            parts = parent.parts
        for part in parts:
            if part == "..":
                raise OSError(errno.EINVAL, "parent traversal is not allowed")
            directory_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            directory_descriptors.append(directory_descriptor)
        file_descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
        return read_bounded_local_evidence_bytes_from_descriptor(
            file_descriptor,
            max_bytes=max_bytes,
        )
    except OSError as exc:
        return None, local_evidence_read_error_summary(exc)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for directory_descriptor in reversed(directory_descriptors):
            os.close(directory_descriptor)


def read_local_evidence_artifact_bytes_best_effort(
    path: Path,
    *,
    max_bytes: int = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
) -> tuple[bytes | None, str]:
    """Read the artifact with no-follow flags and descriptor identity checks."""

    file_descriptor: int | None = None
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        file_descriptor = os.open(path, flags)
        path_stat = path.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(path_stat.st_mode) or not stat.S_ISREG(
            descriptor_stat.st_mode
        ):
            return None, "not a file"
        if (path_stat.st_dev, path_stat.st_ino) != (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ):
            return None, "unreadable"
        return read_bounded_local_evidence_bytes_from_descriptor(
            file_descriptor,
            max_bytes=max_bytes,
        )
    except OSError as exc:
        return None, local_evidence_read_error_summary(exc)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def read_bounded_local_evidence_bytes_from_descriptor(
    file_descriptor: int,
    *,
    max_bytes: int = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
) -> tuple[bytes | None, str]:
    """Read at most max_bytes from an already-open local artifact descriptor."""

    descriptor_stat = os.fstat(file_descriptor)
    if not stat.S_ISREG(descriptor_stat.st_mode):
        return None, "not a file"
    if descriptor_stat.st_size > max_bytes:
        return None, f"artifact exceeds {max_bytes} bytes"
    chunks: list[bytes] = []
    bytes_read = 0
    while bytes_read <= max_bytes:
        chunk = os.read(file_descriptor, min(65536, max_bytes + 1 - bytes_read))
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)
    if bytes_read > max_bytes:
        return None, f"artifact exceeds {max_bytes} bytes"
    return b"".join(chunks), ""


def local_evidence_read_error_summary(exc: OSError) -> str:
    """Summarize local artifact read failures without leaking raw paths."""

    if exc.errno == errno.ELOOP:
        return "symlinked path component"
    if exc.errno == errno.ENOTDIR:
        return "symlinked path component"
    if exc.errno == errno.EISDIR:
        return "not a file"
    return "unreadable"
