"""Schema-versioned local evidence index packet reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core import report_schema_versions as _report_schema_versions
from entroping.core.evidence.evidence_index import (
    EvidenceArtifactState,
    build_local_evidence_index,
)
from entroping.core.evidence_common import contains_unredacted_evidence_secret
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

EVIDENCE_INDEX_SCHEMA_VERSION: Final = _report_schema_versions.EVIDENCE_INDEX_SCHEMA_VERSION

EvidenceIndexOutput = Literal["md", "json"]
EvidenceIndexStatus = Literal["ready", "partial", "insufficient"]
EvidenceIndexArtifactState = EvidenceArtifactState

_DEFAULT_OUTPUTS: Final[dict[EvidenceIndexOutput, Path]] = {
    "md": Path("reports") / "evidence-index.md",
    "json": Path("reports") / "evidence-index.json",
}


class EvidenceIndexError(ValueError):
    """Raised when an evidence-index report cannot be generated safely."""


class EvidenceIndexSummary(BaseModel):
    """Aggregate state for canonical local evidence artifacts."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceIndexStatus
    artifacts_total: int = Field(ge=0)
    artifacts_present: int = Field(ge=0)
    artifacts_missing: int = Field(ge=0)
    artifacts_invalid: int = Field(ge=0)
    artifacts_unsafe: int = Field(ge=0)


class EvidenceIndexArtifact(BaseModel):
    """Value-free status row for one canonical local evidence artifact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    path: str
    state: EvidenceIndexArtifactState
    schema_version: str | None = None
    summary: str


class EvidenceIndexPacket(BaseModel):
    """Schema-versioned local evidence-index packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-index.v1"] = EVIDENCE_INDEX_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: EvidenceIndexSummary
    artifacts: tuple[EvidenceIndexArtifact, ...]


@dataclass(frozen=True, slots=True)
class EvidenceIndexResult:
    """Result of writing one evidence-index packet."""

    output_path: Path
    packet: EvidenceIndexPacket


@dataclass(frozen=True, slots=True)
class _ArtifactStateCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


def run_evidence_index_report(
    *,
    project_root: Path,
    output: EvidenceIndexOutput,
    output_path: Path | None = None,
) -> EvidenceIndexResult:
    """Write a local evidence-index packet without executing tests or providers."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-index output: {output}"
        raise EvidenceIndexError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_index_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Evidence index contains secret-like content"
        raise EvidenceIndexError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="evidence index",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceIndexError(str(exc)) from exc
    return EvidenceIndexResult(output_path=written, packet=packet)


def build_evidence_index_packet(*, project_root: Path) -> EvidenceIndexPacket:
    """Build a value-free local evidence-index packet."""

    root = project_root.expanduser().resolve()
    artifacts = tuple(
        EvidenceIndexArtifact(
            id=artifact.id,
            label=artifact.label,
            path=artifact.path,
            state=artifact.state,
            schema_version=artifact.schema_version,
            summary=artifact.summary,
        )
        for artifact in build_local_evidence_index(project_root=root)
    )
    return EvidenceIndexPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        summary=_summary(artifacts),
        artifacts=artifacts,
    )


def render_evidence_index_markdown(packet: EvidenceIndexPacket) -> str:
    """Render a human-readable, value-free evidence-index packet."""

    lines = [
        "# Entroping Evidence Index",
        "",
        "Read-only local evidence artifact index for CLI, PR, desktop, cloud, "
        "mobile, and agent surfaces. This report does not execute Hurl, run "
        "tests, call providers, upload artifacts, parse traffic state, or render "
        "raw report contents.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Artifacts: "
        f"`{packet.summary.artifacts_present}/{packet.summary.artifacts_total}` present, "
        f"`{packet.summary.artifacts_missing}` missing, "
        f"`{packet.summary.artifacts_invalid}` invalid, "
        f"`{packet.summary.artifacts_unsafe}` unsafe",
        "",
        "## Artifacts",
        "",
        "| ID | Label | State | Path | Schema | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for artifact in packet.artifacts:
        lines.append(
            "| "
            f"{_markdown_cell(artifact.id)} | "
            f"{_markdown_cell(artifact.label)} | "
            f"{_markdown_cell(artifact.state)} | "
            f"{_markdown_cell(artifact.path)} | "
            f"{_markdown_cell(artifact.schema_version or 'n/a')} | "
            f"{_markdown_cell(artifact.summary)} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: EvidenceIndexPacket,
    *,
    output: EvidenceIndexOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_index_markdown(packet)


def _resolve_output_path(path: Path, *, root: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        msg = "evidence-index output path must stay under the project root"
        raise EvidenceIndexError(msg) from exc
    if relative.parts and relative.parts[0] in {".entroping", "envs"}:
        msg = "evidence-index packet must not be written into .entroping or envs"
        raise EvidenceIndexError(msg)
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display = _relative_display(symlink_path, root=root)
        msg = f"evidence-index output path uses symlinked component: {display}"
        raise EvidenceIndexError(msg)
    return candidate


def _summary(artifacts: tuple[EvidenceIndexArtifact, ...]) -> EvidenceIndexSummary:
    counts = _state_counts(artifacts)
    return EvidenceIndexSummary(
        status=_status(counts),
        artifacts_total=len(artifacts),
        artifacts_present=counts.present,
        artifacts_missing=counts.missing,
        artifacts_invalid=counts.invalid,
        artifacts_unsafe=counts.unsafe,
    )


def _status(counts: _ArtifactStateCounts) -> EvidenceIndexStatus:
    if counts.invalid or counts.unsafe:
        return "partial"
    if counts.present == 0:
        return "insufficient"
    if counts.missing:
        return "partial"
    return "ready"


def _state_counts(
    artifacts: tuple[EvidenceIndexArtifact, ...],
) -> _ArtifactStateCounts:
    return _ArtifactStateCounts(
        present=sum(1 for artifact in artifacts if artifact.state == "present"),
        missing=sum(1 for artifact in artifacts if artifact.state == "missing"),
        invalid=sum(1 for artifact in artifacts if artifact.state == "invalid"),
        unsafe=sum(1 for artifact in artifacts if artifact.state == "unsafe"),
    )


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    escaped = escape(" ".join(value.split()))
    return (
        escaped.replace("\\", "&#92;")
        .replace("|", "\\|")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
        .replace("`", "&#96;")
    )


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")


def _relative_display(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.name
