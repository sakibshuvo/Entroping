"""Evidence Cloud readiness packets for design-partner pilots."""

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
from entroping.core.evidence.connector_intent import CONNECTOR_INTENT_SCHEMA_VERSION
from entroping.core.evidence.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence.evidence_index_report import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.evidence.pilot_metrics import PILOT_METRICS_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    read_local_evidence_artifact_bytes,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.readiness.devex_readiness import DEVEX_READINESS_SCHEMA_VERSION
from entroping.core.readiness.integration_readiness import INTEGRATION_READINESS_SCHEMA_VERSION
from entroping.core.readiness.team_evidence_readiness import TEAM_EVIDENCE_READINESS_SCHEMA_VERSION
from entroping.core.report_artifact_manifest import REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import (
    SafeWriteError,
    safe_report_output_path,
    safe_write_text,
)

EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION: Final = (
    "entroping.evidence-cloud-readiness.v1"
)

EvidenceCloudReadinessOutput = Literal["md", "json"]
EvidenceCloudReadinessStatus = Literal["ready", "partial", "insufficient"]
EvidenceCloudSourceState = Literal["present", "missing", "invalid", "unsafe"]
EvidenceCloudAreaStatus = Literal["ready", "attention", "blocked"]
EvidenceCloudUploadCandidateState = Literal["ready", "blocked"]
EvidenceCloudNextActionPriority = Literal["high", "medium", "low"]
EvidenceCloudSourceId = Literal[
    "team_evidence_readiness",
    "evidence_bundle",
    "runtime_card",
    "artifact_manifest",
    "design_partner_feedback",
    "pilot_metrics",
    "integration_readiness",
    "devex_readiness",
    "connector_intent",
    "evidence_index",
]
EvidenceCloudAreaId = Literal[
    "team_upload_boundary",
    "runtime_governance_visibility",
    "design_partner_context",
    "integration_connector_surface",
    "developer_experience_surface",
    "cloud_boundary_controls",
]
EvidenceCloudUploadCandidateId = Literal[
    "team_evidence_bundle",
    "runtime_governance_card",
    "integration_surface_packet",
    "developer_experience_packet",
]
EvidenceCloudForbiddenDataClass = Literal[
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
    "design_partner_free_form_text",
    "ticket_payloads",
    "webhook_urls",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[EvidenceCloudReadinessOutput, Path]] = {
    "md": Path("reports") / "evidence-cloud-readiness.md",
    "json": Path("reports") / "evidence-cloud-readiness.json",
}
_FORBIDDEN_DATA_CLASSES: Final[tuple[EvidenceCloudForbiddenDataClass, ...]] = (
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
    "design_partner_free_form_text",
    "ticket_payloads",
    "webhook_urls",
)
_NEXT_COMMANDS_BY_SOURCE: Final[dict[EvidenceCloudSourceId, str]] = {
    "team_evidence_readiness": "entroping report team-evidence-readiness --output json",
    "evidence_bundle": "entroping report evidence-bundle",
    "runtime_card": "entroping report runtime-card --output json",
    "artifact_manifest": "entroping report artifact-manifest",
    "design_partner_feedback": "entroping report design-partner-feedback",
    "pilot_metrics": "entroping report pilot-metrics --output json",
    "integration_readiness": "entroping report integration-readiness --output json",
    "devex_readiness": "entroping report devex-readiness --output json",
    "connector_intent": "entroping report connector-intent --output json",
    "evidence_index": "entroping report evidence-index --output json",
}


class EvidenceCloudReadinessError(ValueError):
    """Raised when Evidence Cloud readiness cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: EvidenceCloudSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: EvidenceCloudSource
    document: dict[str, object] | None


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="team_evidence_readiness",
        label="Team evidence readiness",
        path=Path("reports") / "team-evidence-readiness.json",
        schema_version=TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
    ),
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
        id="artifact_manifest",
        label="Artifact manifest",
        path=Path("reports") / "artifact-manifest.json",
        schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="design_partner_feedback",
        label="Design-partner feedback",
        path=Path("reports") / "design-partner-feedback.json",
        schema_version=DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="pilot_metrics",
        label="Pilot metrics",
        path=Path("reports") / "pilot-metrics.json",
        schema_version=PILOT_METRICS_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="integration_readiness",
        label="Integration readiness",
        path=Path("reports") / "integration-readiness.json",
        schema_version=INTEGRATION_READINESS_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="devex_readiness",
        label="Developer experience readiness",
        path=Path("reports") / "devex-readiness.json",
        schema_version=DEVEX_READINESS_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="connector_intent",
        label="Connector intent",
        path=Path("reports") / "connector-intent.json",
        schema_version=CONNECTOR_INTENT_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="evidence_index",
        label="Evidence index",
        path=Path("reports") / "evidence-index.json",
        schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
    ),
)


class EvidenceCloudSummary(BaseModel):
    """Aggregate Evidence Cloud readiness status."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceCloudReadinessStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    areas_total: int = Field(ge=0)
    areas_ready: int = Field(ge=0)
    areas_attention: int = Field(ge=0)
    areas_blocked: int = Field(ge=0)
    upload_candidates_total: int = Field(ge=0)
    upload_candidates_ready: int = Field(ge=0)
    upload_candidates_blocked: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidenceCloudSource(BaseModel):
    """One sanitized local artifact used for Evidence Cloud readiness."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudSourceId
    label: str
    path: str
    state: EvidenceCloudSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class EvidenceCloudReadinessArea(BaseModel):
    """One Evidence Cloud readiness area derived from local artifacts."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudAreaId
    label: str
    status: EvidenceCloudAreaStatus
    source_ids: tuple[EvidenceCloudSourceId, ...]
    boundary: str
    upload_candidate: bool
    blockers: tuple[str, ...] = ()
    next_action: str


class EvidenceCloudBoundary(BaseModel):
    """Boundary controls before any hosted Evidence Cloud surface exists."""

    model_config = ConfigDict(extra="forbid")

    explicit_user_intent_required: bool
    upload_implemented: bool
    hosted_sync_implemented: bool
    access_control_audit_required: bool
    forbidden_data_classes: tuple[EvidenceCloudForbiddenDataClass, ...]
    boundary_summary: str


class EvidenceCloudUploadCandidate(BaseModel):
    """One value-free source group that could later become an upload packet."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudUploadCandidateId
    label: str
    state: EvidenceCloudUploadCandidateState
    source_ids: tuple[EvidenceCloudSourceId, ...]
    description: str
    blockers: tuple[str, ...] = ()


class EvidenceCloudNextAction(BaseModel):
    """One local action before Evidence Cloud promotion."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidenceCloudNextActionPriority
    action: str
    source_ids: tuple[EvidenceCloudSourceId, ...] = ()
    area_ids: tuple[EvidenceCloudAreaId, ...] = ()


class EvidenceCloudReadinessPacket(BaseModel):
    """Schema-versioned local Evidence Cloud readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-cloud-readiness.v1"] = (
        EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: EvidenceCloudSummary
    cloud_boundary: EvidenceCloudBoundary
    sources: tuple[EvidenceCloudSource, ...]
    readiness_areas: tuple[EvidenceCloudReadinessArea, ...]
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...]
    next_actions: tuple[EvidenceCloudNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCloudReadinessResult:
    """Result of writing one Evidence Cloud readiness packet."""

    output_path: Path
    packet: EvidenceCloudReadinessPacket


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _AreaCounts:
    ready: int
    attention: int
    blocked: int


@dataclass(frozen=True, slots=True)
class _CandidateCounts:
    ready: int
    blocked: int


def run_evidence_cloud_readiness_report(
    *,
    project_root: Path,
    output: EvidenceCloudReadinessOutput,
    output_path: Path | None = None,
) -> EvidenceCloudReadinessResult:
    """Write a local Evidence Cloud readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-cloud-readiness output: {output}"
        raise EvidenceCloudReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_cloud_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "Evidence Cloud readiness packet contains secret-like content"
        raise EvidenceCloudReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="Evidence Cloud readiness packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceCloudReadinessError(str(exc)) from exc
    return EvidenceCloudReadinessResult(output_path=written, packet=packet)


def build_evidence_cloud_readiness(*, project_root: Path) -> EvidenceCloudReadinessPacket:
    """Build a value-free Evidence Cloud readiness packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "Evidence Cloud readiness packet contains secret-like content"
        raise EvidenceCloudReadinessError(msg)
    return packet


def render_evidence_cloud_readiness_markdown(
    packet: EvidenceCloudReadinessPacket,
) -> str:
    """Render a human-readable Evidence Cloud readiness packet."""

    lines = [
        "# Entroping Evidence Cloud Readiness",
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
        "- Upload candidates: "
        f"`{packet.summary.upload_candidates_ready}/"
        f"{packet.summary.upload_candidates_total}` ready, "
        f"`{packet.summary.upload_candidates_blocked}` blocked",
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
        "| hosted_sync_implemented | "
        f"{_markdown_cell(str(packet.cloud_boundary.hosted_sync_implemented))} |",
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
            "| Area | Status | Sources | Upload Candidate | Blockers | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for area in packet.readiness_areas:
        lines.append(
            "| "
            f"{_markdown_cell(area.id)} | "
            f"{_markdown_cell(area.status)} | "
            f"{_markdown_cell(', '.join(area.source_ids))} | "
            f"{_markdown_cell(str(area.upload_candidate))} | "
            f"{_markdown_cell('; '.join(area.blockers) or 'none')} | "
            f"{_markdown_cell(area.next_action)} |"
        )

    lines.extend(
        [
            "",
            "## Upload Candidates",
            "",
            "| Candidate | State | Sources | Blockers | Description |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for candidate in packet.upload_candidates:
        lines.append(
            "| "
            f"{_markdown_cell(candidate.id)} | "
            f"{_markdown_cell(candidate.state)} | "
            f"{_markdown_cell(', '.join(candidate.source_ids))} | "
            f"{_markdown_cell('; '.join(candidate.blockers) or 'none')} | "
            f"{_markdown_cell(candidate.description)} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No Evidence Cloud readiness actions are currently needed.")
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


def _build_packet(*, root: Path) -> EvidenceCloudReadinessPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    areas = _readiness_areas(sources=sources)
    upload_candidates = _upload_candidates(sources=sources)
    next_actions = _next_actions(
        sources=sources,
        areas=areas,
        upload_candidates=upload_candidates,
    )
    return EvidenceCloudReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(
            sources=sources,
            areas=areas,
            upload_candidates=upload_candidates,
            next_actions=next_actions,
        ),
        cloud_boundary=_cloud_boundary(),
        sources=sources,
        readiness_areas=areas,
        upload_candidates=upload_candidates,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: EvidenceCloudReadinessPacket,
    *,
    output: EvidenceCloudReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_cloud_readiness_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    try:
        path = _resolve_source_path(definition.path, root=root)
    except EvidenceCloudReadinessError as exc:
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
    except EvidenceCloudReadinessError as exc:
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
    except EvidenceCloudReadinessError as exc:
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
    state: EvidenceCloudSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=EvidenceCloudSource(
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
    try:
        symlink_path = first_symlink_path_component(candidate, root=root)
    except ValueError as exc:
        msg = "Evidence Cloud readiness source path must stay under the project root"
        raise EvidenceCloudReadinessError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"Evidence Cloud readiness source path uses symlinked component: {display_path}"
        raise EvidenceCloudReadinessError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = "Evidence Cloud readiness source path must stay under the project root"
        raise EvidenceCloudReadinessError(msg) from exc
    if resolved.exists() and not resolved.is_file():
        msg = f"Evidence Cloud readiness source path is not a file: {raw_path.as_posix()}"
        raise EvidenceCloudReadinessError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(
            raw_path,
            root=root,
            artifact="Evidence Cloud readiness packet",
        )
    except SafeWriteError as exc:
        msg = str(exc)
        raise EvidenceCloudReadinessError(msg) from exc


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    raw_bytes, load_error = _read_source_artifact_bytes(path)
    if raw_bytes is None:
        msg = f"Could not read {artifact}: {load_error}"
        raise EvidenceCloudReadinessError(msg)
    return raw_bytes


def _read_source_artifact_bytes(path: Path) -> tuple[bytes | None, str]:
    return read_local_evidence_artifact_bytes(
        path,
        max_bytes=_MAX_SOURCE_BYTES,
    )


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise EvidenceCloudReadinessError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise EvidenceCloudReadinessError(msg)
    return document


def _source_summary(
    definition: _SourceDefinition,
    document: Mapping[str, object],
) -> str:
    if definition.id == "design_partner_feedback":
        evidence = _object_field(document, "evidence")
        bundle = _text_field(evidence, "evidence_bundle_status") or "unknown"
        runtime = _text_field(evidence, "runtime_card_status") or "unknown"
        return f"bundle {bundle}; runtime {runtime}"
    summary = _object_field(document, "summary")
    status = _text_field(summary, "status") or "summary available"
    if definition.id == "team_evidence_readiness":
        present = _int_field(summary, "sources_present")
        total = _int_field(summary, "sources_total")
        if present is not None and total is not None:
            return f"{status}; {present}/{total} sources present"
    if definition.id == "artifact_manifest":
        present = _int_field(summary, "total_present")
        missing = _int_field(summary, "total_missing")
        if present is not None and missing is not None:
            return f"{present} present; {missing} missing"
    return status


def _readiness_areas(
    *,
    sources: tuple[EvidenceCloudSource, ...],
) -> tuple[EvidenceCloudReadinessArea, ...]:
    by_id = {source.id: source for source in sources}
    return (
        _area(
            "team_upload_boundary",
            label="Team upload boundary",
            source_ids=("team_evidence_readiness", "evidence_bundle", "artifact_manifest"),
            by_id=by_id,
            upload_candidate=True,
        ),
        _area(
            "runtime_governance_visibility",
            label="Runtime governance visibility",
            source_ids=("runtime_card", "evidence_index"),
            by_id=by_id,
            upload_candidate=True,
        ),
        _area(
            "design_partner_context",
            label="Design-partner context",
            source_ids=("design_partner_feedback", "pilot_metrics"),
            by_id=by_id,
            upload_candidate=False,
        ),
        _area(
            "integration_connector_surface",
            label="Integration and connector surface",
            source_ids=("integration_readiness", "connector_intent"),
            by_id=by_id,
            upload_candidate=True,
        ),
        _area(
            "developer_experience_surface",
            label="Developer experience surface",
            source_ids=("devex_readiness",),
            by_id=by_id,
            upload_candidate=True,
        ),
        _cloud_controls_area(by_id=by_id),
    )


def _area(
    area_id: EvidenceCloudAreaId,
    *,
    label: str,
    source_ids: tuple[EvidenceCloudSourceId, ...],
    by_id: Mapping[EvidenceCloudSourceId, EvidenceCloudSource],
    upload_candidate: bool,
) -> EvidenceCloudReadinessArea:
    selected = tuple(by_id[source_id] for source_id in source_ids)
    blockers = _source_blockers(selected)
    status = _area_status(selected)
    return EvidenceCloudReadinessArea(
        id=area_id,
        label=label,
        status=status,
        source_ids=source_ids,
        boundary=(
            "Future Evidence Cloud surfaces may reference only sanitized packet "
            "metadata after explicit user intent and access-control review."
        ),
        upload_candidate=upload_candidate,
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
    by_id: Mapping[EvidenceCloudSourceId, EvidenceCloudSource],
) -> EvidenceCloudReadinessArea:
    unsafe_or_invalid = tuple(
        source for source in by_id.values() if source.state in {"invalid", "unsafe"}
    )
    blockers = _source_blockers(unsafe_or_invalid)
    status: EvidenceCloudAreaStatus = "blocked" if blockers else "ready"
    return EvidenceCloudReadinessArea(
        id="cloud_boundary_controls",
        label="Cloud boundary controls",
        status=status,
        source_ids=tuple(by_id),
        boundary=(
            "Evidence Cloud work remains local-only until upload intent, access "
            "control, audit, and value-free data boundaries are implemented."
        ),
        upload_candidate=False,
        blockers=blockers,
        next_action=(
            "Repair unsafe or invalid evidence before any Evidence Cloud pilot."
            if blockers
            else "Keep Evidence Cloud promotion explicit, audited, and value-free."
        ),
    )


def _upload_candidates(
    *,
    sources: tuple[EvidenceCloudSource, ...],
) -> tuple[EvidenceCloudUploadCandidate, ...]:
    by_id = {source.id: source for source in sources}
    definitions: tuple[
        tuple[
            EvidenceCloudUploadCandidateId,
            str,
            tuple[EvidenceCloudSourceId, ...],
            str,
        ],
        ...,
    ] = (
        (
            "team_evidence_bundle",
            "Team evidence bundle",
            ("team_evidence_readiness", "evidence_bundle", "artifact_manifest"),
            "Sanitized team evidence readiness, bundle, and manifest metadata.",
        ),
        (
            "runtime_governance_card",
            "Runtime governance card",
            ("runtime_card", "evidence_index"),
            "Value-free runtime governance and evidence-navigation metadata.",
        ),
        (
            "integration_surface_packet",
            "Integration surface packet",
            ("integration_readiness", "connector_intent"),
            "Read-only connector and integration intent metadata.",
        ),
        (
            "developer_experience_packet",
            "Developer experience packet",
            ("devex_readiness",),
            "Read-only CLI/editor/workbench/cloud surface readiness metadata.",
        ),
    )
    candidates: list[EvidenceCloudUploadCandidate] = []
    for candidate_id, label, source_ids, description in definitions:
        selected = tuple(by_id[source_id] for source_id in source_ids)
        blockers = _source_blockers(selected)
        candidates.append(
            EvidenceCloudUploadCandidate(
                id=candidate_id,
                label=label,
                state="blocked" if blockers else "ready",
                source_ids=source_ids,
                description=description,
                blockers=blockers,
            )
        )
    return tuple(candidates)


def _area_status(
    sources: tuple[EvidenceCloudSource, ...],
) -> EvidenceCloudAreaStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "blocked"
    if all(source.state == "present" for source in sources):
        return "ready"
    return "attention"


def _source_blockers(sources: tuple[EvidenceCloudSource, ...]) -> tuple[str, ...]:
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
    status: EvidenceCloudAreaStatus,
    source_ids: tuple[EvidenceCloudSourceId, ...],
    blockers: tuple[str, ...],
) -> str:
    if status == "ready":
        return f"{label} evidence is ready for local Evidence Cloud pilot review."
    commands = tuple(_NEXT_COMMANDS_BY_SOURCE[source_id] for source_id in source_ids)
    if blockers:
        return f"Resolve {label} blockers, then run: {'; '.join(commands)}."
    return f"Generate {label} evidence with: {'; '.join(commands)}."


def _next_actions(
    *,
    sources: tuple[EvidenceCloudSource, ...],
    areas: tuple[EvidenceCloudReadinessArea, ...],
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...],
) -> tuple[EvidenceCloudNextAction, ...]:
    actions: list[EvidenceCloudNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: EvidenceCloudNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            EvidenceCloudNextAction(
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
        actions.append(
            EvidenceCloudNextAction(
                priority="high" if area.status == "blocked" else "medium",
                action=area.next_action,
                source_ids=area.source_ids,
                area_ids=(area.id,),
            )
        )
    for candidate in upload_candidates:
        if candidate.state == "ready":
            continue
        actions.append(
            EvidenceCloudNextAction(
                priority="medium",
                action=f"Complete {candidate.label} before Evidence Cloud export.",
                source_ids=candidate.source_ids,
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: list[EvidenceCloudNextAction],
) -> tuple[EvidenceCloudNextAction, ...]:
    seen: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[EvidenceCloudNextAction] = []
    for action in actions:
        key = (action.priority, action.action, action.source_ids, action.area_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[EvidenceCloudSource, ...],
    areas: tuple[EvidenceCloudReadinessArea, ...],
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...],
    next_actions: tuple[EvidenceCloudNextAction, ...],
) -> EvidenceCloudSummary:
    source_counts = _source_counts(sources)
    area_counts = _area_counts(areas)
    candidate_counts = _candidate_counts(upload_candidates)
    blockers_total = len(_unique_blockers(areas=areas, upload_candidates=upload_candidates))
    return EvidenceCloudSummary(
        status=_status(sources=sources, areas=areas, upload_candidates=upload_candidates),
        sources_total=len(sources),
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        areas_total=len(areas),
        areas_ready=area_counts.ready,
        areas_attention=area_counts.attention,
        areas_blocked=area_counts.blocked,
        upload_candidates_total=len(upload_candidates),
        upload_candidates_ready=candidate_counts.ready,
        upload_candidates_blocked=candidate_counts.blocked,
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _source_counts(sources: tuple[EvidenceCloudSource, ...]) -> _SourceCounts:
    return _SourceCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _area_counts(areas: tuple[EvidenceCloudReadinessArea, ...]) -> _AreaCounts:
    return _AreaCounts(
        ready=sum(1 for area in areas if area.status == "ready"),
        attention=sum(1 for area in areas if area.status == "attention"),
        blocked=sum(1 for area in areas if area.status == "blocked"),
    )


def _candidate_counts(
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...],
) -> _CandidateCounts:
    return _CandidateCounts(
        ready=sum(1 for candidate in upload_candidates if candidate.state == "ready"),
        blocked=sum(1 for candidate in upload_candidates if candidate.state == "blocked"),
    )


def _unique_blockers(
    *,
    areas: tuple[EvidenceCloudReadinessArea, ...],
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...],
) -> frozenset[str]:
    return frozenset(
        {blocker for area in areas for blocker in area.blockers}
        | {blocker for candidate in upload_candidates for blocker in candidate.blockers}
    )


def _status(
    *,
    sources: tuple[EvidenceCloudSource, ...],
    areas: tuple[EvidenceCloudReadinessArea, ...],
    upload_candidates: tuple[EvidenceCloudUploadCandidate, ...],
) -> EvidenceCloudReadinessStatus:
    if (
        sources
        and all(source.state == "present" for source in sources)
        and all(area.status == "ready" for area in areas)
        and all(candidate.state == "ready" for candidate in upload_candidates)
    ):
        return "ready"
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _cloud_boundary() -> EvidenceCloudBoundary:
    return EvidenceCloudBoundary(
        explicit_user_intent_required=True,
        upload_implemented=False,
        hosted_sync_implemented=False,
        access_control_audit_required=True,
        forbidden_data_classes=_FORBIDDEN_DATA_CLASSES,
        boundary_summary=(
            "This packet is a local Evidence Cloud readiness view only. Future "
            "hosted surfaces must move sanitized artifact references and compact "
            "summaries after explicit user intent, access-control review, and "
            "audit design."
        ),
    )


def _project_from_documents(
    documents: Mapping[EvidenceCloudSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "team_evidence_readiness",
        "runtime_card",
        "evidence_bundle",
        "integration_readiness",
        "devex_readiness",
        "connector_intent",
        "pilot_metrics",
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
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return _safe_text(project)
    return None


def _schema_version(document: Mapping[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _object_field(document: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = document.get(field)
    return value if isinstance(value, dict) else {}


def _text_field(document: Mapping[str, object], field: str) -> str | None:
    value = document.get(field)
    if isinstance(value, str) and value.strip():
        return _safe_text(value)
    return None


def _int_field(document: Mapping[str, object], field: str) -> int | None:
    value = document.get(field)
    return value if isinstance(value, int) and value >= 0 else None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    escaped = escape(" ".join(value.split())).replace("\\", "&#92;")
    return _escape_backticks(escaped.replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")


def _packet_json(packet: EvidenceCloudReadinessPacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", warnings=False, fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json", warnings=False)
        return json.dumps(payload)
    except Exception as exc:
        msg = "Evidence Cloud readiness packet could not be serialized safely"
        raise EvidenceCloudReadinessError(msg) from exc


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)
