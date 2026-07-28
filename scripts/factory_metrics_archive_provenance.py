from __future__ import annotations

import hashlib
import os
import re
import stat
from typing import cast

from scripts.factory_metrics_archive_errors import FactoryMetricsArchiveError
from scripts.factory_metrics_archive_io import (
    LedgerSpec,
    open_child_directory,
    open_descendant_directory,
)
from scripts.factory_metrics_modules.storage import (
    ACTIVE_METRICS_BYTE_LIMIT,
    ACTIVE_METRICS_DEPTH_LIMIT,
    ACTIVE_METRICS_ENTRY_LIMIT,
)
from scripts.factory_retention_fs import list_names

_DIGEST = re.compile(r"[0-9a-f]{64}")
type PreparedLedger = tuple[LedgerSpec, bytes]


def archive_manifest(ledgers: tuple[PreparedLedger, ...]) -> list[dict[str, object]]:
    return [
        {
            "path": "/".join(spec[0]),
            "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for spec, payload in sorted(ledgers, key=lambda item: item[0][0])
    ]


def verify_archive_manifest(archive_fd: int, value: object) -> None:
    expected = _parse_manifest(value)
    observed = set(archive_ledger_paths(archive_fd))
    if observed != set(expected):
        raise FactoryMetricsArchiveError(
            "terminal factory metrics archive has a different ledger set"
        )
    for parts, (expected_size, expected_digest) in expected.items():
        _verify_ledger(archive_fd, parts, expected_size, expected_digest)


def archive_ledger_paths(archive_fd: int) -> tuple[tuple[str, ...], ...]:
    paths: list[tuple[str, ...]] = []
    _archive_directory(archive_fd, prefix=(), depth=0, seen=[0], paths=paths)
    return tuple(paths)


def _parse_manifest(value: object) -> dict[tuple[str, ...], tuple[int, str]]:
    if not isinstance(value, list):
        raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
    items = cast(list[object], value)
    if len(items) > ACTIVE_METRICS_ENTRY_LIMIT:
        raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
    parsed: dict[tuple[str, ...], tuple[int, str]] = {}
    total = 0
    for raw in items:
        if not isinstance(raw, dict):
            raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
        item = cast(dict[str, object], raw)
        if set(item) != {"path", "byte_size", "sha256"}:
            raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
        parts = _manifest_path(item.get("path"))
        size = item.get("byte_size")
        digest = item.get("sha256")
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or size > ACTIVE_METRICS_BYTE_LIMIT
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            or parts in parsed
        ):
            raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
        total += size
        if total > ACTIVE_METRICS_BYTE_LIMIT:
            raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
        parsed[parts] = (size, digest)
    return parsed


def _manifest_path(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
    parts = tuple(value.split("/"))
    if (
        not parts
        or "/".join(parts) != value
        or len(parts) - 1 > ACTIVE_METRICS_DEPTH_LIMIT
        or not parts[-1].endswith(".jsonl")
        or any(
            not part
            or part in {".", ".."}
            or any(ord(character) < 32 or ord(character) == 127 for character in part)
            for part in parts
        )
    ):
        raise FactoryMetricsArchiveError("factory metrics archive manifest is invalid")
    return parts


def _verify_ledger(
    archive_fd: int,
    parts: tuple[str, ...],
    expected_size: int,
    expected_digest: str,
) -> None:
    try:
        with open_descendant_directory(archive_fd, parts[:-1], create=False) as parent_fd:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(parts[-1], flags, dir_fd=parent_fd)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
                    raise FactoryMetricsArchiveError(
                        "terminal factory metrics archive content drifted"
                    )
                digest = hashlib.sha256()
                remaining = expected_size
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        raise FactoryMetricsArchiveError(
                            "terminal factory metrics archive content drifted"
                        )
                    digest.update(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1) or digest.hexdigest() != expected_digest:
                    raise FactoryMetricsArchiveError(
                        "terminal factory metrics archive content drifted"
                    )
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise FactoryMetricsArchiveError(
            "terminal factory metrics archive content drifted"
        ) from exc


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
