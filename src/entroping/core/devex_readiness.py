"""Developer experience readiness packets for local-first product surfaces."""

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

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_index_report import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.integration_readiness import INTEGRATION_READINESS_SCHEMA_VERSION
from entroping.core.notification_packet import NOTIFICATION_PACKET_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.team_access_control_plan import (
    TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
)

DEVEX_READINESS_SCHEMA_VERSION: Final = "entroping.devex-readiness.v1"

DevexReadinessOutput = Literal["md", "json"]
DevexReadinessStatus = Literal["ready", "partial", "insufficient"]
DevexReadinessSourceState = Literal["present", "missing", "invalid", "unsafe"]
DevexReadinessFamilyStatus = Literal["ready", "attention", "blocked"]
DevexReadinessNextActionPriority = Literal["high", "medium", "low"]
DevexReadinessSourceId = Literal[
    "runtime_card",
    "handoff",
    "evidence_index",
    "integration_readiness",
    "notification_packet",
    "team_access_control_plan",
]
DevexReadinessFamilyId = Literal[
    "cli",
    "editor",
    "local_workbench",
    "pr_runtime_card",
    "desktop",
    "cloud",
    "mobile",
]
DevexReadinessSurfaceId = Literal[
    "cli",
    "vscode",
    "editor",
    "local_workbench",
    "pr_runtime_card",
    "desktop",
    "cloud",
    "mobile",
]
DevexReadinessForbiddenAction = Literal[
    "execute_hurl",
    "run_tests",
    "call_external_api",
    "invoke_model_provider",
    "upload_artifacts",
    "mutate_external_system",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "sync_raw_repo_or_vault",
    "render_raw_artifact_contents",
    "implement_app_surface",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[DevexReadinessOutput, Path]] = {
    "md": Path("reports") / "devex-readiness.md",
    "json": Path("reports") / "devex-readiness.json",
}
_FORBIDDEN_ACTIONS: Final[tuple[DevexReadinessForbiddenAction, ...]] = (
    "execute_hurl",
    "run_tests",
    "call_external_api",
    "invoke_model_provider",
    "upload_artifacts",
    "mutate_external_system",
    "read_provider_keys",
    "override_hurl_qanstitution_result",
    "sync_raw_repo_or_vault",
    "render_raw_artifact_contents",
    "implement_app_surface",
)
_LINK_REQUIREMENTS: Final[tuple[str, ...]] = (
    "artifact_id",
    "source_path",
    "source_schema_version",
    "source_sha256",
    "generated_at",
)
_ACTION_REQUIREMENTS: Final[tuple[str, ...]] = (
    "actor_role",
    "target_surface",
    "artifact_id",
    "source_sha256",
    "intent",
    "explicit_user_action",
    "timestamp",
)


class DevexReadinessError(ValueError):
    """Raised when a developer experience readiness packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: DevexReadinessSourceId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: DevexReadinessSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _FamilyDefinition:
    id: DevexReadinessFamilyId
    label: str
    surface_ids: tuple[DevexReadinessSurfaceId, ...]
    required_source_ids: tuple[DevexReadinessSourceId, ...]
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
        id="evidence_index",
        label="Evidence index",
        path=Path("reports") / "evidence-index.json",
        schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="integration_readiness",
        label="Integration readiness",
        path=Path("reports") / "integration-readiness.json",
        schema_version=INTEGRATION_READINESS_SCHEMA_VERSION,
    ),
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
)
_FAMILY_DEFINITIONS: Final[tuple[_FamilyDefinition, ...]] = (
    _FamilyDefinition(
        id="cli",
        label="CLI",
        surface_ids=("cli",),
        required_source_ids=("runtime_card", "handoff", "evidence_index"),
        ready_action="Use local packet metadata for CLI report discovery and latest-run status.",
        attention_action=(
            "Generate runtime, handoff, and evidence-index packets before CLI "
            "developer-experience surfaces."
        ),
    ),
    _FamilyDefinition(
        id="editor",
        label="Editor",
        surface_ids=("vscode", "editor"),
        required_source_ids=("runtime_card", "evidence_index", "notification_packet"),
        ready_action="Expose value-free run status and problem-matchable evidence in editors.",
        attention_action=(
            "Generate runtime, evidence-index, and notification packets before "
            "editor integrations."
        ),
    ),
    _FamilyDefinition(
        id="local_workbench",
        label="Local workbench",
        surface_ids=("local_workbench",),
        required_source_ids=("evidence_index", "handoff", "runtime_card"),
        ready_action="Render local read-only evidence navigation from sanitized packet metadata.",
        attention_action=(
            "Generate evidence-index, handoff, and runtime packets before local "
            "workbench views."
        ),
    ),
    _FamilyDefinition(
        id="pr_runtime_card",
        label="PR runtime card",
        surface_ids=("pr_runtime_card",),
        required_source_ids=(
            "runtime_card",
            "notification_packet",
            "team_access_control_plan",
        ),
        ready_action=(
            "Use value-free runtime and notification fields for future PR evidence cards."
        ),
        attention_action=(
            "Generate runtime, notification, and access-control packets before "
            "PR runtime cards."
        ),
    ),
    _FamilyDefinition(
        id="desktop",
        label="Desktop",
        surface_ids=("desktop",),
        required_source_ids=("handoff", "evidence_index", "integration_readiness"),
        ready_action="Use handoff and evidence IDs for read-only desktop evidence views.",
        attention_action=(
            "Generate handoff, evidence-index, and integration-readiness packets "
            "before desktop surfaces."
        ),
    ),
    _FamilyDefinition(
        id="cloud",
        label="Cloud",
        surface_ids=("cloud",),
        required_source_ids=(
            "integration_readiness",
            "team_access_control_plan",
            "handoff",
        ),
        ready_action=(
            "Use integration and access-control metadata for future hosted read-only views."
        ),
        attention_action=(
            "Generate integration-readiness, access-control, and handoff packets "
            "before cloud continuity."
        ),
    ),
    _FamilyDefinition(
        id="mobile",
        label="Mobile",
        surface_ids=("mobile",),
        required_source_ids=("handoff", "runtime_card", "notification_packet"),
        ready_action=(
            "Use value-free handoff and notification metadata for phone-friendly status."
        ),
        attention_action=(
            "Generate handoff, runtime, and notification packets before mobile views."
        ),
    ),
)


class DevexReadinessSummary(BaseModel):
    """Aggregate developer experience readiness state."""

    model_config = ConfigDict(extra="forbid")

    status: DevexReadinessStatus
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


class DevexReadinessSource(BaseModel):
    """One local source artifact used for developer-experience planning."""

    model_config = ConfigDict(extra="forbid")

    id: DevexReadinessSourceId
    label: str
    path: str
    state: DevexReadinessSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class DevexReadinessFamily(BaseModel):
    """One future developer-experience surface family and its local readiness boundary."""

    model_config = ConfigDict(extra="forbid")

    id: DevexReadinessFamilyId
    label: str
    status: DevexReadinessFamilyStatus
    surface_ids: tuple[DevexReadinessSurfaceId, ...]
    required_source_ids: tuple[DevexReadinessSourceId, ...]
    present_source_ids: tuple[DevexReadinessSourceId, ...]
    missing_source_ids: tuple[DevexReadinessSourceId, ...]
    blockers: tuple[str, ...] = ()
    link_requirements: tuple[str, ...]
    action_requirements: tuple[str, ...]
    forbidden_actions: tuple[DevexReadinessForbiddenAction, ...]
    next_action: str


class DevexReadinessNextAction(BaseModel):
    """One local action before enabling future developer-experience surfaces."""

    model_config = ConfigDict(extra="forbid")

    priority: DevexReadinessNextActionPriority
    action: str
    source_ids: tuple[DevexReadinessSourceId, ...] = ()
    family_ids: tuple[DevexReadinessFamilyId, ...] = ()


class DevexReadinessPacket(BaseModel):
    """Schema-versioned local developer experience readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.devex-readiness.v1"] = (
        DEVEX_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: DevexReadinessSummary
    sources: tuple[DevexReadinessSource, ...]
    families: tuple[DevexReadinessFamily, ...]
    next_actions: tuple[DevexReadinessNextAction, ...]


@dataclass(frozen=True, slots=True)
class DevexReadinessResult:
    """Result of writing one developer experience readiness packet."""

    output_path: Path
    packet: DevexReadinessPacket


def run_devex_readiness_report(
    *,
    project_root: Path,
    output: DevexReadinessOutput,
    output_path: Path | None = None,
) -> DevexReadinessResult:
    """Write a local developer experience readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported devex-readiness output: {output}"
        raise DevexReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_devex_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "developer experience readiness packet contains secret-like content"
        raise DevexReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="developer experience readiness packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise DevexReadinessError(str(exc)) from exc
    return DevexReadinessResult(output_path=written, packet=packet)


def build_devex_readiness(*, project_root: Path) -> DevexReadinessPacket:
    """Build a value-free developer experience readiness packet from local artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_secret_like_value(_packet_json(packet)):
        msg = "developer experience readiness packet contains secret-like content"
        raise DevexReadinessError(msg)
    return packet


def render_devex_readiness_markdown(packet: DevexReadinessPacket) -> str:
    """Render a human-readable developer experience readiness packet."""

    lines = [
        "# Entroping Developer Experience Readiness",
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
            "Missing Sources | Blockers | Link Requirements | Action Requirements | "
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
            f"{_markdown_cell(', '.join(family.action_requirements))} | "
            f"{_markdown_cell(', '.join(family.forbidden_actions))} | "
            f"{_markdown_cell(family.next_action)} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No developer experience readiness actions are currently needed.")
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


def _build_packet(*, root: Path) -> DevexReadinessPacket:
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    sources = tuple(item.source for item in loaded)
    documents = {item.source.id: item.document for item in loaded}
    families = _families(sources)
    next_actions = _next_actions(sources=sources, families=families)
    return DevexReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(documents),
        summary=_summary(sources=sources, families=families, next_actions=next_actions),
        sources=sources,
        families=families,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: DevexReadinessPacket,
    *,
    output: DevexReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_devex_readiness_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    schema_version: str | None = None
    try:
        path = _resolve_source_path(definition.path, root=root)
    except DevexReadinessError as exc:
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
    except DevexReadinessError as exc:
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
    except DevexReadinessError as exc:
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
    state: DevexReadinessSourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=DevexReadinessSource(
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
        msg = "developer experience readiness source path must stay under the project root"
        raise DevexReadinessError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"developer experience readiness source path uses symlinked component: {display_path}"
        raise DevexReadinessError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = "developer experience readiness source path must stay under the project root"
        raise DevexReadinessError(msg) from exc
    if resolved.exists() and not resolved.is_file():
        msg = f"developer experience readiness source path is not a file: {raw_path.as_posix()}"
        raise DevexReadinessError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "developer experience readiness output path must stay under the project root"
        raise DevexReadinessError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"developer experience readiness output path uses symlinked component: {display_path}"
        raise DevexReadinessError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "developer experience readiness output path must stay under the project root"
        raise DevexReadinessError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "developer experience readiness packet must not be written into .entroping or envs"
        raise DevexReadinessError(msg)
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
            raise DevexReadinessError(msg)
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            msg = f"{artifact.capitalize()} {path.name} changed during read"
            raise DevexReadinessError(msg)
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            raw_bytes = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise DevexReadinessError(msg) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
    if len(raw_bytes) > _MAX_SOURCE_BYTES:
        msg = f"{artifact.capitalize()} {path.name} exceeds {_MAX_SOURCE_BYTES} bytes"
        raise DevexReadinessError(msg)
    return raw_bytes


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise DevexReadinessError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise DevexReadinessError(msg)
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
    if definition.id == "evidence_index":
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
    if definition.id == "integration_readiness":
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
    findings = _required_non_negative_int(summary, "findings", artifact=definition.label)
    return f"{status}; {findings} findings"


def _families(
    sources: tuple[DevexReadinessSource, ...],
) -> tuple[DevexReadinessFamily, ...]:
    source_by_id = {source.id: source for source in sources}
    return tuple(_family(definition, source_by_id) for definition in _FAMILY_DEFINITIONS)


def _family(
    definition: _FamilyDefinition,
    source_by_id: Mapping[DevexReadinessSourceId, DevexReadinessSource],
) -> DevexReadinessFamily:
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
        status: DevexReadinessFamilyStatus = "blocked"
        next_action = "Repair unsafe or invalid source evidence before enabling devex surfaces."
    elif len(present_source_ids) == len(required_sources):
        status = "ready"
        next_action = definition.ready_action
    else:
        status = "attention"
        next_action = definition.attention_action
    return DevexReadinessFamily(
        id=definition.id,
        label=definition.label,
        status=status,
        surface_ids=definition.surface_ids,
        required_source_ids=definition.required_source_ids,
        present_source_ids=present_source_ids,
        missing_source_ids=missing_source_ids,
        blockers=blockers,
        link_requirements=_LINK_REQUIREMENTS,
        action_requirements=_ACTION_REQUIREMENTS,
        forbidden_actions=_FORBIDDEN_ACTIONS,
        next_action=next_action,
    )


def _next_actions(
    *,
    sources: tuple[DevexReadinessSource, ...],
    families: tuple[DevexReadinessFamily, ...],
) -> tuple[DevexReadinessNextAction, ...]:
    actions: list[DevexReadinessNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: DevexReadinessNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            DevexReadinessNextAction(
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
            DevexReadinessNextAction(
                priority=priority,
                action=family.next_action,
                family_ids=(family.id,),
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: list[DevexReadinessNextAction],
) -> tuple[DevexReadinessNextAction, ...]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[DevexReadinessNextAction] = []
    for action in actions:
        key = (action.action, action.source_ids, action.family_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _summary(
    *,
    sources: tuple[DevexReadinessSource, ...],
    families: tuple[DevexReadinessFamily, ...],
    next_actions: tuple[DevexReadinessNextAction, ...],
) -> DevexReadinessSummary:
    blockers_total = len({blocker for family in families for blocker in family.blockers})
    return DevexReadinessSummary(
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


def _status(sources: tuple[DevexReadinessSource, ...]) -> DevexReadinessStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if any(source.state == "missing" for source in sources):
        return "partial"
    return "ready"


def _project_from_documents(
    documents: Mapping[DevexReadinessSourceId, dict[str, object] | None],
) -> str | None:
    for source_id in (
        "handoff",
        "evidence_index",
        "integration_readiness",
        "notification_packet",
        "team_access_control_plan",
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
        raise DevexReadinessError(msg)
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
        raise DevexReadinessError(msg)
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
        raise DevexReadinessError(msg)
    return value


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return escape(value, quote=False).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = escape(str(value), quote=False).replace("`", "&#96;")
    return text.replace("\n", " ").replace("|", "&#124;")


def _packet_json(packet: DevexReadinessPacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True)
    except Exception as exc:
        msg = "developer experience readiness packet could not be serialized safely"
        raise DevexReadinessError(msg) from exc


def _contains_unredacted_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(text)
