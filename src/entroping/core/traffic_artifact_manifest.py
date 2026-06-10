"""Approval manifests for generated artifacts derived from redacted traffic."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.bridge.redaction_review import (
    RedactionReviewCategory,
    RedactionReviewReport,
    compile_redaction_review,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.traffic import TrafficExchange

TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION: Final = (
    "entroping.traffic-artifact-approval.v1"
)
TrafficArtifactWorkflow = Literal["freeze-hurl", "freeze-wiremock", "dependency-map"]
TrafficArtifactKind = Literal["hurl", "wiremock", "dependency_map"]


class TrafficArtifactApprovalError(ValueError):
    """Raised when captured-traffic artifact approval evidence cannot be written."""


@dataclass(frozen=True, slots=True)
class TrafficArtifactManifestArtifact:
    """One generated artifact included in a traffic approval manifest."""

    kind: TrafficArtifactKind
    path: Path


@dataclass(frozen=True, slots=True)
class TrafficArtifactApprovalResult:
    """Result of writing a captured-traffic approval manifest."""

    manifest_path: Path


def write_traffic_artifact_approval_manifest(
    *,
    project_root: Path,
    manifest_name: str,
    workflow: TrafficArtifactWorkflow,
    source_session_name: str,
    source_records: tuple[TrafficExchange, ...],
    artifacts: tuple[TrafficArtifactManifestArtifact, ...],
) -> TrafficArtifactApprovalResult:
    """Write a value-free approval manifest for generated traffic artifacts."""

    root = project_root.expanduser().resolve()
    safe_manifest_name = _safe_file_stem(manifest_name, field="approval manifest name")
    safe_session_name = _safe_plain_text(source_session_name, field="source session name")
    if not source_records:
        msg = "approval manifest requires at least one source traffic record"
        raise TrafficArtifactApprovalError(msg)
    if not artifacts:
        msg = "approval manifest requires at least one generated artifact"
        raise TrafficArtifactApprovalError(msg)

    for exchange in source_records:
        if not exchange.redacted:
            msg = "approval manifest requires redacted traffic"
            raise TrafficArtifactApprovalError(msg)

    resolved_artifacts = tuple(_artifact_payload(artifact, root=root) for artifact in artifacts)
    record_fingerprints = tuple(_record_fingerprint(exchange) for exchange in source_records)
    redaction_report = compile_redaction_review(source_records)
    payload = {
        "schema_version": TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION,
        "workflow": workflow,
        "source": {
            "session_name": safe_session_name,
            "session_id": _source_session_id(safe_session_name, record_fingerprints),
            "record_count": len(source_records),
            "record_fingerprints": list(record_fingerprints),
        },
        "redaction": _redaction_payload(redaction_report),
        "artifacts": list(resolved_artifacts),
    }

    manifest_path = root / "reports" / "approvals" / f"{safe_manifest_name}.json"
    try:
        safe_write_text(
            manifest_path,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            artifact="traffic artifact approval manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise TrafficArtifactApprovalError(str(exc)) from exc
    return TrafficArtifactApprovalResult(manifest_path=manifest_path)


def _artifact_payload(
    artifact: TrafficArtifactManifestArtifact,
    *,
    root: Path,
) -> dict[str, object]:
    path = _resolve_artifact_path(artifact.path, root=root)
    content = path.read_bytes()
    return {
        "kind": artifact.kind,
        "path": _display_path(path, root),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _resolve_artifact_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    _reject_symlink_path(path, root=root, artifact="generated artifact")
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"generated artifact path must stay inside the project: {raw_path}"
        raise TrafficArtifactApprovalError(msg) from exc
    if relative_parts and relative_parts[0] == ".entroping":
        msg = f"generated artifact path refuses local traffic state: {raw_path}"
        raise TrafficArtifactApprovalError(msg)
    if relative_parts and relative_parts[0] == "envs":
        msg = f"generated artifact path refuses local env files: {raw_path}"
        raise TrafficArtifactApprovalError(msg)
    if not resolved.exists():
        msg = f"generated artifact does not exist: {_display_path(resolved, root)}"
        raise TrafficArtifactApprovalError(msg)
    if not resolved.is_file():
        msg = f"generated artifact is not a file: {_display_path(resolved, root)}"
        raise TrafficArtifactApprovalError(msg)
    return resolved


def _record_fingerprint(exchange: TrafficExchange) -> str:
    canonical = json.dumps(
        exchange.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_session_id(session_name: str, record_fingerprints: tuple[str, ...]) -> str:
    material = "\n".join((session_name, *record_fingerprints))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _redaction_payload(report: RedactionReviewReport) -> dict[str, object]:
    return {
        "total_records": report.total_records,
        "redacted_records": report.redacted_records,
        "unredacted_records": report.unredacted_records,
        "low_confidence_records": report.low_confidence_records,
        "request_count": report.request_count,
        "response_count": report.response_count,
        "header_categories": _category_payload(report.header_categories),
        "query_categories": _category_payload(report.query_categories),
        "body_categories": _category_payload(report.body_categories),
        "body_summary_categories": _category_payload(report.body_summary_categories),
    }


def _category_payload(
    categories: Sequence[RedactionReviewCategory],
) -> list[dict[str, object]]:
    return [
        {"category": category.category, "count": category.count}
        for category in categories
    ]


def _safe_file_stem(value: str, *, field: str) -> str:
    text = _safe_plain_text(value, field=field)
    if "/" in text or "\\" in text or ".." in text or text.startswith("."):
        msg = f"{field} must be a safe file stem"
        raise TrafficArtifactApprovalError(msg)
    if not all(character.isalnum() or character in {"_", "-", "."} for character in text):
        msg = f"{field} must contain only letters, numbers, dots, dashes, or underscores"
        raise TrafficArtifactApprovalError(msg)
    return text


def _safe_plain_text(value: str, *, field: str) -> str:
    text = value.strip()
    if not text:
        msg = f"{field} must not be empty"
        raise TrafficArtifactApprovalError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        msg = f"{field} must not contain control characters"
        raise TrafficArtifactApprovalError(msg)
    return text


def _reject_symlink_path(path: Path, *, root: Path, artifact: str) -> None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = f"{artifact} path must stay inside the project: {path}"
        raise TrafficArtifactApprovalError(msg) from exc
    if symlink_path is not None:
        msg = f"Refusing to write {artifact} through symlinked path component: {symlink_path}"
        raise TrafficArtifactApprovalError(msg)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return str(path)
