"""Deterministic local QA brain fine-tune readiness packet reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import contains_unredacted_evidence_secret
from entroping.core.qa_brain_eval_plan import QaBrainEvalCaseReadiness
from entroping.core.qa_brain_prompt_plan import (
    QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
    QaBrainPromptPlanError,
    QaBrainPromptPlanRow,
    build_qa_brain_prompt_plan,
)
from entroping.core.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION: Final = (
    "entroping.qa-brain-fine-tune-readiness.v1"
)

QaBrainFineTuneReadinessOutput = Literal["md", "json"]
QaBrainFineTuneReadinessStatus = Literal["ready", "partial", "insufficient"]
QaBrainFineTuneReadinessStage = Literal[
    "metadata_ready",
    "needs_evidence",
    "needs_repair",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainFineTuneReadinessOutput, Path]] = {
    "md": Path("reports") / "qa-brain-fine-tune-readiness.md",
    "json": Path("reports") / "qa-brain-fine-tune-readiness.json",
}

_READINESS_STAGES: Final[
    dict[QaBrainEvalCaseReadiness, QaBrainFineTuneReadinessStage]
] = {
    "ready": "metadata_ready",
    "missing": "needs_evidence",
    "attention": "needs_repair",
}

_EVIDENCE_COVERAGE: Final[dict[QaBrainEvalCaseReadiness, str]] = {
    "ready": (
        "Stable prompt-plan source evidence IDs are present for future "
        "metadata-only dataset design review."
    ),
    "missing": (
        "Prompt-plan source evidence is absent; add value-free local evidence "
        "before future dataset design."
    ),
    "attention": (
        "Prompt-plan source evidence needs repair before it can support future "
        "dataset design review."
    ),
}

_EVAL_CASE_COVERAGE: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "Covers weak generated-test detection signals without trusting coverage "
        "volume alone."
    ),
    "missing_gate_discovery": (
        "Covers missing QAnstitution gate discovery while preserving final gate "
        "authority."
    ),
    "unsafe_generated_hurl": (
        "Covers unsafe generated-Hurl proposal detection without source-Hurl "
        "mutation."
    ),
    "bogus_evidence": (
        "Covers unsupported evidence-claim rejection through artifact and schema "
        "metadata."
    ),
    "redaction_mistakes": (
        "Covers redaction-risk detection through counts, confidence states, and "
        "artifact IDs."
    ),
    "api_drift_reasoning": (
        "Covers API drift reasoning through value-free operation and inventory "
        "metadata."
    ),
    "mutation_fuzz_readiness": (
        "Covers mutation and fuzz readiness signals without executing mutation "
        "or fuzz tests."
    ),
    "cross_surface_handoff_quality": (
        "Covers cross-surface handoff quality for CLI, cloud, desktop, mobile, "
        "and agent metadata."
    ),
}

_SAFETY_BOUNDARIES: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "Provider-free local metadata only; no prompt execution, embeddings, "
        "uploads, dataset export, model training, fine-tuning, or model packaging."
    )
    for eval_id in _EVAL_CASE_COVERAGE
}

_REDACTION_BOUNDARIES: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "Do not include secrets, headers, cookies, tokens, request bodies, "
        "response bodies, raw URLs, source Hurl, raw report content, executable "
        "prompts, provider output, or environment values."
    )
    for eval_id in _EVAL_CASE_COVERAGE
}


class QaBrainFineTuneReadinessError(ValueError):
    """Raised when a QA brain fine-tune readiness report cannot be generated safely."""


class QaBrainFineTuneReadinessSummary(BaseModel):
    """Aggregate QA brain fine-tune readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainFineTuneReadinessStatus
    readiness_total: int = Field(ge=0)
    readiness_ready: int = Field(ge=0)
    readiness_missing: int = Field(ge=0)
    readiness_attention: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainFineTuneReadinessRow(BaseModel):
    """One deterministic future QA brain fine-tune readiness row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainEvalCaseReadiness
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    readiness_stage: QaBrainFineTuneReadinessStage
    evidence_coverage: str
    prompt_plan_completeness: str
    safety_boundary: str
    eval_case_coverage: str
    redaction_boundary: str
    deterministic_acceptance: str
    blockers: tuple[str, ...] = ()
    next_action: str


class QaBrainFineTuneReadinessNextAction(BaseModel):
    """Action needed before future QA brain fine-tune readiness."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainFineTuneReadinessPacket(BaseModel):
    """Schema-versioned local QA brain fine-tune readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-fine-tune-readiness.v1"] = (
        QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    prompt_plan_schema_version: Literal["entroping.qa-brain-prompt-plan.v1"]
    summary: QaBrainFineTuneReadinessSummary
    readiness_rows: tuple[QaBrainFineTuneReadinessRow, ...]
    next_actions: tuple[QaBrainFineTuneReadinessNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainFineTuneReadinessResult:
    """Result of writing one QA brain fine-tune readiness packet."""

    output_path: Path
    packet: QaBrainFineTuneReadinessPacket


@dataclass(frozen=True, slots=True)
class _ReadinessCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_fine_tune_readiness_report(
    *,
    project_root: Path,
    output: QaBrainFineTuneReadinessOutput,
    output_path: Path | None = None,
) -> QaBrainFineTuneReadinessResult:
    """Write a deterministic local QA brain fine-tune readiness packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-fine-tune-readiness output: {output}"
        raise QaBrainFineTuneReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_fine_tune_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain fine-tune readiness contains secret-like content"
        raise QaBrainFineTuneReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain fine-tune readiness",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainFineTuneReadinessError(str(exc)) from exc
    return QaBrainFineTuneReadinessResult(output_path=written, packet=packet)


