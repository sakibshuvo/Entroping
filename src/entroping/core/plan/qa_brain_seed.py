"""Deterministic local QA brain seed packet reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index import EvidenceArtifactState, build_local_evidence_index
from entroping.core.evidence_common import contains_unredacted_evidence_secret
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_SEED_SCHEMA_VERSION: Final = "entroping.qa-brain-seed.v1"

QaBrainSeedOutput = Literal["md", "json"]
QaBrainSeedStatus = Literal["ready", "partial", "insufficient"]
QaBrainSeedSourceState = EvidenceArtifactState
QaBrainSeedCategory = Literal[
    "runtime_governance",
    "policy_governance",
    "generated_test_quality",
    "test_pyramid",
    "api_inventory",
    "mutation_fuzz",
    "redaction_safety",
    "cross_surface_handoff",
    "agent_review",
    "review_signal",
    "generic_evidence",
]
QaBrainEvalSliceId = Literal[
    "weak_test_detection",
    "missing_gate_discovery",
    "unsafe_generated_hurl",
    "bogus_evidence",
    "redaction_mistakes",
    "api_drift_reasoning",
    "mutation_fuzz_readiness",
    "cross_surface_handoff_quality",
]
QaBrainEvalSliceStatus = Literal["ready", "missing", "attention"]
QaBrainNextActionPriority = Literal["high", "medium", "low"]

_DEFAULT_OUTPUTS: Final[dict[QaBrainSeedOutput, Path]] = {
    "md": Path("reports") / "qa-brain-seed.md",
    "json": Path("reports") / "qa-brain-seed.json",
}

_CATEGORY_BY_ID: Final[dict[str, QaBrainSeedCategory]] = {
    "run-json": "runtime_governance",
    "run-plan-json": "runtime_governance",
    "junit-xml": "runtime_governance",
    "run-html": "runtime_governance",
    "runtime-card-md": "runtime_governance",
    "runtime-card-json": "runtime_governance",
    "effective-policy-json": "policy_governance",
    "effective-policy-md": "policy_governance",
    "gate-coverage-json": "policy_governance",
    "gate-coverage-md": "policy_governance",
    "gate-injection-json": "policy_governance",
    "gate-injection-md": "policy_governance",
    "test-quality-json": "generated_test_quality",
    "test-quality-md": "generated_test_quality",
    "test-pyramid-json": "test_pyramid",
    "test-pyramid-md": "test_pyramid",
    "api-inventory-json": "api_inventory",
    "api-inventory-md": "api_inventory",
    "drift-json": "api_inventory",
    "mutation-readiness-json": "mutation_fuzz",
    "mutation-readiness-md": "mutation_fuzz",
    "capture-summary-json": "redaction_safety",
    "capture-summary-md": "redaction_safety",
    "handoff-json": "cross_surface_handoff",
    "handoff-md": "cross_surface_handoff",
    "notification-packet-json": "cross_surface_handoff",
    "notification-packet-md": "cross_surface_handoff",
    "observability-packet-json": "cross_surface_handoff",
    "observability-packet-md": "cross_surface_handoff",
    "evidence-index-json": "cross_surface_handoff",
    "evidence-index-md": "cross_surface_handoff",
    "artifact-manifest-json": "cross_surface_handoff",
    "evidence-bundle-json": "cross_surface_handoff",
    "agent-bundle-json": "agent_review",
    "agent-bundle-md": "agent_review",
    "review-summary-md": "review_signal",
}

_EVAL_SOURCE_IDS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    "weak_test_detection": (
        "test-quality-json",
        "test-quality-md",
        "test-pyramid-json",
        "test-pyramid-md",
    ),
    "missing_gate_discovery": (
        "effective-policy-json",
        "effective-policy-md",
        "gate-coverage-json",
        "gate-coverage-md",
        "gate-injection-json",
        "gate-injection-md",
    ),
    "unsafe_generated_hurl": (
        "test-quality-json",
        "test-quality-md",
        "mutation-readiness-json",
        "mutation-readiness-md",
    ),
    "bogus_evidence": (
        "artifact-manifest-json",
        "evidence-bundle-json",
        "evidence-index-json",
        "evidence-index-md",
        "run-json",
        "drift-json",
        "agent-bundle-json",
        "review-summary-md",
    ),
    "redaction_mistakes": ("capture-summary-json", "capture-summary-md"),
    "api_drift_reasoning": (
        "api-inventory-json",
        "api-inventory-md",
        "drift-json",
    ),
    "mutation_fuzz_readiness": (
        "mutation-readiness-json",
        "mutation-readiness-md",
        "test-quality-json",
    ),
    "cross_surface_handoff_quality": (
        "handoff-json",
        "handoff-md",
        "notification-packet-json",
        "notification-packet-md",
        "observability-packet-json",
        "observability-packet-md",
        "evidence-index-json",
        "evidence-index-md",
        "runtime-card-json",
        "runtime-card-md",
    ),
}

_EVAL_LABELS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": "Weak-test detection",
    "missing_gate_discovery": "Missing-gate discovery",
    "unsafe_generated_hurl": "Unsafe generated Hurl",
    "bogus_evidence": "Bogus evidence",
    "redaction_mistakes": "Redaction mistakes",
    "api_drift_reasoning": "API drift reasoning",
    "mutation_fuzz_readiness": "Mutation/fuzz readiness",
    "cross_surface_handoff_quality": "Cross-surface handoff quality",
}

_READY_ACTIONS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": "Use generated-test quality evidence for weak-test eval design.",
    "missing_gate_discovery": "Use policy and gate evidence for missing-gate eval design.",
    "unsafe_generated_hurl": "Use generated-test safety evidence for unsafe-Hurl eval design.",
    "bogus_evidence": "Use artifact integrity evidence for bogus-evidence eval design.",
    "redaction_mistakes": "Use redaction summary evidence for redaction-mistake eval design.",
    "api_drift_reasoning": "Use API inventory and drift evidence for API-drift eval design.",
    "mutation_fuzz_readiness": "Use mutation-readiness evidence for mutation/fuzz eval design.",
    "cross_surface_handoff_quality": "Use handoff evidence for cross-surface eval design.",
}


class QaBrainSeedError(ValueError):
    """Raised when a QA brain seed report cannot be generated safely."""


class QaBrainSeedSummary(BaseModel):
    """Aggregate QA brain seed readiness state."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainSeedStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    eval_slices_total: int = Field(ge=0)
    eval_slices_ready: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainSeedSource(BaseModel):
    """One local value-free source row for future QA brain seed material."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    path: str
    state: QaBrainSeedSourceState
    schema_version: str | None = None
    category: QaBrainSeedCategory
    eval_slices: tuple[QaBrainEvalSliceId, ...] = ()
    summary: str


class QaBrainEvalSlice(BaseModel):
    """One future deterministic QA brain evaluation slice."""

    model_config = ConfigDict(extra="forbid")

    id: QaBrainEvalSliceId
    label: str
    status: QaBrainEvalSliceStatus
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    next_action: str


class QaBrainNextAction(BaseModel):
    """Action needed before future QA brain retrieval/eval work."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    source_ids: tuple[str, ...] = ()


