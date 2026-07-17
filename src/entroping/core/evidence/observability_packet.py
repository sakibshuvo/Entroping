"""Vendor-neutral observability packets from local sanitized evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_packet_base import (
    EvidencePacketResult,
    write_evidence_packet_report,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_schema_versions import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION, RuntimeCardReport
from entroping.core.safe_write import safe_write_text
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    StructuredDiagnosticEvent,
    StructuredDiagnosticsError,
    read_diagnostic_events,
)

OBSERVABILITY_PACKET_SCHEMA_VERSION: Final = "entroping.observability-packet.v1"

ObservabilityOutput = Literal["md", "json"]
ObservabilityStatus = Literal["ready", "partial", "insufficient"]
ObservabilitySeverity = Literal["info", "attention", "blocker"]
ObservabilitySourceState = Literal["present", "missing", "invalid", "unsafe"]
ObservabilitySourceId = Literal["diagnostics", "runtime_card", "evidence_index"]
ObservabilitySurface = Literal[
    "opentelemetry",
    "datadog",
    "splunk",
    "grafana",
    "generic",
]
ObservabilityEventSeverity = Literal["debug", "info", "warning", "error"]

_MAX_OBSERVABILITY_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DIAGNOSTICS_PATH: Final = Path(".entroping") / "latest-diagnostics.jsonl"
_RUNTIME_CARD_PATH: Final = Path("reports") / "runtime-card.json"
_EVIDENCE_INDEX_PATH: Final = Path("reports") / "evidence-index.json"
_DEFAULT_OUTPUTS: Final[dict[ObservabilityOutput, Path]] = {
    "md": Path("reports") / "observability-packet.md",
    "json": Path("reports") / "observability-packet.json",
}
_SOURCE_LABELS: Final[dict[ObservabilitySourceId, str]] = {
    "diagnostics": "Structured diagnostics",
    "runtime_card": "Runtime card",
    "evidence_index": "Evidence index",
}
_SOURCE_PATHS: Final[dict[ObservabilitySourceId, Path]] = {
    "diagnostics": _DIAGNOSTICS_PATH,
    "runtime_card": _RUNTIME_CARD_PATH,
    "evidence_index": _EVIDENCE_INDEX_PATH,
}
_SURFACE_LABELS: Final[dict[ObservabilitySurface, str]] = {
    "opentelemetry": "OpenTelemetry",
    "datadog": "Datadog",
    "splunk": "Splunk",
    "grafana": "Grafana",
    "generic": "Generic observability",
}
_SURFACE_ACTIONS: Final[dict[ObservabilitySurface, str]] = {
    "opentelemetry": "Use this packet as value-free OTLP adapter input.",
    "datadog": "Attach this packet to a Datadog dashboard or monitor review.",
    "splunk": "Attach this packet to a Splunk search or incident review.",
    "grafana": "Attach this packet to a Grafana dashboard or incident review.",
    "generic": "Use this packet as vendor-neutral observability evidence.",
}


class ObservabilityPacketError(ValueError):
    """Raised when an observability packet cannot be generated safely."""


class ObservabilitySummary(BaseModel):
    """Aggregate observability packet state."""

    model_config = ConfigDict(extra="forbid")

    status: ObservabilityStatus
    severity: ObservabilitySeverity
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    events_total: int = Field(ge=0)
    debug_events: int = Field(ge=0)
    info_events: int = Field(ge=0)
    warning_events: int = Field(ge=0)
    error_events: int = Field(ge=0)


class ObservabilityRuntimeSummary(BaseModel):
    """Value-free runtime-card fields carried into observability."""

    model_config = ConfigDict(extra="forbid")

    status: str
    findings: int = Field(ge=0)
    evidence_links: int = Field(ge=0)
    failed_gate_ids: int = Field(ge=0)


class ObservabilitySource(BaseModel):
    """One local artifact used to build the packet."""

    model_config = ConfigDict(extra="forbid")

    id: ObservabilitySourceId
    label: str
    path: str
    state: ObservabilitySourceState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class ObservabilityEventSummary(BaseModel):
    """One value-free diagnostic event summary."""

    model_config = ConfigDict(extra="forbid")

    component: str
    operation: str
    severity: ObservabilityEventSeverity
    code: str
    summary: str


class ObservabilityComponentSummary(BaseModel):
    """Aggregated diagnostic event counts for one component."""

    model_config = ConfigDict(extra="forbid")

    component: str
    events_total: int = Field(ge=0)
    debug_events: int = Field(ge=0)
    info_events: int = Field(ge=0)
    warning_events: int = Field(ge=0)
    error_events: int = Field(ge=0)
    operations: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()


class ObservabilityMessage(BaseModel):
    """One downstream observability surface summary."""

    model_config = ConfigDict(extra="forbid")

    surface: ObservabilitySurface
    label: str
    severity: ObservabilitySeverity
    title: str
    body: str
    next_action: str
    artifact_paths: tuple[str, ...] = ()


class ObservabilityPacket(BaseModel):
    """Schema-versioned vendor-neutral observability packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.observability-packet.v1"] = (
        OBSERVABILITY_PACKET_SCHEMA_VERSION
    )
    generated_at: str
    project: str | None
    summary: ObservabilitySummary
    runtime: ObservabilityRuntimeSummary | None
    sources: tuple[ObservabilitySource, ...]
    events: tuple[ObservabilityEventSummary, ...]
    components: tuple[ObservabilityComponentSummary, ...]
    messages: tuple[ObservabilityMessage, ...]