def build_qa_brain_fine_tune_readiness(
    *,
    project_root: Path,
) -> QaBrainFineTuneReadinessPacket:
    """Build fine-tune readiness metadata from local prompt-plan readiness."""

    root = project_root.expanduser().resolve()
    try:
        prompt_plan = build_qa_brain_prompt_plan(project_root=root)
    except QaBrainPromptPlanError as exc:
        raise QaBrainFineTuneReadinessError(str(exc)) from exc
    readiness_rows = tuple(_row_from_prompt_plan(plan) for plan in prompt_plan.prompt_plans)
    next_actions = _next_actions(readiness_rows)
    packet = QaBrainFineTuneReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        prompt_plan_schema_version=QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
        summary=_summary(readiness_rows=readiness_rows, next_actions=next_actions),
        readiness_rows=readiness_rows,
        next_actions=next_actions,
    )
    if contains_unredacted_evidence_secret(packet.model_dump_json()):
        msg = "QA brain fine-tune readiness contains secret-like content"
        raise QaBrainFineTuneReadinessError(msg)
    return packet


def render_qa_brain_fine_tune_readiness_markdown(
    packet: QaBrainFineTuneReadinessPacket,
) -> str:
    """Render a human-readable, value-free QA brain fine-tune readiness packet."""

    lines = [
        "# Entroping QA Brain Fine-Tune Readiness",
        "",
        "Deterministic local readiness metadata for future Entroping QA Brain "
        "proprietary-model experiments. This report does not execute Hurl, run "
        "tests, call providers, create embeddings, use a vector database, "
        "retrieve documents, execute prompts, export datasets, upload artifacts, "
        "fine-tune models, train models, package models, parse traffic state, "
        "run mutations, or render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Generated at: `{_inline_code(packet.generated_at)}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Prompt-plan schema: `{packet.prompt_plan_schema_version}`",
        "- Readiness rows: "
        f"`{packet.summary.readiness_ready}/{packet.summary.readiness_total}` ready, "
        f"`{packet.summary.readiness_missing}` missing, "
        f"`{packet.summary.readiness_attention}` attention",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Readiness Rows",
        "",
        "| ID | Label | Readiness | Stage | Sources | Evidence Coverage | "
        "Prompt Plan | Safety Boundary | Eval Coverage | Redaction Boundary | "
        "Deterministic Acceptance | Blockers | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in packet.readiness_rows:
        lines.append(
            "| "
            f"{_markdown_cell(row.case_id)} | "
            f"{_markdown_cell(row.label)} | "
            f"{_markdown_cell(row.readiness)} | "
            f"{_markdown_cell(row.readiness_stage)} | "
            f"{_markdown_cell(', '.join(row.source_ids) or 'n/a')} | "
            f"{_markdown_cell(row.evidence_coverage)} | "
            f"{_markdown_cell(row.prompt_plan_completeness)} | "
            f"{_markdown_cell(row.safety_boundary)} | "
            f"{_markdown_cell(row.eval_case_coverage)} | "
            f"{_markdown_cell(row.redaction_boundary)} | "
            f"{_markdown_cell(row.deterministic_acceptance)} | "
            f"{_markdown_cell('; '.join(row.blockers) or 'none')} | "
            f"{_markdown_cell(row.next_action)} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain fine-tune readiness actions are currently needed.")
    else:
        lines.extend(["| Priority | Action | Cases |", "| --- | --- | --- |"])
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.case_ids) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: QaBrainFineTuneReadinessPacket,
    *,
    output: QaBrainFineTuneReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_fine_tune_readiness_markdown(packet)