class QaBrainSeedPacket(BaseModel):
    """Schema-versioned local QA brain seed packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-seed.v1"] = QA_BRAIN_SEED_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: QaBrainSeedSummary
    sources: tuple[QaBrainSeedSource, ...]
    eval_slices: tuple[QaBrainEvalSlice, ...]
    next_actions: tuple[QaBrainNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainSeedResult:
    """Result of writing one QA brain seed packet."""

    output_path: Path
    packet: QaBrainSeedPacket


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


def run_qa_brain_seed_report(
    *,
    project_root: Path,
    output: QaBrainSeedOutput,
    output_path: Path | None = None,
) -> QaBrainSeedResult:
    """Write a deterministic local QA brain seed packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-seed output: {output}"
        raise QaBrainSeedError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_seed(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain seed contains secret-like content"
        raise QaBrainSeedError(msg)
    try:
        written = safe_write_text(destination, content, artifact="QA brain seed", root=root)
    except SafeWriteError as exc:
        raise QaBrainSeedError(str(exc)) from exc
    return QaBrainSeedResult(output_path=written, packet=packet)


def build_qa_brain_seed(*, project_root: Path) -> QaBrainSeedPacket:
    """Build value-free QA brain seed metadata from local evidence states."""

    root = project_root.expanduser().resolve()
    sources = tuple(
        QaBrainSeedSource(
            id=artifact.id,
            label=artifact.label,
            path=artifact.path,
            state=artifact.state,
            schema_version=artifact.schema_version,
            category=_seed_category(artifact.id),
            eval_slices=_eval_slices_for_source(artifact.id),
            summary=artifact.summary,
        )
        for artifact in build_local_evidence_index(project_root=root)
    )
    eval_slices = _eval_slices(sources)
    next_actions = _next_actions(eval_slices)
    return QaBrainSeedPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        summary=_summary(sources=sources, eval_slices=eval_slices, next_actions=next_actions),
        sources=sources,
        eval_slices=eval_slices,
        next_actions=next_actions,
    )


