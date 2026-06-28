from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, assert_never

from entroping.core.factory_inbox_io import (
    InboxError,
    JsonObject,
    read_json_object,
    resolve_artifact_dir,
    review_packet,
    write_json_object,
)

DEFAULT_ARTIFACT_ROOT: Final = Path(".entroping") / "ai-reviews"
RESULT_FILENAMES: Final = ("result.md", "RESULT.md", "worker-result.md")
TEST_FILENAMES: Final = ("tests.txt", "TESTS.txt", "test-output.txt")
READY_STATUSES: Final = frozenset({"ready_for_codex", "ready-for-codex"})
LEGACY_READY_STATUSES: Final = frozenset({"completed", "patch-proposed"})
OPEN_INBOX_STATUSES: Final = frozenset({"ready", "ready_for_codex", "ready-for-codex"})
MARK_DECISIONS: Final = {
    "mark-reviewed": "reviewed",
    "mark-accepted": "accepted",
    "mark-rejected": "rejected",
    "mark-needs-review": "needs_review",
}


@dataclass(frozen=True, slots=True)
class InboxItem:
    artifact_dir: Path
    issue: str | None
    status: str
    codex_inbox_status: str | None
    provider_lane: str | None
    model: str | None
    updated_at: float


@dataclass(frozen=True, slots=True)
class SkippedArtifact:
    artifact_dir: Path
    reason: str


def list_payload(artifact_root: Path, *, include_completed: bool) -> JsonObject:
    ready, skipped = discover(artifact_root, include_completed=include_completed)
    return {
        "schema_version": "entroping.factory-inbox.v1",
        "artifact_root": str(artifact_root),
        "ready": [item_payload(item) for item in ready],
        "skipped": [skipped_payload(item) for item in skipped],
    }


def next_payload(
    repo_root_path: Path,
    artifact_root: Path,
    *,
    include_completed: bool,
    newest: bool,
    claim: bool,
) -> JsonObject:
    ready, skipped = discover(artifact_root, include_completed=include_completed)
    if not ready:
        msg = f"no ready OpenCode handoffs found under {artifact_root}"
        raise InboxError(msg)
    ordered = sorted(ready, key=lambda item: (item.updated_at, str(item.artifact_dir)))
    item = ordered[-1] if newest else ordered[0]
    if claim:
        write_inbox_status(item.artifact_dir, decision="in_review", timestamp_key="claimed_at")
        item = replace(
            item,
            codex_inbox_status="in_review",
            updated_at=datetime.now(UTC).timestamp(),
        )
    return {
        "schema_version": "entroping.factory-inbox.v1",
        "selection_rule": "newest ready handoff" if newest else "oldest ready handoff",
        "inbox": item_payload(item),
        "review_packet": review_packet(repo_root_path, artifact_root, item.artifact_dir),
        "skipped_count": len(skipped),
        "mark_commands": mark_commands(item.artifact_dir),
    }


def mark_payload(artifact_root: Path, raw_artifact_dir: Path, *, decision: str) -> JsonObject:
    artifact_dir = resolve_artifact_dir(artifact_root, raw_artifact_dir)
    metadata = write_inbox_status(artifact_dir, decision=decision, timestamp_key="reviewed_at")
    return {
        "schema_version": "entroping.factory-inbox.v1",
        "artifact_dir": str(artifact_dir),
        "codex_inbox_status": decision,
        "review_decision": decision,
        "metadata_path": str(artifact_dir / "metadata.json"),
        "issue": string_value(metadata, "issue"),
    }


def discover(
    artifact_root: Path,
    *,
    include_completed: bool,
) -> tuple[tuple[InboxItem, ...], tuple[SkippedArtifact, ...]]:
    if not artifact_root.exists():
        return (), ()
    if not artifact_root.is_dir():
        msg = f"artifact root is not a directory: {artifact_root}"
        raise InboxError(msg)
    ready: list[InboxItem] = []
    skipped: list[SkippedArtifact] = []
    for artifact_dir in sorted(path for path in artifact_root.iterdir() if path.is_dir()):
        candidate = candidate_from_dir(artifact_dir, include_completed=include_completed)
        match candidate:
            case InboxItem():
                ready.append(candidate)
            case SkippedArtifact():
                skipped.append(candidate)
            case unreachable:
                assert_never(unreachable)
    return tuple(ready), tuple(skipped)