def _row_from_prompt_plan(
    plan: QaBrainPromptPlanRow,
) -> QaBrainFineTuneReadinessRow:
    readiness_stage = _metadata_by_readiness(
        mapping=_READINESS_STAGES,
        readiness=plan.readiness,
        field="readiness_stage",
    )
    return QaBrainFineTuneReadinessRow(
        case_id=plan.case_id,
        label=plan.label,
        readiness=plan.readiness,
        source_ids=plan.source_ids,
        source_paths=plan.source_paths,
        readiness_stage=readiness_stage,
        evidence_coverage=_metadata_by_readiness(
            mapping=_EVIDENCE_COVERAGE,
            readiness=plan.readiness,
            field="evidence_coverage",
        ),
        prompt_plan_completeness=_prompt_plan_completeness(plan),
        eval_case_coverage=_metadata_by_case(
            mapping=_EVAL_CASE_COVERAGE,
            case_id=plan.case_id,
            field="eval_case_coverage",
        ),
        safety_boundary=_metadata_by_case(
            mapping=_SAFETY_BOUNDARIES,
            case_id=plan.case_id,
            field="safety_boundary",
        ),
        redaction_boundary=_metadata_by_case(
            mapping=_REDACTION_BOUNDARIES,
            case_id=plan.case_id,
            field="redaction_boundary",
        ),
        deterministic_acceptance=_deterministic_acceptance(plan),
        blockers=_blockers(plan),
        next_action=_plan_next_action(plan),
    )


def _metadata_by_readiness[T](
    *,
    mapping: Mapping[QaBrainEvalCaseReadiness, T],
    readiness: QaBrainEvalCaseReadiness,
    field: str,
) -> T:
    try:
        return mapping[readiness]
    except KeyError as exc:
        msg = f"QA brain fine-tune readiness is missing {field} metadata for {readiness}"
        raise QaBrainFineTuneReadinessError(msg) from exc


def _metadata_by_case[T](
    *,
    mapping: Mapping[QaBrainEvalSliceId, T],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> T:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain fine-tune readiness is missing {field} metadata for {case_id}"
        raise QaBrainFineTuneReadinessError(msg) from exc


def _prompt_plan_completeness(plan: QaBrainPromptPlanRow) -> str:
    missing = _missing_prompt_plan_fields(plan)
    if missing:
        return "Prompt-plan metadata is incomplete: " + ", ".join(missing) + "."
    return (
        "Prompt-plan metadata includes objective, allowed inputs, forbidden inputs, "
        "expected outputs, acceptance signals, negative controls, and safety notes."
    )


def _missing_prompt_plan_fields(plan: QaBrainPromptPlanRow) -> tuple[str, ...]:
    required_fields = {
        "prompt objective": bool(plan.prompt_objective.strip()),
        "allowed inputs": bool(plan.prompt_inputs_allowed),
        "forbidden inputs": bool(plan.prompt_inputs_forbidden),
        "expected outputs": bool(plan.expected_output_fields),
        "acceptance signals": bool(plan.deterministic_acceptance_signals),
        "negative controls": bool(plan.negative_controls),
        "safety notes": bool(plan.safety_notes),
    }
    return tuple(name for name, present in required_fields.items() if not present)


def _deterministic_acceptance(plan: QaBrainPromptPlanRow) -> str:
    signals = " ".join(plan.deterministic_acceptance_signals).strip()
    if not signals:
        return "No deterministic prompt-plan acceptance signals are available."
    return signals


def _blockers(plan: QaBrainPromptPlanRow) -> tuple[str, ...]:
    blockers: list[str] = []
    if plan.readiness == "missing":
        blockers.append(
            "Add value-free prompt-plan evidence before future fine-tune dataset design."
        )
    elif plan.readiness == "attention":
        blockers.append(
            "Repair invalid or unsafe prompt-plan evidence before future fine-tune dataset design."
        )
    if _missing_prompt_plan_fields(plan):
        blockers.append("Complete prompt-plan metadata before future dataset design.")
    return tuple(blockers)


def _plan_next_action(plan: QaBrainPromptPlanRow) -> str:
    if plan.readiness == "ready":
        return (
            f"Use {plan.label} metadata for future fine-tune dataset design review "
            "without exporting data."
        )
    if plan.readiness == "attention":
        return (
            f"Repair {plan.label} prompt-plan evidence before future fine-tune "
            "dataset design."
        )
    return f"Add {plan.label} prompt-plan evidence before future fine-tune dataset design."


_ACTION_PRIORITY_RANK: Final[dict[QaBrainNextActionPriority, int]] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def _next_actions(
    readiness_rows: tuple[QaBrainFineTuneReadinessRow, ...],
) -> tuple[QaBrainFineTuneReadinessNextAction, ...]:
    actions_by_case: dict[QaBrainEvalSliceId, QaBrainFineTuneReadinessNextAction] = {}
    case_order: list[QaBrainEvalSliceId] = []
    for row in readiness_rows:
        if row.readiness == "ready" and not row.blockers:
            continue
        priority: QaBrainNextActionPriority = (
            "high" if row.readiness == "attention" else "medium"
        )
        action = QaBrainFineTuneReadinessNextAction(
            priority=priority,
            action=row.next_action,
            case_ids=(row.case_id,),
        )
        previous = actions_by_case.get(row.case_id)
        if previous is None:
            actions_by_case[row.case_id] = action
            case_order.append(row.case_id)
        elif _ACTION_PRIORITY_RANK[priority] > _ACTION_PRIORITY_RANK[previous.priority]:
            actions_by_case[row.case_id] = action
    return tuple(actions_by_case[case_id] for case_id in case_order)


def _summary(
    *,
    readiness_rows: tuple[QaBrainFineTuneReadinessRow, ...],
    next_actions: tuple[QaBrainFineTuneReadinessNextAction, ...],
) -> QaBrainFineTuneReadinessSummary:
    counts = _readiness_counts(readiness_rows)
    blockers_total = len(
        {blocker for row in readiness_rows for blocker in row.blockers}
    )
    return QaBrainFineTuneReadinessSummary(
        status=_status(
            counts=counts,
            total=len(readiness_rows),
            blockers_total=blockers_total,
        ),
        readiness_total=len(readiness_rows),
        readiness_ready=counts.ready,
        readiness_missing=counts.missing,
        readiness_attention=counts.attention,
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _readiness_counts(
    readiness_rows: tuple[QaBrainFineTuneReadinessRow, ...],
) -> _ReadinessCounts:
    return _ReadinessCounts(
        ready=sum(1 for row in readiness_rows if row.readiness == "ready"),
        missing=sum(1 for row in readiness_rows if row.readiness == "missing"),
        attention=sum(1 for row in readiness_rows if row.readiness == "attention"),
    )


def _status(
    *,
    counts: _ReadinessCounts,
    total: int,
    blockers_total: int,
) -> QaBrainFineTuneReadinessStatus:
    if total and counts.ready == total and blockers_total == 0:
        return "ready"
    if counts.ready or counts.attention:
        return "partial"
    return "insufficient"


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")
