
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import ClassVar, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index import read_local_evidence_json_artifact_bytes
from entroping.core.evidence.otel_mapping import OTEL_MAPPING_SCHEMA_VERSION
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

OTLP_PREVIEW_SCHEMA_VERSION: Final = "entroping.otlp-preview.v1"

OtlpPreviewOutput = Literal["md", "json"]
OtlpPreviewStatus = Literal["ready", "partial", "insufficient"]
OtlpPreviewSeverity = Literal["info", "attention", "blocker"]
OtlpPreviewSourceState = Literal["present", "missing", "invalid", "unsafe"]
OtlpPreviewSourceId = Literal["run_report", "runtime_card", "otel_mapping"]
OtlpPreviewValueKind = Literal["string", "count", "status", "classification"]
OtlpPreviewSpanStatus = Literal["OK", "ERROR"]
OtlpPreviewNextActionPriority = Literal["high", "medium", "low"]

_DEFAULT_OUTPUTS: Final[dict[OtlpPreviewOutput, Path]] = {
    "md": Path("reports") / "otlp-preview.md",
    "json": Path("reports") / "otlp-preview.json",
}
_SOURCE_LABELS: Final[dict[OtlpPreviewSourceId, str]] = {
    "run_report": "Run report",
    "runtime_card": "Runtime card",
    "otel_mapping": "OpenTelemetry mapping",
}


class OtlpPreviewError(ValueError):
    pass


