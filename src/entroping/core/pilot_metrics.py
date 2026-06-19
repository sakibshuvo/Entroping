"""Local pilot metrics report generation from sanitized evidence artifacts."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.secrets import contains_secret_like_value, redact_secret_like_values

PILOT_METRICS_SCHEMA_VERSION: Final = "entroping.pilot-metrics.v1"

PilotMetricsOutput = Literal["md", "json"]
PilotMetricsStatus = Literal["partial", "insufficient"]
PilotMetricState = Literal["known", "unknown", "manual_input_required"]
PilotEvidenceSourceState = Literal["present", "missing", "invalid", "unsafe"]
PilotMetricId = Literal[
    "setup_time_minutes",
    "evidence_bundle_ready_rate",
    "useful_failures",
    "false_positives",
    "waived_gates",
    "human_steering_events",
]
PilotEvidenceSourceId = Literal[
    "run_report",
    "runtime_card",
    "evidence_bundle",
    "artifact_manifest",
    "agent_bundle",
]

_MAX_PILOT_METRICS_ARTIFACT_BYTES: Final = 100 * 1024 * 1024
_DEFAULT_OUTPUTS: Final[dict[PilotMetricsOutput, Path]] = {
    "md": Path("reports") / "pilot-metrics.md",
    "json": Path("reports") / "pilot-metrics.json",
}
_ASCII_CONTROL_CHAR_TRANSLATION: Final = {
    codepoint: " "
    for codepoint in range(32)
    if codepoint not in {9, 10, 13}
}


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: PilotEvidenceSourceId
    label: str
    path: Path
    schema_version: str


_SOURCE_DEFINITIONS: Final = (
    _SourceDefinition(
        id="run_report",
        label="Run report",
        path=Path("reports") / "run-latest.json",
        schema_version="entroping.run-report.v1",
    ),
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version="entroping.runtime-card.v1",
    ),
    _SourceDefinition(
        id="evidence_bundle",
        label="Evidence bundle",
        path=Path("reports") / "evidence-bundle.json",
        schema_version="entroping.evidence-bundle.v1",
    ),
    _SourceDefinition(
        id="artifact_manifest",
        label="Artifact manifest",
        path=Path("reports") / "artifact-manifest.json",
        schema_version="entroping.report-artifact-manifest.v1",
    ),
    _SourceDefinition(
        id="agent_bundle",
        label="Agent bundle",
        path=Path("reports") / "agent-bundle.json",
        schema_version="entroping.agent-review-bundle.v1",
    ),
)


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: "PilotEvidenceSource"
    document: dict[str, object] | None


class PilotMetricsSummary(BaseModel):
    """Aggregate state for a local pilot metrics report."""

    model_config = ConfigDict(extra="forbid")

    status: PilotMetricsStatus
    metrics_total: int = Field(ge=0)
    metrics_known: int = Field(ge=0)
    metrics_unknown: int = Field(ge=0)
    metrics_manual_input_required: int = Field(ge=0)
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)


class PilotMetric(BaseModel):
    """One pilot metric and whether it is locally inferable."""

    model_config = ConfigDict(extra="forbid")

    id: PilotMetricId
    label: str
    state: PilotMetricState
    value: int | float | None
    unit: str | None
    numerator: int | None
    denominator: int | None
    summary: str
    source_paths: tuple[str, ...] = ()


class PilotEvidenceSource(BaseModel):
    """One sanitized local source consulted by the pilot metrics report."""

    model_config = ConfigDict(extra="forbid")

    id: PilotEvidenceSourceId
    label: str
    path: str
    state: PilotEvidenceSourceState
    schema_version: str | None
    summary: str


class PilotMetricsReport(BaseModel):
    """Machine-readable local pilot metrics report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.pilot-metrics.v1"] = "entroping.pilot-metrics.v1"
    generated_at: str
    project: str | None
    summary: PilotMetricsSummary
    metrics: tuple[PilotMetric, ...]
    sources: tuple[PilotEvidenceSource, ...]


