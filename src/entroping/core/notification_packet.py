"""Work-management and chat notification packets from sanitized evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_packet_base import (
    EvidencePacketResult,
    write_evidence_packet_report,
)
from entroping.core.handoff_packet import (
    HANDOFF_SCHEMA_VERSION,
    HandoffArtifact,
    HandoffPacket,
    build_handoff_packet,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import safe_write_text

NOTIFICATION_PACKET_SCHEMA_VERSION: Final = "entroping.notification-packet.v1"

NotificationOutput = Literal["md", "json"]
NotificationStatus = Literal["ready", "partial", "insufficient"]
NotificationSeverity = Literal["info", "attention", "blocker"]
NotificationSourceState = Literal["present", "missing", "invalid", "unsafe"]
NotificationSourceId = Literal[
    "handoff",
    "runtime_card",
    "evidence_bundle",
    "pilot_metrics",
    "artifact_manifest",
    "test_pyramid",
]
NotificationSurface = Literal[
    "jira",
    "linear",
    "monday",
    "slack",
    "discord",
    "workato",
    "agent",
]

_MAX_NOTIFICATION_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_HANDOFF_PATH: Final = Path("reports") / "handoff.json"
_DEFAULT_OUTPUTS: Final[dict[NotificationOutput, Path]] = {
    "md": Path("reports") / "notification-packet.md",
    "json": Path("reports") / "notification-packet.json",
}
_SURFACE_LABELS: Final[dict[NotificationSurface, str]] = {
    "jira": "Jira",
    "linear": "Linear",
    "monday": "monday.com",
    "slack": "Slack",
    "discord": "Discord",
    "workato": "Workato",
    "agent": "Agent",
}
_SURFACE_ACTIONS: Final[dict[NotificationSurface, str]] = {
    "jira": "Attach this packet as read-only issue evidence.",
    "linear": "Attach this packet as read-only issue evidence.",
    "monday": "Attach this packet as read-only work-item evidence.",
    "slack": "Post this summary with links to sanitized artifacts only.",
    "discord": "Post this summary with links to sanitized artifacts only.",
    "workato": "Use this packet as a trigger payload after explicit connector setup.",
    "agent": "Use this packet as bounded context before proposing work.",
}


class NotificationPacketError(ValueError):
    """Raised when a notification packet cannot be generated safely."""


class NotificationSummary(BaseModel):
    """Aggregate notification packet state."""

    model_config = ConfigDict(extra="forbid")

    status: NotificationStatus
    severity: NotificationSeverity
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)


class NotificationRuntimeSummary(BaseModel):
    """Value-free runtime status used by notification surfaces."""

    model_config = ConfigDict(extra="forbid")

    status: str
    findings: int = Field(ge=0)
    evidence_links: int = Field(ge=0)
    failed_gate_ids: int = Field(ge=0)


class NotificationSource(BaseModel):
    """One local evidence artifact used to build the packet."""

    model_config = ConfigDict(extra="forbid")

    id: NotificationSourceId
    label: str
    path: str
    state: NotificationSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class NotificationMessage(BaseModel):
    """One value-free message for a work-management or chat surface."""

    model_config = ConfigDict(extra="forbid")

    surface: NotificationSurface
    label: str
    severity: NotificationSeverity
    title: str
    body: str
    next_action: str
    artifact_paths: tuple[str, ...] = ()


class NotificationPacket(BaseModel):
    """Schema-versioned read-only notification packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.notification-packet.v1"] = (
        NOTIFICATION_PACKET_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: NotificationSummary
    runtime: NotificationRuntimeSummary | None
    sources: tuple[NotificationSource, ...]
    messages: tuple[NotificationMessage, ...]


@dataclass(frozen=True, slots=True)
class NotificationPacketResult:
    """Result of writing one notification packet."""

    output_path: Path
    packet: NotificationPacket


@dataclass(frozen=True, slots=True)
class _LoadedHandoff:
    source: NotificationSource
    packet: HandoffPacket | None


