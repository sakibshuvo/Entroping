"""Connector intent packets for future integration surfaces."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index_report import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.evidence.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.evidence.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.evidence.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.readiness.devex_readiness import DEVEX_READINESS_SCHEMA_VERSION
from entroping.core.readiness.integration_readiness import INTEGRATION_READINESS_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

CONNECTOR_INTENT_SCHEMA_VERSION: Final = "entroping.connector-intent.v1"

ConnectorIntentOutput = Literal["md", "json"]
ConnectorIntentStatus = Literal["ready", "partial", "insufficient"]
ConnectorIntentSourceState = Literal["present", "missing", "invalid", "unsafe"]
ConnectorIntentRecordStatus = Literal["ready", "attention", "blocked"]
ConnectorIntentCapabilityStatus = Literal["ready", "attention", "blocked"]
ConnectorIntentNextActionPriority = Literal["high", "medium", "low"]
ConnectorIntentSourceId = Literal[
    "runtime_card",
    "handoff",
    "notification_packet",
    "integration_readiness",
    "devex_readiness",
    "observability_packet",
    "evidence_index",
]
ConnectorIntentId = Literal[
    "issue_tracker",
    "chat",
    "enterprise_automation",
    "enterprise_ai",
    "observability",
    "devex_surface",
]
ConnectorIntentTargetFamily = ConnectorIntentId
ConnectorIntentKind = Literal[
    "issue_link",
    "chat_notification",
    "workflow_handoff",
    "ai_handoff",
    "telemetry_signal",
    "surface_handoff",
]
ConnectorIntentTargetSystem = Literal[
    "jira",
    "linear",
    "monday",
    "github_issues",
    "generic_tracker",
    "slack",
    "discord",
    "teams",
    "generic_chat",
    "workato",
    "zapier",
    "generic_workflow",
    "claude",
    "codex",
    "openai_compatible_agent",
    "generic_ai_assistant",
    "opentelemetry",
    "datadog",
    "splunk",
    "grafana",
    "generic_observability",
    "vscode",
    "editor",
    "local_workbench",
    "desktop",
    "cloud",
    "mobile",
    "pr_card",
]
ConnectorIntentForbiddenAction = Literal[
    "call_external_api",
    "invoke_model_provider",
    "upload_artifacts",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "mutate_dashboard_or_monitor",
    "mutate_workflow",
    "sync_raw_repo_or_vault",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "render_raw_artifact_contents",
    "implement_app_surface",
    "execute_hurl",
    "run_tests",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[ConnectorIntentOutput, Path]] = {
    "md": Path("reports") / "connector-intent.md",
    "json": Path("reports") / "connector-intent.json",
}
_MINIMUM_PAYLOAD_FIELDS: Final[tuple[str, ...]] = (
    "artifact_id",
    "source_path",
    "source_schema_version",
    "source_sha256",
    "schema_version",
    "intent_kind",
    "target_family",
    "target_system",
    "generated_at",
)
_AUDIT_FIELDS: Final[tuple[str, ...]] = (
    "actor_role",
    "requested_at",
    "target_family",
    "target_system",
    "artifact_id",
    "source_sha256",
    "approval_id",
    "connector_config_id",
)
_FORBIDDEN_ACTIONS: Final[tuple[ConnectorIntentForbiddenAction, ...]] = (
    "call_external_api",
    "invoke_model_provider",
    "upload_artifacts",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "mutate_dashboard_or_monitor",
    "mutate_workflow",
    "sync_raw_repo_or_vault",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "render_raw_artifact_contents",
    "implement_app_surface",
    "execute_hurl",
    "run_tests",
)


class ConnectorIntentError(ValueError):
    """Raised when a connector intent packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: ConnectorIntentSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: ConnectorIntentSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _IntentDefinition:
    id: ConnectorIntentId
    label: str
    target_family: ConnectorIntentTargetFamily
    target_systems: tuple[ConnectorIntentTargetSystem, ...]
    intent_kind: ConnectorIntentKind
    required_source_ids: tuple[ConnectorIntentSourceId, ...]
    ready_action: str
    attention_action: str


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version=RUNTIME_CARD_SCHEMA_VERSION,
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
        id="observability_packet",
        label="Observability packet",
        path=Path("reports") / "observability-packet.json",
        schema_version=OBSERVABILITY_PACKET_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="evidence_index",
        label="Evidence index",
        path=Path("reports") / "evidence-index.json",
        schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
    ),
)
_INTENT_DEFINITIONS: Final[tuple[_IntentDefinition, ...]] = (
    _IntentDefinition(
        id="issue_tracker",
        label="Issue tracker",
        target_family="issue_tracker",
        target_systems=("jira", "linear", "monday", "github_issues", "generic_tracker"),
        intent_kind="issue_link",
        required_source_ids=(
            "runtime_card",
            "notification_packet",
            "integration_readiness",
        ),
        ready_action="Prepare read-only Entroping evidence links for tracker work items.",
        attention_action=(
            "Generate runtime, notification, and integration-readiness evidence "
            "before issue tracker connector intents."
        ),
    ),
    _IntentDefinition(
        id="chat",
        label="Chat",
        target_family="chat",
        target_systems=("slack", "discord", "teams", "generic_chat"),
        intent_kind="chat_notification",
        required_source_ids=("notification_packet", "handoff", "integration_readiness"),
        ready_action="Prepare value-free run summaries and evidence links for chat review.",
        attention_action=(
            "Generate notification, handoff, and integration-readiness evidence "
            "before chat connector intents."
        ),
    ),
    _IntentDefinition(
        id="enterprise_automation",
        label="Enterprise automation",
        target_family="enterprise_automation",
        target_systems=("workato", "zapier", "generic_workflow"),
        intent_kind="workflow_handoff",
        required_source_ids=("notification_packet", "integration_readiness", "handoff"),
        ready_action="Prepare explicit-user-approved workflow handoff metadata.",
        attention_action=(
            "Generate notification, integration-readiness, and handoff evidence "
            "before workflow automation intents."
        ),
    ),
    _IntentDefinition(
        id="enterprise_ai",
        label="Enterprise AI",
        target_family="enterprise_ai",
        target_systems=(
            "claude",
            "codex",
            "openai_compatible_agent",
            "generic_ai_assistant",
        ),
        intent_kind="ai_handoff",
        required_source_ids=("devex_readiness", "handoff", "evidence_index"),
        ready_action="Prepare value-free evidence IDs for enterprise AI handoff context.",
        attention_action=(
            "Generate devex-readiness, handoff, and evidence-index evidence "
            "before enterprise AI handoff intents."
        ),
    ),
    _IntentDefinition(
        id="observability",
        label="Observability",
        target_family="observability",
        target_systems=(
            "opentelemetry",
            "datadog",
            "splunk",
            "grafana",
            "generic_observability",
        ),
        intent_kind="telemetry_signal",
        required_source_ids=("observability_packet", "evidence_index"),
        ready_action="Prepare vendor-neutral telemetry signal metadata.",
        attention_action=(
            "Generate observability and evidence-index evidence before telemetry intents."
        ),
    ),
    _IntentDefinition(
        id="devex_surface",
        label="Developer experience surface",
        target_family="devex_surface",
        target_systems=(
            "vscode",
            "editor",
            "local_workbench",
            "desktop",
            "cloud",
            "mobile",
            "pr_card",
        ),
        intent_kind="surface_handoff",
        required_source_ids=("devex_readiness", "evidence_index"),
        ready_action="Prepare cross-surface evidence handoff metadata.",
        attention_action=(
            "Generate devex-readiness and evidence-index evidence before "
            "developer-experience surface intents."
        ),
    ),
)


