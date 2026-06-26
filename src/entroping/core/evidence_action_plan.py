"""Local value-free evidence action plan from sanitized Entroping reports."""

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

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_index import (
    EvidenceArtifactState,
    LocalEvidenceArtifact,
    build_local_evidence_index,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

EVIDENCE_ACTION_PLAN_SCHEMA_VERSION: Final = "entroping.evidence-action-plan.v1"

EvidenceActionPlanOutput = Literal["md", "json"]
EvidenceActionPlanStatus = Literal["ready", "partial", "insufficient"]
EvidenceActionPlanSourceState = EvidenceArtifactState
EvidenceActionPlanPriority = Literal["high", "medium", "low"]
EvidenceActionPlanCategory = Literal["generate", "repair", "review"]
EvidenceActionPlanSourceId = Literal[
    "pr-evidence-card-json",
    "evidence-portal-json",
    "evidence-links-json",
    "evidence-cloud-dashboard-json",
    "devex-readiness-json",
    "integration-readiness-json",
    "connector-intent-json",
    "observability-packet-json",
    "mutation-readiness-json",
    "test-pyramid-json",
]

_DEFAULT_OUTPUTS: Final[dict[EvidenceActionPlanOutput, Path]] = {
    "md": Path("reports") / "evidence-action-plan.md",
    "json": Path("reports") / "evidence-action-plan.json",
}
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
_SOURCE_IDS: Final[tuple[EvidenceActionPlanSourceId, ...]] = (
    "pr-evidence-card-json",
    "evidence-portal-json",
    "evidence-links-json",
    "evidence-cloud-dashboard-json",
    "devex-readiness-json",
    "integration-readiness-json",
    "connector-intent-json",
    "observability-packet-json",
    "mutation-readiness-json",
    "test-pyramid-json",
)
_SOURCE_LABELS: Final[dict[EvidenceActionPlanSourceId, str]] = {
    "pr-evidence-card-json": "PR Evidence Card",
    "evidence-portal-json": "Evidence Portal",
    "evidence-links-json": "Evidence Links",
    "evidence-cloud-dashboard-json": "Evidence Cloud Dashboard",
    "devex-readiness-json": "Developer Experience Readiness",
    "integration-readiness-json": "Integration Readiness",
    "connector-intent-json": "Connector Intent",
    "observability-packet-json": "Observability Packet",
    "mutation-readiness-json": "Mutation Readiness",
    "test-pyramid-json": "Test Pyramid",
}


class EvidenceActionPlanError(ValueError):
    """Raised when the evidence action plan cannot be generated safely."""


class EvidenceActionPlanSummary(BaseModel):
    """Aggregate local action-plan state."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceActionPlanStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    sources_blocked: int = Field(ge=0)
    sources_attention: int = Field(ge=0)
    actions_total: int = Field(ge=0)
    actions_high: int = Field(ge=0)
    actions_medium: int = Field(ge=0)
    actions_low: int = Field(ge=0)


class EvidenceActionPlanSource(BaseModel):
    """One sanitized local source artifact summarized for action planning."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceActionPlanSourceId
    label: str
    path: str
    state: EvidenceActionPlanSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    status: str | None = None


class EvidenceActionPlanItem(BaseModel):
    """One prioritized local next action."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidenceActionPlanPriority
    category: EvidenceActionPlanCategory
    action: str
    source_ids: tuple[EvidenceActionPlanSourceId, ...] = ()
    status: str | None = None


class EvidenceActionPlanPacket(BaseModel):
    """Schema-versioned local evidence action-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-action-plan.v1"] = (
        EVIDENCE_ACTION_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: EvidenceActionPlanSummary
    sources: tuple[EvidenceActionPlanSource, ...]
    actions: tuple[EvidenceActionPlanItem, ...]


@dataclass(frozen=True, slots=True)
class EvidenceActionPlanResult:
    """Result of writing one evidence action-plan report."""

    output_path: Path
    packet: EvidenceActionPlanPacket


def run_evidence_action_plan_report(
    *,
    project_root: Path,
    output: EvidenceActionPlanOutput,
    output_path: Path | None = None,
) -> EvidenceActionPlanResult:
    """Write a local evidence action-plan report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-action-plan output: {output}"
        raise EvidenceActionPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_action_plan_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_action_plan_secret(content):
        msg = "Evidence action plan contains secret-like content"
        raise EvidenceActionPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="evidence action plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceActionPlanError(str(exc)) from exc
    return EvidenceActionPlanResult(output_path=written, packet=packet)


def build_evidence_action_plan_packet(*, project_root: Path) -> EvidenceActionPlanPacket:
    """Build a value-free local evidence action-plan packet."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    sources: list[EvidenceActionPlanSource] = []
    documents: dict[EvidenceActionPlanSourceId, dict[str, object]] = {}
    for source_id in _SOURCE_IDS:
        source, document = _source_from_index(source_id, indexed.get(source_id), root=root)
        sources.append(source)
        if document is not None:
            documents[source_id] = document
    source_rows = tuple(sources)
    action_rows = _actions(sources=source_rows, documents=documents)
    return EvidenceActionPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=documents.values()),
        summary=_summary(sources=source_rows, actions=action_rows),
        sources=source_rows,
        actions=action_rows,
    )


