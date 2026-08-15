"""Held-descriptor POSIX primitives for mutation materialization."""

from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
from collections.abc import Callable, Collection
from contextlib import suppress
from pathlib import Path
from typing import Final

from entroping.models.secrets import contains_secret_like_value, has_disallowed_control

HURL_SOURCE_MAX_BYTES: Final = 10 * 1024 * 1024
NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY_FLAG: Final = getattr(os, "O_DIRECTORY", 0)
NONBLOCK: Final = getattr(os, "O_NONBLOCK", 0)
DIR_FLAGS: Final = os.O_RDONLY | DIRECTORY_FLAG | NOFOLLOW
TEMP_SUFFIX: Final = ".materializing"
_CLONE_NOFOLLOW_ANY: Final = 0x0008
_CLONE_RESOLVE_BENEATH: Final = 0x0010
_AT_EMPTY_PATH: Final = 0x1000


class MutationMaterializerError(ValueError):
    """Fixed content-free materialization failure."""


PublicationBackend = Callable[[int, int, bytes], int | None]
DarwinPrimitive = Callable[[int, int, bytes, int], int]


def _load_darwin_clonefileat() -> DarwinPrimitive | None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.fclonefileat
    except (AttributeError, OSError):
        return None
    function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    function.restype = ctypes.c_int
    return function


_DARWIN_CLONEFILEAT: DarwinPrimitive | None = (
    _load_darwin_clonefileat() if sys.platform == "darwin" else None
)


def _darwin_publish(descriptor: int, destination_fd: int, name: bytes) -> int | None:
    if _DARWIN_CLONEFILEAT is None:
        return None
    result = _DARWIN_CLONEFILEAT(
        descriptor,
        destination_fd,
        name,
        _CLONE_NOFOLLOW_ANY | _CLONE_RESOLVE_BENEATH,
    )
    return 0 if result == 0 else ctypes.get_errno()


def _linux_proc_fd_link(descriptor: int, destination_fd: int, name: bytes) -> int | None:
    try:
        os.link(
            f"/proc/self/fd/{descriptor}",
            os.fsdecode(name),
            dst_dir_fd=destination_fd,
            follow_symlinks=True,
        )
    except FileExistsError:
        return errno.EEXIST
    except OSError as exc:
        return exc.errno
    return 0


def _publication_backend() -> PublicationBackend | None:
    if sys.platform == "darwin":
        return _darwin_publish if _DARWIN_CLONEFILEAT is not None else None
    if sys.platform == "linux" and os.path.isdir("/proc/self/fd"):
        return _linux_proc_fd_link
    return None


_PUBLICATION_BACKEND = _publication_backend()


def platform_capability_preflight(
    nofollow: int = NOFOLLOW,
    directory_flag: int = DIRECTORY_FLAG,
    nonblock: int = NONBLOCK,
) -> None:
    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    supports_follow_symlinks = getattr(os, "supports_follow_symlinks", ())
    if not all(
        (
            nofollow,
            directory_flag,
            nonblock,
            all(function in supports_dir_fd for function in (os.open, os.stat, os.unlink)),
            all(function in supports_follow_symlinks for function in (os.stat,)),
            _linux_link_supported(supports_dir_fd, supports_follow_symlinks),
            _PUBLICATION_BACKEND is not None,
        )
    ):
        raise MutationMaterializerError("platform capability unsupported")


def _linux_link_supported(
    supports_dir_fd: Collection[object], supports_follow_symlinks: Collection[object]
) -> bool:
    return sys.platform != "linux" or (
        os.link in supports_dir_fd and os.link in supports_follow_symlinks
    )


def open_root(root: Path) -> int:
    if not root.is_absolute() or root.is_symlink():
        raise MutationMaterializerError("project root is unsafe")
    try:
        descriptor = os.open(root, DIR_FLAGS)
    except OSError as exc:
        raise MutationMaterializerError("project root is unavailable") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise MutationMaterializerError("project root is not a directory")
    return descriptor


def relative_parts(value: str, *, label: str) -> tuple[str, ...]:
    if any((not value, has_disallowed_control(value), contains_secret_like_value(value))):
        raise MutationMaterializerError(f"{label} is unsafe")
    path = Path(value)
    raw_parts = value.split("/")
    if path.is_absolute() or {"", ".", ".."}.intersection(raw_parts):
        raise MutationMaterializerError(f"{label} must be project-relative")
    return tuple(path.parts)


