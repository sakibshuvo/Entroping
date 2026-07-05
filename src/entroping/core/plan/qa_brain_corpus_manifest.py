from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    read_local_evidence_artifact_bytes,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.plan.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalCategory,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanPacket,
    build_qa_brain_retrieval_plan,
)
from entroping.core.plan.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_CORPUS_MANIFEST_SCHEMA_VERSION: Final = (
    "entroping.qa-brain-corpus-manifest.v1"
)

QaBrainCorpusManifestOutput = Literal["md", "json"]
QaBrainCorpusManifestStatus = Literal["ready", "partial", "insufficient"]
QaBrainCorpusCandidateState = Literal["eligible", "excluded"]
QaBrainCorpusExclusionReason = Literal[
    "missing",
    "unsafe_path",
    "unreadable",
    "too_large",
    "invalid_utf8",
    "invalid_json",
    "non_object_json",
    "missing_schema_version",
    "secret_like_content",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainCorpusManifestOutput, Path]] = {
    "md": Path("reports") / "qa-brain-corpus-manifest.md",
    "json": Path("reports") / "qa-brain-corpus-manifest.json",
}


class QaBrainCorpusManifestError(ValueError):
    pass


class QaBrainCorpusManifestSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    status: QaBrainCorpusManifestStatus
    candidates_total: int = Field(ge=0)
    eligible_total: int = Field(ge=0)
    excluded_total: int = Field(ge=0)
    categories_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainCorpusCandidate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source_id: str
    state: QaBrainCorpusCandidateState
    source_category: QaBrainRetrievalCategory
    schema_id: str | None = None
    path: str
    case_ids: tuple[QaBrainEvalSliceId, ...]
    exclusion_reason: QaBrainCorpusExclusionReason | None = None


class QaBrainCorpusManifestNextAction(BaseModel):

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    source_ids: tuple[str, ...]


class QaBrainCorpusManifestPacket(BaseModel):

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-corpus-manifest.v1"] = (
        QA_BRAIN_CORPUS_MANIFEST_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    retrieval_plan_schema_version: Literal["entroping.qa-brain-retrieval-plan.v1"]
    summary: QaBrainCorpusManifestSummary
    candidates: tuple[QaBrainCorpusCandidate, ...]
    next_actions: tuple[QaBrainCorpusManifestNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainCorpusManifestResult:

    output_path: Path
    packet: QaBrainCorpusManifestPacket


@dataclass(frozen=True, slots=True)
class _ArtifactProbe:
    schema_id: str | None = None
    exclusion_reason: QaBrainCorpusExclusionReason | None = None


def run_qa_brain_corpus_manifest_report(
    *,
    project_root: Path,
    output: QaBrainCorpusManifestOutput,
    output_path: Path | None = None,
) -> QaBrainCorpusManifestResult:

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-corpus-manifest output: {output}"
        raise QaBrainCorpusManifestError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_corpus_manifest(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain corpus manifest contains secret-like content"
        raise QaBrainCorpusManifestError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain corpus manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainCorpusManifestError(str(exc)) from exc
    return QaBrainCorpusManifestResult(output_path=written, packet=packet)


def build_qa_brain_corpus_manifest(
    *,
    project_root: Path,
) -> QaBrainCorpusManifestPacket:

    root = project_root.expanduser().resolve()
    try:
        retrieval_plan = build_qa_brain_retrieval_plan(project_root=root)
    except QaBrainRetrievalPlanError as exc:
        raise QaBrainCorpusManifestError(str(exc)) from exc
    return build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=root,
        retrieval_plan=retrieval_plan,
    )


def build_qa_brain_corpus_manifest_from_retrieval_plan(
    *,
    project_root: Path,
    retrieval_plan: QaBrainRetrievalPlanPacket,
) -> QaBrainCorpusManifestPacket:

    root = project_root.expanduser().resolve()
    candidates = _candidates_from_retrieval_plan(root=root, retrieval_plan=retrieval_plan)
    next_actions = _next_actions(candidates)
    return QaBrainCorpusManifestPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        retrieval_plan_schema_version=QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
        summary=_summary(candidates=candidates, next_actions=next_actions),
        candidates=candidates,
        next_actions=next_actions,
    )


