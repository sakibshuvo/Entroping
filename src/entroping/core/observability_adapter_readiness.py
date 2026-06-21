"""Local observability adapter readiness packets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core import report_schema_versions as _report_schema_versions
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_index import read_local_evidence_json_artifact_bytes
from entroping.core.evidence_index_report import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.observability_contracts import OBSERVABILITY_FORBIDDEN_VALUE_FIELDS
from entroping.core.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.otel_mapping import OTEL_MAPPING_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION: Final = (
    _report_schema_versions.OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION
)

ObservabilityAdapterReadinessOutput = Literal["md", "json"]
ObservabilityAdapterReadinessStatus = Literal["ready", "partial", "insufficient"]
ObservabilityAdapterReadinessSeverity = Literal["info", "attention", "blocker"]
ObservabilityAdapterReadinessSourceState = Literal["present", "missing", "invalid", "unsafe"]
ObservabilityAdapterStatus = Literal["ready", "attention", "blocked"]
ObservabilityAdapterBoundaryState = Literal["active"]
ObservabilityAdapterNextActionPriority = Literal["high", "medium", "low"]
ObservabilityAdapterSourceId = Literal[
    "observability_packet",
    "otel_mapping",
    "evidence_index",
    "runtime_card",
]
ObservabilityAdapterId = Literal[
    "opentelemetry",
    "datadog",
    "splunk",
    "grafana",
    "generic",
]

_DEFAULT_OUTPUTS: Final[dict[ObservabilityAdapterReadinessOutput, Path]] = {
    "md": Path("reports") / "observability-adapter-readiness.md",
    "json": Path("reports") / "observability-adapter-readiness.json",
}
_SOURCE_LABELS: Final[dict[ObservabilityAdapterSourceId, str]] = {
    "observability_packet": "Observability packet",
    "otel_mapping": "OpenTelemetry mapping",
    "evidence_index": "Evidence index",
    "runtime_card": "Runtime card",
}
_FORBIDDEN_VALUE_FIELDS: Final[tuple[str, ...]] = OBSERVABILITY_FORBIDDEN_VALUE_FIELDS


class ObservabilityAdapterReadinessError(ValueError):
    """Raised when an observability adapter readiness packet cannot be generated."""


class ObservabilityAdapterReadinessSummary(BaseModel):
    """Aggregate readiness for future observability adapters."""

    model_config = ConfigDict(extra="forbid")

    status: ObservabilityAdapterReadinessStatus
    severity: ObservabilityAdapterReadinessSeverity
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    adapters_total: int = Field(ge=0)
    adapters_ready: int = Field(ge=0)
    adapters_attention: int = Field(ge=0)
    adapters_blocked: int = Field(ge=0)
    boundary_controls: int = Field(ge=0)


class ObservabilityAdapterReadinessSource(BaseModel):
    """One local sanitized evidence source for adapter readiness."""

    model_config = ConfigDict(extra="forbid")

    id: ObservabilityAdapterSourceId
    label: str
    path: str
    state: ObservabilityAdapterReadinessSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class ObservabilityAdapterReadinessRow(BaseModel):
    """One future observability adapter readiness row."""

    model_config = ConfigDict(extra="forbid")

    id: ObservabilityAdapterId
    label: str
    status: ObservabilityAdapterStatus
    required_source_ids: tuple[ObservabilityAdapterSourceId, ...]
    optional_source_ids: tuple[ObservabilityAdapterSourceId, ...]
    summary: str
    next_action: str
    forbidden_fields: tuple[str, ...]


class ObservabilityAdapterBoundaryControl(BaseModel):
    """One boundary that keeps this packet local and value-free."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: ObservabilityAdapterBoundaryState
    summary: str


class ObservabilityAdapterNextAction(BaseModel):
    """One next action before enabling future adapter work."""

    model_config = ConfigDict(extra="forbid")

    priority: ObservabilityAdapterNextActionPriority
    action: str
    source_ids: tuple[ObservabilityAdapterSourceId, ...]
    adapter_ids: tuple[ObservabilityAdapterId, ...]