def open_relative_directory(
    root_fd: int, parts: tuple[str, ...]
) -> tuple[int, tuple[tuple[int, int], ...]]:
    current = os.dup(root_fd)
    identities: list[tuple[int, int]] = []
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = child
            metadata = os.fstat(current)
            if not stat.S_ISDIR(metadata.st_mode):
                raise MutationMaterializerError("destination ancestry is not a directory")
            identities.append((metadata.st_dev, metadata.st_ino))
        return current, tuple(identities)
    except (OSError, MutationMaterializerError):
        with suppress(OSError):
            os.close(current)
        raise


def open_regular(parent_fd: int, name: str, flags: int, error: str) -> int:
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    if stat.S_ISREG(os.fstat(descriptor).st_mode):
        return descriptor
    os.close(descriptor)
    raise MutationMaterializerError(error)


def open_source(root_fd: int, parts: tuple[str, ...]) -> tuple[int, int, str]:
    if len(parts) < 2 or parts[-1].endswith("/"):
        raise MutationMaterializerError("source path is unsafe")
    parent_fd, _ = open_relative_directory(root_fd, parts[:-1])
    try:
        source_fd = open_regular(
            parent_fd, parts[-1], os.O_RDONLY | NONBLOCK | NOFOLLOW, "source is not a regular file"
        )
    except (OSError, MutationMaterializerError):
        os.close(parent_fd)
        raise
    return source_fd, parent_fd, parts[-1]


def read_bounded_fd(descriptor: int, limit: int) -> bytes:
    if limit < 0:
        raise MutationMaterializerError("bounded input limit is invalid")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(64 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise MutationMaterializerError("bounded input is oversized")


def recheck_source(
    parent_fd: int,
    leaf: str,
    first_stat: os.stat_result,
    first_bytes: bytes,
    second_stat: os.stat_result,
    second_bytes: bytes,
) -> None:
    current = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (first_stat.st_dev, first_stat.st_ino):
        raise MutationMaterializerError("source changed before publication")
    if (second_stat.st_dev, second_stat.st_ino, second_stat.st_size, second_stat.st_mtime_ns) != (
        first_stat.st_dev,
        first_stat.st_ino,
        first_stat.st_size,
        first_stat.st_mtime_ns,
    ) or second_bytes != first_bytes:
        raise MutationMaterializerError("source changed before publication")


def create_output(destination_fd: int, name: str, content: str) -> None:
    temporary_name = f".{name}{TEMP_SUFFIX}"
    try:
        descriptor = os.open(
            temporary_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | NOFOLLOW,
            0o600,
            dir_fd=destination_fd,
        )
    except FileExistsError as exc:
        raise MutationMaterializerError("candidate output is already being materialized") from exc
    descriptor_open = descriptor
    try:
        _write_output(descriptor, content)
        os.fsync(descriptor)
        _publish_output(descriptor, destination_fd, temporary_name, name)
        with suppress(OSError):
            os.close(descriptor)
        descriptor_open = -1
    except MutationMaterializerError:
        _cleanup_output(descriptor_open, destination_fd, temporary_name)
        raise
    except OSError as exc:
        _cleanup_output(descriptor_open, destination_fd, temporary_name)
        raise MutationMaterializerError("candidate output could not be written") from exc


def _publish_output(descriptor: int, destination_fd: int, temporary_name: str, name: str) -> None:
    if _PUBLICATION_BACKEND is None:
        raise MutationMaterializerError("platform capability unsupported")
    result = _PUBLICATION_BACKEND(descriptor, destination_fd, os.fsencode(name))
    if result == errno.EEXIST:
        raise MutationMaterializerError("candidate output already exists")
    if result in {errno.ENOTSUP, errno.EOPNOTSUPP}:
        raise MutationMaterializerError("candidate output publication unsupported")
    if result != 0:
        raise MutationMaterializerError("candidate output could not be published")
    with suppress(OSError):
        os.unlink(temporary_name, dir_fd=destination_fd)


def _write_output(descriptor: int, content: str) -> None:
    raw = content.encode("utf-8")
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise MutationMaterializerError("candidate output write made no progress")
        offset += written


def _cleanup_output(descriptor: int, destination_fd: int, name: str) -> None:
    failed = False
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except OSError:
            failed = True
    try:
        os.unlink(name, dir_fd=destination_fd)
    except OSError:
        failed = True
    if failed:
        raise MutationMaterializerError("candidate output cleanup failed")