@dataclass(frozen=True, slots=True)
class ObservabilityPacketResult:
    """Result of writing one observability packet."""

    output_path: Path
    packet: ObservabilityPacket


@dataclass(frozen=True, slots=True)
class _LoadedDiagnostics:
    source: ObservabilitySource
    events: tuple[StructuredDiagnosticEvent, ...]


@dataclass(frozen=True, slots=True)
class _LoadedRuntimeCard:
    source: ObservabilitySource
    card: RuntimeCardReport | None


@dataclass(frozen=True, slots=True)
class _LoadedEvidenceIndex:
    source: ObservabilitySource


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    total: int
    present: int
    missing: int
    invalid: int
    unsafe: int
    status: ObservabilityStatus


@dataclass(frozen=True, slots=True)
class _EventCounts:
    total: int
    debug: int
    info: int
    warning: int
    error: int


def run_observability_packet_report(
    *,
    project_root: Path,
    output: str,
    output_path: Path | None = None,
) -> ObservabilityPacketResult:
    """Write a local vendor-neutral observability packet."""

    observability_output = _observability_output(output)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(
        output_path or _DEFAULT_OUTPUTS[observability_output],
        root=root,
    )
    packet = build_observability_packet(
        project_root=root,
        packet_path=destination.relative_to(root).as_posix(),
    )
    result: EvidencePacketResult[ObservabilityPacket] = write_evidence_packet_report(
        project_root=root,
        output=observability_output,
        output_path=destination,
        packet=packet,
        render_markdown=render_observability_packet_markdown,
        has_secret_content=_contains_unredacted_secret_like_value,
        unsafe_content_message="observability packet contains secret-like content",
        artifact="observability packet",
        error_type=ObservabilityPacketError,
        safe_write=safe_write_text,
    )
    return ObservabilityPacketResult(output_path=result.output_path, packet=result.packet)


def _observability_output(output: str) -> ObservabilityOutput:
    if output == "md":
        return "md"
    if output == "json":
        return "json"
    msg = f"Unsupported observability output: {output}"
    raise ObservabilityPacketError(msg)


def build_observability_packet(
    *,
    project_root: Path,
    packet_path: str = "reports/observability-packet.json",
) -> ObservabilityPacket:
    """Build a value-free observability packet from local evidence."""

    root = project_root.expanduser().resolve()
    diagnostics = _load_diagnostics(root=root)
    runtime_card = _load_runtime_card(root=root)
    evidence_index = _load_evidence_index(root=root)
    runtime = _runtime_summary(runtime_card.card)
    event_summaries = tuple(_event_summary(event) for event in diagnostics.events)
    sources = (diagnostics.source, runtime_card.source, evidence_index.source)
    summary = _summary(sources=sources, runtime=runtime, events=event_summaries)
    return ObservabilityPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_runtime_card(runtime_card.card),
        summary=summary,
        runtime=runtime,
        sources=sources,
        events=event_summaries,
        components=_component_summaries(event_summaries),
        messages=_messages(
            sources=sources,
            summary=summary,
            runtime=runtime,
            packet_path=_safe_text(packet_path),
        ),
    )


