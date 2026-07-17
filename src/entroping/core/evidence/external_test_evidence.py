"""External test evidence packets for standard local artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any, Final, Literal

from defusedxml import ElementTree as SafeET
from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION: Final = "entroping.external-test-evidence.v1"

ExternalTestEvidenceOutput = Literal["md", "json"]
ExternalTestEvidenceStatus = Literal["ready", "partial", "insufficient"]
ExternalTestEvidenceSourceState = Literal["present", "missing", "invalid", "unsafe"]
ExternalTestEvidenceSourceKind = Literal["junit", "coverage_xml", "lcov", "sarif"]
ExternalTestEvidenceLayerStatus = Literal["covered", "missing", "blocked"]
ExternalTestEvidenceNextActionPriority = Literal["high", "medium"]
ExternalTestEvidenceLayerId = Literal[
    "unit",
    "integration",
    "component",
    "contract",
    "e2e",
]
ExternalTestEvidenceSourceId = Literal[
    "unit_junit",
    "integration_junit",
    "component_junit",
    "contract_junit",
    "e2e_junit",
    "coverage_xml",
    "lcov_info",
    "sarif_json",
]

_MAX_SOURCE_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b")
_DEFAULT_OUTPUTS: Final[dict[ExternalTestEvidenceOutput, Path]] = {
    "md": Path("reports") / "external-test-evidence.md",
    "json": Path("reports") / "external-test-evidence.json",
}
_EXTERNAL_REPORT_ROOT: Final = Path("reports") / "external-tests"


class ExternalTestEvidenceError(ValueError):
    """Raised when an external test evidence packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: ExternalTestEvidenceSourceId
    label: str
    path: Path
    kind: ExternalTestEvidenceSourceKind
    layer: ExternalTestEvidenceLayerId | None


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    source: ExternalTestEvidenceSource


@dataclass(frozen=True, slots=True)
class _LayerDefinition:
    id: ExternalTestEvidenceLayerId
    label: str
    junit_source_id: ExternalTestEvidenceSourceId


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _EventCounts:
    tests: int
    failures: int
    errors: int
    skipped: int


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="unit_junit",
        label="unit JUnit",
        path=_EXTERNAL_REPORT_ROOT / "unit-junit.xml",
        kind="junit",
        layer="unit",
    ),
    _SourceDefinition(
        id="integration_junit",
        label="integration JUnit",
        path=_EXTERNAL_REPORT_ROOT / "integration-junit.xml",
        kind="junit",
        layer="integration",
    ),
    _SourceDefinition(
        id="component_junit",
        label="component JUnit",
        path=_EXTERNAL_REPORT_ROOT / "component-junit.xml",
        kind="junit",
        layer="component",
    ),
    _SourceDefinition(
        id="contract_junit",
        label="contract JUnit",
        path=_EXTERNAL_REPORT_ROOT / "contract-junit.xml",
        kind="junit",
        layer="contract",
    ),
    _SourceDefinition(
        id="e2e_junit",
        label="e2e JUnit",
        path=_EXTERNAL_REPORT_ROOT / "e2e-junit.xml",
        kind="junit",
        layer="e2e",
    ),
    _SourceDefinition(
        id="coverage_xml",
        label="coverage XML",
        path=_EXTERNAL_REPORT_ROOT / "coverage.xml",
        kind="coverage_xml",
        layer=None,
    ),
    _SourceDefinition(
        id="lcov_info",
        label="LCOV info",
        path=_EXTERNAL_REPORT_ROOT / "lcov.info",
        kind="lcov",
        layer=None,
    ),
    _SourceDefinition(
        id="sarif_json",
        label="SARIF JSON",
        path=_EXTERNAL_REPORT_ROOT / "sarif.json",
        kind="sarif",
        layer=None,
    ),
)
_LAYER_DEFINITIONS: Final[tuple[_LayerDefinition, ...]] = (
    _LayerDefinition(id="unit", label="Unit", junit_source_id="unit_junit"),
    _LayerDefinition(
        id="integration",
        label="Integration",
        junit_source_id="integration_junit",
    ),
    _LayerDefinition(
        id="component",
        label="Component",
        junit_source_id="component_junit",
    ),
    _LayerDefinition(id="contract", label="Contract", junit_source_id="contract_junit"),
    _LayerDefinition(id="e2e", label="End-to-end", junit_source_id="e2e_junit"),
)


