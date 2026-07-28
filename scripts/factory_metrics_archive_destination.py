from __future__ import annotations

import fcntl
import os
import stat
import uuid
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from scripts import ai_job_fs
from scripts.factory_metrics_archive_errors import FactoryMetricsArchiveError
from scripts.factory_metrics_archive_io import (
    FactoryMetricsArchiveIoError,
    LedgerSpec,
    open_child_directory,
    open_descendant_directory,
    open_directory,
    open_or_create_child_directory,
)
from scripts.factory_metrics_archive_metadata import read_archive_metadata
from scripts.factory_metrics_modules.storage import (
    ACTIVE_METRICS_DEPTH_LIMIT,
    ACTIVE_METRICS_ENTRY_LIMIT,
)
from scripts.factory_retention_fs import (
    RetentionFsError,
    list_names,
    read_bounded_regular,
)

_LOCK_NAME = "retention.lock"


def copy_archive(
    *,
    repo_root: Path,
    issue: int,
    payload: dict[str, object],
    ledgers: tuple[tuple[LedgerSpec, bytes], ...],
) -> None:
    try:
        with (
            _open_entroping_with_lock(repo_root) as entroping_fd,
            open_descendant_directory(
                entroping_fd,
                ("factory-metrics", "finished-issues", f"issue-{issue}"),
                create=True,
            ) as archive_fd,
        ):
            existing = read_archive_metadata(archive_fd)
            expected_paths = {spec[0] for spec, _ in ledgers}
            observed_paths = set(_archive_ledger_paths(archive_fd))
            if existing is not None:
                if existing != payload:
                    raise FactoryMetricsArchiveError(
                        "factory metrics archive metadata already exists with different provenance"
                    )
                if observed_paths != expected_paths:
                    raise FactoryMetricsArchiveError(
                        "terminal factory metrics archive has a different ledger set"
                    )
                _verify_terminal_archive(archive_fd, ledgers)
                return
            if not observed_paths.issubset(expected_paths):
                raise FactoryMetricsArchiveError(
                    "factory metrics archive contains an unexpected ledger"
                )
            for spec, data in ledgers:
                with open_descendant_directory(
                    archive_fd,
                    spec[0][:-1],
                    create=True,
                ) as parent_fd:
                    _atomic_replace_regular(parent_fd, spec[0][-1], data)
            ai_job_fs.atomic_write_json(
                archive_fd,
                "metadata.json",
                payload,
                exclusive=True,
            )
    except (OSError, RetentionFsError, FactoryMetricsArchiveIoError) as exc:
        raise FactoryMetricsArchiveError("factory metrics archive path is unsafe") from exc


def verify_empty_source_archive(
    repo_root: Path,
    issue: int,
    payload: dict[str, object],
) -> None:
    try:
        with (
            _open_entroping_with_lock(repo_root) as entroping_fd,
            open_descendant_directory(
                entroping_fd,
                ("factory-metrics", "finished-issues", f"issue-{issue}"),
                create=False,
            ) as archive_fd,
        ):
            existing = read_archive_metadata(archive_fd)
            observed = _archive_ledger_paths(archive_fd)
            if existing is None:
                if observed:
                    raise FactoryMetricsArchiveError(
                        "factory metrics archive contains an unexpected ledger"
                    )
                return
            if existing != payload:
                raise FactoryMetricsArchiveError(
                    "factory metrics archive metadata already exists with different provenance"
                )
            if observed:
                raise FactoryMetricsArchiveError(
                    "terminal factory metrics archive has a different ledger set"
                )
    except FileNotFoundError:
        return
    except (OSError, RetentionFsError, FactoryMetricsArchiveIoError) as exc:
        raise FactoryMetricsArchiveError("factory metrics archive path is unsafe") from exc


def _verify_terminal_archive(
    archive_fd: int,
    ledgers: tuple[tuple[LedgerSpec, bytes], ...],
) -> None:
    for spec, source in ledgers:
        try:
            with open_descendant_directory(
                archive_fd,
                spec[0][:-1],
                create=False,
            ) as parent_fd:
                archived = read_bounded_regular(
                    parent_fd,
                    spec[0][-1],
                    limit=spec[1],
                )
        except (OSError, RetentionFsError, FactoryMetricsArchiveIoError) as exc:
            raise FactoryMetricsArchiveError(
                "terminal factory metrics archive is incomplete"
            ) from exc
        if archived != source:
            raise FactoryMetricsArchiveError(
                "terminal factory metrics archive differs from source ledgers"
            )


def _archive_ledger_paths(archive_fd: int) -> tuple[tuple[str, ...], ...]:
    paths: list[tuple[str, ...]] = []
    _archive_directory(archive_fd, prefix=(), depth=0, seen=[0], paths=paths)
    return tuple(paths)


def _archive_directory(
    directory_fd: int,
    *,
    prefix: tuple[str, ...],
    depth: int,
    seen: list[int],
    paths: list[tuple[str, ...]],
) -> None:
    if depth > ACTIVE_METRICS_DEPTH_LIMIT:
        raise FactoryMetricsArchiveError(
            "factory metrics archive exceeds the directory depth limit"
        )
    for name in list_names(directory_fd):
        if not prefix and name == "metadata.json":
            continue
        seen[0] += 1
        if seen[0] > ACTIVE_METRICS_ENTRY_LIMIT:
            raise FactoryMetricsArchiveError("factory metrics archive exceeds the entry limit")
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        parts = (*prefix, name)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = open_child_directory(directory_fd, name)
            try:
                _archive_directory(
                    child_fd,
                    prefix=parts,
                    depth=depth + 1,
                    seen=seen,
                    paths=paths,
                )
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(metadata.st_mode) and name.endswith(".jsonl"):
            paths.append(parts)
        else:
            raise FactoryMetricsArchiveError("factory metrics archive contains an unexpected entry")


@contextmanager
def _open_entroping_with_lock(repo_root: Path) -> Generator[int, None, None]:
    root_fd = open_directory(repo_root)
    entroping_fd = -1
    lock_fd = -1
    try:
        entroping_fd = open_or_create_child_directory(root_fd, ".entroping")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(_LOCK_NAME, flags, 0o600, dir_fd=entroping_fd)
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise FactoryMetricsArchiveError("retention lock must be a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except (OSError, FactoryMetricsArchiveError) as exc:
        if lock_fd >= 0:
            os.close(lock_fd)
        if entroping_fd >= 0:
            os.close(entroping_fd)
        os.close(root_fd)
        if isinstance(exc, FactoryMetricsArchiveError):
            raise
        raise FactoryMetricsArchiveError("factory metrics archive path is unsafe") from exc
    try:
        yield entroping_fd
    finally:
        os.close(lock_fd)
        os.close(entroping_fd)
        os.close(root_fd)


def _atomic_replace_regular(directory_fd: int, name: str, payload: bytes) -> None:
    try:
        existing = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise FactoryMetricsArchiveError("factory metrics archive target must be a regular file")
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise FactoryMetricsArchiveError("factory metrics archive write failed")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)