def render_qa_brain_corpus_manifest_markdown(
    packet: QaBrainCorpusManifestPacket,
) -> str:

    lines = [
        "# Entroping QA Brain Corpus Manifest",
        "",
        "Deterministic local corpus-manifest metadata for future Entroping QA Brain "
        "retrieval. This report records schema IDs, source categories, safe local "
        "paths, and exclusion reasons only. It does not create embeddings, use a "
        "vector database, call providers, upload artifacts, parse traffic state, "
        "or render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Retrieval-plan schema: `{packet.retrieval_plan_schema_version}`",
        "- Candidates: "
        f"`{packet.summary.eligible_total}/{packet.summary.candidates_total}` eligible, "
        f"`{packet.summary.excluded_total}` excluded",
        f"- Categories: `{packet.summary.categories_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Corpus Candidates",
        "",
        "| Source | State | Category | Schema | Path | Cases | Exclusion |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in packet.candidates:
        lines.append(
            "| "
            f"{_markdown_cell(candidate.source_id)} | "
            f"{_markdown_cell(candidate.state)} | "
            f"{_markdown_cell(candidate.source_category)} | "
            f"{_markdown_cell(candidate.schema_id or 'n/a')} | "
            f"{_markdown_cell(candidate.path)} | "
            f"{_markdown_cell(', '.join(candidate.case_ids) or 'n/a')} | "
            f"{_markdown_cell(candidate.exclusion_reason or 'n/a')} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain corpus-manifest actions are currently needed.")
    else:
        lines.extend(["| Priority | Action | Sources |", "| --- | --- | --- |"])
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: QaBrainCorpusManifestPacket,
    *,
    output: QaBrainCorpusManifestOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_corpus_manifest_markdown(packet)


def _candidates_from_retrieval_plan(
    *,
    root: Path,
    retrieval_plan: QaBrainRetrievalPlanPacket,
) -> tuple[QaBrainCorpusCandidate, ...]:
    candidates: list[QaBrainCorpusCandidate] = []
    for plan in retrieval_plan.retrieval_plans:
        for source_id, source_path in zip(plan.source_ids, plan.source_paths, strict=False):
            probe = _probe_artifact(root=root, source_path=source_path)
            state: QaBrainCorpusCandidateState = (
                "eligible" if probe.exclusion_reason is None else "excluded"
            )
            candidates.append(
                QaBrainCorpusCandidate(
                    source_id=source_id,
                    state=state,
                    source_category=plan.retrieval_category,
                    schema_id=probe.schema_id,
                    path=source_path,
                    case_ids=(plan.case_id,),
                    exclusion_reason=probe.exclusion_reason,
                )
            )
    return tuple(candidates)


def _probe_artifact(*, root: Path, source_path: str) -> _ArtifactProbe:
    safe_path = _safe_artifact_path(root=root, source_path=source_path)
    if safe_path is None:
        return _ArtifactProbe(exclusion_reason="unsafe_path")
    if not safe_path.exists():
        return _ArtifactProbe(exclusion_reason="missing")
    content, error = read_local_evidence_artifact_bytes(safe_path)
    if content is None:
        return _ArtifactProbe(exclusion_reason=_read_error_reason(error))
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError:
        return _ArtifactProbe(exclusion_reason="invalid_utf8")
    if contains_unredacted_evidence_secret(raw_text):
        return _ArtifactProbe(exclusion_reason="secret_like_content")
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return _ArtifactProbe(exclusion_reason="invalid_json")
    if not isinstance(document, dict):
        return _ArtifactProbe(exclusion_reason="non_object_json")
    schema_id = document.get("schema_version")
    if not isinstance(schema_id, str) or not schema_id.strip():
        return _ArtifactProbe(exclusion_reason="missing_schema_version")
    return _ArtifactProbe(schema_id=schema_id)


def _safe_artifact_path(*, root: Path, source_path: str) -> Path | None:
    raw_path = Path(source_path)
    if raw_path.is_absolute():
        return None
    candidate = root / raw_path
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        return None
    if first_symlink_path_component(candidate, root=root) is not None:
        return None
    return candidate


def _read_error_reason(error: str) -> QaBrainCorpusExclusionReason:
    if "exceeds" in error:
        return "too_large"
    if "symlink" in error:
        return "unsafe_path"
    return "unreadable"


def _next_actions(
    candidates: tuple[QaBrainCorpusCandidate, ...],
) -> tuple[QaBrainCorpusManifestNextAction, ...]:
    excluded_source_ids = tuple(
        candidate.source_id for candidate in candidates if candidate.state == "excluded"
    )
    if not excluded_source_ids:
        return ()
    return (
        QaBrainCorpusManifestNextAction(
            priority="high",
            action=(
                "Repair, remove, or replace excluded local evidence before future "
                "QA Brain retrieval indexing."
            ),
            source_ids=excluded_source_ids,
        ),
    )


def _summary(
    *,
    candidates: tuple[QaBrainCorpusCandidate, ...],
    next_actions: tuple[QaBrainCorpusManifestNextAction, ...],
) -> QaBrainCorpusManifestSummary:
    eligible_total = sum(1 for candidate in candidates if candidate.state == "eligible")
    excluded_total = len(candidates) - eligible_total
    categories = {candidate.source_category for candidate in candidates}
    return QaBrainCorpusManifestSummary(
        status=_status(total=len(candidates), eligible_total=eligible_total),
        candidates_total=len(candidates),
        eligible_total=eligible_total,
        excluded_total=excluded_total,
        categories_total=len(categories),
        next_actions_total=len(next_actions),
    )


def _status(*, total: int, eligible_total: int) -> QaBrainCorpusManifestStatus:
    if total and eligible_total == total:
        return "ready"
    if eligible_total:
        return "partial"
    return "insufficient"


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")