def render_observability_packet_markdown(packet: ObservabilityPacket) -> str:
    """Render a human-readable observability packet."""

    lines = [
        "# Entroping Observability Packet",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Severity: `{packet.summary.severity}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        (
            f"- Sources: `{packet.summary.sources_present}/"
            + f"{packet.summary.sources_total}` present, "
            + f"`{packet.summary.sources_missing}` missing, "
            + f"`{packet.summary.sources_invalid}` invalid, "
            + f"`{packet.summary.sources_unsafe}` unsafe"
        ),
        (
            f"- Events: `{packet.summary.events_total}` total, "
            + f"`{packet.summary.error_events}` error, "
            + f"`{packet.summary.warning_events}` warning, "
            + f"`{packet.summary.info_events}` info, "
            + f"`{packet.summary.debug_events}` debug"
        ),
        "",
        "## Runtime",
        "",
    ]
    if packet.runtime is None:
        lines.append("No runtime-card summary is available.")
    else:
        lines.extend(
            [
                f"- Runtime status: `{_inline_code(packet.runtime.status)}`",
                f"- Findings: `{packet.runtime.findings}`",
                f"- Evidence links: `{packet.runtime.evidence_links}`",
                f"- Failed gates: `{packet.runtime.failed_gate_ids}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Source | State | Path | Schema | SHA-256 | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
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
            "## Components",
            "",
            "| Component | Total | Error | Warning | Info | Debug | Operations | Codes |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for component in packet.components:
        lines.append(
            "| "
            f"{_markdown_cell(component.component)} | "
            f"{component.events_total} | "
            f"{component.error_events} | "
            f"{component.warning_events} | "
            f"{component.info_events} | "
            f"{component.debug_events} | "
            f"{_markdown_cell(', '.join(component.operations) or 'n/a')} | "
            f"{_markdown_cell(', '.join(component.codes) or 'n/a')} |"
        )

    lines.extend(
        [
            "",
            "## Events",
            "",
            "| Component | Operation | Severity | Code | Summary |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for event in packet.events:
        lines.append(
            "| "
            f"{_markdown_cell(event.component)} | "
            f"{_markdown_cell(event.operation)} | "
            f"{_markdown_cell(event.severity)} | "
            f"{_markdown_cell(event.code)} | "
            f"{_markdown_cell(event.summary)} |"
        )

    lines.extend(
        [
            "",
            "## Messages",
            "",
            "| Surface | Severity | Title | Next Action | Artifact Paths |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for message in packet.messages:
        lines.append(
            "| "
            f"{_markdown_cell(message.surface)} | "
            f"{_markdown_cell(message.severity)} | "
            f"{_markdown_cell(message.title)} | "
            f"{_markdown_cell(message.next_action)} | "
            f"{_markdown_cell(', '.join(message.artifact_paths) or 'n/a')} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_diagnostics(*, root: Path) -> _LoadedDiagnostics:
    source_id: ObservabilitySourceId = "diagnostics"
    try:
        path = _resolve_source_path(_DIAGNOSTICS_PATH, root=root)
    except ObservabilityPacketError as exc:
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            ),
            events=(),
        )
    if not path.exists():
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="missing",
                schema_version=None,
                sha256=None,
                summary="Structured diagnostics log is missing.",
            ),
            events=(),
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact="structured diagnostics log")
        raw_text = raw_bytes.decode("utf-8")
    except ObservabilityPacketError as exc:
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            ),
            events=(),
        )
    except UnicodeDecodeError as exc:
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Could not decode structured diagnostics as UTF-8: {exc}"),
            ),
            events=(),
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary="Structured diagnostics log contains secret-like content.",
            ),
            events=(),
        )
    try:
        events = tuple(read_diagnostic_events(path))
    except StructuredDiagnosticsError as exc:
        return _LoadedDiagnostics(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(str(exc)),
            ),
            events=(),
        )
    return _LoadedDiagnostics(
        source=_source(
            source_id,
            state="present",
            schema_version=STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            summary=f"{len(events)} diagnostic events.",
        ),
        events=events,
    )


