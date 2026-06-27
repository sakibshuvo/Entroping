"""Integration readiness packets for work-management and team surfaces."""

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

from entroping.core.api_inventory import API_INVENTORY_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    read_local_evidence_artifact_bytes,
    safe_evidence_text,
)
from entroping.core.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import (
    SafeWriteError,
    safe_report_output_path,
    safe_write_text,
)
from entroping.core.team_access_control_plan import (
    TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
)

INTEGRATION_READINESS_SCHEMA_VERSION: Final = "entroping.integration-readiness.v1"

IntegrationReadinessOutput = Literal["md", "json"]
IntegrationReadinessStatus = Literal["ready", "partial", "insufficient"]
IntegrationReadinessSourceState = Literal["present", "missing", "invalid", "unsafe"]
IntegrationReadinessFamilyStatus = Literal["ready", "attention", "blocked"]
IntegrationReadinessNextActionPriority = Literal["high", "medium", "low"]
IntegrationReadinessSourceId = Literal[
    "team_access_control_plan",
    "notification_packet",
    "handoff",
    "observability_packet",
    "api_inventory",
    "runtime_card",
]
IntegrationReadinessFamilyId = Literal[
    "issue_trackers",
    "chat",
    "enterprise_automation",
    "cross_surface_continuity",
    "observability",
    "api_governance",
]
IntegrationReadinessSurfaceId = Literal[
    "jira",
    "linear",
    "monday",
    "slack",
    "discord",
    "workato",
    "claude",
    "codex",
    "cli",
    "desktop",
    "cloud",
    "mobile",
    "opentelemetry",
    "datadog",
    "splunk",
    "openapi",
    "graphql",
    "soap_xml",
    "grpc",
    "webhooks",
    "asyncapi",
    "websocket",
]
IntegrationReadinessForbiddenAction = Literal[
    "call_external_api",
    "upload_artifacts",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "sync_raw_repo_or_vault",
    "render_raw_artifact_contents",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[IntegrationReadinessOutput, Path]] = {
    "md": Path("reports") / "integration-readiness.md",
    "json": Path("reports") / "integration-readiness.json",
}
_FORBIDDEN_ACTIONS: Final[tuple[IntegrationReadinessForbiddenAction, ...]] = (
    "call_external_api",
    "upload_artifacts",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "sync_raw_repo_or_vault",
    "render_raw_artifact_contents",
)
_LINK_REQUIREMENTS: Final[tuple[str, ...]] = (
    "artifact_id",
    "source_path",
    "source_schema_version",
    "source_sha256",
    "generated_at",
)
_EVENT_REQUIREMENTS: Final[tuple[str, ...]] = (
    "actor_role",
    "target_surface",
    "artifact_id",
    "source_sha256",
    "intent",
    "timestamp",
)