class ConnectorIntentSummary(BaseModel):
    """Aggregate connector intent state."""

    model_config = ConfigDict(extra="forbid")

    status: ConnectorIntentStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    intents_total: int = Field(ge=0)
    intents_ready: int = Field(ge=0)
    intents_attention: int = Field(ge=0)
    intents_blocked: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class ConnectorIntentSource(BaseModel):
    """One local source artifact used for connector-intent planning."""

    model_config = ConfigDict(extra="forbid")

    id: ConnectorIntentSourceId
    label: str
    path: str
    state: ConnectorIntentSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class ConnectorIntentRecord(BaseModel):
    """One future connector intent and its local safety boundary."""

    model_config = ConfigDict(extra="forbid")

    id: ConnectorIntentId
    label: str
    target_family: ConnectorIntentTargetFamily
    target_systems: tuple[ConnectorIntentTargetSystem, ...]
    status: ConnectorIntentRecordStatus
    intent_kind: ConnectorIntentKind
    required_source_ids: tuple[ConnectorIntentSourceId, ...]
    present_source_ids: tuple[ConnectorIntentSourceId, ...]
    missing_source_ids: tuple[ConnectorIntentSourceId, ...]
    minimum_payload_fields: tuple[str, ...]
    required_user_action: str
    audit_fields: tuple[str, ...]
    forbidden_actions: tuple[ConnectorIntentForbiddenAction, ...]
    blockers: tuple[str, ...] = ()
    next_action: str


