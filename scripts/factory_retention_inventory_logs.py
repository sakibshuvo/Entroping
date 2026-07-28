from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_retention_fs import (
    RetentionFsError,
    SnapshotBudget,
    entry_snapshot,
    list_names,
    open_relative_directory,
    path_exists,
)
from scripts.factory_retention_inventory_metadata import InventoryEntry
from scripts.factory_retention_models import ArtifactCandidate
from scripts.factory_retention_types import CANDIDATE_SCHEMA_VERSION

_LOG_NAME = re.compile(r"factory-tick\.(?:out|err)\.log(?:\.\d+)?")


def inventory_logs(
    repo_root: Path,
    snapshot_budget: SnapshotBudget,
) -> tuple[list[InventoryEntry], list[str]]:
    parts = (".entroping", "factory-logs")
    if not path_exists(repo_root, parts):
        return [], []
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    try:
        with open_relative_directory(repo_root, parts) as directory_fd:
            for name in list_names(directory_fd):
                if _LOG_NAME.fullmatch(name) is None:
                    continue
                relative_path = f".entroping/factory-logs/{name}"
                try:
                    snapshot = entry_snapshot(
                        directory_fd,
                        name,
                        budget=snapshot_budget,
                    )
                    if snapshot.kind != "file":
                        raise RetentionFsError("factory log must be a regular file")
                    state = "active" if name.endswith(".log") else "rotated"
                    candidate = ArtifactCandidate(
                        schema_version=CANDIDATE_SCHEMA_VERSION,
                        artifact_id=f"log:{name}",
                        bundle_id=f"log:{name}",
                        artifact_class="factory_log",
                        relative_path=relative_path,
                        byte_size=snapshot.byte_size,
                        created_at=datetime.fromtimestamp(
                            snapshot.mtime_ns / 1_000_000_000,
                            UTC,
                        ),
                        state=state,
                    )
                    entries.append(InventoryEntry(candidate=candidate, snapshot=snapshot))
                except (OSError, ValueError, ValidationError, RetentionFsError) as exc:
                    errors.append(
                        f"invalid factory log {relative_path}: {type(exc).__name__}"
                    )
    except (OSError, RetentionFsError) as exc:
        errors.append(f"unsafe factory log root: {type(exc).__name__}")
    return entries, errors
