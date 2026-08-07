from __future__ import annotations

import json
import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path

from scripts.factory_issue_selector_json import JsonBoundaryError, decode_json
from scripts.factory_issue_selector_models import GitHubSnapshot
from scripts.factory_issue_selector_snapshot import (
    SnapshotCodecError,
    decode_snapshot,
    encode_snapshot,
)
from scripts.factory_retention_fs import (
    RetentionFsError,
    open_relative_directory,
    read_bounded_regular,
)

CACHE_RELATIVE_PATH = Path(".entroping/factory-selector/github-snapshot.v1.json")
_CACHE_PARTS = (".entroping", "factory-selector")
_CACHE_NAME = "github-snapshot.v1.json"
_MAX_CACHE_BYTES = 1_048_576
_OWNER_ONLY_MODE = 0o600


class CacheError(ValueError):
    pass


def write_snapshot(repo_root: Path, snapshot: GitHubSnapshot) -> None:
    try:
        payload = encode_snapshot(snapshot)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    except (SnapshotCodecError, TypeError, ValueError) as exc:
        raise CacheError(str(exc)) from exc
    if len(encoded) > _MAX_CACHE_BYTES:
        raise CacheError("cache exceeds bounded size")
    try:
        with open_relative_directory(repo_root, _CACHE_PARTS, create=True) as directory_fd:
            _validate_existing(directory_fd, required=False)
            _validate_managed_directories(repo_root, directory_fd)
            _atomic_write_cache(directory_fd, encoded)
            metadata = os.stat(_CACHE_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_IMODE(metadata.st_mode) != _OWNER_ONLY_MODE:
                raise CacheError("cache file must be owner-only")
    except (OSError, RetentionFsError) as exc:
        raise CacheError("cache path must be a regular non-symlink path") from exc


def read_snapshot(repo_root: Path, *, expected_repo: str) -> GitHubSnapshot:
    try:
        with open_relative_directory(repo_root, _CACHE_PARTS) as directory_fd:
            _validate_existing(directory_fd, required=True)
            _validate_managed_directories(repo_root, directory_fd)
            raw = read_bounded_regular(directory_fd, _CACHE_NAME, limit=_MAX_CACHE_BYTES)
    except FileNotFoundError as exc:
        raise CacheError("cache missing") from exc
    except (OSError, RetentionFsError) as exc:
        raise CacheError("cache path must be a regular non-symlink path") from exc
    try:
        payload = decode_json(raw)
    except JsonBoundaryError as exc:
        raise CacheError("cache contains invalid JSON") from exc
    try:
        return decode_snapshot(payload, expected_repo=expected_repo)
    except SnapshotCodecError as exc:
        raise CacheError(str(exc)) from exc


def _validate_existing(directory_fd: int, *, required: bool) -> None:
    try:
        metadata = os.stat(_CACHE_NAME, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        if required:
            raise
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise CacheError("cache entry must be regular and non-symlink")
    if stat.S_IMODE(metadata.st_mode) != _OWNER_ONLY_MODE:
        raise CacheError("cache file must be owner-only")
    if metadata.st_size > _MAX_CACHE_BYTES:
        raise CacheError("cache exceeds bounded size")


def _validate_managed_directories(repo_root: Path, directory_fd: int) -> None:
    try:
        with open_relative_directory(repo_root, (".entroping",)) as parent_fd:
            parent = os.fstat(parent_fd)
        managed = os.fstat(directory_fd)
    except (OSError, RetentionFsError) as exc:
        raise CacheError("managed directory permissions are invalid") from exc
    owner = os.geteuid()
    parent_unsafe = parent.st_uid != owner or stat.S_IMODE(parent.st_mode) & 0o022
    managed_unsafe = (
        managed.st_uid != owner or stat.S_IMODE(managed.st_mode) != 0o700
    )
    if parent_unsafe or managed_unsafe:
        raise CacheError("managed directory permissions are invalid")


def _atomic_write_cache(directory_fd: int, encoded: bytes) -> None:
    temporary = f".{_CACHE_NAME}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    file_fd = os.open(temporary, flags, _OWNER_ONLY_MODE, dir_fd=directory_fd)
    try:
        with os.fdopen(file_fd, "wb", closefd=False) as stream:
            _ = stream.write(encoded)
            stream.flush()
            os.fsync(file_fd)
        os.replace(
            temporary,
            _CACHE_NAME,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        os.close(file_fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)