class ConnectorIntentCapability(BaseModel):
    """One local connector-capability row for a target system."""

    model_config = ConfigDict(extra="forbid")

    target_system: ConnectorIntentTargetSystem
    intent_id: ConnectorIntentId
    status: ConnectorIntentCapabilityStatus
    local_evidence_prerequisites: tuple[ConnectorIntentSourceId, ...]
    forbidden_actions: tuple[ConnectorIntentForbiddenAction, ...]
    blockers: tuple[str, ...] = ()


class ConnectorIntentNextAction(BaseModel):
    """One local action before enabling future connector intents."""

    model_config = ConfigDict(extra="forbid")

    priority: ConnectorIntentNextActionPriority
    action: str
    source_ids: tuple[ConnectorIntentSourceId, ...] = ()
    intent_ids: tuple[ConnectorIntentId, ...] = ()


class ConnectorIntentPacket(BaseModel):
    """Schema-versioned local connector intent packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.connector-intent.v1"] = (
        CONNECTOR_INTENT_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: ConnectorIntentSummary
    sources: tuple[ConnectorIntentSource, ...]
    intents: tuple[ConnectorIntentRecord, ...]
    capability_matrix: tuple[ConnectorIntentCapability, ...] = ()
    next_actions: tuple[ConnectorIntentNextAction, ...]


@dataclass(frozen=True, slots=True)
class ConnectorIntentResult:
    """Result of writing one connector intent packet."""

    output_path: Path
    packet: ConnectorIntentPacket


def run_connector_intent_report(
    *,
    project_root: Path,
    output: ConnectorIntentOutput,
    output_path: Path | None = None,
) -> ConnectorIntentResult:
    """Write a local connector intent packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported connector-intent output: {output}"
        raise ConnectorIntentError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_connector_intent(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "connector intent packet contains secret-like content"
        raise ConnectorIntentError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="connector intent packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise ConnectorIntentError(str(exc)) from exc
    return ConnectorIntentResult(output_path=written, packet=packet)


def build_connector_intent(*, project_root: Path) -> ConnectorIntentPacket:
    """Build a value-free connector intent packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "connector intent packet contains secret-like content"
        raise ConnectorIntentError(msg)
    return packet


def render_connector_intent_markdown(packet: ConnectorIntentPacket) -> str:
    """Render a human-readable connector intent packet."""

    lines = [
        "# Entroping Connector Intent",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Intents: "
        f"`{packet.summary.intents_ready}/{packet.summary.intents_total}` ready, "
        f"`{packet.summary.intents_attention}` attention, "
        f"`{packet.summary.intents_blocked}` blocked",
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
            "## Intents",
            "",
            "| Intent | Status | Target Systems | Kind | Required Sources | "
            + "Present Sources | Missing Sources | Minimum Payload Fields | "
            + "Required User Action | Audit Fields | Forbidden Actions | "
            + "Blockers | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for intent in packet.intents:
        lines.append(
            "| "
            f"{_markdown_cell(intent.id)} | "
            f"{_markdown_cell(intent.status)} | "
            f"{_markdown_cell(', '.join(intent.target_systems))} | "
            f"{_markdown_cell(intent.intent_kind)} | "
            f"{_markdown_cell(', '.join(intent.required_source_ids))} | "
            f"{_markdown_cell(', '.join(intent.present_source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(intent.missing_source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(intent.minimum_payload_fields))} | "
            f"{_markdown_cell(intent.required_user_action)} | "
            f"{_markdown_cell(', '.join(intent.audit_fields))} | "
            f"{_markdown_cell(', '.join(intent.forbidden_actions))} | "
            f"{_markdown_cell('; '.join(intent.blockers) or 'none')} | "
            f"{_markdown_cell(intent.next_action)} |"
        )

    lines.extend(
        [
            "",
            "## Capability Matrix",
            "",
            "| Target System | Intent | Capability | Local Evidence Prerequisites | "
            + "Forbidden Actions | Blockers |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for capability in packet.capability_matrix:
        lines.append(
            "| "
            f"{_markdown_cell(capability.target_system)} | "
            f"{_markdown_cell(capability.intent_id)} | "
            f"{_markdown_cell(capability.status)} | "
            f"{_markdown_cell(', '.join(capability.local_evidence_prerequisites) or 'n/a')} | "
            f"{_markdown_cell(', '.join(capability.forbidden_actions))} | "
            f"{_markdown_cell('; '.join(capability.blockers) or 'none')} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No connector intent actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Sources | Intents |",
                "| --- | --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.intent_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_packet(*, root: Path) -> ConnectorIntentPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    intents = _intents(sources)
    source_by_id = {source.id: source for source in sources}
    capability_matrix = _capability_matrix(
        intents=intents,
        source_by_id=source_by_id,
    )
    next_actions = _next_actions(sources=sources, intents=intents)
    return ConnectorIntentPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(sources=sources, intents=intents, next_actions=next_actions),
        sources=sources,
        intents=intents,
        capability_matrix=capability_matrix,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: ConnectorIntentPacket,
    *,
    output: ConnectorIntentOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_connector_intent_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    schema_version: str | None = None
    try:
        path = _resolve_source_path(definition.path, root=root)
    except ConnectorIntentError as exc:
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
    except ConnectorIntentError as exc:
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
    except ConnectorIntentError as exc:
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
    state: ConnectorIntentSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=ConnectorIntentSource(
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
        msg = "connector intent source path must stay under the project root"
        raise ConnectorIntentError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"connector intent source path uses symlinked component: {display_path}"
        raise ConnectorIntentError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = "connector intent source path must stay under the project root"
        raise ConnectorIntentError(msg) from exc
    if resolved.exists() and not resolved.is_file():
        msg = f"connector intent source path is not a file: {raw_path.as_posix()}"
        raise ConnectorIntentError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "connector intent output path must stay under the project root"
        raise ConnectorIntentError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"connector intent output path uses symlinked component: {display_path}"
        raise ConnectorIntentError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "connector intent output path must stay under the project root"
        raise ConnectorIntentError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "connector intent packet must not be written into .entroping or envs"
        raise ConnectorIntentError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(path, flags)
        descriptor_stat = os.fstat(file_descriptor)
        path_stat = path.stat(follow_symlinks=False)
        if not path.is_file():
            msg = f"{artifact.capitalize()} {path.name} is not a regular file"
            raise ConnectorIntentError(msg)
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            msg = f"{artifact.capitalize()} {path.name} changed during read"
            raise ConnectorIntentError(msg)
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            raw_bytes = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise ConnectorIntentError(msg) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
    if len(raw_bytes) > _MAX_SOURCE_BYTES:
        msg = f"{artifact.capitalize()} {path.name} exceeds {_MAX_SOURCE_BYTES} bytes"
        raise ConnectorIntentError(msg)
    return raw_bytes


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise ConnectorIntentError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise ConnectorIntentError(msg)
    return document


def _source_summary(definition: _SourceDefinition, document: Mapping[str, object]) -> str:
    summary = _required_object(document, "summary", artifact=definition.label)
    status = _required_text(summary, "status", artifact=definition.label)
    if definition.id == "runtime_card":
        findings = _required_non_negative_int(summary, "findings", artifact=definition.label)
        return f"{status}; {findings} findings"
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
    if definition.id == "notification_packet":
        severity = _required_text(summary, "severity", artifact=definition.label)
        return f"{status}; {severity} severity"
    if definition.id in {"integration_readiness", "devex_readiness"}:
        families_ready = _required_non_negative_int(
            summary,
            "families_ready",
            artifact=definition.label,
        )
        families_total = _required_non_negative_int(
            summary,
            "families_total",
            artifact=definition.label,
        )
        blockers = _required_non_negative_int(summary, "blockers_total", artifact=definition.label)
        return f"{status}; {families_ready}/{families_total} families ready; {blockers} blockers"
    if definition.id == "observability_packet":
        severity = _required_text(summary, "severity", artifact=definition.label)
        events = _required_non_negative_int(summary, "events_total", artifact=definition.label)
        return f"{status}; {severity} severity; {events} events"
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
    return f"{status}; {present}/{total} indexed artifacts present"


def _intents(
    sources: tuple[ConnectorIntentSource, ...],
) -> tuple[ConnectorIntentRecord, ...]:
    source_by_id = {source.id: source for source in sources}
    return tuple(_intent(definition, source_by_id) for definition in _INTENT_DEFINITIONS)


def _intent(
    definition: _IntentDefinition,
    source_by_id: Mapping[ConnectorIntentSourceId, ConnectorIntentSource],
) -> ConnectorIntentRecord:
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
        status: ConnectorIntentRecordStatus = "blocked"
        next_action = "Repair unsafe or invalid source evidence before enabling connector intents."
    elif len(present_source_ids) == len(required_sources):
        status = "ready"
        next_action = definition.ready_action
    else:
        status = "attention"
        next_action = definition.attention_action
    return ConnectorIntentRecord(
        id=definition.id,
        label=definition.label,
        target_family=definition.target_family,
        target_systems=definition.target_systems,
        status=status,
        intent_kind=definition.intent_kind,
        required_source_ids=definition.required_source_ids,
        present_source_ids=present_source_ids,
        missing_source_ids=missing_source_ids,
        minimum_payload_fields=_MINIMUM_PAYLOAD_FIELDS,
        required_user_action="explicit_user_approval",
        audit_fields=_AUDIT_FIELDS,
        forbidden_actions=_FORBIDDEN_ACTIONS,
        blockers=blockers,
        next_action=next_action,
    )


def _next_actions(
    *,
    sources: tuple[ConnectorIntentSource, ...],
    intents: tuple[ConnectorIntentRecord, ...],
) -> tuple[ConnectorIntentNextAction, ...]:
    actions: list[ConnectorIntentNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: ConnectorIntentNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            ConnectorIntentNextAction(
                priority=priority,
                action=(
                    f"Repair {source.label} local evidence."
                    if source.state in {"invalid", "unsafe"}
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
            )
        )
    for intent in intents:
        if intent.status == "ready":
            continue
        priority = "high" if intent.status == "blocked" else "medium"
        actions.append(
            ConnectorIntentNextAction(
                priority=priority,
                action=intent.next_action,
                intent_ids=(intent.id,),
            )
        )
    return tuple(_dedupe_actions(actions))


def _capability_matrix(
    *,
    intents: tuple[ConnectorIntentRecord, ...],
    source_by_id: Mapping[ConnectorIntentSourceId, ConnectorIntentSource],
) -> tuple[ConnectorIntentCapability, ...]:
    rows: list[ConnectorIntentCapability] = []
    for intent in intents:
        blockers = tuple(
            f"{source_by_id[source_id].label} is {source_by_id[source_id].state}: "
            f"{source_by_id[source_id].summary}"
            for source_id in intent.required_source_ids
            if source_by_id[source_id].state in {"invalid", "unsafe"}
        )
        status: ConnectorIntentCapabilityStatus = (
            "blocked" if blockers else intent.status
        )
        for target_system in intent.target_systems:
            rows.append(
                ConnectorIntentCapability(
                    target_system=target_system,
                    intent_id=intent.id,
                    status=status,
                    local_evidence_prerequisites=intent.required_source_ids,
                    forbidden_actions=intent.forbidden_actions,
                    blockers=blockers,
                )
            )
    return tuple(rows)


def _dedupe_actions(
    actions: list[ConnectorIntentNextAction],
) -> tuple[ConnectorIntentNextAction, ...]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[ConnectorIntentNextAction] = []
    for action in actions:
        key = (action.action, action.source_ids, action.intent_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[ConnectorIntentSource, ...],
    intents: tuple[ConnectorIntentRecord, ...],
    next_actions: tuple[ConnectorIntentNextAction, ...],
) -> ConnectorIntentSummary:
    blockers_total = len({blocker for intent in intents for blocker in intent.blockers})
    return ConnectorIntentSummary(
        status=_status(sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        intents_total=len(intents),
        intents_ready=sum(1 for intent in intents if intent.status == "ready"),
        intents_attention=sum(1 for intent in intents if intent.status == "attention"),
        intents_blocked=sum(1 for intent in intents if intent.status == "blocked"),
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _status(sources: tuple[ConnectorIntentSource, ...]) -> ConnectorIntentStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if any(source.state == "missing" for source in sources):
        return "partial"
    return "ready"


def _project_from_documents(
    documents: Mapping[ConnectorIntentSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "handoff",
        "integration_readiness",
        "devex_readiness",
        "notification_packet",
        "observability_packet",
        "evidence_index",
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
        raise ConnectorIntentError(msg)
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
        raise ConnectorIntentError(msg)
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
        raise ConnectorIntentError(msg)
    return value


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return escape(value, quote=False).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = escape(str(value), quote=False).replace("`", "&#96;")
    return text.replace("\n", " ").replace("|", "&#124;")


def _packet_json(packet: ConnectorIntentPacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True)
    except Exception as exc:
        msg = "connector intent packet could not be serialized safely"
        raise ConnectorIntentError(msg) from exc


def _contains_unredacted_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(text)
