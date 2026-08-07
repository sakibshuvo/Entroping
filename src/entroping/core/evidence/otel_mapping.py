"""Local OpenTelemetry evidence mapping packets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from entroping.bridge.test_pyramid import TEST_PYRAMID_REPORT_SCHEMA_VERSION
from entroping.core import report_schema_versions as _report_schema_versions
from entroping.core.evidence.evidence_index import read_local_evidence_json_artifact_bytes
from entroping.core.evidence.external_test_evidence import EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
from entroping.core.evidence.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.observability_contracts import OBSERVABILITY_FORBIDDEN_VALUE_FIELDS
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

OTEL_MAPPING_SCHEMA_VERSION: Final = _report_schema_versions.OTEL_MAPPING_SCHEMA_VERSION

OtelMappingOutput = Literal["md", "json"]
OtelMappingStatus = Literal["ready", "partial", "insufficient"]
OtelMappingSeverity = Literal["info", "attention", "blocker"]
OtelMappingSourceState = Literal["present", "missing", "invalid", "unsafe"]
OtelMappingSourceId = Literal[
    "observability_packet",
    "runtime_card",
    "test_pyramid",
    "external_test_evidence",
]
OtelSignal = Literal["resource", "log", "metric", "trace"]
OtelRequirement = Literal["required", "optional"]
OtelValueKind = Literal[
    "identifier",
    "status",
    "count",
    "percent",
    "classification",
    "artifact_path",
]
OtelBoundaryState = Literal["active"]
OtelNextActionPriority = Literal["high", "medium", "low"]

_DEFAULT_OUTPUTS: Final[dict[OtelMappingOutput, Path]] = {
    "md": Path("reports") / "otel-mapping.md",
    "json": Path("reports") / "otel-mapping.json",
}
_FORBIDDEN_VALUE_FIELDS: Final[tuple[str, ...]] = OBSERVABILITY_FORBIDDEN_VALUE_FIELDS
_SOURCE_LABELS: Final[dict[OtelMappingSourceId, str]] = {
    "observability_packet": "Observability packet",
    "runtime_card": "Runtime card",
    "test_pyramid": "Test pyramid",
    "external_test_evidence": "External test evidence",
}


class OtelMappingError(ValueError):
    """Raised when an OpenTelemetry mapping packet cannot be generated safely."""


class OtelMappingSummary(BaseModel):
    """Aggregate OpenTelemetry mapping readiness."""

    model_config = ConfigDict(extra="forbid")

    status: OtelMappingStatus
    severity: OtelMappingSeverity
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    mappings_total: int = Field(ge=0)
    resource_mappings: int = Field(ge=0)
    log_mappings: int = Field(ge=0)
    metric_mappings: int = Field(ge=0)
    trace_mappings: int = Field(ge=0)
    boundary_controls: int = Field(ge=0)


class OtelMappingSource(BaseModel):
    """One local sanitized evidence source for OpenTelemetry mapping."""

    model_config = ConfigDict(extra="forbid")

    id: OtelMappingSourceId
    label: str
    path: str
    state: OtelMappingSourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class OtelAttributeMapping(BaseModel):
    """One future OpenTelemetry attribute mapping."""

    model_config = ConfigDict(extra="forbid")

    signal: OtelSignal
    attribute: str
    requirement: OtelRequirement
    value_kind: OtelValueKind
    source_ids: tuple[OtelMappingSourceId, ...]
    summary: str
    forbidden_fields: tuple[str, ...]


class OtelBoundaryControl(BaseModel):
    """One boundary that keeps this packet local and value-free."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: OtelBoundaryState
    summary: str


class OtelMappingNextAction(BaseModel):
    """One action before a future OTLP adapter is enabled."""

    model_config = ConfigDict(extra="forbid")

    priority: OtelNextActionPriority
    action: str
    source_ids: tuple[OtelMappingSourceId, ...]


