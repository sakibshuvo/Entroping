"""Local Evidence Cloud export manifests for design-partner review."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_index import (
    EvidenceArtifactState,
    LocalEvidenceArtifact,
    build_local_evidence_index,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION: Final = "entroping.evidence-cloud-export.v1"

EvidenceCloudExportOutput = Literal["md", "json"]
EvidenceCloudExportStatus = Literal["ready", "partial", "insufficient"]
EvidenceCloudExportSourceState = EvidenceArtifactState
EvidenceCloudExportItemState = Literal["ready", "blocked"]
EvidenceCloudExportNextActionPriority = Literal["high", "medium", "low"]
EvidenceCloudExportSourceId = Literal[
    "evidence-portal-json",
    "evidence-links-json",
    "evidence-cloud-readiness-json",
    "team-evidence-readiness-json",
    "evidence-bundle-json",
    "artifact-manifest-json",
    "runtime-card-json",
    "handoff-json",
    "integration-readiness-json",
    "devex-readiness-json",
    "connector-intent-json",
    "observability-packet-json",
    "evidence-index-json",
]
EvidenceCloudExportBoundaryControlId = Literal[
    "explicit_upload_only",
    "no_remote_api",
    "no_raw_traffic",
    "no_secrets",
    "no_prompts_or_provider_outputs",
    "no_source_hurl",
    "no_env_values",
    "no_full_report_payloads",
]

_DEFAULT_OUTPUTS: Final[dict[EvidenceCloudExportOutput, Path]] = {
    "md": Path("reports") / "evidence-cloud-export.md",
    "json": Path("reports") / "evidence-cloud-export.json",
}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b")


class EvidenceCloudExportError(ValueError):
    """Raised when an Evidence Cloud export manifest cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: EvidenceCloudExportSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _BoundaryControlDefinition:
    id: EvidenceCloudExportBoundaryControlId
    label: str
    summary: str


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        "evidence-portal-json",
        "Evidence Portal JSON",
        Path("reports") / "evidence-portal.json",
        "entroping.evidence-portal.v1",
    ),
    _SourceDefinition(
        "evidence-links-json",
        "Evidence Links JSON",
        Path("reports") / "evidence-links.json",
        "entroping.evidence-links.v1",
    ),
    _SourceDefinition(
        "evidence-cloud-readiness-json",
        "Evidence Cloud Readiness JSON",
        Path("reports") / "evidence-cloud-readiness.json",
        "entroping.evidence-cloud-readiness.v1",
    ),
    _SourceDefinition(
        "team-evidence-readiness-json",
        "Team Evidence Readiness JSON",
        Path("reports") / "team-evidence-readiness.json",
        "entroping.team-evidence-readiness.v1",
    ),
    _SourceDefinition(
        "evidence-bundle-json",
        "Evidence Bundle",
        Path("reports") / "evidence-bundle.json",
        "entroping.evidence-bundle.v1",
    ),
    _SourceDefinition(
        "artifact-manifest-json",
        "Artifact Manifest",
        Path("reports") / "artifact-manifest.json",
        "entroping.report-artifact-manifest.v1",
    ),
    _SourceDefinition(
        "runtime-card-json",
        "Runtime Card JSON",
        Path("reports") / "runtime-card.json",
        "entroping.runtime-card.v1",
    ),
    _SourceDefinition(
        "handoff-json",
        "Handoff JSON",
        Path("reports") / "handoff.json",
        "entroping.handoff.v1",
    ),
    _SourceDefinition(
        "integration-readiness-json",
        "Integration Readiness JSON",
        Path("reports") / "integration-readiness.json",
        "entroping.integration-readiness.v1",
    ),
    _SourceDefinition(
        "devex-readiness-json",
        "Developer Experience Readiness JSON",
        Path("reports") / "devex-readiness.json",
        "entroping.devex-readiness.v1",
    ),
    _SourceDefinition(
        "connector-intent-json",
        "Connector Intent JSON",
        Path("reports") / "connector-intent.json",
        "entroping.connector-intent.v1",
    ),
    _SourceDefinition(
        "observability-packet-json",
        "Observability Packet JSON",
        Path("reports") / "observability-packet.json",
        "entroping.observability-packet.v1",
    ),
    _SourceDefinition(
        "evidence-index-json",
        "Evidence Index JSON",
        Path("reports") / "evidence-index.json",
        "entroping.evidence-index.v1",
    ),
)

