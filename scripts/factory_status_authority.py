from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from pydantic import ValidationError

from scripts.ai_worker_file_safety import secret_like_content_reason
from scripts.factory_cost_policy_io import (
    POLICY_MAX_BYTES,
    _reject_secret_like_json,
    _verify_unambiguous_json,
)
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_retention_fs import RetentionFsError, open_relative_directory
from scripts.factory_retention_models import RetentionPolicy
from scripts.provider_capability_io import (
    REGISTRY_MAX_BYTES,
    _parse_unambiguous_json,
    _validate_json_depth,
)
from scripts.provider_capability_types import ProviderCapabilityRegistry, ProviderRegistryError

from .factory_status_errors import FactoryStatusError

type Fingerprints = list[tuple[str, int, int, int]]


def load_cost_policy(
    root: Path, path: Path, fingerprints: Fingerprints
) -> FactoryCostPolicy:
    """Parse cost policy bytes from one no-follow descriptor snapshot."""

    document = _policy_document(_read_authority(root, path, POLICY_MAX_BYTES, fingerprints))
    return FactoryCostPolicy.model_validate_json(document, strict=True)


def load_retention_policy(
    root: Path, path: Path, fingerprints: Fingerprints
) -> RetentionPolicy:
    """Parse retention policy bytes from one no-follow descriptor snapshot."""

    document = _policy_document(_read_authority(root, path, POLICY_MAX_BYTES, fingerprints))
    return RetentionPolicy.model_validate_json(document, strict=True)


def load_registry(
    root: Path, path: Path, fingerprints: Fingerprints
) -> ProviderCapabilityRegistry:
    """Parse registry bytes from one no-follow descriptor snapshot."""

    raw = _read_authority(root, path, REGISTRY_MAX_BYTES, fingerprints)
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderRegistryError(
            "registry_file", "provider registry must be valid UTF-8"
        ) from exc
    parsed = _parse_unambiguous_json(document)
    _validate_json_depth(parsed)
    normalized = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if secret_like_content_reason(normalized) is not None:
        raise ProviderRegistryError(
            "registry_secret", "provider registry contains secret-like content"
        )
    return ProviderCapabilityRegistry.model_validate_json(document)


def _policy_document(raw: bytes) -> str:
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FactoryStatusError("policy authority is not UTF-8") from exc
    parsed = _verify_unambiguous_json(document)
    _reject_secret_like_json(parsed)
    return document


def _read_authority(
    root: Path,
    path: Path,
    max_bytes: int,
    fingerprints: Fingerprints,
) -> bytes:
    descriptor: int | None = None
    try:
        relative = path.relative_to(root)
        with open_relative_directory(root, relative.parts[:-1]) as parent:
            descriptor = os.open(
                relative.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent,
            )
            before = os.fstat(descriptor)
            _validate_regular(before, max_bytes)
            payload = _pread_exact(descriptor, before.st_size)
            after = os.fstat(descriptor)
            if _identity(before) != _identity(after) or before.st_size != after.st_size:
                raise FactoryStatusError("authority changed during read")
            fingerprints.append(
                (relative.as_posix(), after.st_ino, after.st_size, after.st_mtime_ns)
            )
            return payload
    except (OSError, RetentionFsError, ValidationError) as exc:
        raise FactoryStatusError("authority could not be read safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _pread_exact(descriptor: int, expected_size: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < expected_size:
        chunk = os.pread(descriptor, min(65_536, expected_size - offset), offset)
        if not chunk:
            raise FactoryStatusError("authority changed during read")
        chunks.append(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, expected_size):
        raise FactoryStatusError("authority changed during read")
    return b"".join(chunks)


def _validate_regular(metadata: os.stat_result, max_bytes: int) -> None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise FactoryStatusError("authority is not a private regular file")
    if metadata.st_size > max_bytes:
        raise FactoryStatusError("authority exceeds its read bound")


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_mtime_ns,
    )