class PilotMetricsError(ValueError):
    """Raised when pilot metrics evidence cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class PilotMetricsResult:
    """Result of a pilot metrics report workflow."""

    output_path: Path
    report: PilotMetricsReport


def run_pilot_metrics_report(
    *,
    project_root: Path,
    output: PilotMetricsOutput,
    output_path: Path | None = None,
) -> PilotMetricsResult:
    """Write local pilot metrics inferred from sanitized report artifacts."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported pilot metrics output: {output}"
        raise PilotMetricsError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    report = build_pilot_metrics_report(project_root=root)
    content = _render_report_content(report, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "pilot metrics report contains secret-like content"
        raise PilotMetricsError(msg)
    try:
        safe_write_text(destination, content, artifact="pilot metrics report", root=root)
    except SafeWriteError as exc:
        raise PilotMetricsError(str(exc)) from exc
    return PilotMetricsResult(output_path=destination, report=report)


def build_pilot_metrics_report(*, project_root: Path) -> PilotMetricsReport:
    """Build a value-free pilot metrics report from existing sanitized artifacts."""

    root = project_root.expanduser().resolve()
    loaded_sources = tuple(
        _load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS
    )
    documents = {loaded.source.id: loaded.document for loaded in loaded_sources}
    sources = tuple(loaded.source for loaded in loaded_sources)
    metrics = _build_metrics(documents=documents, sources=sources)
    return PilotMetricsReport(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_run_report(documents["run_report"]),
        summary=_build_summary(metrics=metrics, sources=sources),
        metrics=metrics,
        sources=sources,
    )


def render_pilot_metrics_markdown(report: PilotMetricsReport) -> str:
    """Render a human-readable pilot metrics report."""

    lines = [
        "# Entroping Pilot Metrics",
        "",
        f"- Status: `{report.summary.status}`",
        f"- Project: `{_inline_code(report.project or 'unknown')}`",
        "- Metrics: "
        f"`{report.summary.metrics_known}/{report.summary.metrics_total}` known, "
        f"`{report.summary.metrics_unknown}` unknown, "
        f"`{report.summary.metrics_manual_input_required}` manual input required",
        "- Sources: "
        f"`{report.summary.sources_present}/{report.summary.sources_total}` present, "
        f"`{report.summary.sources_invalid}` invalid, "
        f"`{report.summary.sources_unsafe}` unsafe",
        "",
        "## Metrics",
        "",
        "| Metric | State | Unit | Value | Summary | Sources |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for metric in report.metrics:
        lines.append(
            "| "
            f"{_markdown_cell(metric.id)} | "
            f"{_markdown_cell(metric.state)} | "
            f"{_markdown_cell(metric.unit or 'n/a')} | "
            f"{_markdown_cell(_metric_value(metric))} | "
            f"{_markdown_cell(metric.summary)} | "
            f"{_markdown_cell(', '.join(metric.source_paths) or 'n/a')} |"
        )

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Source | State | Path | Schema | Summary |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for source in report.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.id)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(source.schema_version or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_report_content(
    report: PilotMetricsReport,
    *,
    output: PilotMetricsOutput,
) -> str:
    if output == "json":
        return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_pilot_metrics_markdown(report)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    try:
        path = _resolve_source_path(definition.path, root=root)
    except PilotMetricsError as exc:
        return _loaded_source(
            definition,
            state="unsafe",
            schema_version=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    if not path.exists():
        return _loaded_source(
            definition,
            state="missing",
            schema_version=None,
            summary="Artifact is missing.",
            document=None,
        )
    try:
        document = _load_json_object(path, artifact=definition.label.lower())
        schema_version = _schema_version(document)
        if schema_version != definition.schema_version:
            return _loaded_source(
                definition,
                state="invalid",
                schema_version=schema_version,
                summary=(
                    "unsupported schema_version; expected "
                    f"{definition.schema_version}"
                ),
                document=None,
            )
        summary = _source_summary(definition, document)
    except PilotMetricsError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    return _loaded_source(
        definition,
        state="present",
        schema_version=definition.schema_version,
        summary=summary,
        document=document,
    )


def _loaded_source(
    definition: _SourceDefinition,
    *,
    state: PilotEvidenceSourceState,
    schema_version: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        source=PilotEvidenceSource(
            id=definition.id,
            label=definition.label,
            path=definition.path.as_posix(),
            state=state,
            schema_version=_safe_text(schema_version) if schema_version is not None else None,
            summary=_safe_text(summary),
        ),
        document=document,
    )


def _load_json_object(path: Path, *, artifact: str) -> dict[str, object]:
    try:
        if path.stat().st_size > _MAX_PILOT_METRICS_ARTIFACT_BYTES:
            msg = (
                f"{artifact.capitalize()} {path.name} exceeds "
                f"{_MAX_PILOT_METRICS_ARTIFACT_BYTES} bytes"
            )
            raise PilotMetricsError(msg)
        raw_json = path.read_text(encoding="utf-8")
    except PilotMetricsError:
        raise
    except UnicodeDecodeError as exc:
        msg = f"Could not decode {artifact} as UTF-8: {exc}"
        raise PilotMetricsError(msg) from exc
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise PilotMetricsError(msg) from exc
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise PilotMetricsError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise PilotMetricsError(msg)
    return data


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    try:
        symlink_path = first_symlink_path_component(candidate, root=root)
    except ValueError as exc:
        msg = f"pilot metrics source path must stay inside the project: {raw_path}"
        raise PilotMetricsError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"pilot metrics source path uses symlinked component: {display_path}"
        raise PilotMetricsError(msg)
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"pilot metrics source path is not a file: {raw_path.as_posix()}"
        raise PilotMetricsError(msg)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"pilot metrics source path must stay inside the project: {raw_path}"
        raise PilotMetricsError(msg) from exc
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "pilot metrics path must stay under the project root"
        raise PilotMetricsError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"pilot metrics output path uses symlinked component: {display_path}"
        raise PilotMetricsError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "pilot metrics path must stay under the project root"
        raise PilotMetricsError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "pilot metrics report must not be written into .entroping or envs"
        raise PilotMetricsError(msg)
    return resolved


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _source_summary(definition: _SourceDefinition, document: dict[str, object]) -> str:
    if definition.id == "run_report":
        summary = _object_field(document, "summary", artifact=definition.label)
        tests = _list_field(document, "tests", artifact=definition.label)
        total = _non_negative_int(summary.get("total"), field="summary.total")
        selected = _optional_non_negative_int(summary.get("selected"))
        selected_tests = selected if selected is not None else total
        known_failures = _count_known_failures(tests)
        return f"{selected_tests} selected tests; {known_failures} known-failure waivers"
    if definition.id == "evidence_bundle":
        summary = _object_field(document, "summary", artifact=definition.label)
        status = _expected_text(summary.get("status"), field="summary.status")
        if status not in {"ready", "not_ready"}:
            msg = "Evidence bundle summary.status must be ready or not_ready"
            raise PilotMetricsError(msg)
        required_present = _non_negative_int(
            summary.get("required_present"),
            field="summary.required_present",
        )
        required_total = _non_negative_int(
            summary.get("required_total"),
            field="summary.required_total",
        )
        return f"{status}; {required_present}/{required_total} required present"
    if definition.id == "runtime_card":
        summary = _object_field(document, "summary", artifact=definition.label)
        status = _expected_text(summary.get("status"), field="summary.status")
        findings = _non_negative_int(summary.get("findings"), field="summary.findings")
        return f"{status}; {findings} findings"
    if definition.id == "artifact_manifest":
        audit = _object_field(document, "audit", artifact=definition.label)
        verification = _object_field(audit, "verification", artifact=definition.label)
        status = _expected_text(verification.get("status"), field="audit.verification.status")
        if status not in {"verified", "broken"}:
            msg = "Artifact manifest audit.verification.status must be verified or broken"
            raise PilotMetricsError(msg)
        return f"audit {status}"
    if definition.id == "agent_bundle":
        summary = _object_field(document, "summary", artifact=definition.label)
        status = _expected_text(summary.get("status"), field="summary.status")
        manifests = _non_negative_int(summary.get("manifests"), field="summary.manifests")
        return f"{status}; {manifests} manifests"
    msg = f"Unsupported pilot metrics source: {definition.id}"
    raise PilotMetricsError(msg)


def _build_metrics(
    *,
    documents: dict[PilotEvidenceSourceId, dict[str, object] | None],
    sources: tuple[PilotEvidenceSource, ...],
) -> tuple[PilotMetric, ...]:
    source_states = {source.id: source for source in sources}
    return (
        _manual_metric(
            id="setup_time_minutes",
            label="Setup time",
            unit="minutes",
            summary=(
                "Measure checkout-to-first-run time from design-partner "
                "or reviewer notes."
            ),
        ),
        _evidence_bundle_ready_rate_metric(
            document=documents["evidence_bundle"],
            source=source_states["evidence_bundle"],
        ),
        _manual_metric(
            id="useful_failures",
            label="Useful failures",
            unit="count",
            summary="Requires reviewer classification of Entroping failures.",
        ),
        _manual_metric(
            id="false_positives",
            label="False positives",
            unit="count",
            summary="Requires reviewer classification of noisy or incorrect failures.",
        ),
        _waived_gates_metric(
            document=documents["run_report"],
            source=source_states["run_report"],
        ),
        _manual_metric(
            id="human_steering_events",
            label="Human steering",
            unit="count",
            summary="Requires tracking commands retried, docs consulted, and help needed.",
        ),
    )


def _manual_metric(
    *,
    id: PilotMetricId,
    label: str,
    unit: str,
    summary: str,
) -> PilotMetric:
    return PilotMetric(
        id=id,
        label=label,
        state="manual_input_required",
        value=None,
        unit=unit,
        numerator=None,
        denominator=None,
        summary=_safe_text(summary),
        source_paths=(),
    )


def _evidence_bundle_ready_rate_metric(
    *,
    document: dict[str, object] | None,
    source: PilotEvidenceSource,
) -> PilotMetric:
    if document is None:
        return _unknown_metric(
            id="evidence_bundle_ready_rate",
            label="Evidence bundle ready rate",
            unit="ratio",
            source=source,
        )
    summary = _object_field(document, "summary", artifact="Evidence bundle")
    status = _expected_text(summary.get("status"), field="summary.status")
    numerator = 1 if status == "ready" else 0
    return PilotMetric(
        id="evidence_bundle_ready_rate",
        label="Evidence bundle ready rate",
        state="known",
        value=float(numerator),
        unit="ratio",
        numerator=numerator,
        denominator=1,
        summary=(
            "One local evidence bundle is ready."
            if numerator == 1
            else "One local evidence bundle is not ready."
        ),
        source_paths=(source.path,),
    )


def _waived_gates_metric(
    *,
    document: dict[str, object] | None,
    source: PilotEvidenceSource,
) -> PilotMetric:
    if document is None:
        return _unknown_metric(
            id="waived_gates",
            label="Waived gates",
            unit="count",
            source=source,
        )
    tests = _list_field(document, "tests", artifact="Run report")
    known_failures = _count_known_failures(tests)
    return PilotMetric(
        id="waived_gates",
        label="Waived gates",
        state="known",
        value=known_failures,
        unit="count",
        numerator=known_failures,
        denominator=None,
        summary=f"{known_failures} known-failure waivers in the latest run report.",
        source_paths=(source.path,),
    )


def _unknown_metric(
    *,
    id: PilotMetricId,
    label: str,
    unit: str,
    source: PilotEvidenceSource,
) -> PilotMetric:
    return PilotMetric(
        id=id,
        label=label,
        state="unknown",
        value=None,
        unit=unit,
        numerator=None,
        denominator=None,
        summary=f"Source {source.path} is {source.state}.",
        source_paths=(source.path,),
    )


def _build_summary(
    *,
    metrics: tuple[PilotMetric, ...],
    sources: tuple[PilotEvidenceSource, ...],
) -> PilotMetricsSummary:
    metrics_known = sum(1 for metric in metrics if metric.state == "known")
    metrics_unknown = sum(1 for metric in metrics if metric.state == "unknown")
    metrics_manual = sum(
        1 for metric in metrics if metric.state == "manual_input_required"
    )
    status: PilotMetricsStatus = "partial" if metrics_known > 0 else "insufficient"
    return PilotMetricsSummary(
        status=status,
        metrics_total=len(metrics),
        metrics_known=metrics_known,
        metrics_unknown=metrics_unknown,
        metrics_manual_input_required=metrics_manual,
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _project_from_run_report(document: dict[str, object] | None) -> str | None:
    if document is None:
        return None
    project = document.get("project")
    return _safe_text(project) if isinstance(project, str) and project.strip() else None


def _count_known_failures(tests: list[object]) -> int:
    count = 0
    for test in tests:
        if not isinstance(test, dict):
            continue
        known_failures = test.get("known_failures", [])
        if known_failures in (None, []):
            continue
        if not isinstance(known_failures, list):
            msg = "Run report test known_failures must be a list"
            raise PilotMetricsError(msg)
        count += sum(1 for item in known_failures if isinstance(item, dict))
    return count


def _object_field(
    document: dict[str, object],
    field: str,
    *,
    artifact: str,
) -> dict[str, object]:
    value = document.get(field)
    if not isinstance(value, dict):
        msg = f"{artifact} field {field} must be an object"
        raise PilotMetricsError(msg)
    return value


def _list_field(
    document: dict[str, object],
    field: str,
    *,
    artifact: str,
) -> list[object]:
    value = document.get(field)
    if not isinstance(value, list):
        msg = f"{artifact} field {field} must be a list"
        raise PilotMetricsError(msg)
    return value


def _non_negative_int(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"Pilot metrics source field {field} must be a non-negative integer"
        raise PilotMetricsError(msg)
    return value


def _optional_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, field="summary.selected")


def _expected_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"Pilot metrics source field {field} must be a non-empty string"
        raise PilotMetricsError(msg)
    return _safe_text(value)


def _metric_value(metric: PilotMetric) -> str:
    if metric.value is None:
        return "n/a"
    return str(metric.value)


def _safe_text(value: str) -> str:
    sanitized = redact_secret_like_values(value).translate(_ASCII_CONTROL_CHAR_TRANSLATION)
    return " ".join(sanitized.replace("\r", " ").replace("\n", " ").split())


def _contains_unredacted_secret_like_value(value: str) -> bool:
    normalized = value.replace("[REDACTED]`", "[REDACTED]")
    return contains_secret_like_value(normalized)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    return escape(value.replace("\r", " "), quote=False).replace("|", "\\|")
