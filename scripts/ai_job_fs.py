from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path


class SafeStateError(RuntimeError):
    pass


def ensure_job_root(job_root: Path) -> None:
    job_root.mkdir(parents=True, exist_ok=True)
    if job_root.is_symlink() or not job_root.is_dir():
        raise SafeStateError(f"job root must be a regular directory: {job_root}")


@contextmanager
def open_state_directory(
    job_root: Path,
    name: str,
    *,
    create: bool = True,
) -> Generator[int, None, None]:
    if not name or Path(name).name != name:
        raise SafeStateError(f"invalid state directory name: {name}")
    root_flags = os.O_RDONLY | _directory_flag() | _nofollow_flag()
    try:
        root_fd = os.open(job_root, root_flags)
    except OSError as exc:
        raise SafeStateError(f"unsafe job root: {job_root}") from exc
    state_fd: int | None = None
    try:
        if create:
            with suppress(FileExistsError):
                os.mkdir(name, mode=0o700, dir_fd=root_fd)
        try:
            state_fd = os.open(name, root_flags, dir_fd=root_fd)
        except OSError as exc:
            raise SafeStateError(
                f"state directory must be a regular non-symlink directory: {name}"
            ) from exc
        if not stat.S_ISDIR(os.fstat(state_fd).st_mode):
            raise SafeStateError(f"state path is not a directory: {name}")
        yield state_fd
    finally:
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


def list_json_names(directory_fd: int) -> list[str]:
    return sorted(
        name
        for name in os.listdir(directory_fd)
        if name.endswith(".json")
    )


def read_regular_bytes(directory_fd: int, name: str) -> bytes:
    _validate_entry_name(name)
    flags = os.O_RDONLY | _nofollow_flag()
    try:
        file_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise SafeStateError(
            f"state entry must be a regular non-symlink file: {name}"
        ) from exc
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise SafeStateError(
                f"state entry must be a regular non-symlink file: {name}"
            )
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(file_fd)


def entry_exists(directory_fd: int, name: str) -> bool:
    _validate_entry_name(name)
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise SafeStateError(
            f"state entry must be a regular non-symlink file: {name}"
        )
    return True


def atomic_write_json(
    directory_fd: int,
    name: str,
    payload: dict[str, object],
    *,
    exclusive: bool = False,
) -> None:
    _validate_entry_name(name)
    temporary_name = f".{name}.{uuid.uuid4().hex}.tmp"
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _nofollow_flag()
    file_fd = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(file_fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(file_fd)
        if exclusive:
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=directory_fd)
        else:
            os.replace(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        os.fsync(directory_fd)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_fd)


def rename_entry(
    source_fd: int,
    source_name: str,
    target_fd: int,
    target_name: str,
) -> None:
    _validate_entry_name(source_name)
    _validate_entry_name(target_name)
    os.rename(
        source_name,
        target_name,
        src_dir_fd=source_fd,
        dst_dir_fd=target_fd,
    )
    os.fsync(source_fd)
    if target_fd != source_fd:
        os.fsync(target_fd)


def unlink_entry(directory_fd: int, name: str, *, missing_ok: bool = False) -> None:
    _validate_entry_name(name)
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        if not missing_ok:
            raise
    else:
        os.fsync(directory_fd)


def _validate_entry_name(name: str) -> None:
    if not name or Path(name).name != name:
        raise SafeStateError(f"invalid state entry name: {name}")


def _nofollow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _directory_flag() -> int:
    return getattr(os, "O_DIRECTORY", 0)
