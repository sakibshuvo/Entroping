from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from scripts.factory_retention_fs import FsSnapshot
from scripts.factory_retention_models import ArtifactCandidate, ArtifactReference
from scripts.factory_retention_types import SettlementState


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    candidate: ArtifactCandidate
    snapshot: FsSnapshot | None


def artifact_references(payload: dict[str, object]) -> tuple[ArtifactReference, ...]:
    references: list[ArtifactReference] = []
    for key, kind in (("issue", "issue"), ("pr", "pull_request")):
        reference_id = optional_text(payload.get(key))
        if reference_id is not None:
            references.append(
                ArtifactReference.model_validate(
                    {"kind": kind, "reference_id": reference_id, "state": "unknown"}
                )
            )
    return tuple(references)


def review_name(value: object, repo_root: Path) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    path = Path(text)
    if path.is_absolute():
        expected = repo_root / ".entroping" / "ai-reviews" / path.name
        if path.resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError("artifact directory is outside the review root")
    elif path.name != text:
        expected = Path(".entroping") / "ai-reviews" / path.name
        if path != expected:
            raise ValueError("artifact directory is outside the review root")
    if not path.name or path.name in {".", ".."}:
        raise ValueError("artifact directory name is invalid")
    return path.name


def json_object(payload: bytes) -> dict[str, object]:
    decoded = cast(object, json.loads(payload.decode("utf-8")))
    if not isinstance(decoded, dict):
        raise ValueError("metadata must be a JSON object")
    mapping = cast(dict[object, object], decoded)
    result: dict[str, object] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise ValueError("metadata must use string keys")
        result[key] = value
    return result


def required_text(payload: dict[str, object], key: str) -> str:
    value = optional_text(payload.get(key))
    if value is None:
        raise ValueError(f"metadata field is missing: {key}")
    return value


def optional_text(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str | int):
        text = str(value).strip()
        return text or None
    return None


def settlement_state(value: object) -> SettlementState | None:
    text = optional_text(value)
    if text is None:
        return None
    match text:
        case "settled":
            return "settled"
        case "unresolved":
            return "unresolved"
        case "unknown":
            return "unknown"
        case _:
            raise ValueError("settlement state is unsupported")


def payload_timestamp(payload: dict[str, object], fallback_mtime_ns: int) -> datetime:
    for key in ("completed_at", "reviewed_at", "updated_at", "created_at"):
        if key not in payload:
            continue
        value = payload[key]
        if not isinstance(value, str):
            raise ValueError("artifact timestamp must be a UTC ISO-8601 string")
        try:
            normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("artifact timestamp must be valid UTC ISO-8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("artifact timestamp must include a UTC offset")
        return parsed.astimezone(UTC)
    return datetime.fromtimestamp(fallback_mtime_ns / 1_000_000_000, UTC)