class IntegrationReadinessError(ValueError):
    """Raised when an integration readiness packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: IntegrationReadinessSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: IntegrationReadinessSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _FamilyDefinition:
    id: IntegrationReadinessFamilyId
    label: str
    surface_ids: tuple[IntegrationReadinessSurfaceId, ...]
    required_source_ids: tuple[IntegrationReadinessSourceId, ...]
    ready_action: str
    attention_action: str


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="team_access_control_plan",
        label="Team access-control plan",
        path=Path("reports") / "team-access-control-plan.json",
        schema_version=TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="notification_packet",
        label="Notification packet",
        path=Path("reports") / "notification-packet.json",
        schema_version=NOTIFICATION_PACKET_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="handoff",
        label="Cross-surface handoff",
        path=Path("reports") / "handoff.json",
        schema_version=HANDOFF_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="observability_packet",
        label="Observability packet",
        path=Path("reports") / "observability-packet.json",
        schema_version=OBSERVABILITY_PACKET_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="api_inventory",
        label="API inventory",
        path=Path("reports") / "api-inventory.json",
        schema_version=API_INVENTORY_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version=RUNTIME_CARD_SCHEMA_VERSION,
    ),
)
_FAMILY_DEFINITIONS: Final[tuple[_FamilyDefinition, ...]] = (
    _FamilyDefinition(
        id="issue_trackers",
        label="Issue trackers",
        surface_ids=("jira", "linear", "monday"),
        required_source_ids=(
            "team_access_control_plan",
            "notification_packet",
            "runtime_card",
        ),
        ready_action="Attach read-only Entroping evidence links to issue tracker work items.",
        attention_action=(
            "Generate team access-control, notification, and runtime evidence "
            "before issue tracker links."
        ),
    ),
    _FamilyDefinition(
        id="chat",
        label="Chat",
        surface_ids=("slack", "discord"),
        required_source_ids=(
            "notification_packet",
            "handoff",
            "team_access_control_plan",
        ),
        ready_action="Post value-free notification summaries with links to sanitized evidence.",
        attention_action=(
            "Generate notification, handoff, and access-control evidence "
            "before chat summaries."
        ),
    ),
    _FamilyDefinition(
        id="enterprise_automation",
        label="Enterprise automation",
        surface_ids=("workato", "claude", "codex"),
        required_source_ids=("notification_packet", "team_access_control_plan", "handoff"),
        ready_action=(
            "Use the packet as read-only automation context after explicit connector setup."
        ),
        attention_action=(
            "Generate notification, access-control, and handoff evidence before "
            "automation handoffs."
        ),
    ),
    _FamilyDefinition(
        id="cross_surface_continuity",
        label="Cross-surface continuity",
        surface_ids=("cli", "desktop", "cloud", "mobile"),
        required_source_ids=("handoff", "runtime_card", "team_access_control_plan"),
        ready_action=(
            "Use stable evidence identifiers and hashes across CLI, desktop, cloud, "
            "and mobile views."
        ),
        attention_action=(
            "Generate handoff, runtime, and access-control evidence before "
            "cross-surface continuity."
        ),
    ),
    _FamilyDefinition(
        id="observability",
        label="Observability",
        surface_ids=("opentelemetry", "datadog", "splunk"),
        required_source_ids=(
            "observability_packet",
            "runtime_card",
            "team_access_control_plan",
        ),
        ready_action="Map value-free runtime evidence into vendor-neutral observability events.",
        attention_action=(
            "Generate observability, runtime, and access-control evidence before "
            "telemetry adapters."
        ),
    ),
    _FamilyDefinition(
        id="api_governance",
        label="API governance",
        surface_ids=(
            "openapi",
            "graphql",
            "soap_xml",
            "grpc",
            "webhooks",
            "asyncapi",
            "websocket",
        ),
        required_source_ids=("api_inventory", "runtime_card", "handoff"),
        ready_action=(
            "Use API inventory and runtime evidence to plan protocol-specific "
            "governance lanes."
        ),
        attention_action=(
            "Generate API inventory, runtime, and handoff evidence before broader "
            "API governance lanes."
        ),
    ),
)


class IntegrationReadinessSummary(BaseModel):
    """Aggregate integration readiness state."""

    model_config = ConfigDict(extra="forbid")

    status: IntegrationReadinessStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    families_total: int = Field(ge=0)
    families_ready: int = Field(ge=0)
    families_attention: int = Field(ge=0)
    families_blocked: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class IntegrationReadinessSource(BaseModel):
    """One local source artifact used for integration planning."""

    model_config = ConfigDict(extra="forbid")

    id: IntegrationReadinessSourceId
    label: str
    path: str
    state: IntegrationReadinessSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class IntegrationReadinessFamily(BaseModel):
    """One future integration surface family and its local readiness boundary."""

    model_config = ConfigDict(extra="forbid")

    id: IntegrationReadinessFamilyId
    label: str
    status: IntegrationReadinessFamilyStatus
    surface_ids: tuple[IntegrationReadinessSurfaceId, ...]
    required_source_ids: tuple[IntegrationReadinessSourceId, ...]
    present_source_ids: tuple[IntegrationReadinessSourceId, ...]
    missing_source_ids: tuple[IntegrationReadinessSourceId, ...]
    blockers: tuple[str, ...] = ()
    link_requirements: tuple[str, ...]
    event_requirements: tuple[str, ...]
    forbidden_actions: tuple[IntegrationReadinessForbiddenAction, ...]
    next_action: str


class IntegrationReadinessNextAction(BaseModel):
    """One local action before enabling future integrations."""

    model_config = ConfigDict(extra="forbid")

    priority: IntegrationReadinessNextActionPriority
    action: str
    source_ids: tuple[IntegrationReadinessSourceId, ...] = ()
    family_ids: tuple[IntegrationReadinessFamilyId, ...] = ()


class IntegrationReadinessPacket(BaseModel):
    """Schema-versioned local integration readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.integration-readiness.v1"] = (
        INTEGRATION_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: IntegrationReadinessSummary
    sources: tuple[IntegrationReadinessSource, ...]
    families: tuple[IntegrationReadinessFamily, ...]
    next_actions: tuple[IntegrationReadinessNextAction, ...]


@dataclass(frozen=True, slots=True)
class IntegrationReadinessResult:
    """Result of writing one integration readiness packet."""

    output_path: Path
    packet: IntegrationReadinessPacket


def run_integration_readiness_report(
    *,
    project_root: Path,
    output: IntegrationReadinessOutput,
    output_path: Path | None = None,
) -> IntegrationReadinessResult:
    """Write a local integration readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported integration-readiness output: {output}"
        raise IntegrationReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_integration_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "integration readiness packet contains secret-like content"
        raise IntegrationReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="integration readiness packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise IntegrationReadinessError(str(exc)) from exc
    return IntegrationReadinessResult(output_path=written, packet=packet)


def build_integration_readiness(*, project_root: Path) -> IntegrationReadinessPacket:
    """Build a value-free integration readiness packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "integration readiness packet contains secret-like content"
        raise IntegrationReadinessError(msg)
    return packet


def render_integration_readiness_markdown(packet: IntegrationReadinessPacket) -> str:
    """Render a human-readable integration readiness packet."""

    lines = [
        "# Entroping Integration Readiness",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Families: "
        f"`{packet.summary.families_ready}/{packet.summary.families_total}` ready, "
        f"`{packet.summary.families_attention}` attention, "
        f"`{packet.summary.families_blocked}` blocked",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
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
            "## Families",
            "",
            "| Family | Status | Surfaces | Required Sources | Present Sources | "
            "Missing Sources | Blockers | Link Requirements | Event Requirements | "
            "Forbidden Actions | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for family in packet.families:
        lines.append(
            "| "
            f"{_markdown_cell(family.id)} | "
            f"{_markdown_cell(family.status)} | "
            f"{_markdown_cell(', '.join(family.surface_ids))} | "
            f"{_markdown_cell(', '.join(family.required_source_ids))} | "
            f"{_markdown_cell(', '.join(family.present_source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(family.missing_source_ids) or 'n/a')} | "
            f"{_markdown_cell('; '.join(family.blockers) or 'none')} | "
            f"{_markdown_cell(', '.join(family.link_requirements))} | "
            f"{_markdown_cell(', '.join(family.event_requirements))} | "
            f"{_markdown_cell(', '.join(family.forbidden_actions))} | "
            f"{_markdown_cell(family.next_action)} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No integration readiness actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Sources | Families |",
                "| --- | --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.family_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_packet(*, root: Path) -> IntegrationReadinessPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    families = _families(sources)
    next_actions = _next_actions(sources=sources, families=families)
    return IntegrationReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(sources=sources, families=families, next_actions=next_actions),
        sources=sources,
        families=families,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: IntegrationReadinessPacket,
    *,
    output: IntegrationReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_integration_readiness_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    schema_version: str | None = None
    try:
        path = _resolve_source_path(definition.path, root=root)
    except IntegrationReadinessError as exc:
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
    except IntegrationReadinessError as exc:
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
    except IntegrationReadinessError as exc:
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
    state: IntegrationReadinessSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=IntegrationReadinessSource(
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
        msg = "integration readiness source path must stay under the project root"
        raise IntegrationReadinessError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"integration readiness source path uses symlinked component: {display_path}"
        raise IntegrationReadinessError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = "integration readiness source path must stay under the project root"
        raise IntegrationReadinessError(msg) from exc
    if resolved.exists() and not resolved.is_file():
        msg = f"integration readiness source path is not a file: {raw_path.as_posix()}"
        raise IntegrationReadinessError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(
            raw_path,
            root=root,
            artifact="integration readiness packet",
        )
    except SafeWriteError as exc:
        msg = str(exc)
        raise IntegrationReadinessError(msg) from exc


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    raw_bytes, load_error = read_local_evidence_artifact_bytes(
        path,
        max_bytes=_MAX_SOURCE_BYTES,
    )
    if raw_bytes is None:
        msg = f"Could not read {artifact}: {load_error}"
        raise IntegrationReadinessError(msg)
    return raw_bytes


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise IntegrationReadinessError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise IntegrationReadinessError(msg)
    return document


def _source_summary(definition: _SourceDefinition, document: Mapping[str, object]) -> str:
    summary = _required_object(document, "summary", artifact=definition.label)
    status = _required_text(summary, "status", artifact=definition.label)
    if definition.id == "team_access_control_plan":
        roles_ready = _required_non_negative_int(summary, "roles_ready", artifact=definition.label)
        roles_total = _required_non_negative_int(summary, "roles_total", artifact=definition.label)
        blockers = _required_non_negative_int(summary, "blockers_total", artifact=definition.label)
        return f"{status}; {roles_ready}/{roles_total} roles ready; {blockers} blockers"
    if definition.id == "notification_packet":
        severity = _required_text(summary, "severity", artifact=definition.label)
        return f"{status}; {severity} severity"
    if definition.id == "handoff":
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
    if definition.id == "observability_packet":
        severity = _required_text(summary, "severity", artifact=definition.label)
        events = _required_non_negative_int(summary, "events_total", artifact=definition.label)
        return f"{status}; {severity} severity; {events} events"
    if definition.id == "api_inventory":
        styles = _required_non_negative_int(summary, "styles_total", artifact=definition.label)
        operations = _required_non_negative_int(
            summary,
            "operations_total",
            artifact=definition.label,
        )
        return f"{status}; {styles} API styles; {operations} operations"
    findings = _required_non_negative_int(summary, "findings", artifact=definition.label)
    return f"{status}; {findings} findings"


def _families(
    sources: tuple[IntegrationReadinessSource, ...],
) -> tuple[IntegrationReadinessFamily, ...]:
    source_by_id = {source.id: source for source in sources}
    return tuple(_family(definition, source_by_id) for definition in _FAMILY_DEFINITIONS)


def _family(
    definition: _FamilyDefinition,
    source_by_id: Mapping[IntegrationReadinessSourceId, IntegrationReadinessSource],
) -> IntegrationReadinessFamily:
    required_sources = tuple(
        source_by_id[source_id] for source_id in definition.required_source_ids
    )
    present_source_ids = tuple(
        source.id for source in required_sources if source.state == "present"
    )
    missing_source_ids = tuple(
        source.id for source in required_sources if source.state == "missing"
    )
    blockers = tuple(
        f"{source.label} is {source.state}: {source.summary}"
        for source in required_sources
        if source.state in {"invalid", "unsafe"}
    )
    if blockers:
        status: IntegrationReadinessFamilyStatus = "blocked"
        next_action = "Repair unsafe or invalid source evidence before enabling integrations."
    elif len(present_source_ids) == len(required_sources):
        status = "ready"
        next_action = definition.ready_action
    else:
        status = "attention"
        next_action = definition.attention_action
    return IntegrationReadinessFamily(
        id=definition.id,
        label=definition.label,
        status=status,
        surface_ids=definition.surface_ids,
        required_source_ids=definition.required_source_ids,
        present_source_ids=present_source_ids,
        missing_source_ids=missing_source_ids,
        blockers=blockers,
        link_requirements=_LINK_REQUIREMENTS,
        event_requirements=_EVENT_REQUIREMENTS,
        forbidden_actions=_FORBIDDEN_ACTIONS,
        next_action=next_action,
    )


def _next_actions(
    *,
    sources: tuple[IntegrationReadinessSource, ...],
    families: tuple[IntegrationReadinessFamily, ...],
) -> tuple[IntegrationReadinessNextAction, ...]:
    actions: list[IntegrationReadinessNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: IntegrationReadinessNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            IntegrationReadinessNextAction(
                priority=priority,
                action=(
                    f"Repair {source.label} local evidence."
                    if source.state in {"invalid", "unsafe"}
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
            )
        )
    for family in families:
        if family.status == "ready":
            continue
        priority = "high" if family.status == "blocked" else "medium"
        actions.append(
            IntegrationReadinessNextAction(
                priority=priority,
                action=family.next_action,
                family_ids=(family.id,),
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: list[IntegrationReadinessNextAction],
) -> tuple[IntegrationReadinessNextAction, ...]:
    seen: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[IntegrationReadinessNextAction] = []
    for action in actions:
        key = (action.priority, action.action, action.source_ids, action.family_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[IntegrationReadinessSource, ...],
    families: tuple[IntegrationReadinessFamily, ...],
    next_actions: tuple[IntegrationReadinessNextAction, ...],
) -> IntegrationReadinessSummary:
    blockers_total = len({blocker for family in families for blocker in family.blockers})
    return IntegrationReadinessSummary(
        status=_status(sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        families_total=len(families),
        families_ready=sum(1 for family in families if family.status == "ready"),
        families_attention=sum(1 for family in families if family.status == "attention"),
        families_blocked=sum(1 for family in families if family.status == "blocked"),
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _status(sources: tuple[IntegrationReadinessSource, ...]) -> IntegrationReadinessStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if any(source.state == "missing" for source in sources):
        return "partial"
    return "ready"


def _project_from_documents(
    documents: Mapping[IntegrationReadinessSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "team_access_control_plan",
        "notification_packet",
        "handoff",
        "observability_packet",
        "api_inventory",
    ):
        document = documents[source_id]
        if document is None:
            continue
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return _safe_text(project)
    runtime_card = documents["runtime_card"]
    if runtime_card is not None:
        run = runtime_card.get("run")
        if isinstance(run, dict):
            project = run.get("project")
            if isinstance(project, str) and project.strip():
                return _safe_text(project)
        project = runtime_card.get("project")
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
        raise IntegrationReadinessError(msg)
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
        raise IntegrationReadinessError(msg)
    return _safe_text(value)


def _required_non_negative_int(
    document: Mapping[str, object],
    field: str,
    *,
    artifact: str,
) -> int:
    value = document.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"{artifact} {field} must be a non-negative integer"
        raise IntegrationReadinessError(msg)
    return value


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return escape(value, quote=False).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = escape(str(value), quote=False).replace("`", "&#96;")
    return text.replace("\n", " ").replace("|", "&#124;")


def _packet_json(packet: IntegrationReadinessPacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True)
    except Exception as exc:
        msg = "integration readiness packet could not be serialized safely"
        raise IntegrationReadinessError(msg) from exc


def _contains_unredacted_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(text)
