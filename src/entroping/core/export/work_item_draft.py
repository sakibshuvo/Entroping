"""Local value-free work item drafts from sanitized Entroping evidence."""

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

WORK_ITEM_DRAFT_SCHEMA_VERSION: Final = "entroping.work-item-draft.v1"

WorkItemDraftOutput = Literal["md", "json"]
WorkItemDraftStatus = Literal["ready", "partial", "insufficient"]
WorkItemDraftSourceState = EvidenceArtifactState
WorkItemDraftPriority = Literal["high", "medium", "low"]
WorkItemDraftCategory = Literal["draft", "generate", "repair"]
WorkItemTargetSystem = Literal[
    "jira",
    "linear",
    "monday",
    "github_issues",
    "generic_tracker",
]
WorkItemForbiddenAction = Literal[
    "call_external_api",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "upload_artifacts",
    "invoke_model_provider",
    "execute_hurl",
    "run_tests",
    "read_provider_keys",
    "parse_raw_traffic",
    "render_raw_artifact_contents",
]
WorkItemDraftSourceId = Literal[
    "evidence-action-plan-json",
    "connector-intent-json",
    "integration-readiness-json",
    "evidence-links-json",
    "notification-packet-json",
]

_DEFAULT_OUTPUTS: Final[dict[WorkItemDraftOutput, Path]] = {
    "md": Path("reports") / "work-item-draft.md",
    "json": Path("reports") / "work-item-draft.json",
}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_READY_STATUSES: Final = {"pass", "ready", "verified", "complete", "known"}
_SOURCE_IDS: Final[tuple[WorkItemDraftSourceId, ...]] = (
    "evidence-action-plan-json",
    "connector-intent-json",
    "integration-readiness-json",
    "evidence-links-json",
    "notification-packet-json",
)
_SOURCE_LABELS: Final[dict[WorkItemDraftSourceId, str]] = {
    "evidence-action-plan-json": "Evidence Action Plan",
    "connector-intent-json": "Connector Intent",
    "integration-readiness-json": "Integration Readiness",
    "evidence-links-json": "Evidence Links",
    "notification-packet-json": "Notification Packet",
}
_TARGET_SYSTEMS: Final[tuple[WorkItemTargetSystem, ...]] = (
    "jira",
    "linear",
    "monday",
    "github_issues",
    "generic_tracker",
)
_FORBIDDEN_ACTIONS: Final[tuple[WorkItemForbiddenAction, ...]] = (
    "call_external_api",
    "mutate_issue_tracker",
    "post_chat_message",
    "execute_chat_command",
    "upload_artifacts",
    "invoke_model_provider",
    "execute_hurl",
    "run_tests",
    "read_provider_keys",
    "parse_raw_traffic",
    "render_raw_artifact_contents",
)


class WorkItemDraftError(ValueError):
    """Raised when work item drafts cannot be generated safely."""


class WorkItemDraftSummary(BaseModel):
    """Aggregate work item draft state."""

    model_config = ConfigDict(extra="forbid")

    status: WorkItemDraftStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    items_total: int = Field(ge=0)
    items_high: int = Field(ge=0)
    items_medium: int = Field(ge=0)
    items_low: int = Field(ge=0)
    source_action_count: int = Field(ge=0)


class WorkItemDraftSource(BaseModel):
    """One sanitized local source artifact summarized for draft generation."""

    model_config = ConfigDict(extra="forbid")

    id: WorkItemDraftSourceId
    label: str
    path: str
    state: WorkItemDraftSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    status: str | None = None


class WorkItemDraftItem(BaseModel):
    """One value-free draft work item row."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: WorkItemDraftCategory
    priority: WorkItemDraftPriority
    title: str
    summary: str
    target_systems: tuple[WorkItemTargetSystem, ...] = _TARGET_SYSTEMS
    source_ids: tuple[WorkItemDraftSourceId, ...] = ()
    source_action_ids: tuple[str, ...] = ()
    source_action_count: int = Field(ge=0)
    forbidden_actions: tuple[WorkItemForbiddenAction, ...] = _FORBIDDEN_ACTIONS
    status: str | None = None


class WorkItemDraftPacket(BaseModel):
    """Schema-versioned local work item draft packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.work-item-draft.v1"] = (
        WORK_ITEM_DRAFT_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: WorkItemDraftSummary
    sources: tuple[WorkItemDraftSource, ...]
    items: tuple[WorkItemDraftItem, ...]


