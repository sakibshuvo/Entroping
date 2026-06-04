"""Pure OpenAPI operation-change detection.

This module compares OpenAPI operation metadata only. It does not read files,
call Git, invoke Hurl, call providers, or write generated tests.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from entroping.bridge.openapi_to_hurl import OpenApiCompilationError

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
OpenApiOperationChangeType = Literal["added", "modified", "renamed", "removed"]


@dataclass(frozen=True)
class OpenApiOperationChange:
    """One changed OpenAPI operation relative to a baseline document."""

    change_type: OpenApiOperationChangeType
    operation_id: str
    method: str
    path: str
    previous_operation_id: str | None = None


@dataclass(frozen=True)
class OpenApiOperationChanges:
    """Deterministic OpenAPI operation-change result."""

    items: tuple[OpenApiOperationChange, ...]
    unchanged: int

    @property
    def generation_operation_ids(self) -> tuple[str, ...]:
        """Return current operation IDs that should be regenerated."""

        return tuple(
            item.operation_id
            for item in self.items
            if item.change_type in {"added", "modified", "renamed"}
        )

    @property
    def summary(self) -> dict[str, int]:
        """Return human-readable change counts."""

        return {
            "added": sum(1 for item in self.items if item.change_type == "added"),
            "modified": sum(1 for item in self.items if item.change_type == "modified"),
            "renamed": sum(1 for item in self.items if item.change_type == "renamed"),
            "removed": sum(1 for item in self.items if item.change_type == "removed"),
            "unchanged": self.unchanged,
        }


@dataclass(frozen=True)
class _OperationSnapshot:
    operation_id: str
    method: str
    path: str
    endpoint_key: tuple[str, str]
    fingerprint: str


def detect_openapi_operation_changes(
    base_document: Mapping[str, object],
    current_document: Mapping[str, object],
) -> OpenApiOperationChanges:
    """Compare OpenAPI documents and classify operation-level changes."""

    base_operations = _operation_snapshots(base_document, document_name="baseline")
    current_operations = _operation_snapshots(current_document, document_name="current")
    base_by_id = _operations_by_id(base_operations, document_name="baseline")
    current_by_id = _operations_by_id(current_operations, document_name="current")
    base_by_endpoint = {operation.endpoint_key: operation for operation in base_operations}

    changes: list[OpenApiOperationChange] = []
    unchanged = 0
    renamed_base_ids: set[str] = set()
    for current in current_operations:
        base_by_same_id = base_by_id.get(current.operation_id)
        if base_by_same_id is None:
            previous = base_by_endpoint.get(current.endpoint_key)
            if previous is not None and previous.operation_id not in current_by_id:
                renamed_base_ids.add(previous.operation_id)
                changes.append(
                    OpenApiOperationChange(
                        change_type="renamed",
                        operation_id=current.operation_id,
                        method=current.method,
                        path=current.path,
                        previous_operation_id=previous.operation_id,
                    )
                )
            else:
                changes.append(
                    OpenApiOperationChange(
                        change_type="added",
                        operation_id=current.operation_id,
                        method=current.method,
                        path=current.path,
                    )
                )
            continue
        if current.fingerprint == base_by_same_id.fingerprint:
            unchanged += 1
            continue
        changes.append(
            OpenApiOperationChange(
                change_type="modified",
                operation_id=current.operation_id,
                method=current.method,
                path=current.path,
            )
        )

    for base in base_operations:
        if base.operation_id in current_by_id or base.operation_id in renamed_base_ids:
            continue
        changes.append(
            OpenApiOperationChange(
                change_type="removed",
                operation_id=base.operation_id,
                method=base.method,
                path=base.path,
            )
        )

    return OpenApiOperationChanges(items=tuple(changes), unchanged=unchanged)


def _operation_snapshots(
    document: Mapping[str, object],
    *,
    document_name: str,
) -> tuple[_OperationSnapshot, ...]:
    paths = _mapping_field(
        document,
        "paths",
        f"OpenAPI {document_name} document must contain a paths mapping",
    )
    snapshots: list[_OperationSnapshot] = []
    for raw_path, path_item_value in paths.items():
        if not isinstance(raw_path, str) or not raw_path.startswith("/") or _has_control(raw_path):
            msg = f"OpenAPI path keys must be absolute path strings, got {raw_path!r}"
            raise OpenApiCompilationError(msg)
        path_item = _ensure_mapping(path_item_value, f"OpenAPI path {raw_path!r}")
        path_context = {
            key: value
            for key, value in path_item.items()
            if not (isinstance(key, str) and key.lower() in _HTTP_METHODS)
        }
        for raw_method, operation_value in path_item.items():
            method = raw_method.lower() if isinstance(raw_method, str) else ""
            if method not in _HTTP_METHODS:
                continue
            operation = _ensure_mapping(
                operation_value,
                f"OpenAPI operation {raw_method!r} {raw_path}",
            )
            operation_id = _operation_id(operation, method=method, path=raw_path)
            method_upper = method.upper()
            snapshots.append(
                _OperationSnapshot(
                    operation_id=operation_id,
                    method=method_upper,
                    path=raw_path,
                    endpoint_key=(method_upper, raw_path),
                    fingerprint=_operation_fingerprint(
                        method=method_upper,
                        path=raw_path,
                        path_context=path_context,
                        operation=operation,
                    ),
                )
            )
    return tuple(snapshots)


def _operations_by_id(
    operations: Sequence[_OperationSnapshot],
    *,
    document_name: str,
) -> dict[str, _OperationSnapshot]:
    by_id: dict[str, _OperationSnapshot] = {}
    for operation in operations:
        if operation.operation_id in by_id:
            msg = (
                f"OpenAPI operationId must be unique in {document_name} document: "
                f"{operation.operation_id!r}"
            )
            raise OpenApiCompilationError(msg)
        by_id[operation.operation_id] = operation
    return by_id


def _operation_fingerprint(
    *,
    method: str,
    path: str,
    path_context: Mapping[str, object],
    operation: Mapping[str, object],
) -> str:
    normalized_operation = {
        key: value for key, value in operation.items() if key != "operationId"
    }
    payload = {
        "method": method,
        "path": path,
        "path_context": _ensure_json_value(path_context, context=f"{method} {path} path item"),
        "operation": _ensure_json_value(normalized_operation, context=f"{method} {path} operation"),
    }
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _operation_id(operation: Mapping[str, object], *, method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        stripped = operation_id.strip()
        if _has_control(stripped):
            msg = f"OpenAPI operationId is not safe for change detection: {operation_id!r}"
            raise OpenApiCompilationError(msg)
        return stripped
    path_slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method}_{path_slug or 'root'}"


def _mapping_field(
    mapping: Mapping[str, object],
    key: str,
    error: str,
) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise OpenApiCompilationError(error)
    return _ensure_string_keys(value, context=key)


def _ensure_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{context} must be a mapping"
        raise OpenApiCompilationError(msg)
    return _ensure_string_keys(value, context=context)


def _ensure_string_keys(value: Mapping[object, object], *, context: str) -> Mapping[str, object]:
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            msg = f"{context} keys must be strings"
            raise OpenApiCompilationError(msg)
        normalized[key] = item
    return normalized


def _ensure_json_value(value: object, *, context: str) -> object:
    if value is None or isinstance(value, str | bool | int):
        if isinstance(value, str) and _has_control(value):
            msg = f"{context} contains control characters"
            raise OpenApiCompilationError(msg)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            msg = f"{context} must be finite"
            raise OpenApiCompilationError(msg)
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_ensure_json_value(item, context=context) for item in value]
    if isinstance(value, Mapping):
        normalized = _ensure_string_keys(value, context=context)
        return {
            key: _ensure_json_value(item, context=f"{context}.{key}")
            for key, item in normalized.items()
        }
    msg = f"{context} must be JSON-compatible"
    raise OpenApiCompilationError(msg)


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