def run_notification_packet_report(
    *,
    project_root: Path,
    output: NotificationOutput,
    output_path: Path | None = None,
) -> NotificationPacketResult:
    """Write a local work-management/chat notification packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported notification output: {output}"
        raise NotificationPacketError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_notification_packet(
        project_root=root,
        packet_path=destination.relative_to(root).as_posix(),
    )
    result: EvidencePacketResult[NotificationPacket] = write_evidence_packet_report(
        project_root=root,
        output=output,
        output_path=destination,
        packet=packet,
        render_markdown=render_notification_packet_markdown,
        has_secret_content=_contains_unredacted_secret_like_value,
        unsafe_content_message="notification packet contains secret-like content",
        artifact="notification packet",
        error_type=NotificationPacketError,
        safe_write=safe_write_text,
    )
    return NotificationPacketResult(output_path=result.output_path, packet=result.packet)


def build_notification_packet(
    *,
    project_root: Path,
    packet_path: str = "reports/notification-packet.json",
) -> NotificationPacket:
    """Build a value-free notification packet from local report artifacts."""

    root = project_root.expanduser().resolve()
    loaded_handoff = _load_handoff(root=root)
    handoff_packet = loaded_handoff.packet or build_handoff_packet(project_root=root)
    sources = (
        loaded_handoff.source,
        *(
            _source_from_handoff_artifact(artifact)
            for artifact in handoff_packet.artifacts
        ),
    )
    runtime = _runtime_from_handoff(handoff_packet)
    summary = _summary(sources=sources, runtime=runtime)
    return NotificationPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_safe_optional_text(handoff_packet.project),
        summary=summary,
        runtime=runtime,
        sources=sources,
        messages=_messages(
            sources=sources,
            runtime=runtime,
            summary=summary,
            packet_path=_safe_text(packet_path),
        ),
    )


def render_notification_packet_markdown(packet: NotificationPacket) -> str:
    """Render a human-readable notification packet."""

    lines = [
        "# Entroping Notification Packet",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Severity: `{packet.summary.severity}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "",
        "## Runtime",
        "",
    ]
    if packet.runtime is None:
        lines.append("No runtime summary is available.")
    else:
        lines.extend(
            [
                f"- Runtime status: `{_inline_code(packet.runtime.status)}`",
                f"- Findings: `{packet.runtime.findings}`",
                f"- Evidence links: `{packet.runtime.evidence_links}`",
                f"- Failed gates: `{packet.runtime.failed_gate_ids}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Source | State | Path | Schema | SHA-256 | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.id)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(source.schema_version or 'n/a')} | "
            f"{_markdown_cell(source.sha256 or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )

    lines.extend(
        [
            "",
            "## Messages",
            "",
            "| Surface | Severity | Title | Next Action | Artifact Paths |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for message in packet.messages:
        lines.append(
            "| "
            f"{_markdown_cell(message.surface)} | "
            f"{_markdown_cell(message.severity)} | "
            f"{_markdown_cell(message.title)} | "
            f"{_markdown_cell(message.next_action)} | "
            f"{_markdown_cell(', '.join(message.artifact_paths) or 'n/a')} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_handoff(*, root: Path) -> _LoadedHandoff:
    try:
        path = _resolve_source_path(_HANDOFF_PATH, root=root)
    except NotificationPacketError as exc:
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary=_safe_text(str(exc)),
            ),
            packet=None,
        )
    if not path.exists():
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="missing",
                schema_version=None,
                sha256=None,
                summary="Handoff packet is missing.",
            ),
            packet=None,
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact="handoff packet")
        raw_text = raw_bytes.decode("utf-8")
    except NotificationPacketError as exc:
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(str(exc)),
            ),
            packet=None,
        )
    except UnicodeDecodeError as exc:
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Could not decode handoff packet as UTF-8: {exc}"),
            ),
            packet=None,
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary="Handoff packet contains secret-like content.",
            ),
            packet=None,
        )
    try:
        document = json.loads(raw_text)
        if not isinstance(document, dict):
            msg = "Handoff packet must be a JSON object"
            raise NotificationPacketError(msg)
        schema_version = _schema_version(document)
        if schema_version != HANDOFF_SCHEMA_VERSION:
            msg = (
                "Handoff packet uses unsupported schema "
                f"{schema_version or 'unknown'}; expected {HANDOFF_SCHEMA_VERSION}"
            )
            raise NotificationPacketError(msg)
        packet = HandoffPacket.model_validate(document)
    except (json.JSONDecodeError, ValidationError, NotificationPacketError) as exc:
        return _LoadedHandoff(
            source=_source(
                "handoff",
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Invalid handoff packet: {exc}"),
            ),
            packet=None,
        )
    return _LoadedHandoff(
        source=_source(
            "handoff",
            state="present",
            schema_version=HANDOFF_SCHEMA_VERSION,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            summary=f"{packet.summary.status} handoff evidence",
        ),
        packet=packet,
    )


def _source_from_handoff_artifact(artifact: HandoffArtifact) -> NotificationSource:
    return NotificationSource(
        id=artifact.id,
        label=artifact.label,
        path=artifact.path,
        state=artifact.state,
        schema_version=artifact.schema_version,
        sha256=artifact.sha256,
        summary=artifact.summary,
    )


def _source(
    source_id: NotificationSourceId,
    *,
    state: NotificationSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
) -> NotificationSource:
    return NotificationSource(
        id=source_id,
        label="Cross-surface handoff",
        path=_HANDOFF_PATH.as_posix(),
        state=state,
        schema_version=schema_version,
        sha256=sha256,
        summary=summary,
    )


def _runtime_from_handoff(packet: HandoffPacket) -> NotificationRuntimeSummary | None:
    if packet.runtime is None:
        return None
    return NotificationRuntimeSummary(
        status=packet.runtime.status,
        findings=packet.runtime.findings,
        evidence_links=packet.runtime.evidence_links,
        failed_gate_ids=packet.runtime.failed_gate_ids,
    )


def _summary(
    *,
    sources: tuple[NotificationSource, ...],
    runtime: NotificationRuntimeSummary | None,
) -> NotificationSummary:
    present = sum(1 for source in sources if source.state == "present")
    missing = sum(1 for source in sources if source.state == "missing")
    invalid = sum(1 for source in sources if source.state == "invalid")
    unsafe = sum(1 for source in sources if source.state == "unsafe")
    if present == 0:
        status: NotificationStatus = "insufficient"
    elif missing or invalid or unsafe:
        status = "partial"
    else:
        status = "ready"
    return NotificationSummary(
        status=status,
        severity=_severity(status=status, invalid=invalid, unsafe=unsafe, runtime=runtime),
        sources_total=len(sources),
        sources_present=present,
        sources_missing=missing,
        sources_invalid=invalid,
        sources_unsafe=unsafe,
    )


def _severity(
    *,
    status: NotificationStatus,
    invalid: int,
    unsafe: int,
    runtime: NotificationRuntimeSummary | None,
) -> NotificationSeverity:
    if runtime is not None and runtime.failed_gate_ids > 0:
        return "blocker"
    if runtime is not None and runtime.status.lower() in {"fail", "failed", "failure"}:
        return "blocker"
    if status in {"partial", "insufficient"} or invalid > 0 or unsafe > 0:
        return "attention"
    if runtime is not None and runtime.status.lower() in {"attention", "warn", "warning"}:
        return "attention"
    return "info"


def _messages(
    *,
    sources: tuple[NotificationSource, ...],
    runtime: NotificationRuntimeSummary | None,
    summary: NotificationSummary,
    packet_path: str,
) -> tuple[NotificationMessage, ...]:
    artifact_paths = _artifact_paths(packet_path=packet_path, sources=sources)
    body = _message_body(summary=summary, runtime=runtime)
    title = _message_title(summary.severity)
    return tuple(
        NotificationMessage(
            surface=surface,
            label=_SURFACE_LABELS[surface],
            severity=summary.severity,
            title=title,
            body=body,
            next_action=_SURFACE_ACTIONS[surface],
            artifact_paths=artifact_paths,
        )
        for surface in _SURFACE_LABELS
    )


def _artifact_paths(
    *,
    packet_path: str,
    sources: tuple[NotificationSource, ...],
) -> tuple[str, ...]:
    paths: list[str] = [_safe_text(packet_path)]
    for source in sources:
        if source.state == "present" and source.path not in paths:
            paths.append(source.path)
    return tuple(paths)


def _message_title(severity: NotificationSeverity) -> str:
    if severity == "blocker":
        return "Entroping runtime governance needs attention"
    if severity == "attention":
        return "Entroping evidence needs review"
    return "Entroping runtime governance evidence is ready"


def _message_body(
    *,
    summary: NotificationSummary,
    runtime: NotificationRuntimeSummary | None,
) -> str:
    runtime_status = runtime.status if runtime is not None else "unknown"
    failed_gates = runtime.failed_gate_ids if runtime is not None else 0
    return _safe_text(
        f"Runtime status {runtime_status}; {failed_gates} failed gates; "
        f"{summary.sources_present}/{summary.sources_total} sources present."
    )


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    path = root / raw_path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "notification source path must stay under the project root"
        raise NotificationPacketError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"notification source path uses symlinked component: {display_path}"
        raise NotificationPacketError(msg)
    if path.exists() and not path.is_file():
        msg = f"notification source path is not a file: {raw_path.as_posix()}"
        raise NotificationPacketError(msg)
    return path


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "notification output path must stay under the project root"
        raise NotificationPacketError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"notification output path uses symlinked component: {display_path}"
        raise NotificationPacketError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "notification output path must stay under the project root"
        raise NotificationPacketError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "notification packet must not be written into .entroping or envs"
        raise NotificationPacketError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    try:
        if path.stat().st_size > _MAX_NOTIFICATION_ARTIFACT_BYTES:
            msg = (
                f"{artifact.capitalize()} {path.name} exceeds "
                f"{_MAX_NOTIFICATION_ARTIFACT_BYTES} bytes"
            )
            raise NotificationPacketError(msg)
        return path.read_bytes()
    except NotificationPacketError:
        raise
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise NotificationPacketError(msg) from exc


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _safe_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    safe = _safe_text(value)
    return safe or None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    backslash_placeholder = "\0ENTROPING_BACKSLASH\0"
    text = value.replace("\r", " ").replace("\\", backslash_placeholder)
    text = escape(text, quote=False).replace("|", "\\|")
    return text.replace(backslash_placeholder, "&#92;")