class OtlpPreviewSummary(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: OtlpPreviewStatus
    severity: OtlpPreviewSeverity
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    resource_attributes_total: int = Field(ge=0)
    log_records_total: int = Field(ge=0)
    metrics_total: int = Field(ge=0)
    spans_total: int = Field(ge=0)


class OtlpPreviewSource(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: OtlpPreviewSourceId
    label: str
    path: str
    state: OtlpPreviewSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class OtlpPreviewAttribute(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    key: str
    value_kind: OtlpPreviewValueKind
    value: str | int
    source_ids: tuple[OtlpPreviewSourceId, ...]


class OtlpPreviewLogRecord(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str
    severity_text: OtlpPreviewSeverity
    attributes: tuple[OtlpPreviewAttribute, ...]


class OtlpPreviewMetric(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str
    unit: str
    value_kind: Literal["sum", "gauge"]
    value: int
    attributes: tuple[OtlpPreviewAttribute, ...] = ()


class OtlpPreviewSpan(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str
    status_code: OtlpPreviewSpanStatus
    attributes: tuple[OtlpPreviewAttribute, ...]


class OtlpPreviewFixture(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    transport: Literal["otlp-json-preview"] = "otlp-json-preview"
    network_policy: Literal["local-only-no-export"] = "local-only-no-export"
    resource_attributes: tuple[OtlpPreviewAttribute, ...]
    log_records: tuple[OtlpPreviewLogRecord, ...]
    metrics: tuple[OtlpPreviewMetric, ...]
    spans: tuple[OtlpPreviewSpan, ...]


class OtlpPreviewBoundaryControl(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str
    summary: str


class OtlpPreviewNextAction(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    priority: OtlpPreviewNextActionPriority
    action: str
    source_ids: tuple[OtlpPreviewSourceId, ...]


class OtlpPreviewPacket(BaseModel):

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.otlp-preview.v1"] = OTLP_PREVIEW_SCHEMA_VERSION
    generated_at: str
    summary: OtlpPreviewSummary
    sources: tuple[OtlpPreviewSource, ...]
    fixture: OtlpPreviewFixture
    boundary_controls: tuple[OtlpPreviewBoundaryControl, ...]
    next_actions: tuple[OtlpPreviewNextAction, ...]


@dataclass(frozen=True, slots=True)
class OtlpPreviewResult:

    output_path: Path
    packet: OtlpPreviewPacket


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: OtlpPreviewSourceId
    path: Path
    schema_version: str
    required: bool


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: OtlpPreviewSource
    document: dict[str, object] | None


def run_otlp_preview_report(
    *,
    project_root: Path,
    output: str,
    output_path: Path | None = None,
) -> OtlpPreviewResult:

    selected_output = _otlp_preview_output(output)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(
        output_path or _DEFAULT_OUTPUTS[selected_output],
        root=root,
    )
    packet = build_otlp_preview_packet(project_root=root)
    content = _render_packet_content(packet, output=selected_output)
    if contains_unredacted_evidence_secret(content):
        msg = "otlp-preview packet contains secret-like content"
        raise OtlpPreviewError(msg)
    try:
        written = safe_write_text(destination, content, artifact="otlp-preview packet", root=root)
    except SafeWriteError as exc:
        raise OtlpPreviewError(str(exc)) from exc
    return OtlpPreviewResult(output_path=written, packet=packet)


def build_otlp_preview_packet(*, project_root: Path) -> OtlpPreviewPacket:

    root = project_root.expanduser().resolve()
    loaded_sources = tuple(_load_source(definition, root=root) for definition in _sources())
    sources = tuple(loaded.source for loaded in loaded_sources)
    fixture = _fixture(loaded_sources=loaded_sources)
    summary = _summary(sources=sources, fixture=fixture)
    return OtlpPreviewPacket(
        generated_at=datetime.now(UTC).isoformat(),
        summary=summary,
        sources=sources,
        fixture=fixture,
        boundary_controls=_boundary_controls(),
        next_actions=_next_actions(sources=sources),
    )


def render_otlp_preview_markdown(packet: OtlpPreviewPacket) -> str:

    lines = [
        "# Entroping OTLP Preview",
        "",
        _join_text(
            "Local-only OTLP-shaped preview from sanitized Entroping reports. This ",
            "is not an exporter, does not configure collectors, and does not send ",
            "telemetry to vendor APIs.",
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Severity: `{packet.summary.severity}`",
        _join_text(
            "- Sources: ",
            f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, ",
            f"`{packet.summary.sources_missing}` missing, ",
            f"`{packet.summary.sources_invalid}` invalid, ",
            f"`{packet.summary.sources_unsafe}` unsafe",
        ),
        _join_text(
            "- Fixture: ",
            f"`{packet.summary.resource_attributes_total}` resource attributes, ",
            f"`{packet.summary.log_records_total}` logs, ",
            f"`{packet.summary.metrics_total}` metrics, ",
            f"`{packet.summary.spans_total}` spans",
        ),
        "",
        "## Sources",
        "",
        "| Source | State | Path | Schema | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in packet.sources:
        lines.append(
            _join_text(
                "| ",
                f"{_markdown_cell(source.id)} | ",
                f"{_markdown_cell(source.state)} | ",
                f"{_markdown_cell(source.path)} | ",
                f"{_markdown_cell(source.schema_version or 'n/a')} | ",
                f"{_markdown_cell(source.sha256 or 'n/a')} | ",
                f"{_markdown_cell(source.summary)} |",
            )
        )
    lines.extend(
        [
            "",
            "## Fixture",
            "",
            f"- Transport: `{packet.fixture.transport}`",
            f"- Network policy: `{packet.fixture.network_policy}`",
            "",
            "### Resource Attributes",
            "",
            "| Key | Kind | Value | Sources |",
            "| --- | --- | --- | --- |",
        ]
    )
    for attribute in packet.fixture.resource_attributes:
        lines.append(_attribute_row(attribute))
    lines.extend(["", "### Logs", "", "| Name | Severity | Attributes |", "| --- | --- | --- |"])
    for record in packet.fixture.log_records:
        lines.append(
            _join_text(
                "| ",
                f"{_markdown_cell(record.name)} | ",
                f"{_markdown_cell(record.severity_text)} | ",
                f"{_markdown_cell(_attribute_names(record.attributes))} |",
            )
        )
    lines.extend(
        [
            "",
            "### Metrics",
            "",
            "| Name | Unit | Kind | Value |",
            "| --- | --- | --- | --- |",
        ]
    )
    for metric in packet.fixture.metrics:
        lines.append(
            _join_text(
                "| ",
                f"{_markdown_cell(metric.name)} | ",
                f"{_markdown_cell(metric.unit)} | ",
                f"{_markdown_cell(metric.value_kind)} | ",
                f"{_markdown_cell(metric.value)} |",
            )
        )
    lines.extend(["", "### Spans", "", "| Name | Status | Attributes |", "| --- | --- | --- |"])
    for span in packet.fixture.spans:
        lines.append(
            _join_text(
                "| ",
                f"{_markdown_cell(span.name)} | ",
                f"{_markdown_cell(span.status_code)} | ",
                f"{_markdown_cell(_attribute_names(span.attributes))} |",
            )
        )
    lines.extend(["", "## Boundary Controls", "", "| Control | Summary |", "| --- | --- |"])
    for control in packet.boundary_controls:
        lines.append(f"| {_markdown_cell(control.id)} | {_markdown_cell(control.summary)} |")
    if packet.next_actions:
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
                _join_text(
                    "| ",
                    f"{_markdown_cell(action.priority)} | ",
                    f"{_markdown_cell(action.action)} | ",
                    f"{_markdown_cell(', '.join(action.source_ids))} |",
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def _otlp_preview_output(output: str) -> OtlpPreviewOutput:
    if output == "md":
        return "md"
    if output == "json":
        return "json"
    msg = f"Unsupported otlp-preview output: {output}"
    raise OtlpPreviewError(msg)


def _render_packet_content(packet: OtlpPreviewPacket, *, output: OtlpPreviewOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_otlp_preview_markdown(packet)


def _sources() -> tuple[_SourceDefinition, ...]:
    return (
        _SourceDefinition(
            id="run_report",
            path=Path("reports") / "run-latest.json",
            schema_version=RUN_REPORT_SCHEMA_VERSION,
            required=True,
        ),
        _SourceDefinition(
            id="runtime_card",
            path=Path("reports") / "runtime-card.json",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
            required=False,
        ),
        _SourceDefinition(
            id="otel_mapping",
            path=Path("reports") / "otel-mapping.json",
            schema_version=OTEL_MAPPING_SCHEMA_VERSION,
            required=False,
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
        state: OtlpPreviewSourceState = (
            "unsafe" if load_error in {"not a file", "path outside project"} else "invalid"
        )
        return _loaded_source(definition, state, None, load_error, None, None)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _loaded_source(
            definition,
            "invalid",
            None,
            f"invalid UTF-8: {exc.reason}",
            digest,
            None,
        )
    if contains_unredacted_evidence_secret(raw_text):
        return _loaded_source(definition, "unsafe", None, "secret-like content", digest, None)
    try:
        document = cast(object, json.loads(raw_text))
    except json.JSONDecodeError as exc:
        return _loaded_source(definition, "invalid", None, f"invalid JSON: {exc.msg}", digest, None)
    if not isinstance(document, dict):
        return _loaded_source(
            definition,
            "invalid",
            None,
            "JSON artifact must be an object",
            digest,
            None,
        )
    document = cast(dict[str, object], document)
    schema_version = _string_field(document, "schema_version")
    if schema_version != definition.schema_version:
        return _loaded_source(
            definition,
            "invalid",
            schema_version,
            f"schema mismatch: expected {definition.schema_version}",
            digest,
            None,
        )
    return _loaded_source(
        definition,
        "present",
        definition.schema_version,
        _source_summary(definition.id, document),
        digest,
        document,
    )


def _loaded_source(
    definition: _SourceDefinition,
    state: OtlpPreviewSourceState,
    schema_version: str | None,
    summary: str,
    sha256: str | None,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=OtlpPreviewSource(
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
        _ = resolved.relative_to(root)
    except ValueError:
        return "path outside project"
    return None


def _source_summary(source_id: OtlpPreviewSourceId, document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    if source_id == "run_report":
        total = _int_field(summary, "total")
        passed = _int_field(summary, "passed")
        failed = _int_field(summary, "failed")
        exit_code = _int_field(summary, "exit_code")
        status = "pass" if exit_code == 0 and failed == 0 else "fail"
        return (
            f"{status} run, {_count(total)} total, {_count(passed)} passed, "
            f"{_count(failed)} failed"
        )
    if source_id == "runtime_card":
        status = _string_field(summary, "status") or "unknown"
        findings = _int_field(summary, "findings")
        return f"{status} runtime card, {_count(findings)} findings"
    status = _string_field(summary, "status") or "unknown"
    mappings = _int_field(summary, "mappings_total")
    return f"{status} OTEL mapping, {_count(mappings)} mappings"


def _fixture(*, loaded_sources: tuple[_LoadedSource, ...]) -> OtlpPreviewFixture:
    run_document = _document_by_id(loaded_sources, "run_report")
    if run_document is None:
        return OtlpPreviewFixture(
            resource_attributes=(),
            log_records=(),
            metrics=(),
            spans=(),
        )
    summary = _object_field(run_document, "summary")
    total = _safe_int(_int_field(summary, "total"))
    passed = _safe_int(_int_field(summary, "passed"))
    failed = _safe_int(_int_field(summary, "failed"))
    exit_code = _safe_int(_int_field(summary, "exit_code"))
    status_code: OtlpPreviewSpanStatus = "OK" if exit_code == 0 and failed == 0 else "ERROR"
    severity: OtlpPreviewSeverity = "info" if status_code == "OK" else "attention"
    resource_attributes = (
        _attribute("service.name", "string", "entroping-local-preview", ("run_report",)),
        _attribute("telemetry.sdk.name", "classification", "entroping", ("run_report",)),
        _attribute("entroping.preview.mode", "classification", "local-only", ("run_report",)),
    )
    run_attributes = (
        _attribute("entroping.tests.total", "count", total, ("run_report",)),
        _attribute("entroping.tests.passed", "count", passed, ("run_report",)),
        _attribute("entroping.tests.failed", "count", failed, ("run_report",)),
        _attribute("entroping.run.status", "status", status_code.lower(), ("run_report",)),
    )
    return OtlpPreviewFixture(
        resource_attributes=resource_attributes,
        log_records=(
            OtlpPreviewLogRecord(
                name="entroping.run.summary",
                severity_text=severity,
                attributes=run_attributes,
            ),
        ),
        metrics=(
            OtlpPreviewMetric(
                name="entroping.tests.total",
                unit="1",
                value_kind="sum",
                value=total,
            ),
            OtlpPreviewMetric(
                name="entroping.tests.passed",
                unit="1",
                value_kind="sum",
                value=passed,
            ),
            OtlpPreviewMetric(
                name="entroping.tests.failed",
                unit="1",
                value_kind="sum",
                value=failed,
            ),
        ),
        spans=(
            OtlpPreviewSpan(
                name="entroping.run",
                status_code=status_code,
                attributes=run_attributes,
            ),
        ),
    )


def _summary(
    *,
    sources: tuple[OtlpPreviewSource, ...],
    fixture: OtlpPreviewFixture,
) -> OtlpPreviewSummary:
    present = sum(1 for source in sources if source.state == "present")
    missing = sum(1 for source in sources if source.state == "missing")
    invalid = sum(1 for source in sources if source.state == "invalid")
    unsafe = sum(1 for source in sources if source.state == "unsafe")
    required_run = next(source for source in sources if source.id == "run_report")
    if unsafe or invalid or required_run.state != "present":
        status: OtlpPreviewStatus = "insufficient"
    elif missing:
        status = "partial"
    else:
        status = "ready"
    severity: OtlpPreviewSeverity = "blocker" if unsafe or invalid else _fixture_severity(fixture)
    return OtlpPreviewSummary(
        status=status,
        severity=severity,
        sources_total=len(sources),
        sources_present=present,
        sources_missing=missing,
        sources_invalid=invalid,
        sources_unsafe=unsafe,
        resource_attributes_total=len(fixture.resource_attributes),
        log_records_total=len(fixture.log_records),
        metrics_total=len(fixture.metrics),
        spans_total=len(fixture.spans),
    )


def _fixture_severity(fixture: OtlpPreviewFixture) -> OtlpPreviewSeverity:
    span = next(iter(fixture.spans), None)
    if span is None:
        return "attention"
    return "attention" if span.status_code == "ERROR" else "info"


def _boundary_controls() -> tuple[OtlpPreviewBoundaryControl, ...]:
    return (
        OtlpPreviewBoundaryControl(
            id="local-only",
            summary="Writes a local preview file only; it does not contact collectors or vendors.",
        ),
        OtlpPreviewBoundaryControl(
            id="value-free",
            summary="Uses aggregate counts and status classifications, not raw test output.",
        ),
        OtlpPreviewBoundaryControl(
            id="deterministic",
            summary="Derives preview fields from existing sanitized report artifacts.",
        ),
    )


def _next_actions(sources: tuple[OtlpPreviewSource, ...]) -> tuple[OtlpPreviewNextAction, ...]:
    actions: list[OtlpPreviewNextAction] = []
    by_id = {source.id: source for source in sources}
    run_source = by_id["run_report"]
    if run_source.state != "present":
        actions.append(
            OtlpPreviewNextAction(
                priority="high",
                action="Generate reports/run-latest.json with entroping run before OTLP preview.",
                source_ids=("run_report",),
            )
        )
    for source_id in ("runtime_card", "otel_mapping"):
        source = by_id[source_id]
        if source.state == "missing":
            command = {
                "runtime_card": "entroping report runtime-card --output json",
                "otel_mapping": "entroping report otel-mapping --output json",
            }[source_id]
            actions.append(
                OtlpPreviewNextAction(
                    priority="medium",
                    action=f"Generate {source.path} with {command}.",
                    source_ids=(source_id,),
                )
            )
        elif source.state in {"invalid", "unsafe"}:
            actions.append(
                OtlpPreviewNextAction(
                    priority="high",
                    action=f"Repair {source.path} before relying on OTLP preview readiness.",
                    source_ids=(source_id,),
                )
            )
    return tuple(actions)


def _resolve_output_path(path: Path, *, root: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        msg = "otlp-preview output path must stay under the project root"
        raise OtlpPreviewError(msg) from exc
    if relative.parts and relative.parts[0] in {".entroping", "envs"}:
        msg = "otlp-preview packet must not be written into .entroping or envs"
        raise OtlpPreviewError(msg)
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display = _relative_display(symlink_path, root=root)
        msg = f"otlp-preview output path uses symlinked component: {display}"
        raise OtlpPreviewError(msg)
    return candidate


def _document_by_id(
    loaded_sources: tuple[_LoadedSource, ...],
    source_id: OtlpPreviewSourceId,
) -> dict[str, object] | None:
    for loaded in loaded_sources:
        if loaded.source.id == source_id:
            return loaded.document
    return None


def _attribute(
    key: str,
    value_kind: OtlpPreviewValueKind,
    value: str | int,
    source_ids: tuple[OtlpPreviewSourceId, ...],
) -> OtlpPreviewAttribute:
    return OtlpPreviewAttribute(
        key=key,
        value_kind=value_kind,
        value=value,
        source_ids=source_ids,
    )


def _object_field(document: dict[str, object], field: str) -> dict[str, object]:
    value = document.get(field)
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _string_field(document: dict[str, object], field: str) -> str | None:
    value = document.get(field)
    return value if isinstance(value, str) and value else None


def _int_field(document: dict[str, object], field: str) -> int | None:
    value = document.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_int(value: int | None) -> int:
    return value if value is not None and value >= 0 else 0


def _count(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _safe_optional_text(value: object) -> str | None:
    return None if value is None else _safe_text(value)


def _attribute_names(attributes: tuple[OtlpPreviewAttribute, ...]) -> str:
    return ", ".join(attribute.key for attribute in attributes)


def _attribute_row(attribute: OtlpPreviewAttribute) -> str:
    return (
        "| "
        f"{_markdown_cell(attribute.key)} | "
        f"{_markdown_cell(attribute.value_kind)} | "
        f"{_markdown_cell(attribute.value)} | "
        f"{_markdown_cell(', '.join(attribute.source_ids))} |"
    )


def _join_text(*parts: str) -> str:
    return "".join(parts)


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
