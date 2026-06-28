"""Cross-surface evidence link packets for local report artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index import (
    EvidenceArtifactState,
    LocalEvidenceArtifact,
    build_local_evidence_index,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

EVIDENCE_LINKS_SCHEMA_VERSION: Final = "entroping.evidence-links.v1"

EvidenceLinksOutput = Literal["md", "json"]
EvidenceLinksStatus = Literal["ready", "partial", "insufficient"]
EvidenceLinksSourceState = EvidenceArtifactState
EvidenceLinksTargetState = Literal["ready", "blocked"]
EvidenceLinksPriority = Literal["high", "medium"]
EvidenceLinkSurface = Literal["cli", "pr", "desktop", "cloud", "mobile", "agent"]
EvidenceLinksSourceId = Literal[
    "evidence-index-json",
    "handoff-json",
    "runtime-card-json",
    "evidence-bundle-json",
    "evidence-cloud-readiness-json",
    "notification-packet-json",
    "connector-intent-json",
    "integration-readiness-json",
    "devex-readiness-json",
]

_SURFACES: Final[tuple[EvidenceLinkSurface, ...]] = (
    "cli",
    "pr",
    "desktop",
    "cloud",
    "mobile",
    "agent",
)
_DEFAULT_OUTPUTS: Final[dict[EvidenceLinksOutput, Path]] = {
    "md": Path("reports") / "evidence-links.md",
    "json": Path("reports") / "evidence-links.json",
}


class EvidenceLinksError(ValueError):
    """Raised when an evidence-links packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _LinkSourceDefinition:
    id: EvidenceLinksSourceId
    surfaces: tuple[EvidenceLinkSurface, ...]


_LINK_SOURCE_DEFINITIONS: Final[tuple[_LinkSourceDefinition, ...]] = (
    _LinkSourceDefinition(
        "evidence-index-json",
        ("cli", "desktop", "cloud", "mobile", "agent"),
    ),
    _LinkSourceDefinition(
        "handoff-json",
        ("cli", "desktop", "cloud", "mobile", "agent"),
    ),
    _LinkSourceDefinition(
        "runtime-card-json",
        ("cli", "pr", "desktop", "cloud", "mobile", "agent"),
    ),
    _LinkSourceDefinition(
        "evidence-bundle-json",
        ("cli", "pr", "desktop", "cloud", "agent"),
    ),
    _LinkSourceDefinition(
        "evidence-cloud-readiness-json",
        ("desktop", "cloud", "mobile", "agent"),
    ),
    _LinkSourceDefinition(
        "notification-packet-json",
        ("pr", "cloud", "mobile", "agent"),
    ),
    _LinkSourceDefinition(
        "connector-intent-json",
        ("cloud", "agent"),
    ),
    _LinkSourceDefinition(
        "integration-readiness-json",
        ("desktop", "cloud", "agent"),
    ),
    _LinkSourceDefinition(
        "devex-readiness-json",
        ("cli", "desktop", "cloud", "mobile", "agent"),
    ),
)
_SURFACES_BY_SOURCE_ID: Final[dict[EvidenceLinksSourceId, tuple[EvidenceLinkSurface, ...]]] = {
    definition.id: definition.surfaces for definition in _LINK_SOURCE_DEFINITIONS
}


class EvidenceLinksSummary(BaseModel):
    """Aggregate source and link-target readiness."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceLinksStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    targets_total: int = Field(ge=0)
    targets_ready: int = Field(ge=0)
    targets_blocked: int = Field(ge=0)
    surfaces_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidenceLinksSource(BaseModel):
    """One sanitized local artifact that can back cross-surface links."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceLinksSourceId
    label: str
    path: str
    state: EvidenceLinksSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class EvidenceLinkTarget(BaseModel):
    """One stable value-free link target for future surfaces."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceLinksSourceId
    label: str
    source_id: EvidenceLinksSourceId
    link_token: str
    path: str
    state: EvidenceLinksTargetState
    surfaces: tuple[EvidenceLinkSurface, ...]
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class EvidenceLinksNextAction(BaseModel):
    """One local action before evidence links are ready everywhere."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidenceLinksPriority
    action: str
    source_ids: tuple[EvidenceLinksSourceId, ...] = ()
    target_ids: tuple[EvidenceLinksSourceId, ...] = ()


class EvidenceLinksPacket(BaseModel):
    """Schema-versioned local evidence-links packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-links.v1"] = EVIDENCE_LINKS_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: EvidenceLinksSummary
    sources: tuple[EvidenceLinksSource, ...]
    targets: tuple[EvidenceLinkTarget, ...]
    next_actions: tuple[EvidenceLinksNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidenceLinksResult:
    """Result of writing one evidence-links packet."""

    output_path: Path
    packet: EvidenceLinksPacket


def run_evidence_links_report(
    *,
    project_root: Path,
    output: EvidenceLinksOutput,
    output_path: Path | None = None,
) -> EvidenceLinksResult:
    """Write a local cross-surface evidence-links packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-links output: {output}"
        raise EvidenceLinksError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_links_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Evidence links packet contains secret-like content"
        raise EvidenceLinksError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="evidence links",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceLinksError(str(exc)) from exc
    return EvidenceLinksResult(output_path=written, packet=packet)


def build_evidence_links_packet(*, project_root: Path) -> EvidenceLinksPacket:
    """Build a value-free link packet from sanitized local evidence artifacts."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    sources = tuple(
        _source_from_index(definition, indexed.get(definition.id), root=root)
        for definition in _LINK_SOURCE_DEFINITIONS
    )
    targets = tuple(_target_from_source(source, _surfaces_for(source.id)) for source in sources)
    next_actions = _next_actions(sources=sources, targets=targets)
    return EvidenceLinksPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_sources(root=root, sources=sources) or root.name,
        summary=_summary(sources=sources, targets=targets, next_actions=next_actions),
        sources=sources,
        targets=targets,
        next_actions=next_actions,
    )


def render_evidence_links_markdown(packet: EvidenceLinksPacket) -> str:
    """Render a human-readable, value-free evidence-links packet."""

    lines = [
        "# Entroping Evidence Links",
        "",
        "Read-only local cross-surface link packet for CLI, PR, desktop, cloud, "
        "mobile, and coding-agent handoff surfaces. Link tokens are stable local "
        "references, not registered protocol handlers or hosted uploads.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Targets: "
        f"`{packet.summary.targets_ready}/{packet.summary.targets_total}` ready, "
        f"`{packet.summary.targets_blocked}` blocked",
        "",
        "## Sources",
        "",
        "| ID | State | Path | Schema | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
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
            "## Link Targets",
            "",
            "| ID | State | Link Token | Surfaces | Source |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for target in packet.targets:
        lines.append(
            "| "
            f"{_markdown_cell(target.id)} | "
            f"{_markdown_cell(target.state)} | "
            f"{_markdown_cell(target.link_token)} | "
            f"{_markdown_cell(', '.join(target.surfaces))} | "
            f"{_markdown_cell(target.path)} |"
        )
    if packet.next_actions:
        lines.extend(["", "## Next Actions", ""])
        for action in packet.next_actions:
            lines.append(f"- `{action.priority}` {_inline_code(action.action)}")
    else:
        lines.extend(["", "No evidence-link actions are currently needed."])
    return "\n".join(lines).rstrip() + "\n"


def _source_from_index(
    definition: _LinkSourceDefinition,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> EvidenceLinksSource:
    if artifact is None:
        return EvidenceLinksSource(
            id=definition.id,
            label=_source_label(definition.id),
            path=_source_path(definition.id),
            state="missing",
            schema_version=None,
            sha256=None,
            summary="not indexed",
        )
    state = artifact.state
    sha256: str | None = None
    summary = safe_evidence_text(artifact.summary)
    if state == "present":
        raw_bytes, load_error = read_local_evidence_json_artifact_bytes(
            root / artifact.path,
            root=root,
        )
        if raw_bytes is None:
            state = "invalid"
            summary = safe_evidence_text(load_error)
        elif contains_unredacted_evidence_secret(raw_bytes.decode("utf-8", errors="replace")):
            state = "unsafe"
            summary = "secret-like content"
        else:
            sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return EvidenceLinksSource(
        id=definition.id,
        label=artifact.label,
        path=artifact.path,
        state=state,
        schema_version=artifact.schema_version,
        sha256=sha256,
        summary=summary,
    )


def _target_from_source(
    source: EvidenceLinksSource,
    surfaces: tuple[EvidenceLinkSurface, ...],
) -> EvidenceLinkTarget:
    return EvidenceLinkTarget(
        id=source.id,
        label=source.label,
        source_id=source.id,
        link_token=f"entroping://evidence/{source.id}",
        path=source.path,
        state="ready" if source.state == "present" else "blocked",
        surfaces=surfaces,
        schema_version=source.schema_version,
        sha256=source.sha256,
        summary=source.summary,
    )


def _summary(
    *,
    sources: tuple[EvidenceLinksSource, ...],
    targets: tuple[EvidenceLinkTarget, ...],
    next_actions: tuple[EvidenceLinksNextAction, ...],
) -> EvidenceLinksSummary:
    return EvidenceLinksSummary(
        status=_status(sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        targets_total=len(targets),
        targets_ready=sum(1 for target in targets if target.state == "ready"),
        targets_blocked=sum(1 for target in targets if target.state == "blocked"),
        surfaces_total=len(_SURFACES),
        next_actions_total=len(next_actions),
    )


def _status(sources: tuple[EvidenceLinksSource, ...]) -> EvidenceLinksStatus:
    if all(source.state == "present" for source in sources):
        return "ready"
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _next_actions(
    *,
    sources: tuple[EvidenceLinksSource, ...],
    targets: tuple[EvidenceLinkTarget, ...],
) -> tuple[EvidenceLinksNextAction, ...]:
    actions: list[EvidenceLinksNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        repair = source.state in {"invalid", "unsafe"}
        actions.append(
            EvidenceLinksNextAction(
                priority="high" if repair else "medium",
                action=(
                    f"Repair {source.label} local evidence."
                    if repair
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
                target_ids=(source.id,),
            )
        )
    if any(target.state == "blocked" for target in targets):
        blocked_ids = tuple(target.id for target in targets if target.state == "blocked")
        actions.append(
            EvidenceLinksNextAction(
                priority="medium",
                action="Regenerate evidence links after blocked source artifacts are ready.",
                target_ids=blocked_ids,
            )
        )
    return tuple(actions)


def _project_from_sources(
    *,
    root: Path,
    sources: tuple[EvidenceLinksSource, ...],
) -> str | None:
    for source in sources:
        if source.state != "present":
            continue
        document = _json_document(root / source.path, root=root)
        project = document.get("project") if document is not None else None
        if isinstance(project, str) and project.strip():
            return safe_evidence_text(project)
    return None


def _json_document(path: Path, *, root: Path) -> dict[str, object] | None:
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(path, root=root)
    if raw_bytes is None:
        _ = load_error
        return None
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if contains_unredacted_evidence_secret(raw_text):
        return None
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _surfaces_for(source_id: EvidenceLinksSourceId) -> tuple[EvidenceLinkSurface, ...]:
    return _SURFACES_BY_SOURCE_ID[source_id]


def _render_packet_content(
    packet: EvidenceLinksPacket,
    *,
    output: EvidenceLinksOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_links_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(raw_path, root=root, artifact="Evidence links")
    except SafeWriteError as exc:
        raise EvidenceLinksError(str(exc)) from exc


def _source_label(source_id: EvidenceLinksSourceId) -> str:
    return source_id.replace("-", " ").title()


def _source_path(source_id: EvidenceLinksSourceId) -> str:
    filename = source_id.removesuffix("-json")
    return (Path("reports") / f"{filename}.json").as_posix()


def _inline_code(value: object) -> str:
    return escape(safe_evidence_text(str(value))).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = _inline_code(value)
    return text.replace("|", "\\|")