@dataclass(frozen=True, slots=True)
class WorkItemDraftResult:
    """Result of writing one work item draft report."""

    output_path: Path
    packet: WorkItemDraftPacket


def run_work_item_draft_report(
    *,
    project_root: Path,
    output: WorkItemDraftOutput,
    output_path: Path | None = None,
) -> WorkItemDraftResult:
    """Write a local work item draft report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported work-item-draft output: {output}"
        raise WorkItemDraftError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_work_item_draft_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_work_item_secret(content):
        msg = "Work item draft contains secret-like content"
        raise WorkItemDraftError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="work item draft",
            root=root,
        )
    except SafeWriteError as exc:
        raise WorkItemDraftError(str(exc)) from exc
    return WorkItemDraftResult(output_path=written, packet=packet)


def build_work_item_draft_packet(*, project_root: Path) -> WorkItemDraftPacket:
    """Build a value-free local work item draft packet."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    sources: list[WorkItemDraftSource] = []
    documents: dict[WorkItemDraftSourceId, dict[str, object]] = {}
    for source_id in _SOURCE_IDS:
        source, document = _source_from_index(source_id, indexed.get(source_id), root=root)
        sources.append(source)
        if document is not None:
            documents[source_id] = document
    source_rows = tuple(sources)
    item_rows = _items(sources=source_rows, documents=documents)
    return WorkItemDraftPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=documents.values()),
        summary=_summary(sources=source_rows, items=item_rows),
        sources=source_rows,
        items=item_rows,
    )


