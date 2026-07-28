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
    json_object,
    optional_text,
    payload_timestamp,
    required_text,
    review_name,
    settlement_state,
)
from scripts.factory_retention_models import ArtifactCandidate
from scripts.factory_retention_types import CANDIDATE_SCHEMA_VERSION


def inventory_jobs(
    repo_root: Path,
    state: str,
    snapshot_budget: SnapshotBudget,
) -> tuple[list[InventoryEntry], list[str], list[tuple[str, str]]]:
    parts = (".entroping", "ai-jobs", state)
    if not path_exists(repo_root, parts):
        return [], [], []
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    references: list[tuple[str, str]] = []
    try:
        with open_relative_directory(repo_root, parts) as directory_fd:
            for name in list_names(directory_fd):
                if not name.endswith(".json"):
                    continue
                entry, error, linked_review = _job_entry(
                    repo_root,
                    directory_fd,
                    state,
                    name,
                    snapshot_budget,
                )
                if entry is not None:
                    entries.append(entry)
                if error is not None:
                    errors.append(error)
                if linked_review is not None and entry is not None:
                    references.append((linked_review, entry.candidate.bundle_id))
    except (OSError, RetentionFsError) as exc:
        errors.append(f"unsafe terminal job root {state}: {type(exc).__name__}")
    return entries, errors, references


def _job_entry(
    repo_root: Path,
    directory_fd: int,
    state: str,
    name: str,
    snapshot_budget: SnapshotBudget,
) -> tuple[InventoryEntry | None, str | None, str | None]:
    relative_path = f".entroping/ai-jobs/{state}/{name}"
    snapshot: FsSnapshot | None = None
    try:
        snapshot = entry_snapshot(directory_fd, name, budget=snapshot_budget)
        payload = json_object(read_bounded_regular(directory_fd, name))
        job_id = required_text(payload, "job_id")
        if payload.get("schema_version") != "entroping.ai-job.v1":
            raise ValueError("unsupported job schema")
        if payload.get("queue_status") != state:
            raise ValueError("terminal job state does not match its directory")
        linked_review = review_name(payload.get("artifact_dir"), repo_root)
        candidate = ArtifactCandidate(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            artifact_id=f"job:{state}:{job_id}",
            bundle_id=f"job:{job_id}",
            artifact_class="ai_job",
            relative_path=relative_path,
            byte_size=snapshot.byte_size,
            created_at=payload_timestamp(payload, snapshot.mtime_ns),
            state=state,
            reservation_id=optional_text(payload.get("reservation_id")),
            settlement_state=settlement_state(payload.get("settlement_state")),
        )
        return InventoryEntry(candidate=candidate, snapshot=snapshot), None, linked_review
    except (OSError, UnicodeDecodeError, ValueError, ValidationError, RetentionFsError) as exc:
        fallback = _fallback_candidate(
            directory_fd,
            state,
            name,
            relative_path,
            snapshot_budget,
            snapshot,
        )
        return fallback, f"invalid terminal job {relative_path}: {type(exc).__name__}", None


def _fallback_candidate(
    directory_fd: int,
    state: str,
    name: str,
    relative_path: str,
    snapshot_budget: SnapshotBudget,
    snapshot: FsSnapshot | None,
) -> InventoryEntry | None:
    try:
        actual_snapshot = snapshot or entry_snapshot(
            directory_fd,
            name,
            budget=snapshot_budget,
        )
        candidate = ArtifactCandidate(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            artifact_id=f"invalid-job:{state}:{name}",
            bundle_id=f"invalid-job:{state}:{name}",
            artifact_class="ai_job",
            relative_path=relative_path,
            byte_size=actual_snapshot.byte_size,
            created_at=datetime.fromtimestamp(
                actual_snapshot.mtime_ns / 1_000_000_000,
                UTC,
            ),
            state=state,
            metadata_valid=False,
        )
        return InventoryEntry(candidate=candidate, snapshot=actual_snapshot)
    except (OSError, ValueError, ValidationError, RetentionFsError):
        return None