class ExternalTestEvidenceSummary(BaseModel):
    """Aggregate external test evidence state."""

    model_config = ConfigDict(extra="forbid")

    status: ExternalTestEvidenceStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    layers_total: int = Field(ge=0)
    layers_with_evidence: int = Field(ge=0)
    layers_missing: int = Field(ge=0)
    layers_blocked: int = Field(ge=0)
    total_tests: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    total_errors: int = Field(ge=0)
    total_skipped: int = Field(ge=0)
    line_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    branch_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    sarif_results_total: int = Field(ge=0)
    sarif_error_results: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class ExternalTestEvidenceSource(BaseModel):
    """One fixed local external test evidence artifact."""

    model_config = ConfigDict(extra="forbid")

    id: ExternalTestEvidenceSourceId
    label: str
    path: str
    kind: ExternalTestEvidenceSourceKind
    layer: ExternalTestEvidenceLayerId | None
    state: ExternalTestEvidenceSourceState
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    suites: int | None = Field(default=None, ge=0)
    tests: int | None = Field(default=None, ge=0)
    failures: int | None = Field(default=None, ge=0)
    errors: int | None = Field(default=None, ge=0)
    skipped: int | None = Field(default=None, ge=0)
    line_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    branch_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    lines_covered: int | None = Field(default=None, ge=0)
    lines_valid: int | None = Field(default=None, ge=0)
    branches_covered: int | None = Field(default=None, ge=0)
    branches_valid: int | None = Field(default=None, ge=0)
    sarif_runs: int | None = Field(default=None, ge=0)
    sarif_results_total: int | None = Field(default=None, ge=0)
    sarif_error_results: int | None = Field(default=None, ge=0)
    sarif_warning_results: int | None = Field(default=None, ge=0)
    sarif_note_results: int | None = Field(default=None, ge=0)
    sarif_none_results: int | None = Field(default=None, ge=0)


class ExternalTestEvidenceLayer(BaseModel):
    """Counts-only evidence for one external test-pyramid layer."""

    model_config = ConfigDict(extra="forbid")

    id: ExternalTestEvidenceLayerId
    label: str
    status: ExternalTestEvidenceLayerStatus
    source_ids: tuple[ExternalTestEvidenceSourceId, ...]
    tests: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    blockers: tuple[str, ...] = ()
    next_action: str


class ExternalTestEvidenceNextAction(BaseModel):
    """One local action before external evidence can be treated as complete."""

    model_config = ConfigDict(extra="forbid")

    priority: ExternalTestEvidenceNextActionPriority
    action: str
    source_ids: tuple[ExternalTestEvidenceSourceId, ...] = ()
    layer_ids: tuple[ExternalTestEvidenceLayerId, ...] = ()


