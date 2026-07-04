"""Local value-free PR evidence card from sanitized Entroping reports."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index import (
    EvidenceArtifactState,
    LocalEvidenceArtifact,
    build_local_evidence_index,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

PR_EVIDENCE_CARD_SCHEMA_VERSION: Final = "entroping.pr-evidence-card.v1"

PrEvidenceCardOutput = Literal["md", "json"]
PrEvidenceCardSummaryOutput = Literal["md"]
PrEvidenceCardStatus = Literal["ready", "partial", "insufficient"]
PrEvidenceCardSourceState = EvidenceArtifactState
PrEvidenceCardChecklistState = Literal["ready", "attention", "blocked"]
PrEvidenceCardPriority = Literal["high", "medium", "low"]
PrEvidenceCardSourceId = Literal[
    "runtime-card-json",
    "evidence-bundle-json",
    "test-pyramid-json",
    "mutation-readiness-json",
    "observability-packet-json",
    "integration-readiness-json",
    "devex-readiness-json",
    "connector-intent-json",
    "handoff-json",
    "evidence-cloud-dashboard-json",
    "evidence-index-json",
]
PrEvidenceCardChecklistId = Literal[
    "runtime-governance",
    "evidence-completeness",
    "test-pyramid",
    "generated-test-qa",
    "observability",
    "integrations",
    "developer-experience",
    "connector-intent",
    "cross-surface-handoff",
    "evidence-cloud",
    "evidence-index",
]

_DEFAULT_OUTPUTS: Final[dict[PrEvidenceCardOutput, Path]] = {
    "md": Path("reports") / "pr-evidence-card.md",
    "json": Path("reports") / "pr-evidence-card.json",
}
_DEFAULT_SUMMARY_INPUT_PATH: Final = Path("reports") / "pr-evidence-card.json"
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_READY_STATUSES: Final = {"pass", "ready", "verified", "complete", "known"}
_BLOCKED_STATUSES: Final = {
    "blocked",
    "error",
    "fail",
    "failed",
    "insufficient",
    "invalid",
    "missing",
    "not_ready",
    "unsafe",
}


class PrEvidenceCardError(ValueError):
    """Raised when the PR evidence card cannot be generated safely."""


class PrEvidenceCardSummaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _ChecklistDefinition:
    id: PrEvidenceCardChecklistId
    label: str
    source_id: PrEvidenceCardSourceId


_CHECKLIST_DEFINITIONS: Final[tuple[_ChecklistDefinition, ...]] = (
    _ChecklistDefinition("runtime-governance", "Runtime governance", "runtime-card-json"),
    _ChecklistDefinition("evidence-completeness", "Evidence completeness", "evidence-bundle-json"),
    _ChecklistDefinition("test-pyramid", "Test pyramid", "test-pyramid-json"),
    _ChecklistDefinition("generated-test-qa", "Generated-test QA", "mutation-readiness-json"),
    _ChecklistDefinition("observability", "Observability", "observability-packet-json"),
    _ChecklistDefinition("integrations", "Integrations", "integration-readiness-json"),
    _ChecklistDefinition("developer-experience", "Developer experience", "devex-readiness-json"),
    _ChecklistDefinition("connector-intent", "Connector intent", "connector-intent-json"),
    _ChecklistDefinition("cross-surface-handoff", "Cross-surface handoff", "handoff-json"),
    _ChecklistDefinition("evidence-cloud", "Evidence Cloud", "evidence-cloud-dashboard-json"),
    _ChecklistDefinition("evidence-index", "Evidence index", "evidence-index-json"),
)
_SOURCE_IDS: Final = tuple(definition.source_id for definition in _CHECKLIST_DEFINITIONS)


class PrEvidenceCardSummary(BaseModel):
    """Aggregate local PR evidence-card state."""

    model_config = ConfigDict(extra="forbid")

    status: PrEvidenceCardStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    checklist_total: int = Field(ge=0)
    checklist_ready: int = Field(ge=0)
    checklist_attention: int = Field(ge=0)
    checklist_blocked: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class PrEvidenceCardSource(BaseModel):
    """One sanitized local source artifact summarized for PR review."""

    model_config = ConfigDict(extra="forbid")

    id: PrEvidenceCardSourceId
    label: str
    path: str
    state: PrEvidenceCardSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class PrEvidenceCardChecklistItem(BaseModel):
    """One PR-review checklist row derived from a local evidence artifact."""

    model_config = ConfigDict(extra="forbid")

    id: PrEvidenceCardChecklistId
    label: str
    source_id: PrEvidenceCardSourceId
    state: PrEvidenceCardChecklistState
    path: str
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class PrEvidenceCardNextAction(BaseModel):
    """One local action to make the PR evidence card review-ready."""

    model_config = ConfigDict(extra="forbid")

    priority: PrEvidenceCardPriority
    action: str
    source_ids: tuple[PrEvidenceCardSourceId, ...] = ()
    checklist_ids: tuple[PrEvidenceCardChecklistId, ...] = ()


class PrEvidenceCardPacket(BaseModel):
    """Schema-versioned local PR evidence card packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.pr-evidence-card.v1"] = PR_EVIDENCE_CARD_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: PrEvidenceCardSummary
    sources: tuple[PrEvidenceCardSource, ...]
    checklist: tuple[PrEvidenceCardChecklistItem, ...]
    next_actions: tuple[PrEvidenceCardNextAction, ...]