def render_qa_brain_seed_markdown(packet: QaBrainSeedPacket) -> str:
    """Render a human-readable, value-free QA brain seed packet."""

    lines = [
        "# Entroping QA Brain Seed",
        "",
        "Deterministic local seed metadata for future Entroping QA Brain retrieval "
        + "and eval design. This report does not execute Hurl, run tests, call "
        + "providers, fine-tune models, upload artifacts, parse traffic state, or "
        + "render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        "- Eval slices ready: "
        f"`{packet.summary.eval_slices_ready}/{packet.summary.eval_slices_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Eval Slices",
        "",
        "| ID | Label | Status | Sources | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for eval_slice in packet.eval_slices:
        lines.append(
            "| "
            f"{_markdown_cell(eval_slice.id)} | "
            f"{_markdown_cell(eval_slice.label)} | "
            f"{_markdown_cell(eval_slice.status)} | "
            f"{_markdown_cell(', '.join(eval_slice.source_ids) or 'n/a')} | "
            f"{_markdown_cell(eval_slice.next_action)} |"
        )
    lines.extend(
        [
            "",
            "## Seed Sources",
            "",
            "| ID | Label | Category | State | Path | Schema | Summary |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.id)} | "
            f"{_markdown_cell(source.label)} | "
            f"{_markdown_cell(source.category)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(source.schema_version or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
        ]
    )
    if not packet.next_actions:
        lines.append("No QA brain seed actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Sources |",
                "| --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.source_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: QaBrainSeedPacket,
    *,
    output: QaBrainSeedOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_seed_markdown(packet)


def _seed_category(artifact_id: str) -> QaBrainSeedCategory:
    return _CATEGORY_BY_ID.get(artifact_id, "generic_evidence")


def _eval_slices_for_source(artifact_id: str) -> tuple[QaBrainEvalSliceId, ...]:
    return tuple(
        eval_id
        for eval_id, source_ids in _EVAL_SOURCE_IDS.items()
        if artifact_id in source_ids
    )


def _eval_slices(sources: tuple[QaBrainSeedSource, ...]) -> tuple[QaBrainEvalSlice, ...]:
    by_id = {source.id: source for source in sources}
    slices: list[QaBrainEvalSlice] = []
    for eval_id, expected_ids in _EVAL_SOURCE_IDS.items():
        relevant = tuple(source for source_id in expected_ids if (source := by_id.get(source_id)))
        present = tuple(source for source in relevant if source.state == "present")
        problem = tuple(source for source in relevant if source.state in {"invalid", "unsafe"})
        if problem:
            status: QaBrainEvalSliceStatus = "attention"
        elif present:
            status = "ready"
        else:
            status = "missing"
        ready_sources = present + problem
        slices.append(
            QaBrainEvalSlice(
                id=eval_id,
                label=_EVAL_LABELS[eval_id],
                status=status,
                source_ids=tuple(source.id for source in ready_sources),
                source_paths=tuple(source.path for source in ready_sources),
                next_action=_eval_next_action(eval_id=eval_id, status=status),
            )
        )
    return tuple(slices)


def _eval_next_action(
    *,
    eval_id: QaBrainEvalSliceId,
    status: QaBrainEvalSliceStatus,
) -> str:
    label = _EVAL_LABELS[eval_id].lower()
    if status == "ready":
        return _READY_ACTIONS[eval_id]
    if status == "attention":
        return f"Review invalid or unsafe local evidence for {label} before QA-brain evals."
    return f"Add value-free local evidence for {label} before QA-brain evals."


def _next_actions(eval_slices: tuple[QaBrainEvalSlice, ...]) -> tuple[QaBrainNextAction, ...]:
    actions: list[QaBrainNextAction] = []
    for eval_slice in eval_slices:
        if eval_slice.status == "ready":
            continue
        priority: QaBrainNextActionPriority = (
            "high" if eval_slice.status == "attention" else "medium"
        )
        verb = "Review invalid or unsafe" if priority == "high" else "Add or repair"
        actions.append(
            QaBrainNextAction(
                priority=priority,
                action=f"{verb} value-free local evidence for {eval_slice.label}.",
                source_ids=eval_slice.source_ids,
            )
        )
    return tuple(actions)


def _summary(
    *,
    sources: tuple[QaBrainSeedSource, ...],
    eval_slices: tuple[QaBrainEvalSlice, ...],
    next_actions: tuple[QaBrainNextAction, ...],
) -> QaBrainSeedSummary:
    counts = _source_counts(sources)
    ready = sum(1 for eval_slice in eval_slices if eval_slice.status == "ready")
    return QaBrainSeedSummary(
        status=_status(counts=counts, ready=ready, total=len(eval_slices)),
        sources_total=len(sources),
        sources_present=counts.present,
        sources_missing=counts.missing,
        sources_invalid=counts.invalid,
        sources_unsafe=counts.unsafe,
        eval_slices_total=len(eval_slices),
        eval_slices_ready=ready,
        next_actions_total=len(next_actions),
    )


def _source_counts(sources: tuple[QaBrainSeedSource, ...]) -> _SourceCounts:
    return _SourceCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _status(*, counts: _SourceCounts, ready: int, total: int) -> QaBrainSeedStatus:
    if counts.invalid or counts.unsafe:
        return "partial"
    if ready == total:
        return "ready"
    if counts.present:
        return "partial"
    return "insufficient"


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")