def _load_runtime_card(*, root: Path) -> _LoadedRuntimeCard:
    source_id: ObservabilitySourceId = "runtime_card"
    try:
        path = _resolve_source_path(_RUNTIME_CARD_PATH, root=root)
    except ObservabilityPacketError as exc:
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            ),
            card=None,
        )
    if not path.exists():
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="missing",
                schema_version=None,
                sha256=None,
                summary="Runtime card is missing.",
            ),
            card=None,
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact="runtime card")
        raw_text = raw_bytes.decode("utf-8")
    except ObservabilityPacketError as exc:
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            ),
            card=None,
        )
    except UnicodeDecodeError as exc:
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Could not decode runtime card as UTF-8: {exc}"),
            ),
            card=None,
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary="Runtime card contains secret-like content.",
            ),
            card=None,
        )
    try:
        document = _json_object(raw_text, artifact="Runtime card")
        schema_version = _schema_version(document)
        if schema_version != RUNTIME_CARD_SCHEMA_VERSION:
            msg = (
                "Runtime card uses unsupported schema "
                f"{schema_version or 'unknown'}; expected {RUNTIME_CARD_SCHEMA_VERSION}"
            )
            raise ObservabilityPacketError(msg)
        card = RuntimeCardReport.model_validate(document)
    except (ValidationError, ObservabilityPacketError) as exc:
        return _LoadedRuntimeCard(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Invalid runtime card: {exc}"),
            ),
            card=None,
        )
    return _LoadedRuntimeCard(
        source=_source(
            source_id,
            state="present",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            summary=f"{card.summary.status} runtime evidence",
        ),
        card=card,
    )


def _load_evidence_index(*, root: Path) -> _LoadedEvidenceIndex:
    source_id: ObservabilitySourceId = "evidence_index"
    try:
        path = _resolve_source_path(_EVIDENCE_INDEX_PATH, root=root)
    except ObservabilityPacketError as exc:
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            )
        )
    if not path.exists():
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="missing",
                schema_version=None,
                sha256=None,
                summary="Evidence index is missing.",
            )
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact="evidence index")
        raw_text = raw_bytes.decode("utf-8")
    except ObservabilityPacketError as exc:
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=str(exc),
            )
        )
    except UnicodeDecodeError as exc:
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Could not decode evidence index as UTF-8: {exc}"),
            )
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="unsafe",
                schema_version=None,
                sha256=None,
                summary="Evidence index contains secret-like content.",
            )
        )
    try:
        document = _json_object(raw_text, artifact="Evidence index")
        schema_version = _schema_version(document)
        if schema_version != EVIDENCE_INDEX_SCHEMA_VERSION:
            msg = (
                "Evidence index uses unsupported schema "
                f"{schema_version or 'unknown'}; expected {EVIDENCE_INDEX_SCHEMA_VERSION}"
            )
            raise ObservabilityPacketError(msg)
        status = _evidence_index_status(document)
    except ObservabilityPacketError as exc:
        return _LoadedEvidenceIndex(
            source=_source(
                source_id,
                state="invalid",
                schema_version=None,
                sha256=None,
                summary=_safe_text(f"Invalid evidence index: {exc}"),
            )
        )
    return _LoadedEvidenceIndex(
        source=_source(
            source_id,
            state="present",
            schema_version=EVIDENCE_INDEX_SCHEMA_VERSION,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            summary=f"{status} evidence index",
        )
    )


def _source(
    source_id: ObservabilitySourceId,
    *,
    state: ObservabilitySourceState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
) -> ObservabilitySource:
    return ObservabilitySource(
        id=source_id,
        label=_SOURCE_LABELS[source_id],
        path=_SOURCE_PATHS[source_id].as_posix(),
        state=state,
        schema_version=schema_version,
        sha256=sha256,
        summary=_safe_text(summary),
    )