@dataclass(frozen=True, slots=True)
class PrEvidenceCardResult:
    """Result of writing one PR evidence card report."""

    output_path: Path
    packet: PrEvidenceCardPacket


def run_pr_evidence_card_report(
    *,
    project_root: Path,
    output: PrEvidenceCardOutput,
    output_path: Path | None = None,
) -> PrEvidenceCardResult:
    """Write a local PR evidence card report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported pr-evidence-card output: {output}"
        raise PrEvidenceCardError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_pr_evidence_card_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_pr_card_secret(content):
        msg = "PR evidence card contains secret-like content"
        raise PrEvidenceCardError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="PR evidence card",
            root=root,
        )
    except SafeWriteError as exc:
        raise PrEvidenceCardError(str(exc)) from exc
    return PrEvidenceCardResult(output_path=written, packet=packet)


@dataclass(frozen=True, slots=True)
class PrEvidenceCardSummaryResult:
    artifact_path: Path
    summary_markdown: str
    packet: PrEvidenceCardPacket


def run_pr_evidence_card_summary_report(
    *,
    project_root: Path,
    artifact_path: Path | None = None,
) -> PrEvidenceCardSummaryResult:
    root = project_root.expanduser().resolve()
    source_path = _resolve_summary_input_path(
        artifact_path or _DEFAULT_SUMMARY_INPUT_PATH,
        root=root,
    )
    packet = build_pr_evidence_card_summary_packet(
        artifact_path=source_path,
        project_root=root,
    )
    return PrEvidenceCardSummaryResult(
        artifact_path=source_path,
        summary_markdown=render_pr_evidence_card_summary_markdown(packet),
        packet=packet,
    )


def render_pr_evidence_card_summary_markdown(packet: PrEvidenceCardPacket) -> str:
    source_rows = "\n".join(
        f"| {_md(_source_label(row.id))} | {row.id} | `{_md(row.path)}` | {_md(row.state)} |"
        for row in packet.sources
    )
    checklist_rows = "\n".join(
        f"| {_md(row.label)} | {row.source_id} | `{_md(row.path)}` | {_md(row.state)} |"
        for row in packet.checklist
    )
    if not packet.next_actions:
        next_action_rows = "- No PR evidence-card actions are currently needed."
    else:
        next_action_rows = "\n".join(_action_markdown(row) for row in packet.next_actions)

    return "\n".join(
        (
            "# Entroping PR Evidence Card Summary",
            "",
            f"- Project: `{_md(packet.project)}`",
            f"- Overall status: `{_md(packet.summary.status)}`",
            (
                f"- Sources present: "
                f"`{packet.summary.sources_present}/{packet.summary.sources_total}`"
            ),
            (
                f"- Checklist ready: "
                f"`{packet.summary.checklist_ready}/{packet.summary.checklist_total}`"
            ),
            "",
            "## Sources",
            "",
            "| Label | ID | Path | Status |",
            "| --- | --- | --- | --- |",
            source_rows,
            "",
            "## Checks",
            "",
            "| Check | Source ID | Path | Status |",
            "| --- | --- | --- | --- |",
            checklist_rows,
            "",
            "## Next Actions",
            "",
            next_action_rows,
            "",
        )
    )


def build_pr_evidence_card_summary_packet(
    *,
    project_root: Path,
    artifact_path: Path,
) -> PrEvidenceCardPacket:
    source_path = _resolve_summary_input_path(artifact_path, root=project_root)
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(source_path, root=project_root)
    if raw_bytes is None:
        msg = (
            f"Could not read PR evidence-card artifact at {source_path}"
            if not load_error
            else f"Could not read PR evidence-card artifact at {source_path}: {load_error}"
        )
        raise PrEvidenceCardSummaryError(msg)
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise PrEvidenceCardSummaryError(
            f"PR evidence-card artifact at {source_path} contains non-UTF-8 content",
        ) from None
    if _contains_unredacted_pr_card_secret(raw_text):
        raise PrEvidenceCardSummaryError("PR evidence-card summary contains secret-like content")
    document = _parse_document(raw_text)
    if document is None:
        raise PrEvidenceCardSummaryError(
            f"PR evidence-card artifact at {source_path} does not contain valid JSON",
        )
    try:
        return PrEvidenceCardPacket.model_validate(document)
    except Exception as exc:
        raise PrEvidenceCardSummaryError(
            f"PR evidence-card artifact at {source_path} has an unexpected schema",
        ) from exc


def build_pr_evidence_card_packet(*, project_root: Path) -> PrEvidenceCardPacket:
    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    sources: list[PrEvidenceCardSource] = []
    documents: dict[PrEvidenceCardSourceId, dict[str, object]] = {}
    for source_id in _SOURCE_IDS:
        source, document = _source_from_index(
            source_id,
            indexed.get(source_id),
            root=root,
        )
        sources.append(source)
        if document is not None:
            documents[source_id] = document
    source_rows = tuple(sources)
    checklist = tuple(
        _checklist_item(definition, source_rows=source_rows, documents=documents)
        for definition in _CHECKLIST_DEFINITIONS
    )
    next_actions = _next_actions(sources=source_rows, checklist=checklist)
    return PrEvidenceCardPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=documents.values()),
        summary=_summary(sources=source_rows, checklist=checklist, next_actions=next_actions),
        sources=source_rows,
        checklist=checklist,
        next_actions=next_actions,
    )


def render_pr_evidence_card_markdown(packet: PrEvidenceCardPacket) -> str:
    """Render a value-free Markdown PR evidence card."""

    checklist_rows = "\n".join(_checklist_markdown(row) for row in packet.checklist)
    source_rows = "\n".join(_source_markdown(row) for row in packet.sources)
    action_rows = "\n".join(_action_markdown(row) for row in packet.next_actions)
    if not action_rows:
        action_rows = "- No PR evidence-card actions are currently needed."
    return "\n".join(
        (
            "# Entroping PR Evidence Card",
            "",
            "Deterministic local PR review card for sanitized Entroping evidence.",
            "",
            f"- Project: `{_md(packet.project)}`",
            f"- Status: `{_md(packet.summary.status)}`",
            f"- Sources present: `{packet.summary.sources_present}/{packet.summary.sources_total}`",
            (
                f"- Checklist ready: "
                f"`{packet.summary.checklist_ready}/{packet.summary.checklist_total}`"
            ),
            "",
            "## Review Checklist",
            "",
            "| Area | State | Source | Summary |",
            "| --- | --- | --- | --- |",
            checklist_rows,
            "",
            "## Evidence Sources",
            "",
            "| Source | State | Path | Schema | SHA-256 | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
            source_rows,
            "",
            "## Next Actions",
            "",
            action_rows,
            "",
        )
    )


def _source_from_index(
    source_id: PrEvidenceCardSourceId,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[PrEvidenceCardSource, dict[str, object] | None]:
    if artifact is None:
        return (
            PrEvidenceCardSource(
                id=source_id,
                label=_source_label(source_id),
                path=_source_path(source_id),
                state="missing",
                schema_version=None,
                sha256=None,
                summary="not indexed",
            ),
            None,
        )
    state = artifact.state
    summary = safe_evidence_text(artifact.summary)
    sha256: str | None = None
    document: dict[str, object] | None = None
    if state == "present":
        raw_bytes, load_error = read_local_evidence_json_artifact_bytes(
            root / artifact.path,
            root=root,
        )
        if raw_bytes is None:
            state = _state_from_load_error(load_error)
            summary = safe_evidence_text(load_error)
        else:
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            if _contains_unredacted_pr_card_secret(raw_text):
                state = "unsafe"
                summary = "secret-like content"
            else:
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                document = _parse_document(raw_text)
                if document is None:
                    state = "invalid"
                    summary = "invalid JSON"
                    sha256 = None
    return (
        PrEvidenceCardSource(
            id=source_id,
            label=artifact.label,
            path=artifact.path,
            state=state,
            schema_version=artifact.schema_version,
            sha256=sha256,
            summary=summary,
        ),
        document,
    )


def _checklist_item(
    definition: _ChecklistDefinition,
    *,
    source_rows: tuple[PrEvidenceCardSource, ...],
    documents: dict[PrEvidenceCardSourceId, dict[str, object]],
) -> PrEvidenceCardChecklistItem:
    source_by_id = {source.id: source for source in source_rows}
    source = source_by_id[definition.source_id]
    document = documents.get(definition.source_id)
    summary = _document_status_summary(document) if document is not None else source.summary
    return PrEvidenceCardChecklistItem(
        id=definition.id,
        label=definition.label,
        source_id=definition.source_id,
        state=_checklist_state(source=source, document=document),
        path=source.path,
        schema_version=source.schema_version,
        sha256=source.sha256,
        summary=safe_evidence_text(summary),
    )


def _summary(
    *,
    sources: tuple[PrEvidenceCardSource, ...],
    checklist: tuple[PrEvidenceCardChecklistItem, ...],
    next_actions: tuple[PrEvidenceCardNextAction, ...],
) -> PrEvidenceCardSummary:
    return PrEvidenceCardSummary(
        status=_status(sources=sources, checklist=checklist),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        checklist_total=len(checklist),
        checklist_ready=sum(1 for row in checklist if row.state == "ready"),
        checklist_attention=sum(1 for row in checklist if row.state == "attention"),
        checklist_blocked=sum(1 for row in checklist if row.state == "blocked"),
        next_actions_total=len(next_actions),
    )


def _status(
    *,
    sources: tuple[PrEvidenceCardSource, ...],
    checklist: tuple[PrEvidenceCardChecklistItem, ...],
) -> PrEvidenceCardStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if all(row.state == "ready" for row in checklist):
        return "ready"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _next_actions(
    *,
    sources: tuple[PrEvidenceCardSource, ...],
    checklist: tuple[PrEvidenceCardChecklistItem, ...],
) -> tuple[PrEvidenceCardNextAction, ...]:
    actions: list[PrEvidenceCardNextAction] = []
    checklist_by_source = {row.source_id: row for row in checklist}
    for source in sources:
        if source.state == "present":
            continue
        repair = source.state in {"invalid", "unsafe"}
        checklist_id = checklist_by_source[source.id].id
        actions.append(
            PrEvidenceCardNextAction(
                priority="high" if repair else "medium",
                action=(
                    f"Repair {source.label} before using the PR evidence card."
                    if repair
                    else f"Generate {source.label} before using the PR evidence card."
                ),
                source_ids=(source.id,),
                checklist_ids=(checklist_id,),
            )
        )
    for row in checklist:
        if row.state != "attention":
            continue
        actions.append(
            PrEvidenceCardNextAction(
                priority="low",
                action=f"Review {row.label} attention state before merge.",
                source_ids=(row.source_id,),
                checklist_ids=(row.id,),
            )
        )
    return tuple(actions)


def _checklist_state(
    *,
    source: PrEvidenceCardSource,
    document: dict[str, object] | None,
) -> PrEvidenceCardChecklistState:
    if source.state != "present":
        return "blocked"
    status = _document_status(document)
    if status in _READY_STATUSES:
        return "ready"
    if status in _BLOCKED_STATUSES:
        return "blocked"
    return "attention"


def _project_from_documents(
    *,
    root: Path,
    documents: Iterable[dict[str, object]],
) -> str:
    for document in documents:
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return safe_evidence_text(project)
    return safe_evidence_text(root.name)


def _parse_document(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _document_status_summary(document: dict[str, object] | None) -> str:
    status = _document_status(document)
    return status or "present"


def _document_status(document: dict[str, object] | None) -> str | None:
    summary = _object_field(document or {}, "summary")
    status = summary.get("status")
    if isinstance(status, str) and status.strip():
        return safe_evidence_text(status).lower()
    return None


def _object_field(document: dict[str, object], field: str) -> dict[str, object]:
    value = document.get(field)
    return value if isinstance(value, dict) else {}


def _state_from_load_error(load_error: str) -> EvidenceArtifactState:
    if load_error in {
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    }:
        return "unsafe"
    return "invalid"


def _render_packet_content(
    packet: PrEvidenceCardPacket,
    *,
    output: PrEvidenceCardOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_pr_evidence_card_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(raw_path, root=root, artifact="PR evidence card")
    except SafeWriteError as exc:
        raise PrEvidenceCardError(str(exc)) from exc


def _resolve_summary_input_path(raw_path: Path, *, root: Path) -> Path:
    return root.joinpath(raw_path).resolve()


def _source_label(source_id: PrEvidenceCardSourceId) -> str:
    for definition in _CHECKLIST_DEFINITIONS:
        if definition.source_id == source_id:
            return definition.label
    return source_id


def _source_path(source_id: PrEvidenceCardSourceId) -> str:
    return f"reports/{source_id.removesuffix('-json')}.json"


def _checklist_markdown(row: PrEvidenceCardChecklistItem) -> str:
    return (
        f"| {_md(row.label)} | {_md(row.state)} | "
        f"`{_md(row.path)}` | {_md(row.summary)} |"
    )


def _source_markdown(row: PrEvidenceCardSource) -> str:
    return (
        f"| {_md(row.label)} | {_md(row.state)} | `{_md(row.path)}` | "
        f"{_md(row.schema_version or 'n/a')} | `{_md(row.sha256 or 'n/a')}` | "
        f"{_md(row.summary)} |"
    )


def _action_markdown(row: PrEvidenceCardNextAction) -> str:
    return f"- **{_md(row.priority)}** {_md(row.action)}"


def _contains_unredacted_pr_card_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))


def _md(value: object) -> str:
    return (
        safe_evidence_text(str(value))
        .replace("`", "&#96;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )
