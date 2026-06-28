"""Team access-control and audit planning packets."""

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

from entroping.core.evidence.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.evidence.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.readiness.team_evidence_readiness import (
    TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
)
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION: Final = "entroping.team-access-control-plan.v1"

TeamAccessControlPlanOutput = Literal["md", "json"]
TeamAccessControlPlanStatus = Literal["ready", "partial", "insufficient"]
TeamAccessControlSourceState = Literal["present", "missing", "invalid", "unsafe"]
TeamAccessControlRoleStatus = Literal["ready", "attention", "blocked"]
TeamAccessControlNextActionPriority = Literal["high", "medium", "low"]
TeamAccessControlSourceId = Literal[
    "team_evidence_readiness",
    "handoff",
    "notification_packet",
    "runtime_card",
]
TeamAccessControlRoleId = Literal[
    "owner",
    "maintainer",
    "reviewer",
    "observer",
    "external_design_partner",
]
TeamAccessControlAllowedAction = Literal[
    "view_value_free_evidence",
    "share_evidence_link",
    "acknowledge_status",
    "plan_follow_up_assignment",
]
TeamAccessControlForbiddenAction = Literal[
    "override_hurl_qanstitution_result",
    "view_raw_traffic",
    "view_source_hurl",
    "view_provider_transcripts",
    "view_secrets_or_env",
    "silent_upload",
    "mutate_tickets_or_chat",
]
TeamAccessControlForbiddenDataClass = Literal[
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
]
TeamAccessControlAuditEventId = Literal[
    "evidence_viewed",
    "evidence_link_shared",
    "status_acknowledged",
    "follow_up_assignment_planned",
    "access_policy_reviewed",
    "upload_intent_recorded",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[TeamAccessControlPlanOutput, Path]] = {
    "md": Path("reports") / "team-access-control-plan.md",
    "json": Path("reports") / "team-access-control-plan.json",
}
_PRIMARY_SOURCE: Final[TeamAccessControlSourceId] = "team_evidence_readiness"
_FORBIDDEN_ACTIONS: Final[tuple[TeamAccessControlForbiddenAction, ...]] = (
    "override_hurl_qanstitution_result",
    "view_raw_traffic",
    "view_source_hurl",
    "view_provider_transcripts",
    "view_secrets_or_env",
    "silent_upload",
    "mutate_tickets_or_chat",
)
_FORBIDDEN_DATA_CLASSES: Final[tuple[TeamAccessControlForbiddenDataClass, ...]] = (
    "raw_traffic",
    "secrets",
    "source_hurl",
    "env_values",
    "prompts",
    "provider_outputs",
    "full_report_contents",
)


class TeamAccessControlPlanError(ValueError):
    """Raised when a team access-control plan cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: TeamAccessControlSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: TeamAccessControlSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _RoleDefinition:
    id: TeamAccessControlRoleId
    label: str
    allowed_actions: tuple[TeamAccessControlAllowedAction, ...]
    evidence_scope: str
    audit_event_ids: tuple[TeamAccessControlAuditEventId, ...]


@dataclass(frozen=True, slots=True)
class _AuditEventDefinition:
    id: TeamAccessControlAuditEventId
    label: str
    trigger: str
    required_fields: tuple[str, ...]


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="team_evidence_readiness",
        label="Team evidence readiness",
        path=Path("reports") / "team-evidence-readiness.json",
        schema_version=TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
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
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version=RUNTIME_CARD_SCHEMA_VERSION,
    ),
)
_ROLE_DEFINITIONS: Final[tuple[_RoleDefinition, ...]] = (
    _RoleDefinition(
        id="owner",
        label="Owner",
        allowed_actions=(
            "view_value_free_evidence",
            "share_evidence_link",
            "acknowledge_status",
            "plan_follow_up_assignment",
        ),
        evidence_scope="Can review all sanitized evidence references and plan policy changes.",
        audit_event_ids=(
            "evidence_viewed",
            "evidence_link_shared",
            "status_acknowledged",
            "follow_up_assignment_planned",
            "access_policy_reviewed",
            "upload_intent_recorded",
        ),
    ),
    _RoleDefinition(
        id="maintainer",
        label="Maintainer",
        allowed_actions=(
            "view_value_free_evidence",
            "share_evidence_link",
            "acknowledge_status",
            "plan_follow_up_assignment",
        ),
        evidence_scope="Can review sanitized evidence and plan local follow-up work.",
        audit_event_ids=(
            "evidence_viewed",
            "evidence_link_shared",
            "status_acknowledged",
            "follow_up_assignment_planned",
        ),
    ),
    _RoleDefinition(
        id="reviewer",
        label="Reviewer",
        allowed_actions=(
            "view_value_free_evidence",
            "acknowledge_status",
            "plan_follow_up_assignment",
        ),
        evidence_scope="Can review sanitized evidence and plan review follow-up.",
        audit_event_ids=(
            "evidence_viewed",
            "status_acknowledged",
            "follow_up_assignment_planned",
        ),
    ),
    _RoleDefinition(
        id="observer",
        label="Observer",
        allowed_actions=("view_value_free_evidence", "acknowledge_status"),
        evidence_scope="Can view value-free evidence status and acknowledge receipt.",
        audit_event_ids=("evidence_viewed", "status_acknowledged"),
    ),
    _RoleDefinition(
        id="external_design_partner",
        label="External design partner",
        allowed_actions=("view_value_free_evidence", "acknowledge_status"),
        evidence_scope=("Can view sanitized design-partner evidence links and acknowledge status."),
        audit_event_ids=("evidence_viewed", "status_acknowledged"),
    ),
)
_AUDIT_EVENT_DEFINITIONS: Final[tuple[_AuditEventDefinition, ...]] = (
    _AuditEventDefinition(
        id="evidence_viewed",
        label="Evidence viewed",
        trigger="A future team surface renders a sanitized evidence link or summary.",
        required_fields=("actor_role", "artifact_id", "schema_version", "timestamp"),
    ),
    _AuditEventDefinition(
        id="evidence_link_shared",
        label="Evidence link shared",
        trigger="A future team surface shares a sanitized evidence link.",
        required_fields=("actor_role", "target_surface", "artifact_id", "timestamp"),
    ),
    _AuditEventDefinition(
        id="status_acknowledged",
        label="Status acknowledged",
        trigger="A future team member acknowledges value-free evidence status.",
        required_fields=("actor_role", "status", "artifact_id", "timestamp"),
    ),
    _AuditEventDefinition(
        id="follow_up_assignment_planned",
        label="Follow-up assignment planned",
        trigger="A future team surface plans follow-up ownership without write-back.",
        required_fields=("actor_role", "follow_up_type", "artifact_id", "timestamp"),
    ),
    _AuditEventDefinition(
        id="access_policy_reviewed",
        label="Access policy reviewed",
        trigger="A future owner reviews access policy before enabling hosted evidence.",
        required_fields=("actor_role", "policy_version", "decision", "timestamp"),
    ),
    _AuditEventDefinition(
        id="upload_intent_recorded",
        label="Upload intent recorded",
        trigger="A future owner explicitly requests a sanitized evidence upload.",
        required_fields=("actor_role", "artifact_id", "intent", "timestamp"),
    ),
)
_NEXT_COMMANDS_BY_SOURCE: Final[dict[TeamAccessControlSourceId, str]] = {
    "team_evidence_readiness": "entroping report team-evidence-readiness --output json",
    "handoff": "entroping report handoff --output json",
    "notification_packet": "entroping report notification-packet --output json",
    "runtime_card": "entroping report runtime-card --output json",
}


class TeamAccessControlPlanSummary(BaseModel):
    """Aggregate team access-control plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: TeamAccessControlPlanStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    roles_total: int = Field(ge=0)
    roles_ready: int = Field(ge=0)
    roles_attention: int = Field(ge=0)
    roles_blocked: int = Field(ge=0)
    audit_events_total: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class TeamAccessControlSource(BaseModel):
    """One local source artifact used for access-control planning."""

    model_config = ConfigDict(extra="forbid")

    id: TeamAccessControlSourceId
    label: str
    path: str
    state: TeamAccessControlSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class TeamAccessControlBoundary(BaseModel):
    """Non-implementation boundaries for future team access control."""

    model_config = ConfigDict(extra="forbid")

    explicit_user_intent_required: bool
    upload_implemented: bool
    access_control_enforced: bool
    write_back_implemented: bool
    pass_fail_override_allowed: bool
    forbidden_data_classes: tuple[TeamAccessControlForbiddenDataClass, ...]
    boundary_summary: str


class TeamAccessControlRolePlan(BaseModel):
    """One proposed future team role boundary."""

    model_config = ConfigDict(extra="forbid")

    id: TeamAccessControlRoleId
    label: str
    status: TeamAccessControlRoleStatus
    allowed_actions: tuple[TeamAccessControlAllowedAction, ...]
    forbidden_actions: tuple[TeamAccessControlForbiddenAction, ...]
    evidence_scope: str
    audit_event_ids: tuple[TeamAccessControlAuditEventId, ...]
    blockers: tuple[str, ...] = ()
    next_action: str


