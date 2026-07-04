"""Local read-only work item import bundles from sanitized draft rows."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
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

WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION: Final = "entroping.work-item-import-bundle.v1"
WORK_ITEM_IMPORT_CSV_CONTRACT_VERSION: Final = "entroping.work-item-import-csv.v1"

WorkItemImportBundleOutput = Literal["json", "csv"]
WorkItemImportStatus = Literal["ready", "partial", "insufficient"]
WorkItemImportSourceState = EvidenceArtifactState
WorkItemImportPriority = Literal["high", "medium", "low"]
WorkItemImportActionCategory = Literal["generate", "repair"]
WorkItemImportSourceId = Literal["work-item-draft-json"]
WorkItemImportTrackerFamily = Literal[
    "jira",
    "linear",
    "monday",
    "github_issues",
    "generic_tracker",
]
WorkItemImportForbiddenAction = Literal[
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

_SOURCE_ID: Final[WorkItemImportSourceId] = "work-item-draft-json"
_SOURCE_LABEL: Final = "Work Item Draft"
_SOURCE_PATH: Final = "reports/work-item-draft.json"
_DEFAULT_OUTPUTS: Final[dict[WorkItemImportBundleOutput, Path]] = {
    "json": Path("reports") / "work-item-import-bundle.json",
    "csv": Path("reports") / "work-item-import-bundle.csv",
}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_SLUG_RE: Final = re.compile(r"[^a-z0-9]+")
WORK_ITEM_IMPORT_CSV_COLUMNS: Final[tuple[str, ...]] = (
    "record_type",
    "tracker_family",
    "external_id",
    "title",
    "body",
    "priority",
    "labels",
    "source_ids",
    "source_item_ids",
    "source_action_ids",
    "source_action_count",
    "status",
    "forbidden_actions",
)
_TRACKER_FAMILIES: Final[tuple[WorkItemImportTrackerFamily, ...]] = (
    "jira",
    "linear",
    "monday",
    "github_issues",
    "generic_tracker",
)
_FORBIDDEN_ACTIONS: Final[tuple[WorkItemImportForbiddenAction, ...]] = (
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


class WorkItemImportBundleError(ValueError):
    """Raised when work item import bundles cannot be generated safely."""


class WorkItemImportSummary(BaseModel):
    """Aggregate work item import bundle state."""

    model_config = ConfigDict(extra="forbid")

    status: WorkItemImportStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    rows_total: int = Field(ge=0)
    rows_high: int = Field(ge=0)
    rows_medium: int = Field(ge=0)
    rows_low: int = Field(ge=0)
    actions_total: int = Field(ge=0)
    actions_high: int = Field(ge=0)
    actions_medium: int = Field(ge=0)
    actions_low: int = Field(ge=0)
    source_item_count: int = Field(ge=0)
    source_action_count: int = Field(ge=0)


class WorkItemImportSource(BaseModel):
    """One sanitized source artifact summarized for import bundles."""

    model_config = ConfigDict(extra="forbid")

    id: WorkItemImportSourceId
    label: str
    path: str
    state: WorkItemImportSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    status: str | None = None


class WorkItemImportRow(BaseModel):
    """One import-ready local tracker row."""

    model_config = ConfigDict(extra="forbid")

    record_type: Literal["import_row"] = "import_row"
    id: str
    tracker_family: WorkItemImportTrackerFamily
    external_id: str
    title: str
    body: str
    priority: WorkItemImportPriority
    labels: tuple[str, ...]
    source_ids: tuple[WorkItemImportSourceId, ...] = (_SOURCE_ID,)
    source_item_ids: tuple[str, ...]
    source_action_ids: tuple[str, ...]
    source_action_count: int = Field(ge=0)
    forbidden_actions: tuple[WorkItemImportForbiddenAction, ...] = _FORBIDDEN_ACTIONS
    status: str | None = None


class WorkItemImportAction(BaseModel):
    """One value-free action needed before import rows are useful."""

    model_config = ConfigDict(extra="forbid")

    record_type: Literal["action"] = "action"
    priority: WorkItemImportPriority
    category: WorkItemImportActionCategory
    action: str
    source_ids: tuple[WorkItemImportSourceId, ...]
    status: str | None = None


class WorkItemImportBundle(BaseModel):
    """Schema-versioned local work item import bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.work-item-import-bundle.v1"] = (
        WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION
    )
    csv_contract_version: Literal["entroping.work-item-import-csv.v1"] = (
        WORK_ITEM_IMPORT_CSV_CONTRACT_VERSION
    )
    csv_columns: tuple[str, ...] = WORK_ITEM_IMPORT_CSV_COLUMNS
    generated_at: str
    project: str
    summary: WorkItemImportSummary
    sources: tuple[WorkItemImportSource, ...]
    rows: tuple[WorkItemImportRow, ...]
    actions: tuple[WorkItemImportAction, ...]


@dataclass(frozen=True, slots=True)
class WorkItemImportBundleResult:
    """Result of writing a local work item import bundle."""

    output_path: Path
    packet: WorkItemImportBundle


def run_work_item_import_bundle_report(
    *,
    project_root: Path,
    output: WorkItemImportBundleOutput,
    output_path: Path | None = None,
) -> WorkItemImportBundleResult:
    """Write a local work item import bundle."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported work-item-import-bundle output: {output}"
        raise WorkItemImportBundleError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_work_item_import_bundle(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_import_secret(content):
        msg = "Work item import bundle contains secret-like content"
        raise WorkItemImportBundleError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="work item import bundle",
            root=root,
        )
    except SafeWriteError as exc:
        raise WorkItemImportBundleError(str(exc)) from exc
    return WorkItemImportBundleResult(output_path=written, packet=packet)


def build_work_item_import_bundle(*, project_root: Path) -> WorkItemImportBundle:
    """Build a local import bundle from a sanitized work item draft packet."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    source, document = _source_from_index(indexed.get(_SOURCE_ID), root=root)
    rows = _rows_from_document(source=source, document=document)
    actions = _actions(source)
    return WorkItemImportBundle(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_document(root=root, document=document),
        summary=_summary(source=source, rows=rows, actions=actions),
        sources=(source,),
        rows=rows,
        actions=actions,
    )


def _source_from_index(
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[WorkItemImportSource, dict[str, object] | None]:
    if artifact is None:
        return (
            WorkItemImportSource(
                id=_SOURCE_ID,
                label=_SOURCE_LABEL,
                path=_SOURCE_PATH,
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
            if _contains_unredacted_import_secret(raw_text):
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
        WorkItemImportSource(
            id=_SOURCE_ID,
            label=_SOURCE_LABEL,
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
    source: WorkItemImportSource,
    rows: tuple[WorkItemImportRow, ...],
    actions: tuple[WorkItemImportAction, ...],
) -> WorkItemImportSummary:
    return WorkItemImportSummary(
        status=_status(source=source, rows=rows, actions=actions),
        sources_total=1,
        sources_present=1 if source.state == "present" else 0,
        sources_missing=1 if source.state == "missing" else 0,
        sources_invalid=1 if source.state == "invalid" else 0,
        sources_unsafe=1 if source.state == "unsafe" else 0,
        rows_total=len(rows),
        rows_high=sum(1 for row in rows if row.priority == "high"),
        rows_medium=sum(1 for row in rows if row.priority == "medium"),
        rows_low=sum(1 for row in rows if row.priority == "low"),
        actions_total=len(actions),
        actions_high=sum(1 for action in actions if action.priority == "high"),
        actions_medium=sum(1 for action in actions if action.priority == "medium"),
        actions_low=sum(1 for action in actions if action.priority == "low"),
        source_item_count=len({item_id for row in rows for item_id in row.source_item_ids}),
        source_action_count=sum(row.source_action_count for row in rows),
    )


def _status(
    *,
    source: WorkItemImportSource,
    rows: tuple[WorkItemImportRow, ...],
    actions: tuple[WorkItemImportAction, ...],
) -> WorkItemImportStatus:
    if source.state in {"invalid", "unsafe"}:
        return "insufficient"
    if any(action.priority == "high" for action in actions):
        return "insufficient"
    if source.state != "present":
        return "insufficient"
    if actions:
        return "partial"
    if rows:
        return "partial"
    if source.status in {"ready", "pass", "verified", "complete", "known"}:
        return "ready"
    return "partial"


def _actions(source: WorkItemImportSource) -> tuple[WorkItemImportAction, ...]:
    if source.state == "present":
        return ()
    repair = source.state in {"invalid", "unsafe"}
    return (
        WorkItemImportAction(
            priority="high" if repair else "medium",
            category="repair" if repair else "generate",
            action=(
                "Repair Work Item Draft before building tracker import bundle."
                if repair
                else "Generate Work Item Draft before building tracker import bundle."
            ),
            source_ids=(_SOURCE_ID,),
            status=source.state,
        ),
    )


def _rows_from_document(
    *,
    source: WorkItemImportSource,
    document: dict[str, object] | None,
) -> tuple[WorkItemImportRow, ...]:
    if source.state != "present" or document is None:
        return ()
    raw_items = document.get("items")
    if not isinstance(raw_items, list):
        return ()
    rows: list[WorkItemImportRow] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        rows.extend(_rows_from_item(raw_item))
    return tuple(rows)


def _rows_from_item(raw_item: dict[object, object]) -> tuple[WorkItemImportRow, ...]:
    raw_item_id = raw_item.get("id")
    raw_title = raw_item.get("title")
    if not isinstance(raw_item_id, str) or not isinstance(raw_title, str):
        return ()
    if not raw_item_id.strip() or not raw_title.strip():
        return ()
    if _contains_unredacted_import_secret(raw_item_id) or _contains_unredacted_import_secret(
        raw_title
    ):
        return ()
    item_id = safe_evidence_text(raw_item_id)
    title = safe_evidence_text(raw_title)
    summary = _string_field(raw_item, "summary") or "Draft row from Entroping evidence."
    priority = _priority(raw_item.get("priority"))
    source_action_ids = _string_tuple(raw_item.get("source_action_ids"))
    tracker_families = _tracker_families(raw_item.get("target_systems"))
    rows: list[WorkItemImportRow] = []
    for tracker_family in tracker_families:
        external_id = f"entroping-{_slug(item_id)}-{tracker_family}"
        rows.append(
            WorkItemImportRow(
                id=f"{external_id}:import-row",
                tracker_family=tracker_family,
                external_id=external_id,
                title=title,
                body=_body(
                    summary=summary,
                    item_id=item_id,
                    source_action_ids=source_action_ids,
                ),
                priority=priority,
                labels=_labels(priority=priority, tracker_family=tracker_family),
                source_item_ids=(safe_evidence_text(item_id),),
                source_action_ids=source_action_ids,
                source_action_count=len(source_action_ids),
                status=_string_field(raw_item, "status") or None,
            )
        )
    return tuple(rows)


def _body(*, summary: str, item_id: str, source_action_ids: tuple[str, ...]) -> str:
    action_text = ", ".join(source_action_ids) if source_action_ids else "none"
    return safe_evidence_text(
        f"{summary} Source draft item: {item_id}. Source action IDs: {action_text}."
    )


def _labels(
    *,
    priority: WorkItemImportPriority,
    tracker_family: WorkItemImportTrackerFamily,
) -> tuple[str, ...]:
    return (
        "entroping",
        "runtime-governance",
        "work-item-import",
        f"tracker-{tracker_family}",
        f"priority-{priority}",
    )


def _string_field(raw_item: dict[object, object], field: str) -> str:
    value = raw_item.get(field)
    return safe_evidence_text(value) if isinstance(value, str) else ""


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for raw_item in value:
        if isinstance(raw_item, str) and raw_item.strip():
            sanitized = safe_evidence_text(raw_item)
            if not _contains_unredacted_import_secret(sanitized):
                items.append(sanitized)
    return tuple(items)


def _tracker_families(value: object) -> tuple[WorkItemImportTrackerFamily, ...]:
    if not isinstance(value, list):
        return _TRACKER_FAMILIES
    families: list[WorkItemImportTrackerFamily] = []
    for raw_family in value:
        if raw_family in _TRACKER_FAMILIES:
            families.append(raw_family)
    return tuple(families) or _TRACKER_FAMILIES


def _priority(value: object) -> WorkItemImportPriority:
    if value == "high":
        return "high"
    if value == "low":
        return "low"
    return "medium"


def _project_from_document(*, root: Path, document: dict[str, object] | None) -> str:
    project = document.get("project") if document is not None else None
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
    # Import bundles treat unreadable or oversized source packets as unsafe
    # because they cannot prove the source is value-free before deriving rows.
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
    packet: WorkItemImportBundle,
    *,
    output: WorkItemImportBundleOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_work_item_import_bundle_csv(packet)


def render_work_item_import_bundle_csv(packet: WorkItemImportBundle) -> str:
    """Render deterministic spreadsheet-safe CSV rows."""

    stream = io.StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=WORK_ITEM_IMPORT_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in packet.rows:
        writer.writerow(_csv_row_from_import_row(row))
    for action in packet.actions:
        writer.writerow(_csv_row_from_action(action))
    return stream.getvalue()


def _csv_row_from_import_row(row: WorkItemImportRow) -> dict[str, str]:
    return {
        "record_type": row.record_type,
        "tracker_family": row.tracker_family,
        "external_id": row.external_id,
        "title": _csv_cell(row.title),
        "body": _csv_cell(row.body),
        "priority": row.priority,
        "labels": _csv_cell(";".join(row.labels)),
        "source_ids": _csv_cell(";".join(row.source_ids)),
        "source_item_ids": _csv_cell(";".join(row.source_item_ids)),
        "source_action_ids": _csv_cell(";".join(row.source_action_ids)),
        "source_action_count": str(row.source_action_count),
        "status": _csv_cell(row.status or ""),
        "forbidden_actions": _csv_cell(";".join(row.forbidden_actions)),
    }


def _csv_row_from_action(action: WorkItemImportAction) -> dict[str, str]:
    return {
        "record_type": action.record_type,
        "tracker_family": "generic_tracker",
        "external_id": "",
        "title": _csv_cell(action.action),
        "body": _csv_cell(action.action),
        "priority": action.priority,
        "labels": _csv_cell(f"entroping;work-item-import;priority-{action.priority}"),
        "source_ids": _csv_cell(";".join(action.source_ids)),
        "source_item_ids": "",
        "source_action_ids": "",
        "source_action_count": "0",
        "status": _csv_cell(action.status or ""),
        "forbidden_actions": _csv_cell(";".join(_FORBIDDEN_ACTIONS)),
    }


def _csv_cell(value: str) -> str:
    sanitized = safe_evidence_text(value)
    if sanitized.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{sanitized}"
    return sanitized


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(
            raw_path,
            root=root,
            artifact="Work item import bundle",
            forbid_components_anywhere=True,
        )
    except SafeWriteError as exc:
        raise WorkItemImportBundleError(str(exc)) from exc


def _slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "work-item"


def _contains_unredacted_import_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))
