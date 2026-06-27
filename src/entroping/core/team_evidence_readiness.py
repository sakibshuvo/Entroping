"""Team evidence cloud/design-partner readiness packets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.design_partner_feedback import DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION
from entroping.core.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.pilot_metrics import PILOT_METRICS_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

TEAM_EVIDENCE_READINESS_SCHEMA_VERSION: Final = (
    "entroping.team-evidence-readiness.v1"
)

TeamEvidenceReadinessOutput = Literal["md", "json"]
TeamEvidenceReadinessStatus = Literal["ready", "partial", "insufficient"]
TeamEvidenceSourceState = Literal["present", "missing", "invalid", "unsafe"]
TeamEvidenceReadinessAreaStatus = Literal["ready", "attention", "blocked"]
TeamEvidenceNextActionPriority = Literal["high", "medium", "low"]
TeamEvidenceSourceId = Literal[
    "evidence_bundle",
    "runtime_card",
    "pilot_metrics",
    "design_partner_feedback",
    "handoff",
    "notification_packet",
]
TeamEvidenceReadinessAreaId = Literal[
    "upload_boundary",
    "runtime_visibility",
    "design_partner_pilot",
    "cross_surface_continuity",
    "notification_linkout",
    "cloud_boundary_controls",
]
TeamEvidenceForbiddenDataClass = Literal[
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[TeamEvidenceReadinessOutput, Path]] = {
    "md": Path("reports") / "team-evidence-readiness.md",
    "json": Path("reports") / "team-evidence-readiness.json",
}
_FORBIDDEN_DATA_CLASSES: Final[tuple[TeamEvidenceForbiddenDataClass, ...]] = (
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
)
_NEXT_COMMANDS_BY_SOURCE: Final[dict[TeamEvidenceSourceId, str]] = {
    "evidence_bundle": "entroping report evidence-bundle",
    "runtime_card": "entroping report runtime-card --output json",
    "pilot_metrics": "entroping report pilot-metrics --output json",
    "design_partner_feedback": "entroping report design-partner-feedback",
    "handoff": "entroping report handoff --output json",
    "notification_packet": "entroping report notification-packet --output json",
}


class TeamEvidenceReadinessError(ValueError):
    """Raised when team evidence readiness cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: TeamEvidenceSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: TeamEvidenceSource
    document: dict[str, object] | None


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="evidence_bundle",
        label="Evidence bundle",
        path=Path("reports") / "evidence-bundle.json",
        schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version=RUNTIME_CARD_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="pilot_metrics",
        label="Pilot metrics",
        path=Path("reports") / "pilot-metrics.json",
        schema_version=PILOT_METRICS_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="design_partner_feedback",
        label="Design-partner feedback",
        path=Path("reports") / "design-partner-feedback.json",
        schema_version=DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="handoff",
        label="Cross-surface handoff",
        path=Path("reports") / "handoff.json",
        schema_version=HANDOFF_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="notification_packet",
        label="Notification packet",
        path=Path("reports") / "notification-packet.json",
        schema_version=NOTIFICATION_PACKET_SCHEMA_VERSION,
    ),
)


class TeamEvidenceReadinessSummary(BaseModel):
    """Aggregate team evidence readiness status."""

    model_config = ConfigDict(extra="forbid")

    status: TeamEvidenceReadinessStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    areas_total: int = Field(ge=0)
    areas_ready: int = Field(ge=0)
    areas_attention: int = Field(ge=0)
    areas_blocked: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class TeamEvidenceSource(BaseModel):
    """One sanitized local artifact used for team evidence readiness."""

    model_config = ConfigDict(extra="forbid")

    id: TeamEvidenceSourceId
    label: str
    path: str
    state: TeamEvidenceSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class TeamEvidenceReadinessArea(BaseModel):
    """One team/cloud readiness area derived from existing local evidence."""

    model_config = ConfigDict(extra="forbid")

    id: TeamEvidenceReadinessAreaId
    label: str
    status: TeamEvidenceReadinessAreaStatus
    source_ids: tuple[TeamEvidenceSourceId, ...]
    boundary: str
    blockers: tuple[str, ...] = ()
    next_action: str


class TeamEvidenceCloudBoundary(BaseModel):
    """Non-upload cloud boundary controls for future team evidence surfaces."""

    model_config = ConfigDict(extra="forbid")

    explicit_user_intent_required: bool
    upload_implemented: bool
    access_control_audit_required: bool
    forbidden_data_classes: tuple[TeamEvidenceForbiddenDataClass, ...]
    boundary_summary: str


class TeamEvidenceNextAction(BaseModel):
    """One local command or governance action before team evidence promotion."""

    model_config = ConfigDict(extra="forbid")

    priority: TeamEvidenceNextActionPriority
    action: str
    source_ids: tuple[TeamEvidenceSourceId, ...] = ()
    area_ids: tuple[TeamEvidenceReadinessAreaId, ...] = ()


class TeamEvidenceReadinessPacket(BaseModel):
    """Schema-versioned local team evidence readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.team-evidence-readiness.v1"] = (
        TEAM_EVIDENCE_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: TeamEvidenceReadinessSummary
    cloud_boundary: TeamEvidenceCloudBoundary
    sources: tuple[TeamEvidenceSource, ...]
    readiness_areas: tuple[TeamEvidenceReadinessArea, ...]
    next_actions: tuple[TeamEvidenceNextAction, ...]


@dataclass(frozen=True, slots=True)
class TeamEvidenceReadinessResult:
    """Result of writing one team evidence readiness packet."""

    output_path: Path
    packet: TeamEvidenceReadinessPacket


def run_team_evidence_readiness_report(
    *,
    project_root: Path,
    output: TeamEvidenceReadinessOutput,
    output_path: Path | None = None,
) -> TeamEvidenceReadinessResult:
    """Write a local team evidence readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported team-evidence-readiness output: {output}"
        raise TeamEvidenceReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_team_evidence_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "team evidence readiness packet contains secret-like content"
        raise TeamEvidenceReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="team evidence readiness packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise TeamEvidenceReadinessError(str(exc)) from exc
    return TeamEvidenceReadinessResult(output_path=written, packet=packet)


def build_team_evidence_readiness(*, project_root: Path) -> TeamEvidenceReadinessPacket:
    """Build a value-free team evidence readiness packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "team evidence readiness packet contains secret-like content"
        raise TeamEvidenceReadinessError(msg)
    return packet


def render_team_evidence_readiness_markdown(
    packet: TeamEvidenceReadinessPacket,
) -> str:
    """Render a human-readable team evidence readiness packet."""

    lines = [
        "# Entroping Team Evidence Readiness",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Areas: "
        f"`{packet.summary.areas_ready}/{packet.summary.areas_total}` ready, "
        f"`{packet.summary.areas_attention}` attention, "
        f"`{packet.summary.areas_blocked}` blocked",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Cloud Boundary",
        "",
        "| Control | Value |",
        "| --- | --- |",
        "| explicit_user_intent_required | "
        f"{_markdown_cell(str(packet.cloud_boundary.explicit_user_intent_required))} |",
        "| upload_implemented | "
        f"{_markdown_cell(str(packet.cloud_boundary.upload_implemented))} |",
        "| access_control_audit_required | "
        f"{_markdown_cell(str(packet.cloud_boundary.access_control_audit_required))} |",
        "| forbidden_data_classes | "
        f"{_markdown_cell(', '.join(packet.cloud_boundary.forbidden_data_classes))} |",
        "| boundary_summary | "
        f"{_markdown_cell(packet.cloud_boundary.boundary_summary)} |",
        "",
        "## Sources",
        "",
        "| Source | State | Path | Schema | SHA-256 | Summary |",
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
            "## Readiness Areas",
            "",
            "| Area | Status | Sources | Boundary | Blockers | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for area in packet.readiness_areas:
        lines.append(
            "| "
            f"{_markdown_cell(area.id)} | "
            f"{_markdown_cell(area.status)} | "
            f"{_markdown_cell(', '.join(area.source_ids))} | "
            f"{_markdown_cell(area.boundary)} | "
            f"{_markdown_cell('; '.join(area.blockers) or 'none')} | "
            f"{_markdown_cell(area.next_action)} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No team evidence readiness actions are currently needed.")
    else:
        lines.extend(["| Priority | Action | Sources | Areas |", "| --- | --- | --- | --- |"])
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.area_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_packet(*, root: Path) -> TeamEvidenceReadinessPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    areas = _readiness_areas(sources=sources)
    next_actions = _next_actions(sources=sources, areas=areas)
    return TeamEvidenceReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(
            sources=sources,
            areas=areas,
            next_actions=next_actions,
        ),
        cloud_boundary=_cloud_boundary(),
        sources=sources,
        readiness_areas=areas,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: TeamEvidenceReadinessPacket,
    *,
    output: TeamEvidenceReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_team_evidence_readiness_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    try:
        path = _resolve_source_path(definition.path, root=root)
    except TeamEvidenceReadinessError as exc:
        return _loaded_source(
            definition,
            state="unsafe",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    if not path.exists():
        return _loaded_source(
            definition,
            state="missing",
            schema_version=None,
            sha256=None,
            summary="Artifact is missing.",
            document=None,
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact=definition.label.lower())
        raw_text = raw_bytes.decode("utf-8")
    except TeamEvidenceReadinessError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    except UnicodeDecodeError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(f"Could not decode {definition.label.lower()} as UTF-8: {exc}"),
            document=None,
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _loaded_source(
            definition,
            state="unsafe",
            schema_version=None,
            sha256=None,
            summary=f"{definition.label} contains secret-like content.",
            document=None,
        )
    try:
        document = _json_object(raw_text, artifact=definition.label.lower())
        schema_version = _schema_version(document)
        if schema_version != definition.schema_version:
            return _loaded_source(
                definition,
                state="invalid",
                schema_version=schema_version,
                sha256=None,
                summary=f"unsupported schema_version; expected {definition.schema_version}",
                document=None,
            )
        summary = _source_summary(definition, document)
    except TeamEvidenceReadinessError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    return _loaded_source(
        definition,
        state="present",
        schema_version=definition.schema_version,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        summary=summary,
        document=document,
    )


def _loaded_source(
    definition: _SourceDefinition,
    *,
    state: TeamEvidenceSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=TeamEvidenceSource(
            id=definition.id,
            label=definition.label,
            path=definition.path.as_posix(),
            state=state,
            schema_version=_safe_text(schema_version) if schema_version else None,
            sha256=sha256,
            summary=_safe_text(summary),
        ),
        document=document,
    )


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"team evidence readiness source path uses symlinked component: {display_path}"
        raise TeamEvidenceReadinessError(msg)
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"team evidence readiness source path is not a file: {raw_path.as_posix()}"
        raise TeamEvidenceReadinessError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "team evidence readiness output path must stay under the project root"
        raise TeamEvidenceReadinessError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"team evidence readiness output path uses symlinked component: {display_path}"
        raise TeamEvidenceReadinessError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "team evidence readiness output path must stay under the project root"
        raise TeamEvidenceReadinessError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "team evidence readiness packet must not be written into .entroping or envs"
        raise TeamEvidenceReadinessError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    try:
        if path.stat().st_size > _MAX_SOURCE_BYTES:
            msg = f"{artifact.capitalize()} {path.name} exceeds {_MAX_SOURCE_BYTES} bytes"
            raise TeamEvidenceReadinessError(msg)
        return path.read_bytes()
    except TeamEvidenceReadinessError:
        raise
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise TeamEvidenceReadinessError(msg) from exc


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise TeamEvidenceReadinessError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise TeamEvidenceReadinessError(msg)
    return document


def _source_summary(
    definition: _SourceDefinition,
    document: Mapping[str, object],
) -> str:
    if definition.id == "evidence_bundle":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        present = _required_non_negative_int(
            summary,
            "required_present",
            artifact=definition.label,
        )
        total = _required_non_negative_int(
            summary,
            "required_total",
            artifact=definition.label,
        )
        return f"{status}; {present}/{total} required present"
    if definition.id == "runtime_card":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        findings = _required_non_negative_int(
            summary,
            "findings",
            artifact=definition.label,
        )
        return f"{status}; {findings} findings"
    if definition.id == "pilot_metrics":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        known = _required_non_negative_int(
            summary,
            "metrics_known",
            artifact=definition.label,
        )
        total = _required_non_negative_int(
            summary,
            "metrics_total",
            artifact=definition.label,
        )
        return f"{status}; {known}/{total} metrics known"
    if definition.id == "design_partner_feedback":
        evidence = _required_object(document, "evidence", artifact=definition.label)
        bundle = _required_text(
            evidence,
            "evidence_bundle_status",
            artifact=definition.label,
        )
        runtime = _required_text(
            evidence,
            "runtime_card_status",
            artifact=definition.label,
        )
        return f"bundle {bundle}; runtime {runtime}"
    if definition.id == "handoff":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        present = _required_non_negative_int(
            summary,
            "artifacts_present",
            artifact=definition.label,
        )
        total = _required_non_negative_int(
            summary,
            "artifacts_total",
            artifact=definition.label,
        )
        return f"{status}; {present}/{total} artifacts present"
    summary = _required_object(document, "summary", artifact=definition.label)
    status = _required_text(summary, "status", artifact=definition.label)
    severity = _required_text(summary, "severity", artifact=definition.label)
    return f"{status}; {severity} severity"


def _readiness_areas(
    *,
    sources: tuple[TeamEvidenceSource, ...],
) -> tuple[TeamEvidenceReadinessArea, ...]:
    by_id = {source.id: source for source in sources}
    return (
        _area(
            "upload_boundary",
            label="Upload boundary",
            source_ids=("evidence_bundle",),
            by_id=by_id,
            boundary=(
                "Existing evidence bundle must be ready before a future explicit "
                "team upload can be considered."
            ),
        ),
        _area(
            "runtime_visibility",
            label="PR/runtime visibility",
            source_ids=("runtime_card",),
            by_id=by_id,
            boundary="Runtime-card evidence must exist for team PR/status surfaces.",
        ),
        _area(
            "design_partner_pilot",
            label="Design-partner pilot context",
            source_ids=("pilot_metrics", "design_partner_feedback"),
            by_id=by_id,
            boundary=(
                "Pilot metrics and sanitized feedback context must be present "
                "before design-partner cloud discussions."
            ),
        ),
        _area(
            "cross_surface_continuity",
            label="Cross-surface continuity",
            source_ids=("handoff",),
            by_id=by_id,
            boundary=(
                "CLI, PR, desktop, cloud, mobile, and agent surfaces need a "
                "sanitized handoff packet."
            ),
        ),
        _area(
            "notification_linkout",
            label="Notification link-out",
            source_ids=("notification_packet",),
            by_id=by_id,
            boundary=(
                "Work-management and chat surfaces should receive links and "
                "value-free summaries only."
            ),
        ),
        _cloud_controls_area(by_id=by_id),
    )


def _area(
    area_id: TeamEvidenceReadinessAreaId,
    *,
    label: str,
    source_ids: tuple[TeamEvidenceSourceId, ...],
    by_id: Mapping[TeamEvidenceSourceId, TeamEvidenceSource],
    boundary: str,
) -> TeamEvidenceReadinessArea:
    selected = tuple(by_id[source_id] for source_id in source_ids)
    blockers = _source_blockers(selected)
    status = _area_status(selected)
    return TeamEvidenceReadinessArea(
        id=area_id,
        label=label,
        status=status,
        source_ids=source_ids,
        boundary=boundary,
        blockers=blockers,
        next_action=_area_next_action(
            label=label,
            status=status,
            source_ids=source_ids,
            blockers=blockers,
        ),
    )


def _cloud_controls_area(
    *,
    by_id: Mapping[TeamEvidenceSourceId, TeamEvidenceSource],
) -> TeamEvidenceReadinessArea:
    unsafe_or_invalid = tuple(
        source for source in by_id.values() if source.state in {"invalid", "unsafe"}
    )
    blockers = _source_blockers(unsafe_or_invalid)
    status: TeamEvidenceReadinessAreaStatus = "blocked" if blockers else "ready"
    return TeamEvidenceReadinessArea(
        id="cloud_boundary_controls",
        label="Cloud boundary controls",
        status=status,
        source_ids=tuple(by_id),
        boundary=(
            "Future team/cloud surfaces require explicit user intent, access "
            "control, audit evidence, and value-free artifact references only."
        ),
        blockers=blockers,
        next_action=(
            "Repair unsafe or invalid local evidence before discussing hosted "
            "team evidence."
            if blockers
            else "Keep team evidence cloud work explicit, audited, and value-free."
        ),
    )


def _area_status(
    sources: tuple[TeamEvidenceSource, ...],
) -> TeamEvidenceReadinessAreaStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "blocked"
    if all(source.state == "present" for source in sources):
        return "ready"
    return "attention"


def _source_blockers(sources: tuple[TeamEvidenceSource, ...]) -> tuple[str, ...]:
    blockers: list[str] = []
    for source in sources:
        if source.state == "missing":
            blockers.append(f"{source.label} is missing.")
        elif source.state in {"invalid", "unsafe"}:
            blockers.append(f"{source.label} is {source.state}: {source.summary}")
    return tuple(blockers)


def _area_next_action(
    *,
    label: str,
    status: TeamEvidenceReadinessAreaStatus,
    source_ids: tuple[TeamEvidenceSourceId, ...],
    blockers: tuple[str, ...],
) -> str:
    if status == "ready":
        return f"{label} evidence is ready for local design-partner review."
    commands = tuple(_NEXT_COMMANDS_BY_SOURCE[source_id] for source_id in source_ids)
    if blockers:
        return f"Resolve {label} blockers, then run: {'; '.join(commands)}."
    return f"Generate {label} evidence with: {'; '.join(commands)}."


def _next_actions(
    *,
    sources: tuple[TeamEvidenceSource, ...],
    areas: tuple[TeamEvidenceReadinessArea, ...],
) -> tuple[TeamEvidenceNextAction, ...]:
    actions: list[TeamEvidenceNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: TeamEvidenceNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            TeamEvidenceNextAction(
                priority=priority,
                action=(
                    f"Repair {source.label} local evidence."
                    if source.state in {"invalid", "unsafe"}
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
            )
        )
    for area in areas:
        if area.status == "ready":
            continue
        priority = "high" if area.status == "blocked" else "medium"
        actions.append(
            TeamEvidenceNextAction(
                priority=priority,
                action=area.next_action,
                source_ids=area.source_ids,
                area_ids=(area.id,),
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: list[TeamEvidenceNextAction],
) -> tuple[TeamEvidenceNextAction, ...]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[TeamEvidenceNextAction] = []
    for action in actions:
        key = (action.action, action.source_ids, action.area_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[TeamEvidenceSource, ...],
    areas: tuple[TeamEvidenceReadinessArea, ...],
    next_actions: tuple[TeamEvidenceNextAction, ...],
) -> TeamEvidenceReadinessSummary:
    blockers_total = len({blocker for area in areas for blocker in area.blockers})
    return TeamEvidenceReadinessSummary(
        status=_status(sources=sources, areas=areas),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        areas_total=len(areas),
        areas_ready=sum(1 for area in areas if area.status == "ready"),
        areas_attention=sum(1 for area in areas if area.status == "attention"),
        areas_blocked=sum(1 for area in areas if area.status == "blocked"),
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _status(
    *,
    sources: tuple[TeamEvidenceSource, ...],
    areas: tuple[TeamEvidenceReadinessArea, ...],
) -> TeamEvidenceReadinessStatus:
    if sources and all(source.state == "present" for source in sources) and all(
        area.status == "ready" for area in areas
    ):
        return "ready"
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _cloud_boundary() -> TeamEvidenceCloudBoundary:
    return TeamEvidenceCloudBoundary(
        explicit_user_intent_required=True,
        upload_implemented=False,
        access_control_audit_required=True,
        forbidden_data_classes=_FORBIDDEN_DATA_CLASSES,
        boundary_summary=(
            "This packet is a local readiness view only. Future hosted or team "
            "surfaces must move sanitized artifact references and summaries "
            "after explicit user intent, access-control review, and audit design."
        ),
    )


def _project_from_documents(
    documents: Mapping[TeamEvidenceSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "evidence_bundle",
        "runtime_card",
        "pilot_metrics",
        "handoff",
        "notification_packet",
    ):
        document = documents.get(source_id)
        if not isinstance(document, dict):
            continue
        if source_id == "runtime_card":
            run = document.get("run")
            if isinstance(run, dict):
                project = run.get("project")
                if isinstance(project, str) and project.strip():
                    return _safe_text(project)
            continue
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return _safe_text(project)
    return None


def _schema_version(document: Mapping[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _required_object(
    document: Mapping[str, object],
    field: str,
    *,
    artifact: str,
) -> Mapping[str, object]:
    value = document.get(field)
    if not isinstance(value, dict):
        msg = f"{artifact} {field} must be an object"
        raise TeamEvidenceReadinessError(msg)
    return value


def _required_text(
    document: Mapping[str, object],
    field: str,
    *,
    artifact: str,
) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        msg = f"{artifact} {field} must be a non-empty string"
        raise TeamEvidenceReadinessError(msg)
    return _safe_text(value)


def _required_non_negative_int(
    document: Mapping[str, object],
    field: str,
    *,
    artifact: str,
) -> int:
    value = document.get(field)
    if not isinstance(value, int) or value < 0:
        msg = f"{artifact} {field} must be a non-negative integer"
        raise TeamEvidenceReadinessError(msg)
    return value


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    normalized = value.replace("\\", "&#92;")
    return _escape_backticks(escape(" ".join(normalized.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")


def _packet_json(packet: TeamEvidenceReadinessPacket) -> str:
    return json.dumps(
        packet.model_dump(mode="json", warnings=False, fallback=str),
        default=str,
    )


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)