class TeamAccessControlAuditEvent(BaseModel):
    """One required future audit event design row."""

    model_config = ConfigDict(extra="forbid")

    id: TeamAccessControlAuditEventId
    label: str
    trigger: str
    required_fields: tuple[str, ...]
    forbidden_fields: tuple[TeamAccessControlForbiddenDataClass, ...]


class TeamAccessControlNextAction(BaseModel):
    """One local command or governance action before future team access control."""

    model_config = ConfigDict(extra="forbid")

    priority: TeamAccessControlNextActionPriority
    action: str
    source_ids: tuple[TeamAccessControlSourceId, ...] = ()
    role_ids: tuple[TeamAccessControlRoleId, ...] = ()
    audit_event_ids: tuple[TeamAccessControlAuditEventId, ...] = ()


class TeamAccessControlPlanPacket(BaseModel):
    """Schema-versioned local team access-control plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.team-access-control-plan.v1"] = (
        TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: TeamAccessControlPlanSummary
    boundary: TeamAccessControlBoundary
    sources: tuple[TeamAccessControlSource, ...]
    roles: tuple[TeamAccessControlRolePlan, ...]
    audit_events: tuple[TeamAccessControlAuditEvent, ...]
    next_actions: tuple[TeamAccessControlNextAction, ...]


@dataclass(frozen=True, slots=True)
class TeamAccessControlPlanResult:
    """Result of writing one team access-control plan packet."""

    output_path: Path
    packet: TeamAccessControlPlanPacket


def run_team_access_control_plan_report(
    *,
    project_root: Path,
    output: TeamAccessControlPlanOutput,
    output_path: Path | None = None,
) -> TeamAccessControlPlanResult:
    """Write a local team access-control planning packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported team-access-control-plan output: {output}"
        raise TeamAccessControlPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_team_access_control_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "team access-control plan packet contains secret-like content"
        raise TeamAccessControlPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="team access-control plan packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise TeamAccessControlPlanError(str(exc)) from exc
    return TeamAccessControlPlanResult(output_path=written, packet=packet)