class ObservabilityAdapterReadinessPacket(BaseModel):
    """Schema-versioned observability adapter readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.observability-adapter-readiness.v1"] = (
        OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: ObservabilityAdapterReadinessSummary
    sources: tuple[ObservabilityAdapterReadinessSource, ...]
    adapters: tuple[ObservabilityAdapterReadinessRow, ...]
    boundary_controls: tuple[ObservabilityAdapterBoundaryControl, ...]
    next_actions: tuple[ObservabilityAdapterNextAction, ...]


@dataclass(frozen=True, slots=True)
class ObservabilityAdapterReadinessResult:
    """Result of writing one observability adapter readiness packet."""

    output_path: Path
    packet: ObservabilityAdapterReadinessPacket


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: ObservabilityAdapterSourceId
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: ObservabilityAdapterReadinessSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _AdapterDefinition:
    id: ObservabilityAdapterId
    label: str
    required_source_ids: tuple[ObservabilityAdapterSourceId, ...]
    optional_source_ids: tuple[ObservabilityAdapterSourceId, ...]
    ready_action: str
    attention_action: str


def run_observability_adapter_readiness_report(
    *,
    project_root: Path,
    output: ObservabilityAdapterReadinessOutput,
    output_path: Path | None = None,
) -> ObservabilityAdapterReadinessResult:
    """Write a local observability adapter readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported observability-adapter-readiness output: {output}"
        raise ObservabilityAdapterReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_observability_adapter_readiness_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "observability-adapter-readiness packet contains secret-like content"
        raise ObservabilityAdapterReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="observability adapter readiness packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise ObservabilityAdapterReadinessError(str(exc)) from exc
    return ObservabilityAdapterReadinessResult(output_path=written, packet=packet)


def build_observability_adapter_readiness_packet(
    *,
    project_root: Path,
) -> ObservabilityAdapterReadinessPacket:
    """Build a value-free observability adapter readiness packet from local evidence."""

    root = project_root.expanduser().resolve()
    loaded_sources = tuple(_load_source(definition, root=root) for definition in _sources())
    sources = tuple(loaded.source for loaded in loaded_sources)
    adapters = _adapter_rows(sources)
    controls = _boundary_controls()
    summary = _summary(
        loaded_sources=loaded_sources,
        adapters=adapters,
        controls=controls,
    )
    return ObservabilityAdapterReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_sources(loaded_sources),
        summary=summary,
        sources=sources,
        adapters=adapters,
        boundary_controls=controls,
        next_actions=_next_actions(summary=summary, sources=sources, adapters=adapters),
    )


def render_observability_adapter_readiness_markdown(
    packet: ObservabilityAdapterReadinessPacket,
) -> str:
    """Render a human-readable observability adapter readiness packet."""

    lines = [
        "# Entroping Observability Adapter Readiness",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Severity: `{packet.summary.severity}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Adapters: "
        f"`{packet.summary.adapters_ready}/{packet.summary.adapters_total}` ready, "
        f"`{packet.summary.adapters_attention}` attention, "
        f"`{packet.summary.adapters_blocked}` blocked",
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
            "## Adapter Readiness",
            "",
            "| Adapter | Label | Status | Required Sources | Optional Sources | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for adapter in packet.adapters:
        lines.append(
            "| "
            f"{_markdown_cell(adapter.id)} | "
            f"{_markdown_cell(adapter.label)} | "
            f"{_markdown_cell(adapter.status)} | "
            f"{_markdown_cell(', '.join(adapter.required_source_ids))} | "
            f"{_markdown_cell(', '.join(adapter.optional_source_ids) or 'n/a')} | "
            f"{_markdown_cell(adapter.next_action)} |"
        )

    lines.extend(
        [
            "",
            "## Boundary Controls",
            "",
            "| Control | State | Summary |",
            "| --- | --- | --- |",
        ]
    )
    for control in packet.boundary_controls:
        lines.append(
            "| "
            f"{_markdown_cell(control.id)} | "
            f"{_markdown_cell(control.state)} | "
            f"{_markdown_cell(control.summary)} |"
        )

    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            "| Priority | Action | Sources | Adapters |",
            "| --- | --- | --- | --- |",
        ]
    )
    for action in packet.next_actions:
        lines.append(
            "| "
            f"{_markdown_cell(action.priority)} | "
            f"{_markdown_cell(action.action)} | "
            f"{_markdown_cell(', '.join(action.source_ids))} | "
            f"{_markdown_cell(', '.join(action.adapter_ids))} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: ObservabilityAdapterReadinessPacket,
    *,
    output: ObservabilityAdapterReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_observability_adapter_readiness_markdown(packet)


def _sources() -> tuple[_SourceDefinition, ...]:
    return (
        _SourceDefinition(
            id="observability_packet",
            path=Path("reports") / "observability-packet.json",
            schema_version=OBSERVABILITY_PACKET_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="otel_mapping",
            path=Path("reports") / "otel-mapping.json",
            schema_version=OTEL_MAPPING_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="evidence_index",
            path=Path("reports") / "evidence-index.json",
            schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="runtime_card",
            path=Path("reports") / "runtime-card.json",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
        ),
    )


def _adapter_definitions() -> tuple[_AdapterDefinition, ...]:
    shared_required: tuple[ObservabilityAdapterSourceId, ...] = (
        "observability_packet",
        "otel_mapping",
    )
    shared_optional: tuple[ObservabilityAdapterSourceId, ...] = (
        "evidence_index",
        "runtime_card",
    )
    return (
        _AdapterDefinition(
            id="opentelemetry",
            label="OpenTelemetry",
            required_source_ids=shared_required,
            optional_source_ids=shared_optional,
            ready_action="Use the mapping packet as the value-free contract for an OTLP adapter.",
            attention_action="Generate observability and OpenTelemetry mapping packets first.",
        ),
        _AdapterDefinition(
            id="datadog",
            label="Datadog",
            required_source_ids=shared_required,
            optional_source_ids=shared_optional,
            ready_action="Review Datadog dashboard or monitor design from local packet metadata.",
            attention_action="Generate vendor-neutral packets before Datadog adapter design.",
        ),
        _AdapterDefinition(
            id="splunk",
            label="Splunk",
            required_source_ids=shared_required,
            optional_source_ids=shared_optional,
            ready_action="Review Splunk search or incident design from local packet metadata.",
            attention_action="Generate vendor-neutral packets before Splunk adapter design.",
        ),
        _AdapterDefinition(
            id="grafana",
            label="Grafana",
            required_source_ids=shared_required,
            optional_source_ids=shared_optional,
            ready_action="Review Grafana dashboard design from local packet metadata.",
            attention_action="Generate vendor-neutral packets before Grafana adapter design.",
        ),
        _AdapterDefinition(
            id="generic",
            label="Generic observability",
            required_source_ids=("observability_packet", "evidence_index"),
            optional_source_ids=("otel_mapping", "runtime_card"),
            ready_action="Use the packet as generic read-only observability adapter input.",
            attention_action="Generate observability and evidence-index packets first.",
        ),
    )


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    candidate = root / definition.path
    unsafe_summary = _source_path_error(candidate, root=root)
    if unsafe_summary is not None:
        return _loaded_source(definition, "unsafe", None, unsafe_summary, None, None)
    if not candidate.exists():
        return _loaded_source(definition, "missing", None, "missing", None, None)
    if not candidate.is_file():
        return _loaded_source(definition, "unsafe", None, "not a file", None, None)
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(candidate, root=root)
    if raw_bytes is None:
        state: ObservabilityAdapterReadinessSourceState = (
            "unsafe" if load_error in {"not a file", "path outside project"} else "invalid"
        )
        return _loaded_source(definition, state, None, load_error, None, None)
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _loaded_source(
            definition,
            "invalid",
            None,
            f"invalid UTF-8: {exc.reason}",
            hashlib.sha256(raw_bytes).hexdigest(),
            None,
        )
    if contains_unredacted_evidence_secret(raw_text):
        return _loaded_source(
            definition,
            "unsafe",
            None,
            "secret-like content",
            hashlib.sha256(raw_bytes).hexdigest(),
            None,
        )
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return _loaded_source(
            definition,
            "invalid",
            None,
            f"invalid JSON: {exc.msg}",
            hashlib.sha256(raw_bytes).hexdigest(),
            None,
        )
    if not isinstance(document, dict):
        return _loaded_source(
            definition,
            "invalid",
            None,
            "JSON artifact must be an object",
            hashlib.sha256(raw_bytes).hexdigest(),
            None,
        )
    schema_version = _string_field(document, "schema_version")
    if schema_version != definition.schema_version:
        return _loaded_source(
            definition,
            "invalid",
            schema_version,
            f"schema mismatch: expected {definition.schema_version}",
            hashlib.sha256(raw_bytes).hexdigest(),
            None,
        )
    return _loaded_source(
        definition,
        "present",
        definition.schema_version,
        _source_summary(definition.id, document),
        hashlib.sha256(raw_bytes).hexdigest(),
        document,
    )


def _loaded_source(
    definition: _SourceDefinition,
    state: ObservabilityAdapterReadinessSourceState,
    schema_version: str | None,
    summary: str,
    sha256: str | None,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=ObservabilityAdapterReadinessSource(
            id=definition.id,
            label=_SOURCE_LABELS[definition.id],
            path=definition.path.as_posix(),
            state=state,
            schema_version=_safe_optional_text(schema_version),
            sha256=sha256,
            summary=_safe_text(summary),
        ),
        document=document,
    )


def _source_path_error(path: Path, *, root: Path) -> str | None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return "path outside project"
    if symlink_path is not None:
        return "symlinked path component"
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return "path outside project"
    return None


def _source_summary(source_id: ObservabilityAdapterSourceId, document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    if source_id == "observability_packet":
        status = _string_field(summary, "status") or "unknown"
        severity = _string_field(summary, "severity") or "unknown"
        events = _int_field(summary, "events_total")
        return f"{status} observability, {severity} severity, {_count(events)} events"
    if source_id == "otel_mapping":
        status = _string_field(summary, "status") or "unknown"
        severity = _string_field(summary, "severity") or "unknown"
        mappings = _int_field(summary, "mappings_total")
        return f"{status} otel mapping, {severity} severity, {_count(mappings)} mappings"
    if source_id == "evidence_index":
        status = _string_field(summary, "status") or "unknown"
        total = _int_field(summary, "artifacts_total")
        present = _int_field(summary, "artifacts_present")
        return f"{status} evidence index, {_count(present)}/{_count(total)} artifacts"
    status = _string_field(summary, "status") or "unknown"
    findings = _int_field(summary, "findings")
    links = _int_field(summary, "evidence_links")
    return f"{status} runtime, {_count(findings)} findings, {_count(links)} links"


def _adapter_rows(
    sources: tuple[ObservabilityAdapterReadinessSource, ...],
) -> tuple[ObservabilityAdapterReadinessRow, ...]:
    return tuple(_adapter_row(definition, sources) for definition in _adapter_definitions())


def _adapter_row(
    definition: _AdapterDefinition,
    sources: tuple[ObservabilityAdapterReadinessSource, ...],
) -> ObservabilityAdapterReadinessRow:
    by_id = {source.id: source for source in sources}
    required_sources = tuple(by_id[source_id] for source_id in definition.required_source_ids)
    if any(source.state in {"invalid", "unsafe"} for source in required_sources):
        status: ObservabilityAdapterStatus = "blocked"
        summary = "Required source evidence is invalid or unsafe."
        next_action = "Repair invalid or unsafe local evidence before adapter design."
    elif all(source.state == "present" for source in required_sources):
        status = "ready"
        summary = "Required value-free evidence is present for adapter design."
        next_action = definition.ready_action
    else:
        status = "attention"
        summary = "Required value-free evidence is missing."
        next_action = definition.attention_action
    return ObservabilityAdapterReadinessRow(
        id=definition.id,
        label=definition.label,
        status=status,
        required_source_ids=definition.required_source_ids,
        optional_source_ids=definition.optional_source_ids,
        summary=summary,
        next_action=next_action,
        forbidden_fields=_FORBIDDEN_VALUE_FIELDS,
    )


def _summary(
    *,
    loaded_sources: tuple[_LoadedSource, ...],
    adapters: tuple[ObservabilityAdapterReadinessRow, ...],
    controls: tuple[ObservabilityAdapterBoundaryControl, ...],
) -> ObservabilityAdapterReadinessSummary:
    sources = tuple(loaded.source for loaded in loaded_sources)
    present = sum(1 for source in sources if source.state == "present")
    missing = sum(1 for source in sources if source.state == "missing")
    invalid = sum(1 for source in sources if source.state == "invalid")
    unsafe = sum(1 for source in sources if source.state == "unsafe")
    ready = sum(1 for adapter in adapters if adapter.status == "ready")
    attention = sum(1 for adapter in adapters if adapter.status == "attention")
    blocked = sum(1 for adapter in adapters if adapter.status == "blocked")
    status: ObservabilityAdapterReadinessStatus
    if unsafe or invalid or present == 0 or blocked:
        status = "insufficient"
    elif missing or attention:
        status = "partial"
    else:
        status = "ready"
    severity: ObservabilityAdapterReadinessSeverity = (
        "blocker" if unsafe or invalid or blocked else _source_severity(loaded_sources)
    )
    return ObservabilityAdapterReadinessSummary(
        status=status,
        severity=severity,
        sources_total=len(sources),
        sources_present=present,
        sources_missing=missing,
        sources_invalid=invalid,
        sources_unsafe=unsafe,
        adapters_total=len(adapters),
        adapters_ready=ready,
        adapters_attention=attention,
        adapters_blocked=blocked,
        boundary_controls=len(controls),
    )


def _source_severity(
    loaded_sources: tuple[_LoadedSource, ...],
) -> ObservabilityAdapterReadinessSeverity:
    severities = tuple(
        severity
        for loaded in loaded_sources
        if (severity := _document_severity(loaded.document)) is not None
    )
    if "blocker" in severities:
        return "blocker"
    if "attention" in severities or any(
        loaded.source.state == "missing" for loaded in loaded_sources
    ):
        return "attention"
    return "info"


def _document_severity(
    document: dict[str, object] | None,
) -> ObservabilityAdapterReadinessSeverity | None:
    if document is None:
        return None
    severity = _object_field(document, "summary").get("severity")
    if severity == "blocker":
        return "blocker"
    if severity == "attention":
        return "attention"
    if severity == "info":
        return "info"
    return None


def _boundary_controls() -> tuple[ObservabilityAdapterBoundaryControl, ...]:
    return (
        ObservabilityAdapterBoundaryControl(
            id="no_otlp_export",
            state="active",
            summary="This command writes local readiness evidence only; it does not export OTLP.",
        ),
        ObservabilityAdapterBoundaryControl(
            id="no_vendor_api",
            state="active",
            summary="This command does not call Datadog, Splunk, Grafana, or collectors.",
        ),
        ObservabilityAdapterBoundaryControl(
            id="no_dashboard_mutation",
            state="active",
            summary="This command does not create or mutate dashboards, monitors, or alerts.",
        ),
        ObservabilityAdapterBoundaryControl(
            id="no_external_mutation",
            state="active",
            summary="This command does not mutate tickets, chat, PRs, webhooks, or hosted state.",
        ),
        ObservabilityAdapterBoundaryControl(
            id="deterministic_runtime_preserved",
            state="active",
            summary=(
                "This command does not execute Hurl, run tests, invoke models, or change "
                "entroping run."
            ),
        ),
        ObservabilityAdapterBoundaryControl(
            id="value_free_artifacts",
            state="active",
            summary=(
                "Readiness uses source states, counts, hashes, schema versions, "
                "and paths only."
            ),
        ),
    )


def _next_actions(
    *,
    summary: ObservabilityAdapterReadinessSummary,
    sources: tuple[ObservabilityAdapterReadinessSource, ...],
    adapters: tuple[ObservabilityAdapterReadinessRow, ...],
) -> tuple[ObservabilityAdapterNextAction, ...]:
    present_source_ids = tuple(source.id for source in sources if source.state == "present")
    active_adapter_ids = tuple(adapter.id for adapter in adapters if adapter.status != "ready")
    if summary.status == "ready":
        return (
            ObservabilityAdapterNextAction(
                priority="low",
                action=(
                    "Use this packet as the local value-free adapter readiness contract."
                ),
                source_ids=present_source_ids,
                adapter_ids=tuple(adapter.id for adapter in adapters),
            ),
        )
    if summary.status == "partial":
        return (
            ObservabilityAdapterNextAction(
                priority="medium",
                action="Generate missing sanitized evidence before adapter design.",
                source_ids=present_source_ids,
                adapter_ids=active_adapter_ids,
            ),
        )
    if (
        summary.sources_present == 0
        and summary.sources_invalid == 0
        and summary.sources_unsafe == 0
    ):
        return (
            ObservabilityAdapterNextAction(
                priority="high",
                action="Generate missing sanitized evidence before adapter design.",
                source_ids=present_source_ids,
                adapter_ids=active_adapter_ids,
            ),
        )
    return (
        ObservabilityAdapterNextAction(
            priority="high",
            action="Repair invalid or unsafe evidence before adapter design.",
            source_ids=present_source_ids,
            adapter_ids=active_adapter_ids,
        ),
    )


def _project_from_sources(loaded_sources: tuple[_LoadedSource, ...]) -> str | None:
    for loaded in loaded_sources:
        project = _string_field(loaded.document or {}, "project")
        if project:
            return _safe_text(project)
    return None


def _resolve_output_path(path: Path, *, root: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        msg = "observability-adapter-readiness output path must stay under the project root"
        raise ObservabilityAdapterReadinessError(msg) from exc
    if relative.parts and relative.parts[0] in {".entroping", "envs"}:
        msg = "observability-adapter-readiness packet must not be written into .entroping or envs"
        raise ObservabilityAdapterReadinessError(msg)
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display = _relative_display(symlink_path, root=root)
        msg = f"observability-adapter-readiness output path uses symlinked component: {display}"
        raise ObservabilityAdapterReadinessError(msg)
    return candidate


def _object_field(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _string_field(document: dict[str, object], key: str) -> str | None:
    value = document.get(key)
    return _safe_text(value) if isinstance(value, str) else None


def _int_field(document: dict[str, object], key: str) -> int | None:
    value = document.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _safe_optional_text(value: object) -> str | None:
    return _safe_text(value) if value is not None else None


def _count(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _inline_code(value: str) -> str:
    return escape(value).replace("`", "'")


def _markdown_cell(value: object) -> str:
    escaped = escape(str(value))
    return (
        escaped.replace("\\", "&#92;")
        .replace("|", "\\|")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
        .replace("`", "&#96;")
        .replace("\n", " ")
    )


def _relative_display(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.name