_BOUNDARY_CONTROL_DEFINITIONS: Final[tuple[_BoundaryControlDefinition, ...]] = (
    _BoundaryControlDefinition(
        id="explicit_upload_only",
        label="Explicit upload only",
        summary=(
            "This report writes a local manifest only; any future upload must be "
            "user initiated."
        ),
    ),
    _BoundaryControlDefinition(
        id="no_remote_api",
        label="No remote API",
        summary="The export manifest does not call hosted Evidence Cloud or vendor APIs.",
    ),
    _BoundaryControlDefinition(
        id="no_raw_traffic",
        label="No raw traffic",
        summary="Raw captured traffic is not read, embedded, uploaded, or summarized.",
    ),
    _BoundaryControlDefinition(
        id="no_secrets",
        label="No secrets",
        summary="Credentials, tokens, cookies, and secret-like values fail closed.",
    ),
    _BoundaryControlDefinition(
        id="no_prompts_or_provider_outputs",
        label="No prompts or provider outputs",
        summary="Model prompts and provider responses are not export payloads.",
    ),
    _BoundaryControlDefinition(
        id="no_source_hurl",
        label="No source Hurl",
        summary="Committed Hurl test bodies are not copied into the export manifest.",
    ),
    _BoundaryControlDefinition(
        id="no_env_values",
        label="No environment values",
        summary="Environment variable names or values are not read for this report.",
    ),
    _BoundaryControlDefinition(
        id="no_full_report_payloads",
        label="No full report payloads",
        summary="Only metadata, schema versions, states, paths, and hashes are emitted.",
    ),
)


class EvidenceCloudExportSummary(BaseModel):
    """Aggregate local Evidence Cloud export readiness."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceCloudExportStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    export_items_total: int = Field(ge=0)
    export_items_ready: int = Field(ge=0)
    export_items_blocked: int = Field(ge=0)
    boundary_controls_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidenceCloudExportSource(BaseModel):
    """One sanitized local artifact considered for export."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudExportSourceId
    label: str
    path: str
    state: EvidenceCloudExportSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class EvidenceCloudExportItem(BaseModel):
    """One value-free artifact row eligible for a future explicit upload flow."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudExportSourceId
    label: str
    source_id: EvidenceCloudExportSourceId
    path: str
    state: EvidenceCloudExportItemState
    local_reference: str
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    required_user_action: str


class EvidenceCloudExportBoundaryControl(BaseModel):
    """One local boundary control for the export manifest."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudExportBoundaryControlId
    label: str
    enforced: bool
    summary: str


class EvidenceCloudExportNextAction(BaseModel):
    """One local action needed before Evidence Cloud export review."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidenceCloudExportNextActionPriority
    action: str
    source_ids: tuple[EvidenceCloudExportSourceId, ...] = ()
    export_item_ids: tuple[EvidenceCloudExportSourceId, ...] = ()


class EvidenceCloudExportPacket(BaseModel):
    """Schema-versioned local Evidence Cloud export manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-cloud-export.v1"] = (
        EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: EvidenceCloudExportSummary
    sources: tuple[EvidenceCloudExportSource, ...]
    export_items: tuple[EvidenceCloudExportItem, ...]
    boundary_controls: tuple[EvidenceCloudExportBoundaryControl, ...]
    next_actions: tuple[EvidenceCloudExportNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCloudExportResult:
    """Result of writing one Evidence Cloud export manifest."""

    output_path: Path
    packet: EvidenceCloudExportPacket


def run_evidence_cloud_export_report(
    *,
    project_root: Path,
    output: EvidenceCloudExportOutput,
    output_path: Path | None = None,
) -> EvidenceCloudExportResult:
    """Write a local Evidence Cloud export manifest."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-cloud-export output: {output}"
        raise EvidenceCloudExportError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_cloud_export_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Evidence Cloud export manifest contains secret-like content"
        raise EvidenceCloudExportError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="Evidence Cloud export manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceCloudExportError(str(exc)) from exc
    return EvidenceCloudExportResult(output_path=written, packet=packet)


def build_evidence_cloud_export_packet(*, project_root: Path) -> EvidenceCloudExportPacket:
    """Build a value-free local Evidence Cloud export manifest."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    source_rows: list[EvidenceCloudExportSource] = []
    source_documents: dict[EvidenceCloudExportSourceId, dict[str, object]] = {}
    for definition in _SOURCE_DEFINITIONS:
        source, document = _source_from_index(definition, indexed.get(definition.id), root=root)
        source_rows.append(source)
        if document is not None:
            source_documents[definition.id] = document
    sources = tuple(source_rows)
    export_items = tuple(_export_item_from_source(source) for source in sources)
    boundary_controls = _boundary_controls()
    next_actions = _next_actions(sources=sources, export_items=export_items)
    return EvidenceCloudExportPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=source_documents.values()),
        summary=_summary(
            sources=sources,
            export_items=export_items,
            boundary_controls=boundary_controls,
            next_actions=next_actions,
        ),
        sources=sources,
        export_items=export_items,
        boundary_controls=boundary_controls,
        next_actions=next_actions,
    )


def render_evidence_cloud_export_markdown(packet: EvidenceCloudExportPacket) -> str:
    """Render a human-readable, value-free Evidence Cloud export manifest."""

    lines = [
        "# Entroping Evidence Cloud Export",
        "",
        "Local manifest for a future explicit Evidence Cloud upload review. This",
        "report emits metadata only and does not upload or embed report payloads.",
        "",
        "## Summary",
        "",
        f"- Status: `{_md(packet.summary.status)}`",
        f"- Sources: `{packet.summary.sources_present}/{packet.summary.sources_total}` present",
        f"- Export items: `{packet.summary.export_items_ready}/"
        f"{packet.summary.export_items_total}` ready",
        f"- Boundary controls: `{packet.summary.boundary_controls_total}` enforced",
        "",
        "## Sources",
        "",
        "| ID | State | Path | Schema | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in packet.sources:
        lines.append(
            "| "
            f"{_md(source.id)} | {_md(source.state)} | {_md(source.path)} | "
            f"{_md(source.schema_version or 'n/a')} | {_md(source.sha256 or 'n/a')} | "
            f"{_md(source.summary)} |"
        )
    lines.extend(
        [
            "",
            "## Export Items",
            "",
            "| ID | State | Local Reference | Path | Schema | SHA-256 | Required Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in packet.export_items:
        lines.append(
            "| "
            f"{_md(item.id)} | {_md(item.state)} | {_md(item.local_reference)} | "
            f"{_md(item.path)} | {_md(item.schema_version or 'n/a')} | "
            f"{_md(item.sha256 or 'n/a')} | {_md(item.required_user_action)} |"
        )
    lines.extend(
        [
            "",
            "## Boundary Controls",
            "",
            "| Control | Enforced | Summary |",
            "| --- | --- | --- |",
        ]
    )
    for control in packet.boundary_controls:
        lines.append(
            f"| {_md(control.label)} | {_md(control.enforced)} | {_md(control.summary)} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if packet.next_actions:
        for action in packet.next_actions:
            lines.append(f"- `{_md(action.priority)}` {_md(action.action)}")
    else:
        lines.append("No Evidence Cloud export actions are currently needed.")
    return "\n".join(lines) + "\n"


def _source_from_index(
    definition: _SourceDefinition,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[EvidenceCloudExportSource, dict[str, object] | None]:
    if artifact is None:
        return (
            EvidenceCloudExportSource(
                id=definition.id,
                label=definition.label,
                path=definition.path.as_posix(),
                state="missing",
                schema_version=None,
                sha256=None,
                summary="not indexed",
            ),
            None,
        )
    state = artifact.state
    summary = safe_evidence_text(artifact.summary)
    sha256: str | None = None
    document: dict[str, object] | None = None
    if state == "present":
        raw_bytes, load_error = read_local_evidence_json_artifact_bytes(
            root / artifact.path,
            root=root,
        )
        if raw_bytes is None:
            state = _state_from_load_error(load_error)
            summary = safe_evidence_text(load_error)
        else:
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            if _contains_unredacted_source_secret(raw_text):
                state = "unsafe"
                summary = "secret-like content"
            else:
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                document = _parse_document(raw_text)
                if document is None:
                    state = "invalid"
                    summary = "invalid JSON"
                    sha256 = None
                elif document.get("schema_version") != definition.schema_version:
                    state = "invalid"
                    summary = "schema mismatch"
                    sha256 = None
                    document = None
    return (
        EvidenceCloudExportSource(
            id=definition.id,
            label=artifact.label,
            path=artifact.path,
            state=state,
            schema_version=artifact.schema_version,
            sha256=sha256,
            summary=summary,
        ),
        document,
    )


def _export_item_from_source(source: EvidenceCloudExportSource) -> EvidenceCloudExportItem:
    state: EvidenceCloudExportItemState = "ready" if source.state == "present" else "blocked"
    return EvidenceCloudExportItem(
        id=source.id,
        label=source.label,
        source_id=source.id,
        path=source.path,
        state=state,
        local_reference=f"entroping://evidence-cloud-export/{source.id}",
        schema_version=source.schema_version,
        sha256=source.sha256,
        summary=source.summary,
        required_user_action=_required_user_action(source),
    )


def _required_user_action(source: EvidenceCloudExportSource) -> str:
    if source.state == "present":
        return "Review artifact metadata before explicit upload."
    verb = "Repair" if source.state in {"invalid", "unsafe"} else "Generate"
    return f"{verb} {source.label} before Evidence Cloud export."


def _boundary_controls() -> tuple[EvidenceCloudExportBoundaryControl, ...]:
    return tuple(
        EvidenceCloudExportBoundaryControl(
            id=definition.id,
            label=definition.label,
            enforced=True,
            summary=definition.summary,
        )
        for definition in _BOUNDARY_CONTROL_DEFINITIONS
    )


def _summary(
    *,
    sources: tuple[EvidenceCloudExportSource, ...],
    export_items: tuple[EvidenceCloudExportItem, ...],
    boundary_controls: tuple[EvidenceCloudExportBoundaryControl, ...],
    next_actions: tuple[EvidenceCloudExportNextAction, ...],
) -> EvidenceCloudExportSummary:
    return EvidenceCloudExportSummary(
        status=_status(sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        export_items_total=len(export_items),
        export_items_ready=sum(1 for item in export_items if item.state == "ready"),
        export_items_blocked=sum(1 for item in export_items if item.state == "blocked"),
        boundary_controls_total=sum(1 for control in boundary_controls if control.enforced),
        next_actions_total=len(next_actions),
    )


def _status(sources: tuple[EvidenceCloudExportSource, ...]) -> EvidenceCloudExportStatus:
    if all(source.state == "present" for source in sources):
        return "ready"
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _next_actions(
    *,
    sources: tuple[EvidenceCloudExportSource, ...],
    export_items: tuple[EvidenceCloudExportItem, ...],
) -> tuple[EvidenceCloudExportNextAction, ...]:
    actions: list[EvidenceCloudExportNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        repair = source.state in {"invalid", "unsafe"}
        actions.append(
            EvidenceCloudExportNextAction(
                priority="high" if repair else "medium",
                action=_required_user_action(source),
                source_ids=(source.id,),
                export_item_ids=(source.id,),
            )
        )
    blocked = tuple(item.id for item in export_items if item.state == "blocked")
    if blocked:
        actions.append(
            EvidenceCloudExportNextAction(
                priority="medium",
                action="Regenerate Evidence Cloud export after blocked source artifacts are ready.",
                export_item_ids=blocked,
            )
        )
    return tuple(actions)


def _project_from_documents(
    *,
    root: Path,
    documents: Iterable[dict[str, object]],
) -> str:
    for document in documents:
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return safe_evidence_text(project)
    return safe_evidence_text(root.name)


def _parse_document(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _state_from_load_error(load_error: str) -> EvidenceArtifactState:
    if load_error in {
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    }:
        return "unsafe"
    return "invalid"


def _contains_unredacted_source_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))


def _render_packet_content(
    packet: EvidenceCloudExportPacket,
    *,
    output: EvidenceCloudExportOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_cloud_export_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(raw_path, root=root, artifact="Evidence Cloud export")
    except SafeWriteError as exc:
        raise EvidenceCloudExportError(str(exc)) from exc


def _md(value: object) -> str:
    return safe_evidence_text(str(value)).replace("|", "\\|").replace("\n", " ")