def candidate_from_dir(
    artifact_dir: Path,
    *,
    include_completed: bool,
) -> InboxItem | SkippedArtifact:
    metadata_path = artifact_dir / "metadata.json"
    if not metadata_path.exists():
        return SkippedArtifact(artifact_dir=artifact_dir, reason="missing metadata.json")
    try:
        metadata = read_json_object(metadata_path)
    except InboxError as exc:
        return SkippedArtifact(artifact_dir=artifact_dir, reason=str(exc))
    result_path = first_existing(artifact_dir, RESULT_FILENAMES)
    tests_path = first_existing(artifact_dir, TEST_FILENAMES)
    if result_path is None or tests_path is None:
        return SkippedArtifact(artifact_dir=artifact_dir, reason="missing result.md or tests.txt")
    status = string_value(metadata, "status") or "unknown"
    item = InboxItem(
        artifact_dir=artifact_dir.resolve(),
        issue=string_value(metadata, "issue"),
        status=status,
        codex_inbox_status=string_value(metadata, "codex_inbox_status"),
        provider_lane=string_value(metadata, "provider_lane"),
        model=string_value(metadata, "model"),
        updated_at=updated_at(metadata_path, result_path, tests_path),
    )
    if item_is_ready(item, include_completed=include_completed):
        return item
    return SkippedArtifact(artifact_dir=artifact_dir.resolve(), reason="not ready for Codex")


def item_is_ready(item: InboxItem, *, include_completed: bool) -> bool:
    if item.codex_inbox_status is not None and item.codex_inbox_status not in OPEN_INBOX_STATUSES:
        return False
    if item.status in READY_STATUSES:
        return True
    return include_completed and item.status in LEGACY_READY_STATUSES


def write_inbox_status(artifact_dir: Path, *, decision: str, timestamp_key: str) -> JsonObject:
    metadata_path = artifact_dir / "metadata.json"
    metadata = read_json_object(metadata_path)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    metadata["codex_inbox_status"] = decision
    metadata["review_decision"] = decision
    metadata[timestamp_key] = now
    write_json_object(metadata_path, metadata)
    return metadata


def first_existing(root: Path, filenames: tuple[str, ...]) -> Path | None:
    for filename in filenames:
        path = root / filename
        if path.exists():
            return path
    return None


def updated_at(metadata_path: Path, result_path: Path, tests_path: Path) -> float:
    proposal_path = metadata_path.parent / "proposal.diff"
    paths = [metadata_path, result_path, tests_path]
    if proposal_path.exists():
        paths.append(proposal_path)
    return max(path.stat().st_mtime for path in paths)


def string_value(metadata: JsonObject, key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, str | int | float):
        text = str(value).strip()
        if text:
            return text
    return None


def item_payload(item: InboxItem) -> JsonObject:
    return {
        "artifact_dir": str(item.artifact_dir),
        "issue": item.issue,
        "status": item.status,
        "codex_inbox_status": item.codex_inbox_status,
        "provider_lane": item.provider_lane,
        "model": item.model,
        "updated_at": format_timestamp(item.updated_at),
    }


def skipped_payload(item: SkippedArtifact) -> JsonObject:
    return {"artifact_dir": str(item.artifact_dir.resolve()), "reason": item.reason}


def mark_commands(artifact_dir: Path) -> JsonObject:
    base = ["uv", "run", "python", "scripts/factory_inbox.py"]
    return {
        "reviewed": [*base, "mark-reviewed", str(artifact_dir), "--json"],
        "accepted": [*base, "mark-accepted", str(artifact_dir), "--json"],
        "rejected": [*base, "mark-rejected", str(artifact_dir), "--json"],
        "needs_review": [*base, "mark-needs-review", str(artifact_dir), "--json"],
    }


def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")