class ExternalTestEvidencePacket(BaseModel):
    """Schema-versioned external test evidence packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.external-test-evidence.v1"] = (
        EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: ExternalTestEvidenceSummary
    sources: tuple[ExternalTestEvidenceSource, ...]
    layers: tuple[ExternalTestEvidenceLayer, ...]
    next_actions: tuple[ExternalTestEvidenceNextAction, ...]


@dataclass(frozen=True, slots=True)
class ExternalTestEvidenceResult:
    """Result of writing one external test evidence packet."""

    output_path: Path
    packet: ExternalTestEvidencePacket


def run_external_test_evidence_report(
    *,
    project_root: Path,
    output: ExternalTestEvidenceOutput,
    output_path: Path | None = None,
) -> ExternalTestEvidenceResult:
    """Write a local external test evidence packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported external-test-evidence output: {output}"
        raise ExternalTestEvidenceError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_external_test_evidence(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_packet_secret_like_value(content):
        msg = "external test evidence packet contains secret-like content"
        raise ExternalTestEvidenceError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="external test evidence packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise ExternalTestEvidenceError(str(exc)) from exc
    return ExternalTestEvidenceResult(output_path=written, packet=packet)


def build_external_test_evidence(*, project_root: Path) -> ExternalTestEvidencePacket:
    """Build a value-free packet from fixed external test artifacts."""

    root = project_root.expanduser().resolve()
    packet = _build_packet(root=root)
    if _contains_unredacted_packet_secret_like_value(_packet_json(packet)):
        msg = "external test evidence packet contains secret-like content"
        raise ExternalTestEvidenceError(msg)
    return packet


def render_external_test_evidence_markdown(packet: ExternalTestEvidencePacket) -> str:
    """Render a human-readable external test evidence packet."""

    lines = [
        "# Entroping External Test Evidence",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Layers: "
        f"`{packet.summary.layers_with_evidence}/{packet.summary.layers_total}` covered, "
        f"`{packet.summary.layers_missing}` missing, "
        f"`{packet.summary.layers_blocked}` blocked",
        "- Totals: "
        f"`{packet.summary.total_tests}` tests, "
        f"`{packet.summary.total_failures}` failures, "
        f"`{packet.summary.total_errors}` errors, "
        f"`{packet.summary.total_skipped}` skipped",
        "- Coverage: "
        f"`{_percent_text(packet.summary.line_coverage_percent)}` lines, "
        f"`{_percent_text(packet.summary.branch_coverage_percent)}` branches",
        "- SARIF results: "
        f"`{packet.summary.sarif_results_total}` total, "
        f"`{packet.summary.sarif_error_results}` error",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Sources",
        "",
        "| Source | State | Kind | Layer | Path | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.id)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.kind)} | "
            f"{_markdown_cell(source.layer or 'n/a')} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(source.sha256 or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )

    lines.extend(
        [
            "",
            "## Layers",
            "",
            "| Layer | Status | Sources | Tests | Failures | Errors | Skipped "
            + "| Blockers | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for layer in packet.layers:
        lines.append(
            "| "
            f"{_markdown_cell(layer.id)} | "
            f"{_markdown_cell(layer.status)} | "
            f"{_markdown_cell(', '.join(layer.source_ids))} | "
            f"{layer.tests} | "
            f"{layer.failures} | "
            f"{layer.errors} | "
            f"{layer.skipped} | "
            f"{_markdown_cell('; '.join(layer.blockers) or 'none')} | "
            f"{_markdown_cell(layer.next_action)} |"
        )

    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No external test evidence actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Sources | Layers |",
                "| --- | --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.layer_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_packet(*, root: Path) -> ExternalTestEvidencePacket:
    sources = tuple(
        _load_source(definition, root=root).source
        for definition in _SOURCE_DEFINITIONS
    )
    source_by_id = {source.id: source for source in sources}
    layers = tuple(_layer(definition, source_by_id) for definition in _LAYER_DEFINITIONS)
    next_actions = _next_actions(sources=sources, layers=layers)
    return ExternalTestEvidencePacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        summary=_summary(sources=sources, layers=layers, next_actions=next_actions),
        sources=sources,
        layers=layers,
        next_actions=next_actions,
    )


def _render_packet_content(
    packet: ExternalTestEvidencePacket,
    *,
    output: ExternalTestEvidenceOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_external_test_evidence_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    try:
        path = _resolve_source_path(definition.path, root=root)
    except ExternalTestEvidenceError as exc:
        return _loaded_source(
            definition,
            state="unsafe",
            sha256=None,
            summary=_safe_text(str(exc)),
        )
    if not path.exists():
        return _loaded_source(
            definition,
            state="missing",
            sha256=None,
            summary="Artifact is missing.",
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact=definition.label)
        raw_text = raw_bytes.decode("utf-8")
    except ExternalTestEvidenceError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            sha256=None,
            summary=_safe_text(str(exc)),
        )
    except UnicodeDecodeError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            sha256=None,
            summary=_safe_text(f"Could not decode {definition.label} as UTF-8: {exc}"),
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _loaded_source(
            definition,
            state="unsafe",
            sha256=None,
            summary=f"{definition.label} contains secret-like content.",
        )
    try:
        parsed = _parse_source(definition, raw_text)
    except ExternalTestEvidenceError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            sha256=None,
            summary=_safe_text(str(exc)),
        )
    return _loaded_source(
        definition,
        state="present",
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        summary=parsed.summary,
        metrics=parsed.metrics,
    )


@dataclass(frozen=True, slots=True)
class _ParsedSource:
    summary: str
    metrics: dict[str, int | float]


def _loaded_source(
    definition: _SourceDefinition,
    *,
    state: ExternalTestEvidenceSourceState,
    sha256: str | None,
    summary: str,
    metrics: Mapping[str, int | float] | None = None,
) -> _LoadedSource:
    values = dict(metrics or {})
    return _LoadedSource(
        source=ExternalTestEvidenceSource(
            id=definition.id,
            label=definition.label,
            path=definition.path.as_posix(),
            kind=definition.kind,
            layer=definition.layer,
            state=state,
            sha256=sha256,
            summary=_safe_text(summary),
            suites=_optional_int(values, "suites"),
            tests=_optional_int(values, "tests"),
            failures=_optional_int(values, "failures"),
            errors=_optional_int(values, "errors"),
            skipped=_optional_int(values, "skipped"),
            line_coverage_percent=_optional_float(values, "line_coverage_percent"),
            branch_coverage_percent=_optional_float(values, "branch_coverage_percent"),
            lines_covered=_optional_int(values, "lines_covered"),
            lines_valid=_optional_int(values, "lines_valid"),
            branches_covered=_optional_int(values, "branches_covered"),
            branches_valid=_optional_int(values, "branches_valid"),
            sarif_runs=_optional_int(values, "sarif_runs"),
            sarif_results_total=_optional_int(values, "sarif_results_total"),
            sarif_error_results=_optional_int(values, "sarif_error_results"),
            sarif_warning_results=_optional_int(values, "sarif_warning_results"),
            sarif_note_results=_optional_int(values, "sarif_note_results"),
            sarif_none_results=_optional_int(values, "sarif_none_results"),
        )
    )


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    try:
        symlink_path = first_symlink_path_component(candidate, root=root)
    except ValueError as exc:
        msg = "external test evidence source path must stay under the project root"
        raise ExternalTestEvidenceError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"external test evidence source path uses symlinked component: {display_path}"
        raise ExternalTestEvidenceError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = "external test evidence source path must stay under the project root"
        raise ExternalTestEvidenceError(msg) from exc
    if resolved.exists() and not resolved.is_file():
        msg = f"external test evidence source path is not a file: {raw_path.as_posix()}"
        raise ExternalTestEvidenceError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "external test evidence output path must stay under the project root"
        raise ExternalTestEvidenceError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"external test evidence output path uses symlinked component: {display_path}"
        raise ExternalTestEvidenceError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "external test evidence output path must stay under the project root"
        raise ExternalTestEvidenceError(msg) from exc
    if not {".entroping", "envs"}.isdisjoint(relative_parts):
        msg = "external test evidence packet must not be written into .entroping or envs"
        raise ExternalTestEvidenceError(msg)
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
            msg = f"{artifact} {path.name} is not a regular file"
            raise ExternalTestEvidenceError(msg)
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            msg = f"{artifact} {path.name} changed during read"
            raise ExternalTestEvidenceError(msg)
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            raw_bytes = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise ExternalTestEvidenceError(msg) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
    if len(raw_bytes) > _MAX_SOURCE_BYTES:
        msg = f"{artifact} {path.name} exceeds {_MAX_SOURCE_BYTES} bytes"
        raise ExternalTestEvidenceError(msg)
    return raw_bytes


def _parse_source(definition: _SourceDefinition, raw_text: str) -> _ParsedSource:
    if definition.kind == "junit":
        return _parse_junit(raw_text, artifact=definition.label)
    if definition.kind == "coverage_xml":
        return _parse_coverage_xml(raw_text)
    if definition.kind == "lcov":
        return _parse_lcov(raw_text)
    return _parse_sarif(raw_text)


def _parse_junit(raw_text: str, *, artifact: str) -> _ParsedSource:
    root = _xml_root(raw_text, artifact=artifact)
    root_tag = _local_tag(root.tag)
    if root_tag not in {"testsuite", "testsuites"}:
        msg = f"{artifact} must be JUnit testsuite or testsuites XML"
        raise ExternalTestEvidenceError(msg)
    suite_elements = tuple(
        element for element in root.iter() if _local_tag(element.tag) == "testsuite"
    )
    if _has_count_attrs(root):
        suites = len(suite_elements) if suite_elements else 1
        metrics: dict[str, int | float] = {
            "suites": suites,
            "tests": _non_negative_int_attr(root.attrib, "tests", artifact=artifact),
            "failures": _non_negative_int_attr(root.attrib, "failures", artifact=artifact),
            "errors": _non_negative_int_attr(root.attrib, "errors", artifact=artifact),
            "skipped": _non_negative_int_attr(root.attrib, "skipped", artifact=artifact),
        }
    elif suite_elements and all(_has_count_attrs(element) for element in suite_elements):
        metrics = {
            "suites": len(suite_elements),
            "tests": sum(
                _non_negative_int_attr(element.attrib, "tests", artifact=artifact)
                for element in suite_elements
            ),
            "failures": sum(
                _non_negative_int_attr(element.attrib, "failures", artifact=artifact)
                for element in suite_elements
            ),
            "errors": sum(
                _non_negative_int_attr(element.attrib, "errors", artifact=artifact)
                for element in suite_elements
            ),
            "skipped": sum(
                _non_negative_int_attr(element.attrib, "skipped", artifact=artifact)
                for element in suite_elements
            ),
        }
    else:
        testcases = tuple(
            element for element in root.iter() if _local_tag(element.tag) == "testcase"
        )
        metrics = {
            "suites": len(suite_elements) if suite_elements else 1,
            "tests": len(testcases),
            "failures": sum(_has_child(testcase, "failure") for testcase in testcases),
            "errors": sum(_has_child(testcase, "error") for testcase in testcases),
            "skipped": sum(_has_child(testcase, "skipped") for testcase in testcases),
        }
    return _ParsedSource(
        summary=(
            f"{metrics['tests']} tests; {metrics['failures']} failures; "
            f"{metrics['errors']} errors; {metrics['skipped']} skipped"
        ),
        metrics=metrics,
    )


def _parse_coverage_xml(raw_text: str) -> _ParsedSource:
    root = _xml_root(raw_text, artifact="coverage XML")
    if _local_tag(root.tag) != "coverage":
        msg = "coverage XML must use a coverage root element"
        raise ExternalTestEvidenceError(msg)
    line_rate = _optional_rate(root.attrib, "line-rate", artifact="coverage XML")
    branch_rate = _optional_rate(root.attrib, "branch-rate", artifact="coverage XML")
    lines_covered = _optional_non_negative_int_attr(
        root.attrib,
        "lines-covered",
        artifact="coverage XML",
    )
    lines_valid = _optional_non_negative_int_attr(
        root.attrib,
        "lines-valid",
        artifact="coverage XML",
    )
    branches_covered = _optional_non_negative_int_attr(
        root.attrib,
        "branches-covered",
        artifact="coverage XML",
    )
    branches_valid = _optional_non_negative_int_attr(
        root.attrib,
        "branches-valid",
        artifact="coverage XML",
    )
    line_percent = _percent_from_rate_or_counts(line_rate, lines_covered, lines_valid)
    branch_percent = _percent_from_rate_or_counts(
        branch_rate,
        branches_covered,
        branches_valid,
    )
    if line_percent is None and branch_percent is None:
        msg = "coverage XML metrics are missing"
        raise ExternalTestEvidenceError(msg)
    metrics = {
        "line_coverage_percent": line_percent,
        "branch_coverage_percent": branch_percent,
        "lines_covered": lines_covered,
        "lines_valid": lines_valid,
        "branches_covered": branches_covered,
        "branches_valid": branches_valid,
    }
    compact = {key: value for key, value in metrics.items() if value is not None}
    return _ParsedSource(
        summary=(
            f"line coverage {_percent_text(line_percent)}; "
            f"branch coverage {_percent_text(branch_percent)}"
        ),
        metrics=compact,
    )


def _parse_lcov(raw_text: str) -> _ParsedSource:
    totals = {"lines_valid": 0, "lines_covered": 0, "branches_valid": 0, "branches_covered": 0}
    seen_metric = False
    for line in raw_text.splitlines():
        key, separator, value = line.partition(":")
        if separator != ":" or key not in {"LF", "LH", "BRF", "BRH"}:
            continue
        seen_metric = True
        parsed = _non_negative_int_text(value, artifact="LCOV info", field=key)
        if key == "LF":
            totals["lines_valid"] += parsed
        elif key == "LH":
            totals["lines_covered"] += parsed
        elif key == "BRF":
            totals["branches_valid"] += parsed
        else:
            totals["branches_covered"] += parsed
    if not seen_metric:
        msg = "LCOV info metrics are missing"
        raise ExternalTestEvidenceError(msg)
    line_percent = _percent_from_counts(totals["lines_covered"], totals["lines_valid"])
    branch_percent = _percent_from_counts(
        totals["branches_covered"],
        totals["branches_valid"],
    )
    metrics = {
        **totals,
        "line_coverage_percent": line_percent,
        "branch_coverage_percent": branch_percent,
    }
    compact = {key: value for key, value in metrics.items() if value is not None}
    return _ParsedSource(
        summary=(
            f"line coverage {_percent_text(line_percent)}; "
            f"branch coverage {_percent_text(branch_percent)}"
        ),
        metrics=compact,
    )


def _parse_sarif(raw_text: str) -> _ParsedSource:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse SARIF JSON: {exc}"
        raise ExternalTestEvidenceError(msg) from exc
    if not isinstance(document, dict):
        msg = "SARIF JSON must be a JSON object"
        raise ExternalTestEvidenceError(msg)
    runs = document.get("runs")
    if not isinstance(runs, list):
        msg = "SARIF JSON runs must be a list"
        raise ExternalTestEvidenceError(msg)
    error_results = 0
    warning_results = 0
    note_results = 0
    none_results = 0
    total_results = 0
    for run in runs:
        if not isinstance(run, dict):
            msg = "SARIF JSON run entries must be objects"
            raise ExternalTestEvidenceError(msg)
        results = run.get("results", [])
        if not isinstance(results, list):
            msg = "SARIF JSON results must be lists"
            raise ExternalTestEvidenceError(msg)
        for result in results:
            if not isinstance(result, dict):
                msg = "SARIF JSON result entries must be objects"
                raise ExternalTestEvidenceError(msg)
            total_results += 1
            level = result.get("level", "warning")
            if level == "error":
                error_results += 1
            elif level == "warning":
                warning_results += 1
            elif level == "note":
                note_results += 1
            elif level == "none":
                none_results += 1
            else:
                warning_results += 1
    metrics: dict[str, int | float] = {
        "sarif_runs": len(runs),
        "sarif_results_total": total_results,
        "sarif_error_results": error_results,
        "sarif_warning_results": warning_results,
        "sarif_note_results": note_results,
        "sarif_none_results": none_results,
    }
    return _ParsedSource(
        summary=f"{total_results} results; {error_results} error; {warning_results} warning",
        metrics=metrics,
    )


def _xml_root(raw_text: str, *, artifact: str) -> Any:
    try:
        return SafeET.fromstring(raw_text)
    except Exception as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise ExternalTestEvidenceError(msg) from exc


def _local_tag(tag: object) -> str:
    text = str(tag)
    return text.rsplit("}", maxsplit=1)[-1]


def _has_count_attrs(element: Any) -> bool:
    return "tests" in element.attrib


def _has_child(element: Any, tag: str) -> bool:
    return any(_local_tag(child.tag) == tag for child in element)


def _non_negative_int_attr(
    attributes: Mapping[str, str],
    field: str,
    *,
    artifact: str,
) -> int:
    return _non_negative_int_text(attributes.get(field, "0"), artifact=artifact, field=field)


def _optional_non_negative_int_attr(
    attributes: Mapping[str, str],
    field: str,
    *,
    artifact: str,
) -> int | None:
    if field not in attributes:
        return None
    return _non_negative_int_text(attributes[field], artifact=artifact, field=field)


def _non_negative_int_text(value: str, *, artifact: str, field: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        msg = f"{artifact} {field} must be a non-negative integer"
        raise ExternalTestEvidenceError(msg) from exc
    if parsed < 0:
        msg = f"{artifact} {field} must be a non-negative integer"
        raise ExternalTestEvidenceError(msg)
    return parsed


def _optional_rate(
    attributes: Mapping[str, str],
    field: str,
    *,
    artifact: str,
) -> float | None:
    if field not in attributes:
        return None
    try:
        parsed = float(attributes[field])
    except ValueError as exc:
        msg = f"{artifact} {field} must be a number from 0 to 1"
        raise ExternalTestEvidenceError(msg) from exc
    if parsed < 0 or parsed > 1:
        msg = f"{artifact} {field} must be a number from 0 to 1"
        raise ExternalTestEvidenceError(msg)
    return parsed


def _percent_from_rate_or_counts(
    rate: float | None,
    covered: int | None,
    valid: int | None,
) -> float | None:
    if rate is not None:
        return _round_percent(rate * 100)
    if covered is None or valid is None:
        return None
    return _percent_from_counts(covered, valid)


def _percent_from_counts(covered: int, valid: int) -> float | None:
    if covered > valid:
        msg = "coverage covered count must not exceed valid count"
        raise ExternalTestEvidenceError(msg)
    if valid <= 0:
        return None
    return _round_percent((covered / valid) * 100)


def _round_percent(value: float) -> float:
    return round(value, 2)


def _layer(
    definition: _LayerDefinition,
    source_by_id: Mapping[ExternalTestEvidenceSourceId, ExternalTestEvidenceSource],
) -> ExternalTestEvidenceLayer:
    source = source_by_id[definition.junit_source_id]
    blockers = (
        (f"{source.label} is {source.state}: {source.summary}",)
        if source.state in {"invalid", "unsafe"}
        else ()
    )
    if blockers:
        status: ExternalTestEvidenceLayerStatus = "blocked"
        next_action = "Repair invalid or unsafe external test evidence."
    elif source.state == "present":
        status = "covered"
        next_action = "Review counts-only external test evidence with Entroping runtime evidence."
    else:
        status = "missing"
        next_action = f"Generate {definition.label} JUnit evidence under reports/external-tests."
    return ExternalTestEvidenceLayer(
        id=definition.id,
        label=definition.label,
        status=status,
        source_ids=(definition.junit_source_id,),
        tests=source.tests or 0,
        failures=source.failures or 0,
        errors=source.errors or 0,
        skipped=source.skipped or 0,
        blockers=blockers,
        next_action=next_action,
    )


def _next_actions(
    *,
    sources: tuple[ExternalTestEvidenceSource, ...],
    layers: tuple[ExternalTestEvidenceLayer, ...],
) -> tuple[ExternalTestEvidenceNextAction, ...]:
    source_by_id = {source.id: source for source in sources}
    actions: list[ExternalTestEvidenceNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        priority: ExternalTestEvidenceNextActionPriority = (
            "high" if source.state in {"invalid", "unsafe"} else "medium"
        )
        actions.append(
            ExternalTestEvidenceNextAction(
                priority=priority,
                action=(
                    f"Repair {source.label} external test evidence."
                    if source.state in {"invalid", "unsafe"}
                    else f"Generate {source.label} external test evidence."
                ),
                source_ids=(source.id,),
            )
        )
    for layer in layers:
        if layer.status == "covered":
            continue
        if layer.status == "blocked" and any(
            source_by_id[source_id].state in {"invalid", "unsafe"}
            for source_id in layer.source_ids
        ):
            continue
        priority = "high" if layer.status == "blocked" else "medium"
        actions.append(
            ExternalTestEvidenceNextAction(
                priority=priority,
                action=layer.next_action,
                layer_ids=(layer.id,),
            )
        )
    return tuple(_dedupe_actions(actions))


def _dedupe_actions(
    actions: Sequence[ExternalTestEvidenceNextAction],
) -> tuple[ExternalTestEvidenceNextAction, ...]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    result: list[ExternalTestEvidenceNextAction] = []
    for action in actions:
        key = (action.action, action.source_ids, action.layer_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return tuple(result)


def _source_counts(
    sources: tuple[ExternalTestEvidenceSource, ...],
) -> _SourceCounts:
    return _SourceCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _event_counts(
    sources: tuple[ExternalTestEvidenceSource, ...],
) -> _EventCounts:
    junit_sources = tuple(source for source in sources if source.kind == "junit")
    return _EventCounts(
        tests=sum(source.tests or 0 for source in junit_sources),
        failures=sum(source.failures or 0 for source in junit_sources),
        errors=sum(source.errors or 0 for source in junit_sources),
        skipped=sum(source.skipped or 0 for source in junit_sources),
    )


def _summary(
    *,
    sources: tuple[ExternalTestEvidenceSource, ...],
    layers: tuple[ExternalTestEvidenceLayer, ...],
    next_actions: tuple[ExternalTestEvidenceNextAction, ...],
) -> ExternalTestEvidenceSummary:
    source_counts = _source_counts(sources)
    event_counts = _event_counts(sources)
    sarif_source = next(source for source in sources if source.id == "sarif_json")
    return ExternalTestEvidenceSummary(
        status=_status(sources=sources, layers=layers),
        sources_total=len(sources),
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        layers_total=len(layers),
        layers_with_evidence=sum(1 for layer in layers if layer.status == "covered"),
        layers_missing=sum(1 for layer in layers if layer.status == "missing"),
        layers_blocked=sum(1 for layer in layers if layer.status == "blocked"),
        total_tests=event_counts.tests,
        total_failures=event_counts.failures,
        total_errors=event_counts.errors,
        total_skipped=event_counts.skipped,
        line_coverage_percent=_preferred_coverage(sources, field="line_coverage_percent"),
        branch_coverage_percent=_preferred_coverage(sources, field="branch_coverage_percent"),
        sarif_results_total=sarif_source.sarif_results_total or 0,
        sarif_error_results=sarif_source.sarif_error_results or 0,
        next_actions_total=len(next_actions),
    )


def _status(
    *,
    sources: tuple[ExternalTestEvidenceSource, ...],
    layers: tuple[ExternalTestEvidenceLayer, ...],
) -> ExternalTestEvidenceStatus:
    if any(
        source.state in {"invalid", "unsafe"} and source.layer is not None
        for source in sources
    ):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if all(source.state == "present" for source in sources) and all(
        layer.status == "covered" for layer in layers
    ):
        return "ready"
    return "partial"


def _preferred_coverage(
    sources: tuple[ExternalTestEvidenceSource, ...],
    *,
    field: Literal["line_coverage_percent", "branch_coverage_percent"],
) -> float | None:
    for source_id in ("coverage_xml", "lcov_info"):
        source = next(source for source in sources if source.id == source_id)
        value = (
            source.line_coverage_percent
            if field == "line_coverage_percent"
            else source.branch_coverage_percent
        )
        if value is not None:
            return value
    return None


def _optional_int(values: Mapping[str, int | float], field: str) -> int | None:
    value = values.get(field)
    return value if isinstance(value, int) else None


def _optional_float(values: Mapping[str, int | float], field: str) -> float | None:
    value = values.get(field)
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _inline_code(value: str) -> str:
    return escape(value, quote=False).replace("`", "&#96;")


def _markdown_cell(value: object) -> str:
    text = escape(str(value), quote=False).replace("`", "&#96;")
    return text.replace("\n", " ").replace("|", "&#124;")


def _percent_text(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:g}%"


def _packet_json(packet: ExternalTestEvidencePacket) -> str:
    try:
        try:
            payload = packet.model_dump(mode="json", fallback=str)
        except TypeError:
            payload = packet.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True)
    except Exception as exc:
        msg = "external test evidence packet could not be serialized safely"
        raise ExternalTestEvidenceError(msg) from exc


def _contains_unredacted_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(text)


def _contains_unredacted_packet_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", text))