class OtelMappingPacket(BaseModel):
    """Schema-versioned OpenTelemetry mapping packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.otel-mapping.v1"] = OTEL_MAPPING_SCHEMA_VERSION
    generated_at: str
    project: str | None
    summary: OtelMappingSummary
    sources: tuple[OtelMappingSource, ...]
    mappings: tuple[OtelAttributeMapping, ...]
    boundary_controls: tuple[OtelBoundaryControl, ...]
    next_actions: tuple[OtelMappingNextAction, ...]


@dataclass(frozen=True, slots=True)
class OtelMappingResult:
    """Result of writing one OpenTelemetry mapping packet."""

    output_path: Path
    packet: OtelMappingPacket


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: OtelMappingSourceId
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: OtelMappingSource
    document: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    total: int
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _SignalCounts:
    total: int
    resource: int
    log: int
    metric: int
    trace: int


def run_otel_mapping_report(
    *,
    project_root: Path,
    output: str,
    output_path: Path | None = None,
) -> OtelMappingResult:
    """Write a local OpenTelemetry evidence mapping packet."""

    selected_output = _otel_mapping_output(output)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(
        output_path or _DEFAULT_OUTPUTS[selected_output],
        root=root,
    )
    packet = build_otel_mapping_packet(
        project_root=root,
    )
    content = _render_packet_content(packet, output=selected_output)
    if contains_unredacted_evidence_secret(content):
        msg = "otel-mapping packet contains secret-like content"
        raise OtelMappingError(msg)
    try:
        written = safe_write_text(destination, content, artifact="otel-mapping packet", root=root)
    except SafeWriteError as exc:
        raise OtelMappingError(str(exc)) from exc
    return OtelMappingResult(output_path=written, packet=packet)


def _otel_mapping_output(output: str) -> OtelMappingOutput:
    if output == "md":
        return "md"
    if output == "json":
        return "json"
    msg = f"Unsupported otel-mapping output: {output}"
    raise OtelMappingError(msg)


def build_otel_mapping_packet(*, project_root: Path) -> OtelMappingPacket:
    """Build a value-free OpenTelemetry mapping packet from local evidence."""

    root = project_root.expanduser().resolve()
    loaded_sources = tuple(_load_source(definition, root=root) for definition in _sources())
    sources = tuple(loaded.source for loaded in loaded_sources)
    mappings = _attribute_mappings()
    controls = _boundary_controls()
    summary = _summary(loaded_sources=loaded_sources, mappings=mappings, controls=controls)
    return OtelMappingPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_sources(loaded_sources),
        summary=summary,
        sources=sources,
        mappings=mappings,
        boundary_controls=controls,
        next_actions=_next_actions(summary=summary, sources=sources),
    )


def render_otel_mapping_markdown(packet: OtelMappingPacket) -> str:
    """Render a human-readable OpenTelemetry mapping packet."""

    lines = [
        "# Entroping OpenTelemetry Mapping",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Severity: `{packet.summary.severity}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Mappings: "
        f"`{packet.summary.mappings_total}` total, "
        f"`{packet.summary.resource_mappings}` resource, "
        f"`{packet.summary.log_mappings}` log, "
        f"`{packet.summary.metric_mappings}` metric, "
        f"`{packet.summary.trace_mappings}` trace",
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
            "## Semantic Preview",
            "",
            "| Signal | Attribute | Requirement | Value Kind | Sources | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for mapping in packet.mappings:
        lines.append(
            "| "
            f"{_markdown_cell(mapping.signal)} | "
            f"{_markdown_cell(mapping.attribute)} | "
            f"{_markdown_cell(mapping.requirement)} | "
            f"{_markdown_cell(mapping.value_kind)} | "
            f"{_markdown_cell(', '.join(mapping.source_ids))} | "
            f"{_markdown_cell(mapping.summary)} |"
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
            "| Priority | Action | Sources |",
            "| --- | --- | --- |",
        ]
    )
    for action in packet.next_actions:
        lines.append(
            "| "
            f"{_markdown_cell(action.priority)} | "
            f"{_markdown_cell(action.action)} | "
            f"{_markdown_cell(', '.join(action.source_ids))} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(packet: OtelMappingPacket, *, output: OtelMappingOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_otel_mapping_markdown(packet)


def _sources() -> tuple[_SourceDefinition, ...]:
    return (
        _SourceDefinition(
            id="observability_packet",
            path=Path("reports") / "observability-packet.json",
            schema_version=OBSERVABILITY_PACKET_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="runtime_card",
            path=Path("reports") / "runtime-card.json",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="test_pyramid",
            path=Path("reports") / "test-pyramid.json",
            schema_version=TEST_PYRAMID_REPORT_SCHEMA_VERSION,
        ),
        _SourceDefinition(
            id="external_test_evidence",
            path=Path("reports") / "external-test-evidence.json",
            schema_version=EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
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
        state: OtelMappingSourceState = (
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
    state: OtelMappingSourceState,
    schema_version: str | None,
    summary: str,
    sha256: str | None,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=OtelMappingSource(
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


def _source_summary(source_id: OtelMappingSourceId, document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    if source_id == "observability_packet":
        status = _string_field(summary, "status") or "unknown"
        severity = _string_field(summary, "severity") or "unknown"
        events = _int_field(summary, "events_total")
        return f"{status} observability, {severity} severity, {_count(events)} events"
    if source_id == "runtime_card":
        status = _string_field(summary, "status") or "unknown"
        findings = _int_field(summary, "findings")
        links = _int_field(summary, "evidence_links")
        return f"{status} runtime, {_count(findings)} findings, {_count(links)} links"
    if source_id == "test_pyramid":
        status = _string_field(summary, "status") or "unknown"
        layers_total = _int_field(summary, "layers_total")
        layers_covered = _int_field(summary, "layers_covered")
        return f"{status} test pyramid, {_count(layers_covered)}/{_count(layers_total)} layers"
    status = _string_field(summary, "status") or "unknown"
    tests = _int_field(summary, "total_tests")
    failures = _int_field(summary, "total_failures")
    coverage = _float_field(summary, "line_coverage_percent")
    return (
        f"{status} external tests, {_count(tests)} tests, "
        f"{_count(failures)} failures, {_percent(coverage)} line coverage"
    )


def _summary(
    *,
    loaded_sources: tuple[_LoadedSource, ...],
    mappings: tuple[OtelAttributeMapping, ...],
    controls: tuple[OtelBoundaryControl, ...],
) -> OtelMappingSummary:
    sources = tuple(loaded.source for loaded in loaded_sources)
    source_counts = _source_counts(sources)
    signal_counts = _signal_counts(mappings)
    return OtelMappingSummary(
        status=_summary_status(source_counts),
        severity=_summary_severity(source_counts, loaded_sources=loaded_sources),
        sources_total=source_counts.total,
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        mappings_total=signal_counts.total,
        resource_mappings=signal_counts.resource,
        log_mappings=signal_counts.log,
        metric_mappings=signal_counts.metric,
        trace_mappings=signal_counts.trace,
        boundary_controls=len(controls),
    )


def _source_counts(sources: tuple[OtelMappingSource, ...]) -> _SourceCounts:
    return _SourceCounts(
        total=len(sources),
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _signal_counts(mappings: tuple[OtelAttributeMapping, ...]) -> _SignalCounts:
    return _SignalCounts(
        total=len(mappings),
        resource=sum(1 for mapping in mappings if mapping.signal == "resource"),
        log=sum(1 for mapping in mappings if mapping.signal == "log"),
        metric=sum(1 for mapping in mappings if mapping.signal == "metric"),
        trace=sum(1 for mapping in mappings if mapping.signal == "trace"),
    )


def _summary_status(counts: _SourceCounts) -> OtelMappingStatus:
    if counts.unsafe or counts.invalid or counts.present == 0:
        return "insufficient"
    if counts.missing:
        return "partial"
    return "ready"


def _summary_severity(
    counts: _SourceCounts,
    *,
    loaded_sources: tuple[_LoadedSource, ...],
) -> OtelMappingSeverity:
    if counts.unsafe or counts.invalid:
        return "blocker"
    return _source_severity(loaded_sources)


def _source_severity(loaded_sources: tuple[_LoadedSource, ...]) -> OtelMappingSeverity:
    sources = tuple(loaded.source for loaded in loaded_sources)
    if any(source.state == "missing" for source in sources):
        return "attention"
    observability = next(
        loaded for loaded in loaded_sources if loaded.source.id == "observability_packet"
    )
    document = cast(dict[str, object], observability.document)
    return _observability_packet_severity(document) or "info"


def _observability_packet_severity(
    document: dict[str, object],
) -> OtelMappingSeverity | None:
    severity = _object_field(document, "summary").get("severity")
    if severity == "blocker":
        return "blocker"
    if severity == "attention":
        return "attention"
    if severity == "info":
        return "info"
    return None


def _attribute_mappings() -> tuple[OtelAttributeMapping, ...]:
    return (
        _mapping(
            "resource",
            "service.name",
            "required",
            "identifier",
            ("observability_packet", "runtime_card"),
            "Future OTLP resources can identify the sanitized project/service name.",
        ),
        _mapping(
            "resource",
            "entroping.project",
            "optional",
            "identifier",
            ("observability_packet", "runtime_card"),
            "Future OTLP resources can carry the local Entroping project label.",
        ),
        _mapping(
            "log",
            "entroping.diagnostic.events",
            "required",
            "count",
            ("observability_packet",),
            "Diagnostic event counts map to value-free log attributes.",
        ),
        _mapping(
            "log",
            "entroping.diagnostic.errors",
            "optional",
            "count",
            ("observability_packet",),
            "Error event counts map to value-free log attributes.",
        ),
        _mapping(
            "metric",
            "entroping.test.total",
            "optional",
            "count",
            ("external_test_evidence",),
            "External test totals map to metrics without test names or logs.",
        ),
        _mapping(
            "metric",
            "entroping.coverage.line_percent",
            "optional",
            "percent",
            ("external_test_evidence", "test_pyramid"),
            "Coverage percentages map to metrics without source contents.",
        ),
        _mapping(
            "trace",
            "entroping.runtime.status",
            "required",
            "status",
            ("runtime_card", "observability_packet"),
            "Runtime status maps to trace attributes for future API-span correlation.",
        ),
        _mapping(
            "log",
            "entroping.runtime_governance.status",
            "required",
            "status",
            ("runtime_card", "test_pyramid"),
            "Runtime-governance semantic preview from sanitized status metadata.",
        ),
        _mapping(
            "metric",
            "entroping.runtime_governance.findings",
            "optional",
            "count",
            ("runtime_card", "test_pyramid"),
            "Runtime-governance semantic preview from value-free finding counts.",
        ),
        _mapping(
            "trace",
            "entroping.runtime_governance.evidence_links",
            "optional",
            "count",
            ("runtime_card",),
            "Runtime-governance semantic preview from local evidence-link counts.",
        ),
    )


def _mapping(
    signal: OtelSignal,
    attribute: str,
    requirement: OtelRequirement,
    value_kind: OtelValueKind,
    source_ids: tuple[OtelMappingSourceId, ...],
    summary: str,
) -> OtelAttributeMapping:
    return OtelAttributeMapping(
        signal=signal,
        attribute=attribute,
        requirement=requirement,
        value_kind=value_kind,
        source_ids=source_ids,
        summary=summary,
        forbidden_fields=_FORBIDDEN_VALUE_FIELDS,
    )


def _boundary_controls() -> tuple[OtelBoundaryControl, ...]:
    return (
        OtelBoundaryControl(
            id="no_otlp_export",
            state="active",
            summary="This command writes local mapping evidence only; it does not export OTLP.",
        ),
        OtelBoundaryControl(
            id="no_vendor_api",
            state="active",
            summary="This command does not call Datadog, Splunk, Grafana, or collectors.",
        ),
        OtelBoundaryControl(
            id="value_free_sources",
            state="active",
            summary="Mappings use states, counts, statuses, hashes, and relative artifact paths.",
        ),
        OtelBoundaryControl(
            id="no_external_mutation",
            state="active",
            summary=(
                "This command does not mutate dashboards, monitors, tickets, chat, PRs, "
                "or hosted state."
            ),
        ),
        OtelBoundaryControl(
            id="deterministic_runtime_preserved",
            state="active",
            summary=(
                "This command does not execute Hurl, run tests, invoke models, or change "
                "entroping run."
            ),
        ),
    )


def _next_actions(
    *,
    summary: OtelMappingSummary,
    sources: tuple[OtelMappingSource, ...],
) -> tuple[OtelMappingNextAction, ...]:
    present_source_ids: tuple[OtelMappingSourceId, ...] = tuple(
        source.id for source in sources if source.state == "present"
    )
    if summary.status == "ready":
        return (
            OtelMappingNextAction(
                priority="low",
                action="Use this packet as the value-free contract for a future OTLP adapter.",
                source_ids=present_source_ids,
            ),
        )
    if summary.status == "partial":
        return (
            OtelMappingNextAction(
                priority="medium",
                action="Generate missing sanitized evidence before enabling an OTLP adapter.",
                source_ids=present_source_ids,
            ),
        )
    if (
        summary.sources_present == 0
        and summary.sources_invalid == 0
        and summary.sources_unsafe == 0
    ):
        return (
            OtelMappingNextAction(
                priority="high",
                action="Generate missing sanitized evidence before enabling an OTLP adapter.",
                source_ids=present_source_ids,
            ),
        )
    return (
        OtelMappingNextAction(
            priority="high",
            action="Repair invalid or unsafe evidence before enabling an OTLP adapter.",
            source_ids=present_source_ids,
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
        msg = "otel-mapping output path must stay under the project root"
        raise OtelMappingError(msg) from exc
    if relative.parts and relative.parts[0] in {".entroping", "envs"}:
        msg = "otel-mapping packet must not be written into .entroping or envs"
        raise OtelMappingError(msg)
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display = _relative_display(symlink_path, root=root)
        msg = f"otel-mapping output path uses symlinked component: {display}"
        raise OtelMappingError(msg)
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


def _float_field(document: dict[str, object], key: str) -> float | None:
    value = document.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _safe_optional_text(value: object) -> str | None:
    return _safe_text(value) if value is not None else None


def _count(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _percent(value: float | None) -> str:
    return f"{value:g}%" if value is not None else "unknown"


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