def _runtime_summary(card: RuntimeCardReport | None) -> ObservabilityRuntimeSummary | None:
    if card is None:
        return None
    failed_gate_ids = len(card.run.failed_gate_ids) if card.run is not None else 0
    return ObservabilityRuntimeSummary(
        status=card.summary.status,
        findings=card.summary.findings,
        evidence_links=card.summary.evidence_links,
        failed_gate_ids=failed_gate_ids,
    )


def _project_from_runtime_card(card: RuntimeCardReport | None) -> str | None:
    if card is None or card.run is None:
        return _safe_optional_text(None)
    return _safe_optional_text(card.run.project)


def _event_summary(event: StructuredDiagnosticEvent) -> ObservabilityEventSummary:
    return ObservabilityEventSummary(
        component=_safe_text(event.component),
        operation=_safe_text(event.operation),
        severity=event.severity,
        code=_safe_text(event.code),
        summary=_safe_text(event.summary),
    )


def _component_summaries(
    events: tuple[ObservabilityEventSummary, ...],
) -> tuple[ObservabilityComponentSummary, ...]:
    by_component: dict[str, list[ObservabilityEventSummary]] = {}
    for event in events:
        by_component.setdefault(event.component, []).append(event)
    summaries: list[ObservabilityComponentSummary] = []
    for component in sorted(by_component):
        component_events = by_component[component]
        summaries.append(
            ObservabilityComponentSummary(
                component=component,
                events_total=len(component_events),
                debug_events=sum(1 for event in component_events if event.severity == "debug"),
                info_events=sum(1 for event in component_events if event.severity == "info"),
                warning_events=sum(
                    1 for event in component_events if event.severity == "warning"
                ),
                error_events=sum(1 for event in component_events if event.severity == "error"),
                operations=tuple(sorted({event.operation for event in component_events})),
                codes=tuple(sorted({event.code for event in component_events})),
            )
        )
    return tuple(summaries)


def _summary(
    *,
    sources: tuple[ObservabilitySource, ...],
    runtime: ObservabilityRuntimeSummary | None,
    events: tuple[ObservabilityEventSummary, ...],
) -> ObservabilitySummary:
    source_counts = _source_counts(sources)
    event_counts = _event_counts(events)
    return ObservabilitySummary(
        status=source_counts.status,
        severity=_severity(
            status=source_counts.status,
            runtime=runtime,
            warning_events=event_counts.warning,
            error_events=event_counts.error,
        ),
        sources_total=source_counts.total,
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        events_total=event_counts.total,
        debug_events=event_counts.debug,
        info_events=event_counts.info,
        warning_events=event_counts.warning,
        error_events=event_counts.error,
    )


def _source_counts(sources: tuple[ObservabilitySource, ...]) -> _SourceCounts:
    present = sum(1 for source in sources if source.state == "present")
    missing = sum(1 for source in sources if source.state == "missing")
    invalid = sum(1 for source in sources if source.state == "invalid")
    unsafe = sum(1 for source in sources if source.state == "unsafe")
    if present == 0:
        status: ObservabilityStatus = "insufficient"
    elif missing or invalid or unsafe:
        status = "partial"
    else:
        status = "ready"
    return _SourceCounts(
        total=len(sources),
        status=status,
        present=present,
        missing=missing,
        invalid=invalid,
        unsafe=unsafe,
    )


def _event_counts(events: tuple[ObservabilityEventSummary, ...]) -> _EventCounts:
    return _EventCounts(
        total=len(events),
        debug=sum(1 for event in events if event.severity == "debug"),
        info=sum(1 for event in events if event.severity == "info"),
        warning=sum(1 for event in events if event.severity == "warning"),
        error=sum(1 for event in events if event.severity == "error"),
    )


def _severity(
    *,
    status: ObservabilityStatus,
    runtime: ObservabilityRuntimeSummary | None,
    warning_events: int,
    error_events: int,
) -> ObservabilitySeverity:
    if error_events > 0:
        return "blocker"
    if runtime is not None and runtime.failed_gate_ids > 0:
        return "blocker"
    if runtime is not None and runtime.status.lower() in {"fail", "failed", "failure"}:
        return "blocker"
    if status in {"partial", "insufficient"} or warning_events > 0:
        return "attention"
    if runtime is not None and runtime.status.lower() in {"attention", "warn", "warning"}:
        return "attention"
    return "info"