def render_work_item_draft_markdown(packet: WorkItemDraftPacket) -> str:
    """Render a value-free Markdown work item draft packet."""

    item_rows = "\n".join(_item_markdown(row) for row in packet.items)
    source_rows = "\n".join(_source_markdown(row) for row in packet.sources)
    if not item_rows:
        item_rows = "- No work item draft rows are currently needed."
    return "\n".join(
        (
            "# Entroping Work Item Draft",
            "",
            "Local read-only tracker draft rows for sanitized Entroping evidence.",
            "",
            f"- Project: `{_md(packet.project)}`",
            f"- Status: `{_md(packet.summary.status)}`",
            f"- Sources present: `{packet.summary.sources_present}/{packet.summary.sources_total}`",
            f"- Draft rows: `{packet.summary.items_total}`",
            "",
            "## Draft Rows",
            "",
            item_rows,
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
    source_id: WorkItemDraftSourceId,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[WorkItemDraftSource, dict[str, object] | None]:
    if artifact is None:
        return (
            WorkItemDraftSource(
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
            if _contains_unredacted_work_item_secret(raw_text):
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
        WorkItemDraftSource(
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
    sources: tuple[WorkItemDraftSource, ...],
    items: tuple[WorkItemDraftItem, ...],
) -> WorkItemDraftSummary:
    return WorkItemDraftSummary(
        status=_status(sources=sources, items=items),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        items_total=len(items),
        items_high=sum(1 for item in items if item.priority == "high"),
        items_medium=sum(1 for item in items if item.priority == "medium"),
        items_low=sum(1 for item in items if item.priority == "low"),
        source_action_count=sum(item.source_action_count for item in items),
    )


def _status(
    *,
    sources: tuple[WorkItemDraftSource, ...],
    items: tuple[WorkItemDraftItem, ...],
) -> WorkItemDraftStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(item.priority == "high" for item in items):
        return "insufficient"
    if not any(source.state == "present" for source in sources):
        return "insufficient"
    if items:
        return "partial"
    if all(source.state == "present" and source.status in _READY_STATUSES for source in sources):
        return "ready"
    return "partial"


def _items(
    *,
    sources: tuple[WorkItemDraftSource, ...],
    documents: dict[WorkItemDraftSourceId, dict[str, object]],
) -> tuple[WorkItemDraftItem, ...]:
    items: list[WorkItemDraftItem] = []
    for source in sources:
        if source.state != "present":
            repair = source.state in {"invalid", "unsafe"}
            items.append(
                WorkItemDraftItem(
                    id=f"{source.id}:{'repair' if repair else 'generate'}",
                    category="repair" if repair else "generate",
                    priority="high" if repair else "medium",
                    title=(
                        f"Repair {source.label} before drafting tracker work items."
                        if repair
                        else f"Generate {source.label} before drafting tracker work items."
                    ),
                    summary=(
                        f"{source.label} is {source.state}; keep tracker integration read-only."
                    ),
                    source_ids=(source.id,),
                    source_action_count=0,
                    status=source.state,
                )
            )
            continue
        if source.id == "evidence-action-plan-json":
            items.extend(
                _draft_items_from_action_plan(
                    source=source,
                    document=documents.get(source.id),
                )
            )
    return tuple(items)


def _draft_items_from_action_plan(
    *,
    source: WorkItemDraftSource,
    document: dict[str, object] | None,
) -> tuple[WorkItemDraftItem, ...]:
    raw_actions = document.get("actions") if document is not None else None
    if not isinstance(raw_actions, list):
        return ()
    items: list[WorkItemDraftItem] = []
    action_index = 0
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            continue
        action = raw_action.get("action")
        if not isinstance(action, str) or not action.strip():
            continue
        if _contains_unredacted_work_item_secret(action):
            continue
        action_index += 1
        title = safe_evidence_text(action)
        action_id = f"evidence-action-plan:{action_index:03d}"
        items.append(
            WorkItemDraftItem(
                id=f"work-item-draft:{action_index:03d}",
                category="draft",
                priority=_priority(raw_action.get("priority")),
                title=title,
                summary=_draft_summary(raw_action),
                source_ids=(source.id,),
                source_action_ids=(action_id,),
                source_action_count=1,
                status=_document_status(document),
            )
        )
    return tuple(items)


def _draft_summary(raw_action: dict[object, object]) -> str:
    category = raw_action.get("category")
    status = raw_action.get("status")
    category_text = safe_evidence_text(category) if isinstance(category, str) else "review"
    status_text = safe_evidence_text(status) if isinstance(status, str) else "unknown"
    return f"Draft tracker row for {category_text} evidence action with {status_text} status."


def _priority(value: object) -> WorkItemDraftPriority:
    if value == "high":
        return "high"
    if value == "low":
        return "low"
    return "medium"


def _project_from_documents(*, root: Path, documents: Iterable[dict[str, object]]) -> str:
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
    packet: WorkItemDraftPacket,
    *,
    output: WorkItemDraftOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_work_item_draft_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(
            raw_path,
            root=root,
            artifact="Work item draft",
            forbid_components_anywhere=True,
        )
    except SafeWriteError as exc:
        raise WorkItemDraftError(str(exc)) from exc


def _source_label(source_id: WorkItemDraftSourceId) -> str:
    return _SOURCE_LABELS.get(source_id, source_id)


def _source_path(source_id: WorkItemDraftSourceId) -> str:
    return f"reports/{source_id.removesuffix('-json')}.json"


def _source_markdown(row: WorkItemDraftSource) -> str:
    return (
        f"| {_md(row.label)} | {_md(row.state)} | {_md(row.status or 'n/a')} | "
        f"`{_md(row.path)}` | {_md(row.schema_version or 'n/a')} | "
        f"`{_md(row.sha256 or 'n/a')}` | {_md(row.summary)} |"
    )


def _item_markdown(row: WorkItemDraftItem) -> str:
    systems = ", ".join(row.target_systems)
    return (
        f"- **{_md(row.priority)}** `{_md(row.category)}` {_md(row.title)} "
        f"({_md(systems)}; {_md(', '.join(row.source_action_ids) or 'no source action')})"
    )


def _contains_unredacted_work_item_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))


def _md(value: object) -> str:
    return (
        safe_evidence_text(str(value))
        .replace("`", "&#96;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("!", "&#33;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("(", "&#40;")
        .replace(")", "&#41;")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )
