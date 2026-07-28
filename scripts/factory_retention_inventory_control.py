from __future__ import annotations

import os
import re
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
    payload_timestamp,
)
from scripts.factory_retention_journal import RetentionJournalError, read_journal
from scripts.factory_retention_models import ArtifactCandidate
from scripts.factory_retention_types import (
    CANDIDATE_SCHEMA_VERSION,
    FACTORY_METRICS_ARCHIVE_SCHEMA_VERSION,
)

_ARCHIVE_NAME = re.compile(r"issue-([1-9][0-9]*)")
_JOURNAL_NAME = re.compile(r"([0-9a-f]{32})\.json")


def inventory_metrics_archives(
    repo_root: Path,
    snapshot_budget: SnapshotBudget,
) -> tuple[list[InventoryEntry], list[str]]:
    parts = (".entroping", "factory-metrics", "finished-issues")
    if not path_exists(repo_root, parts):
        return [], []
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    try:
        with open_relative_directory(repo_root, parts) as root_fd:
            for name in list_names(root_fd):
                match = _ARCHIVE_NAME.fullmatch(name)
                if match is None:
                    errors.append("unexpected factory metrics archive entry")
                    continue
                entry, error = _metrics_archive_entry(
                    repo_root,
                    root_fd,
                    name,
                    int(match.group(1)),
                    snapshot_budget,
                )
                entries.append(entry)
                if error is not None:
                    errors.append(error)
    except (OSError, RetentionFsError) as exc:
        errors.append(f"unsafe factory metrics archive root: {type(exc).__name__}")
    return entries, errors


def inventory_journals(
    repo_root: Path,
    snapshot_budget: SnapshotBudget,
) -> tuple[list[InventoryEntry], list[str]]:
    parts = (".entroping", "retention-journal")
    if not path_exists(repo_root, parts):
        return [], []
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    try:
        with open_relative_directory(repo_root, parts) as root_fd:
            for name in list_names(root_fd):
                if _JOURNAL_NAME.fullmatch(name) is None:
                    errors.append("unexpected retention journal entry")
                    continue
                snapshot = entry_snapshot(root_fd, name, budget=snapshot_budget)
                try:
                    journal = read_journal(root_fd, name)
                    if journal.status not in {"completed", "rolled_back"}:
                        continue
                    completed_at = journal.completed_at
                    if completed_at is None:
                        raise RetentionJournalError("terminal journal timestamp is missing")
                    candidate = ArtifactCandidate(
                        schema_version=CANDIDATE_SCHEMA_VERSION,
                        artifact_id=f"journal:{journal.transaction_id}",
                        bundle_id=f"journal:{journal.transaction_id}",
                        artifact_class="retention_journal",
                        relative_path=f".entroping/retention-journal/{name}",
                        byte_size=snapshot.byte_size,
                        created_at=payload_timestamp(
                            {"completed_at": completed_at},
                            snapshot.mtime_ns,
                        ),
                        state=journal.status,
                    )
                    entries.append(InventoryEntry(candidate=candidate, snapshot=snapshot))
                except (
                    OSError,
                    ValueError,
                    ValidationError,
                    RetentionFsError,
                    RetentionJournalError,
                ) as exc:
                    entries.append(_invalid_journal(name, snapshot))
                    errors.append(
                        f"invalid terminal retention journal: {type(exc).__name__}"
                    )
    except (OSError, RetentionFsError) as exc:
        errors.append(f"unsafe retention journal root: {type(exc).__name__}")
    return entries, errors


def _metrics_archive_entry(
    repo_root: Path,
    root_fd: int,
    name: str,
    issue: int,
    snapshot_budget: SnapshotBudget,
) -> tuple[InventoryEntry, str | None]:
    snapshot = entry_snapshot(root_fd, name, budget=snapshot_budget)
    if snapshot.kind != "directory":
        raise RetentionFsError("factory metrics archive must be a directory")
    relative_path = f".entroping/factory-metrics/finished-issues/{name}"
    try:
        with open_relative_directory(
            repo_root,
            (".entroping", "factory-metrics", "finished-issues", name),
        ) as archive_fd:
            try:
                _ = os.stat("metadata.json", dir_fd=archive_fd, follow_symlinks=False)
            except FileNotFoundError:
                return _legacy_metrics_archive(name, relative_path, snapshot), None
            payload = json_object(read_bounded_regular(archive_fd, "metadata.json"))
        _validate_archive_metadata(payload, issue)
        created_at = payload_timestamp(
            {"completed_at": payload["archived_at"]},
            snapshot.mtime_ns,
        )
        candidate = ArtifactCandidate(
            schema_version=CANDIDATE_SCHEMA_VERSION,
            artifact_id=f"metrics:{name}",
            bundle_id=f"metrics:{name}",
            artifact_class="factory_metrics_archive",
            relative_path=relative_path,
            byte_size=snapshot.byte_size,
            created_at=created_at,
            state="archived",
        )
        return InventoryEntry(candidate=candidate, snapshot=snapshot), None
    except (OSError, ValueError, ValidationError, RetentionFsError) as exc:
        return (
            _legacy_metrics_archive(name, relative_path, snapshot),
            f"invalid factory metrics archive {name}: {type(exc).__name__}",
        )


def _validate_archive_metadata(payload: dict[str, object], issue: int) -> None:
    expected = {
        "schema_version",
        "issue",
        "pull_request",
        "status",
        "issue_state",
        "pr_state",
        "archived_at",
    }
    if (
        set(payload) != expected
        or payload.get("schema_version") != FACTORY_METRICS_ARCHIVE_SCHEMA_VERSION
    ):
        raise ValueError("factory metrics archive metadata schema is invalid")
    if payload.get("issue") != issue:
        raise ValueError("factory metrics archive issue is inconsistent")
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, bool) or not isinstance(pull_request, int) or pull_request <= 0:
        raise ValueError("factory metrics archive pull request is invalid")
    if (
        payload.get("status") != "archived"
        or payload.get("issue_state") != "closed"
        or payload.get("pr_state") != "merged"
    ):
        raise ValueError("factory metrics archive is not terminal")
    _ = payload_timestamp({"completed_at": payload.get("archived_at")}, 0)


def _legacy_metrics_archive(
    name: str,
    relative_path: str,
    snapshot: FsSnapshot,
) -> InventoryEntry:
    candidate = ArtifactCandidate(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        artifact_id=f"legacy-metrics:{name}",
        bundle_id=f"legacy-metrics:{name}",
        artifact_class="factory_metrics_archive",
        relative_path=relative_path,
        byte_size=snapshot.byte_size,
        created_at=datetime.fromtimestamp(snapshot.mtime_ns / 1_000_000_000, UTC),
        state="archived",
        metadata_valid=False,
    )
    return InventoryEntry(candidate=candidate, snapshot=snapshot)


def _invalid_journal(name: str, snapshot: FsSnapshot) -> InventoryEntry:
    transaction_id = name.removesuffix(".json")
    candidate = ArtifactCandidate(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        artifact_id=f"invalid-journal:{transaction_id}",
        bundle_id=f"invalid-journal:{transaction_id}",
        artifact_class="retention_journal",
        relative_path=f".entroping/retention-journal/{name}",
        byte_size=snapshot.byte_size,
        created_at=datetime.fromtimestamp(snapshot.mtime_ns / 1_000_000_000, UTC),
        state="unknown",
        metadata_valid=False,
    )
    return InventoryEntry(candidate=candidate, snapshot=snapshot)