def _messages(
    *,
    sources: tuple[ObservabilitySource, ...],
    summary: ObservabilitySummary,
    runtime: ObservabilityRuntimeSummary | None,
    packet_path: str,
) -> tuple[ObservabilityMessage, ...]:
    artifact_paths = _artifact_paths(packet_path=packet_path, sources=sources)
    title = _message_title(summary.severity)
    body = _message_body(summary=summary, runtime=runtime)
    return tuple(
        ObservabilityMessage(
            surface=surface,
            label=_SURFACE_LABELS[surface],
            severity=summary.severity,
            title=title,
            body=body,
            next_action=_SURFACE_ACTIONS[surface],
            artifact_paths=artifact_paths,
        )
        for surface in _SURFACE_LABELS
    )


def _artifact_paths(
    *,
    packet_path: str,
    sources: tuple[ObservabilitySource, ...],
) -> tuple[str, ...]:
    paths: list[str] = [_safe_text(packet_path)]
    for source in sources:
        if source.state == "present" and source.path not in paths:
            paths.append(source.path)
    return tuple(paths)


def _message_title(severity: ObservabilitySeverity) -> str:
    if severity == "blocker":
        return "Entroping observability signals need attention"
    if severity == "attention":
        return "Entroping observability evidence needs review"
    return "Entroping observability evidence is ready"


def _message_body(
    *,
    summary: ObservabilitySummary,
    runtime: ObservabilityRuntimeSummary | None,
) -> str:
    runtime_status = runtime.status if runtime is not None else "unknown"
    return _safe_text(
        f"Runtime status {runtime_status}; {summary.events_total} diagnostic events; "
        f"{summary.error_events} errors; {summary.warning_events} warnings; "
        f"{summary.sources_present}/{summary.sources_total} sources present."
    )


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    path = root / raw_path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "observability source path must stay under the project root"
        raise ObservabilityPacketError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"observability source path uses symlinked component: {display_path}"
        raise ObservabilityPacketError(msg)
    if path.exists() and not path.is_file():
        msg = f"observability source path is not a file: {raw_path.as_posix()}"
        raise ObservabilityPacketError(msg)
    return path


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "observability output path must stay under the project root"
        raise ObservabilityPacketError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"observability output path uses symlinked component: {display_path}"
        raise ObservabilityPacketError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "observability output path must stay under the project root"
        raise ObservabilityPacketError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "observability packet must not be written into .entroping or envs"
        raise ObservabilityPacketError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    try:
        raw_bytes = path.read_bytes()
        if len(raw_bytes) > _MAX_OBSERVABILITY_ARTIFACT_BYTES:
            msg = (
                f"{artifact.capitalize()} {path.name} exceeds "
                f"{_MAX_OBSERVABILITY_ARTIFACT_BYTES} bytes"
            )
            raise ObservabilityPacketError(msg)
        return raw_bytes
    except ObservabilityPacketError:
        raise
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise ObservabilityPacketError(msg) from exc


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"{artifact} contains invalid JSON: {exc}"
        raise ObservabilityPacketError(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"{artifact} must be a JSON object"
        raise ObservabilityPacketError(msg)
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if isinstance(key, str):
            document[key] = value
    return document


def _json_object_field(
    document: dict[str, object],
    field: str,
    *,
    artifact: str,
) -> dict[str, object]:
    value = document.get(field)
    if not isinstance(value, dict):
        msg = f"{artifact} {field} must be a JSON object"
        raise ObservabilityPacketError(msg)
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _evidence_index_status(document: dict[str, object]) -> str:
    summary = _json_object_field(document, "summary", artifact="Evidence index")
    status = summary.get("status")
    if not isinstance(status, str) or status not in {"ready", "partial", "insufficient"}:
        msg = "Evidence index summary status is missing or unsupported"
        raise ObservabilityPacketError(msg)
    return _safe_text(status)


def _safe_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    safe = _safe_text(value)
    return safe or None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    backslash_placeholder = "\0ENTROPING_BACKSLASH\0"
    text = value.replace("\r", " ").replace("\\", backslash_placeholder)
    text = escape(text, quote=False).replace("|", "\\|")
    return text.replace(backslash_placeholder, "&#92;")
