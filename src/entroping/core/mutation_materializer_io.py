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


class MutationMaterializerError(ValueError):
    """Fixed content-free materialization failure."""


PublicationBackend = Callable[[int, int, bytes, str], int | None]
DarwinPrimitive = Callable[[int, int, bytes, int], int]
LinkOperation = Callable[..., object]


_darwin_libc: object | None = None
with suppress(OSError):
    _darwin_libc = ctypes.CDLL(None, use_errno=True)
_darwin_clonefileat: DarwinPrimitive | None = getattr(_darwin_libc, "fclonefileat", None)
_HAS_DARWIN_CLONEFILEAT: Final = _darwin_clonefileat is not None
_DARWIN_CLONEFILEAT: DarwinPrimitive = _darwin_clonefileat or (lambda *_args: -1)


def _darwin_publish(
    descriptor: int, destination_fd: int, name: bytes, _temporary_name: str
) -> int | None:
    function = _DARWIN_CLONEFILEAT
    result = function(
        descriptor,
        destination_fd,
        name,
        _CLONE_NOFOLLOW_ANY | _CLONE_RESOLVE_BENEATH,
    )
    return 0 if result == 0 else ctypes.get_errno() or errno.ENOTSUP


def descriptor_link_backend(link: LinkOperation) -> PublicationBackend:
    def publish(
        descriptor: int,
        destination_fd: int,
        name: bytes,
        _temporary_name: str,
    ) -> int:
        try:
            link(
                f"/proc/self/fd/{descriptor}",
                os.fsdecode(name),
                dst_dir_fd=destination_fd,
                follow_symlinks=True,
            )
        except FileExistsError:
            return errno.EEXIST
        except OSError as exc:
            return exc.errno or errno.EIO
        return 0

    return publish


def publication_backend() -> PublicationBackend:
    return {"darwin": _darwin_publish, "linux": descriptor_link_backend(os.link)}.get(
        sys.platform, lambda *_args: errno.ENOTSUP
    )


_PUBLICATION_CAPABILITY = {
    "darwin": _HAS_DARWIN_CLONEFILEAT,
    "linux": os.path.isdir("/proc/self/fd"),
}.get(sys.platform, False)


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
            _PUBLICATION_CAPABILITY,
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
) -> None:
    current = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (first_stat.st_dev, first_stat.st_ino):
        raise MutationMaterializerError("source changed before publication")


def create_output(
    destination_fd: int,
    name: str,
    content: str,
) -> None:
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
    try:
        _write_output(descriptor, content)
        os.fsync(descriptor)
        _publish_output(descriptor, destination_fd, temporary_name, name)
        with suppress(OSError):
            os.close(descriptor)
    except MutationMaterializerError:
        _cleanup_output(descriptor, destination_fd, temporary_name)
        raise
    except OSError as exc:
        _cleanup_output(descriptor, destination_fd, temporary_name)
        raise MutationMaterializerError("candidate output could not be written") from exc


def verify_published_output(
    descriptor: int,
    destination_fd: int,
    name: str,
    expected_identity: tuple[int, int] | None,
) -> None:
    try:
        held = os.fstat(descriptor)
        final_fd = os.open(
            name,
            os.O_RDONLY | NONBLOCK | NOFOLLOW,
            dir_fd=destination_fd,
        )
    except OSError as exc:
        raise MutationMaterializerError("candidate output verification failed") from exc
    try:
        final = os.fstat(final_fd)
        if not stat.S_ISREG(final.st_mode) or final.st_size != held.st_size:
            raise MutationMaterializerError("candidate output verification failed")
        if (
            expected_identity is not None
            and (
                final.st_dev,
                final.st_ino,
            )
            != expected_identity
        ):
            raise MutationMaterializerError("candidate output verification failed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        expected = read_bounded_fd(descriptor, HURL_SOURCE_MAX_BYTES)
        os.lseek(final_fd, 0, os.SEEK_SET)
        actual = read_bounded_fd(final_fd, HURL_SOURCE_MAX_BYTES)
        current = os.stat(name, dir_fd=destination_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (final.st_dev, final.st_ino) or actual != expected:
            raise MutationMaterializerError("candidate output verification failed")
    except MutationMaterializerError:
        raise
    except OSError as exc:
        raise MutationMaterializerError("candidate output verification failed") from exc
    finally:
        with suppress(OSError):
            os.close(final_fd)


def publication_result_check(result: int | None) -> None:
    if result == errno.EEXIST:
        raise MutationMaterializerError("candidate output already exists")
    if result in {errno.ENOTSUP, errno.EOPNOTSUPP}:
        raise MutationMaterializerError("candidate output publication unsupported")
    if result != 0:
        raise MutationMaterializerError("candidate output could not be published")


def _publish_output(
    descriptor: int,
    destination_fd: int,
    temporary_name: str,
    name: str,
) -> None:
    backend = publication_backend()
    result = backend(descriptor, destination_fd, os.fsencode(name), temporary_name)
    publication_result_check(result)
    held = os.fstat(descriptor)
    expected_identity = {
        "linux": (held.st_dev, held.st_ino),
        "darwin": None,
    }.get(sys.platform)
    verify_published_output(descriptor, destination_fd, name, expected_identity)
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
