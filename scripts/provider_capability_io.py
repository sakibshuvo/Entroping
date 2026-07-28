from __future__ import annotations

import errno
import json
import math
import os
import stat
from pathlib import Path
from typing import Final, NoReturn, cast

from pydantic import ValidationError

from .ai_worker_file_safety import secret_like_content_reason
from .provider_capability_types import (
    ProviderCapabilityRegistry,
    ProviderRegistryError,
)

DEFAULT_REGISTRY_PATH: Final = (
    Path(__file__).resolve().parents[1] / "docs" / "meta" / "provider-capability-registry.json"
)
REGISTRY_MAX_BYTES: Final = 256 * 1024
REGISTRY_MAX_JSON_DEPTH: Final = 64
SIGNED_64_BIT_MAX_DIGITS: Final = 19
_HAS_SAFE_TREE_OPEN: Final = (
    hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
)


def load_provider_registry(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> ProviderCapabilityRegistry:
    raw_document, read_error = _read_local_registry_bytes(
        path,
        max_bytes=REGISTRY_MAX_BYTES,
    )
    if raw_document is None:
        raise ProviderRegistryError(
            code="registry_file",
            detail=f"could not safely read provider registry ({read_error})",
        )
    try:
        document = raw_document.decode("utf-8")
    except UnicodeDecodeError:
        raise ProviderRegistryError(
            code="registry_file",
            detail="provider registry must be valid UTF-8",
        ) from None
    parsed_document = _parse_unambiguous_json(document)
    _validate_json_depth(parsed_document)
    decoded_document = json.dumps(
        parsed_document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    secret_reason = secret_like_content_reason(decoded_document)
    if secret_reason is not None:
        raise ProviderRegistryError(
            code="registry_secret",
            detail=f"provider registry contains secret-like content ({secret_reason})",
        )
    try:
        return ProviderCapabilityRegistry.model_validate_json(document)
    except ValidationError as exc:
        raise ProviderRegistryError(
            code="registry_schema",
            detail=_validation_error_detail(exc),
        ) from None


def _parse_unambiguous_json(document: str) -> object:
    try:
        return cast(
            object,
            json.loads(
                document,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_non_finite,
                parse_float=_parse_finite_float,
                parse_int=_parse_bounded_int,
            ),
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else "nesting is too deep"
        raise ProviderRegistryError(
            code="registry_json",
            detail=f"invalid JSON: {detail}",
        ) from None


def _validate_json_depth(document: object) -> None:
    pending = [(document, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > REGISTRY_MAX_JSON_DEPTH:
            raise ProviderRegistryError(
                code="registry_json",
                detail=f"JSON nesting exceeds {REGISTRY_MAX_JSON_DEPTH} levels",
            )
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderRegistryError(
                code="registry_json",
                detail="duplicate JSON key is forbidden",
            )
        result[key] = value
    return result


def _parse_bounded_int(raw: str) -> int:
    if len(raw.removeprefix("-")) > SIGNED_64_BIT_MAX_DIGITS:
        raise ProviderRegistryError(
            code="registry_json",
            detail="JSON integer exceeds the signed 64-bit boundary",
        )
    value = int(raw)
    if not -(2**63) <= value <= (2**63) - 1:
        raise ProviderRegistryError(
            code="registry_json",
            detail="JSON integer exceeds the signed 64-bit boundary",
        )
    return value


def _parse_finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        _reject_non_finite(raw)
    return value


def _reject_non_finite(raw: str) -> NoReturn:
    raise ProviderRegistryError(
        code="registry_json",
        detail=f"non-finite JSON number is forbidden: {raw}",
    )


def _validation_error_detail(exc: ValidationError) -> str:
    error = exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )[0]
    location = ".".join(str(part) for part in error.get("loc", ()))
    prefix = f"{location}: " if location else ""
    return f"{prefix}{error['msg']}"


def _read_local_registry_bytes(
    path: Path,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    if _HAS_SAFE_TREE_OPEN:
        return _read_local_registry_bytes_no_follow(path, max_bytes=max_bytes)
    return _read_local_registry_bytes_best_effort(path, max_bytes=max_bytes)


def _read_local_registry_bytes_no_follow(
    path: Path,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
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
        return _read_bounded_registry_bytes(file_descriptor, max_bytes=max_bytes)
    except OSError as exc:
        return None, _registry_read_error_summary(exc)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for directory_descriptor in reversed(directory_descriptors):
            os.close(directory_descriptor)


def _read_local_registry_bytes_best_effort(
    path: Path,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        path_stat = path.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(path_stat.st_mode) or not stat.S_ISREG(descriptor_stat.st_mode):
            return None, "not a file"
        if (path_stat.st_dev, path_stat.st_ino) != (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ):
            return None, "unreadable"
        return _read_bounded_registry_bytes(file_descriptor, max_bytes=max_bytes)
    except OSError as exc:
        return None, _registry_read_error_summary(exc)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _read_bounded_registry_bytes(
    file_descriptor: int,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    descriptor_stat = os.fstat(file_descriptor)
    if not stat.S_ISREG(descriptor_stat.st_mode):
        return None, "not a file"
    if descriptor_stat.st_size > max_bytes:
        return None, f"artifact exceeds {max_bytes} bytes"
    chunks: list[bytes] = []
    bytes_read = 0
    while bytes_read <= max_bytes:
        chunk = os.read(file_descriptor, min(65_536, max_bytes + 1 - bytes_read))
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)
    if bytes_read > max_bytes:
        return None, f"artifact exceeds {max_bytes} bytes"
    return b"".join(chunks), ""


def _registry_read_error_summary(exc: OSError) -> str:
    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        return "symlinked path component"
    if exc.errno == errno.EISDIR:
        return "not a file"
    return "unreadable"