def build_team_access_control_plan(*, project_root: Path) -> TeamAccessControlPlanPacket:
    """Build a value-free team access-control plan packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "team access-control plan packet contains secret-like content"
        raise TeamAccessControlPlanError(msg)
    return packet


def render_team_access_control_plan_markdown(
    packet: TeamAccessControlPlanPacket,
) -> str:
    """Render a human-readable team access-control plan packet."""

    lines = [
        "# Entroping Team Access-Control Plan",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Roles: "
        f"`{packet.summary.roles_ready}/{packet.summary.roles_total}` ready, "
        f"`{packet.summary.roles_attention}` attention, "
        f"`{packet.summary.roles_blocked}` blocked",
        f"- Audit events: `{packet.summary.audit_events_total}`",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Boundary",
        "",
        "| Control | Value |",
        "| --- | --- |",
        "| explicit_user_intent_required | "
        f"{_markdown_cell(str(packet.boundary.explicit_user_intent_required))} |",
        f"| upload_implemented | {_markdown_cell(str(packet.boundary.upload_implemented))} |",
        "| access_control_enforced | "
        f"{_markdown_cell(str(packet.boundary.access_control_enforced))} |",
        "| write_back_implemented | "
        f"{_markdown_cell(str(packet.boundary.write_back_implemented))} |",
        "| pass_fail_override_allowed | "
        f"{_markdown_cell(str(packet.boundary.pass_fail_override_allowed))} |",
        "| forbidden_data_classes | "
        f"{_markdown_cell(', '.join(packet.boundary.forbidden_data_classes))} |",
        f"| boundary_summary | {_markdown_cell(packet.boundary.boundary_summary)} |",
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
            "## Roles",
            "",
            "| Role | Status | Allowed Actions | Forbidden Actions | Audit Events | "
            "Blockers | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for role in packet.roles:
        lines.append(
            "| "
            f"{_markdown_cell(role.id)} | "
            f"{_markdown_cell(role.status)} | "
            f"{_markdown_cell(', '.join(role.allowed_actions))} | "
            f"{_markdown_cell(', '.join(role.forbidden_actions))} | "
            f"{_markdown_cell(', '.join(role.audit_event_ids))} | "
            f"{_markdown_cell('; '.join(role.blockers) or 'none')} | "
            f"{_markdown_cell(role.next_action)} |"
        )

    lines.extend(
        [
            "",
            "## Audit Events",
            "",
            "| Event | Trigger | Required Fields | Forbidden Fields |",
            "| --- | --- | --- | --- |",
        ]
    )
    for event in packet.audit_events:
        lines.append(
            "| "
            f"{_markdown_cell(event.id)} | "
            f"{_markdown_cell(event.trigger)} | "
            f"{_markdown_cell(', '.join(event.required_fields))} | "
            f"{_markdown_cell(', '.join(event.forbidden_fields))} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No team access-control actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Sources | Roles | Audit Events |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.role_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.audit_event_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_packet(*, root: Path) -> TeamAccessControlPlanPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    roles = _role_plans(sources=sources)
    audit_events = _audit_events()
    next_actions = _next_actions(sources=sources, roles=roles)
    return TeamAccessControlPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(sources=sources, roles=roles, next_actions=next_actions),
        boundary=_boundary(),
        sources=sources,
        roles=roles,
        audit_events=audit_events,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: TeamAccessControlPlanPacket,
    *,
    output: TeamAccessControlPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_team_access_control_plan_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    schema_version: str | None = None
    try:
        path = _resolve_source_path(definition.path, root=root)
    except TeamAccessControlPlanError as exc:
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
    except TeamAccessControlPlanError as exc:
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
    except TeamAccessControlPlanError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=schema_version,
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
    state: TeamAccessControlSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=TeamAccessControlSource(
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
        msg = f"team access-control source path uses symlinked component: {display_path}"
        raise TeamAccessControlPlanError(msg)
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"team access-control source path is not a file: {raw_path.as_posix()}"
        raise TeamAccessControlPlanError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "team access-control plan output path must stay under the project root"
        raise TeamAccessControlPlanError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"team access-control plan output path uses symlinked component: {display_path}"
        raise TeamAccessControlPlanError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "team access-control plan output path must stay under the project root"
        raise TeamAccessControlPlanError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "team access-control plan packet must not be written into .entroping or envs"
        raise TeamAccessControlPlanError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    try:
        with path.open("rb") as handle:
            raw_bytes = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise TeamAccessControlPlanError(msg) from exc
    if len(raw_bytes) > _MAX_SOURCE_BYTES:
        msg = f"{artifact.capitalize()} {path.name} exceeds {_MAX_SOURCE_BYTES} bytes"
        raise TeamAccessControlPlanError(msg)
    return raw_bytes


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise TeamAccessControlPlanError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise TeamAccessControlPlanError(msg)
    return document


def _source_summary(
    definition: _SourceDefinition,
    document: Mapping[str, object],
) -> str:
    if definition.id == "team_evidence_readiness":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        sources_present = _required_non_negative_int(
            summary,
            "sources_present",
            artifact=definition.label,
        )
        sources_total = _required_non_negative_int(
            summary,
            "sources_total",
            artifact=definition.label,
        )
        areas_ready = _required_non_negative_int(
            summary,
            "areas_ready",
            artifact=definition.label,
        )
        areas_total = _required_non_negative_int(
            summary,
            "areas_total",
            artifact=definition.label,
        )
        return (
            f"{status}; {sources_present}/{sources_total} sources present; "
            f"{areas_ready}/{areas_total} areas ready"
        )
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
    if definition.id == "notification_packet":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        severity = _required_text(summary, "severity", artifact=definition.label)
        return f"{status}; {severity} severity"
    summary = _required_object(document, "summary", artifact=definition.label)
    status = _required_text(summary, "status", artifact=definition.label)
    findings = _required_non_negative_int(summary, "findings", artifact=definition.label)
    return f"{status}; {findings} findings"


def _role_plans(
    *,
    sources: tuple[TeamAccessControlSource, ...],
) -> tuple[TeamAccessControlRolePlan, ...]:
    source_by_id = {source.id: source for source in sources}
    status = _role_status(source_by_id)
    blockers = _role_blockers(source_by_id)
    return tuple(
        TeamAccessControlRolePlan(
            id=definition.id,
            label=definition.label,
            status=status,
            allowed_actions=definition.allowed_actions,
            forbidden_actions=_FORBIDDEN_ACTIONS,
            evidence_scope=definition.evidence_scope,
            audit_event_ids=definition.audit_event_ids,
            blockers=blockers,
            next_action=_role_next_action(
                role_label=definition.label,
                status=status,
                blockers=blockers,
            ),
        )
        for definition in _ROLE_DEFINITIONS
    )


def _role_status(
    source_by_id: Mapping[TeamAccessControlSourceId, TeamAccessControlSource],
) -> TeamAccessControlRoleStatus:
    if any(source.state in {"invalid", "unsafe"} for source in source_by_id.values()):
        return "blocked"
    primary = source_by_id[_PRIMARY_SOURCE]
    if primary.state == "present":
        return "ready"
    return "attention"


def _role_blockers(
    source_by_id: Mapping[TeamAccessControlSourceId, TeamAccessControlSource],
) -> tuple[str, ...]:
    blockers: list[str] = []
    primary = source_by_id[_PRIMARY_SOURCE]
    if primary.state == "missing":
        blockers.append("Team evidence readiness is missing.")
    for source in source_by_id.values():
        if source.state in {"invalid", "unsafe"}:
            blockers.append(f"{source.label} is {source.state}: {source.summary}")
    return tuple(blockers)


def _role_next_action(
    *,
    role_label: str,
    status: TeamAccessControlRoleStatus,
    blockers: tuple[str, ...],
) -> str:
    if status == "ready":
        return f"{role_label} access-control plan is ready for local review."
    if blockers:
        return "Repair access-control source blockers before planning team access."
    return "Generate team evidence readiness before planning team access."


def _audit_events() -> tuple[TeamAccessControlAuditEvent, ...]:
    return tuple(
        TeamAccessControlAuditEvent(
            id=definition.id,
            label=definition.label,
            trigger=definition.trigger,
            required_fields=definition.required_fields,
            forbidden_fields=_FORBIDDEN_DATA_CLASSES,
        )
        for definition in _AUDIT_EVENT_DEFINITIONS
    )


def _next_actions(
    *,
    sources: tuple[TeamAccessControlSource, ...],
    roles: tuple[TeamAccessControlRolePlan, ...],
) -> tuple[TeamAccessControlNextAction, ...]:
    actions: list[TeamAccessControlNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: TeamAccessControlNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            TeamAccessControlNextAction(
                priority=priority,
                action=(
                    f"Repair {source.label} local evidence."
                    if source.state in {"invalid", "unsafe"}
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
            )
        )
    for role in roles:
        if role.status == "ready":
            continue
        priority = "high" if role.status == "blocked" else "medium"
        actions.append(
            TeamAccessControlNextAction(
                priority=priority,
                action=role.next_action,
                role_ids=(role.id,),
                audit_event_ids=role.audit_event_ids,
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: list[TeamAccessControlNextAction],
) -> tuple[TeamAccessControlNextAction, ...]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()
    result: list[TeamAccessControlNextAction] = []
    for action in actions:
        key = (action.action, action.source_ids, action.role_ids, action.audit_event_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[TeamAccessControlSource, ...],
    roles: tuple[TeamAccessControlRolePlan, ...],
    next_actions: tuple[TeamAccessControlNextAction, ...],
) -> TeamAccessControlPlanSummary:
    blockers_total = len({blocker for role in roles for blocker in role.blockers})
    return TeamAccessControlPlanSummary(
        status=_status(sources=sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        roles_total=len(roles),
        roles_ready=sum(1 for role in roles if role.status == "ready"),
        roles_attention=sum(1 for role in roles if role.status == "attention"),
        roles_blocked=sum(1 for role in roles if role.status == "blocked"),
        audit_events_total=len(_AUDIT_EVENT_DEFINITIONS),
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _status(
    *,
    sources: tuple[TeamAccessControlSource, ...],
) -> TeamAccessControlPlanStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    primary = next(source for source in sources if source.id == _PRIMARY_SOURCE)
    if primary.state == "present":
        return "ready"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _boundary() -> TeamAccessControlBoundary:
    return TeamAccessControlBoundary(
        explicit_user_intent_required=True,
        upload_implemented=False,
        access_control_enforced=False,
        write_back_implemented=False,
        pass_fail_override_allowed=False,
        forbidden_data_classes=_FORBIDDEN_DATA_CLASSES,
        boundary_summary=(
            "This packet is a local access-control and audit plan only. Future "
            "team surfaces must require explicit user intent, access-control "
            "implementation, audit logging, and value-free evidence references."
        ),
    )


def _project_from_documents(
    documents: Mapping[TeamAccessControlSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "team_evidence_readiness",
        "handoff",
        "notification_packet",
        "runtime_card",
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
        raise TeamAccessControlPlanError(msg)
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
        raise TeamAccessControlPlanError(msg)
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
        raise TeamAccessControlPlanError(msg)
    return value


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return escape(value, quote=False).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = escape(str(value), quote=False).replace("`", "&#96;")
    return text.replace("\n", " ").replace("|", "&#124;")


def _packet_json(packet: TeamAccessControlPlanPacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True)
    except Exception as exc:
        msg = "team access-control plan packet could not be serialized safely"
        raise TeamAccessControlPlanError(msg) from exc


def _contains_unredacted_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(text)