def render_evidence_action_plan_markdown(packet: EvidenceActionPlanPacket) -> str:
    """Render a value-free Markdown evidence action plan."""

    source_rows = "\n".join(_source_markdown(row) for row in packet.sources)
    action_rows = "\n".join(_action_markdown(row) for row in packet.actions)
    if not action_rows:
        action_rows = "- No evidence action-plan actions are currently needed."
    return "\n".join(
        (
            "# Entroping Evidence Action Plan",
            "",
            "Deterministic local next-action plan for sanitized Entroping evidence.",
            "",
            f"- Project: `{_md(packet.project)}`",
            f"- Status: `{_md(packet.summary.status)}`",
            f"- Sources present: `{packet.summary.sources_present}/{packet.summary.sources_total}`",
            f"- Actions: `{packet.summary.actions_total}`",
            "",
            "## Priority Actions",
            "",
            action_rows,
            "",
            "## Evidence Sources",
            "",
            "| Source | State | Status | Path | Schema | SHA-256 | Summary |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            source_rows,
            "",
        )
    )


def _source_from_index(
    source_id: EvidenceActionPlanSourceId,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[EvidenceActionPlanSource, dict[str, object] | None]:
    if artifact is None:
        return (
            EvidenceActionPlanSource(
                id=source_id,
                label=_source_label(source_id),
                path=_source_path(source_id),
                state="missing",
                schema_version=None,
                sha256=None,
                summary="not indexed",
                status=None,
            ),
            None,
        )
    state = artifact.state
    summary = safe_evidence_text(artifact.summary)
    sha256: str | None = None
    document: dict[str, object] | None = None
    status: str | None = None
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
            if _contains_unredacted_action_plan_secret(raw_text):
                state = "unsafe"
                summary = "secret-like content"
            else:
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                document = _parse_document(raw_text)
                if document is None:
                    state = "invalid"
                    summary = "invalid JSON"
                    sha256 = None
                else:
                    status = _document_status(document)
                    summary = _document_status_summary(document)
    return (
        EvidenceActionPlanSource(
            id=source_id,
            label=_source_label(source_id),
            path=artifact.path,
            state=state,
            schema_version=artifact.schema_version,
            sha256=sha256,
            summary=summary,
            status=status,
        ),
        document,
    )


def _summary(
    *,
    sources: tuple[EvidenceActionPlanSource, ...],
    actions: tuple[EvidenceActionPlanItem, ...],
) -> EvidenceActionPlanSummary:
    return EvidenceActionPlanSummary(
        status=_status(sources=sources, actions=actions),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        sources_blocked=sum(1 for source in sources if source.status in _BLOCKED_STATUSES),
        sources_attention=sum(1 for source in sources if _is_attention_status(source.status)),
        actions_total=len(actions),
        actions_high=sum(1 for action in actions if action.priority == "high"),
        actions_medium=sum(1 for action in actions if action.priority == "medium"),
        actions_low=sum(1 for action in actions if action.priority == "low"),
    )


def _status(
    *,
    sources: tuple[EvidenceActionPlanSource, ...],
    actions: tuple[EvidenceActionPlanItem, ...],
) -> EvidenceActionPlanStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(action.priority == "high" for action in actions):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if actions:
        return "partial"
    if all(source.state == "present" and source.status in _READY_STATUSES for source in sources):
        return "ready"
    return "partial"


def _actions(
    *,
    sources: tuple[EvidenceActionPlanSource, ...],
    documents: dict[EvidenceActionPlanSourceId, dict[str, object]],
) -> tuple[EvidenceActionPlanItem, ...]:
    actions: list[EvidenceActionPlanItem] = []
    for source in sources:
        if source.state != "present":
            repair = source.state in {"invalid", "unsafe"}
            actions.append(
                EvidenceActionPlanItem(
                    priority="high" if repair else "medium",
                    category="repair" if repair else "generate",
                    action=(
                        f"Repair {source.label} before using the evidence action plan."
                        if repair
                        else f"Generate {source.label} before using the evidence action plan."
                    ),
                    source_ids=(source.id,),
                    status=source.state,
                )
            )
            continue
        actions.extend(_document_actions(source=source, document=documents.get(source.id)))
    return tuple(actions)


def _document_actions(
    *,
    source: EvidenceActionPlanSource,
    document: dict[str, object] | None,
) -> tuple[EvidenceActionPlanItem, ...]:
    actions: list[EvidenceActionPlanItem] = []
    status = _document_status(document)
    if status in _BLOCKED_STATUSES:
        actions.append(
            EvidenceActionPlanItem(
                priority="high",
                category="review",
                action=f"Review {source.label} {status} status before merge.",
                source_ids=(source.id,),
                status=status,
            )
        )
    elif _is_attention_status(status):
        actions.append(
            EvidenceActionPlanItem(
                priority="low",
                category="review",
                action=f"Review {source.label} {status} status before merge.",
                source_ids=(source.id,),
                status=status,
            )
        )
    extracted = _extract_next_actions(source=source, document=document)
    actions.extend(extracted)
    if not extracted:
        count = _next_actions_total(document)
        if count > 0:
            actions.append(
                EvidenceActionPlanItem(
                    priority="low",
                    category="review",
                    action=f"Review {source.label} {count} source next actions.",
                    source_ids=(source.id,),
                    status=status,
                )
            )
    return tuple(actions)


def _extract_next_actions(
    *,
    source: EvidenceActionPlanSource,
    document: dict[str, object] | None,
) -> tuple[EvidenceActionPlanItem, ...]:
    raw_actions = document.get("next_actions") if document is not None else None
    if not isinstance(raw_actions, list):
        return ()
    actions: list[EvidenceActionPlanItem] = []
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            continue
        action = raw_action.get("action")
        if not isinstance(action, str) or not action.strip():
            continue
        if _contains_unredacted_action_plan_secret(action):
            continue
        safe_action = safe_evidence_text(action)
        actions.append(
            EvidenceActionPlanItem(
                priority=_priority(raw_action.get("priority")),
                category="review",
                action=safe_action,
                source_ids=(source.id,),
                status=_document_status(document),
            )
        )
    return tuple(actions)


def _priority(value: object) -> EvidenceActionPlanPriority:
    if value == "high":
        return "high"
    if value == "low":
        return "low"
    return "medium"


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


def _is_attention_status(status: str | None) -> bool:
    return bool(status and status not in _READY_STATUSES and status not in _BLOCKED_STATUSES)


def _next_actions_total(document: dict[str, object] | None) -> int:
    summary = _object_field(document or {}, "summary")
    value = summary.get("next_actions_total")
    return value if isinstance(value, int) and value > 0 else 0


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
    packet: EvidenceActionPlanPacket,
    *,
    output: EvidenceActionPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_action_plan_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(raw_path, root=root, artifact="Evidence action plan")
    except SafeWriteError as exc:
        raise EvidenceActionPlanError(str(exc)) from exc


def _source_label(source_id: EvidenceActionPlanSourceId) -> str:
    return _SOURCE_LABELS.get(source_id, source_id)


def _source_path(source_id: EvidenceActionPlanSourceId) -> str:
    return f"reports/{source_id.removesuffix('-json')}.json"


def _source_markdown(row: EvidenceActionPlanSource) -> str:
    return (
        f"| {_md(row.label)} | {_md(row.state)} | {_md(row.status or 'n/a')} | "
        f"`{_md(row.path)}` | {_md(row.schema_version or 'n/a')} | "
        f"`{_md(row.sha256 or 'n/a')}` | {_md(row.summary)} |"
    )


def _action_markdown(row: EvidenceActionPlanItem) -> str:
    return (
        f"- **{_md(row.priority)}** `{_md(row.category)}` "
        f"{_md(row.action)} ({_md(', '.join(row.source_ids))})"
    )


def _contains_unredacted_action_plan_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))


def _md(value: object) -> str:
    return (
        safe_evidence_text(str(value))
        .replace("`", "&#96;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )
