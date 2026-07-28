from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_retention_fs import (
    FsSnapshot,
    RetentionFsError,
    SnapshotBudget,
    entry_snapshot,
    list_names,
    open_relative_directory,
    path_exists,
    read_bounded_regular,
)
from scripts.factory_retention_inventory_metadata import (
    InventoryEntry,
    artifact_references,
    json_object,
    optional_text,
    payload_timestamp,
    required_text,
)
from scripts.factory_retention_models import ArtifactCandidate
from scripts.factory_retention_types import CANDIDATE_SCHEMA_VERSION


def inventory_reviews(
    repo_root: Path,
    review_bundles: dict[str, str],
    snapshot_budget: SnapshotBudget,
) -> tuple[list[InventoryEntry], list[str]]:
    parts = (".entroping", "ai-reviews")
    if not path_exists(repo_root, parts):
        return [], []
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    try:
        with open_relative_directory(repo_root, parts) as root_fd:
            for name in list_names(root_fd):
                entry, error = _review_entry(
                    repo_root,
                    root_fd,
                    name,
                    review_bundles.get(name),
                    snapshot_budget,
                )
                if entry is not None:
                    entries.append(entry)
                if error is not None:
                    errors.append(error)
    except (OSError, RetentionFsError) as exc:
        errors.append(f"unsafe review artifact root: {type(exc).__name__}")
    return entries, errors


def _review_entry(
    repo_root: Path,
    root_fd: int,
    name: str,
    bundle_id: str | None,
    snapshot_budget: SnapshotBudget,
) -> tuple[InventoryEntry | None, str | None]:
    relative_path = f".entroping/ai-reviews/{name}"
    snapshot: FsSnapshot | None = None
    try:
        snapshot = entry_snapshot(root_fd, name, budget=snapshot_budget)
        if snapshot.kind != "directory":
            raise RetentionFsError("review artifact must be a directory")
        with open_relative_directory(
            repo_root,
            (".entroping", "ai-reviews", name),
        ) as review_fd:
            payload = json_object(read_bounded_regular(review_fd, "metadata.json"))
        state = required_text(payload, "status")
        inbox_status = optional_text(payload.get("codex_inbox_status"))
        references = artifact_references(payload)
        linked = bundle_id is not None and bool(bundle_id)
        effective_bundle = bundle_id or f"orphan:{name}"
        candidate = ArtifactCandidate(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            artifact_id=f"review:{name}",
            bundle_id=effective_bundle,
            artifact_class="ai_review",
            relative_path=relative_path,
            byte_size=snapshot.byte_size,
            created_at=payload_timestamp(payload, snapshot.mtime_ns),
            state=state,
            inbox_status=inbox_status,
            references=references,
            metadata_valid=linked,
        )
        error = None if linked else f"unmanaged review artifact: {relative_path}"
        return InventoryEntry(candidate=candidate, snapshot=snapshot), error
    except (OSError, UnicodeDecodeError, ValueError, ValidationError, RetentionFsError) as exc:
        fallback = _fallback_review(
            root_fd,
            name,
            relative_path,
            bundle_id,
            snapshot_budget,
            snapshot,
        )
        return fallback, f"invalid review artifact {relative_path}: {type(exc).__name__}"


def _fallback_review(
    root_fd: int,
    name: str,
    relative_path: str,
    bundle_id: str | None,
    snapshot_budget: SnapshotBudget,
    snapshot: FsSnapshot | None,
) -> InventoryEntry | None:
    try:
        actual_snapshot = snapshot or entry_snapshot(
            root_fd,
            name,
            budget=snapshot_budget,
        )
        candidate = ArtifactCandidate(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            artifact_id=f"invalid-review:{name}",
            bundle_id=bundle_id or f"invalid-review:{name}",
            artifact_class="ai_review",
            relative_path=relative_path,
            byte_size=actual_snapshot.byte_size,
            created_at=datetime.fromtimestamp(
                actual_snapshot.mtime_ns / 1_000_000_000,
                UTC,
            ),
            state="unknown",
            metadata_valid=False,
        )
        return InventoryEntry(candidate=candidate, snapshot=actual_snapshot)
    except (OSError, ValueError, ValidationError, RetentionFsError):
        return None
