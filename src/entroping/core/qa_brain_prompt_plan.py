"""Deterministic local QA brain prompt-plan packet reports."""

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
from entroping.core.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalCategory,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanRow,
    build_qa_brain_retrieval_plan,
)
from entroping.core.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION: Final = "entroping.qa-brain-prompt-plan.v1"

QaBrainPromptPlanOutput = Literal["md", "json"]
QaBrainPromptPlanStatus = Literal["ready", "partial", "insufficient"]

_DEFAULT_OUTPUTS: Final[dict[QaBrainPromptPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-prompt-plan.md",
    "json": Path("reports") / "qa-brain-prompt-plan.json",
}

_PROMPT_OBJECTIVES: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "Design a critique prompt that identifies weak generated API tests using "
        "stable quality, coverage, and evidence IDs only."
    ),
    "missing_gate_discovery": (
        "Design a critique prompt that finds missing QAnstitution gate evidence "
        "without inventing policy or weakening final gates."
    ),
    "unsafe_generated_hurl": (
        "Design a critique prompt that flags unsafe generated-Hurl proposals "
        "without reading source Hurl contents or executing repairs."
    ),
    "bogus_evidence": (
        "Design a critique prompt that challenges unsupported evidence claims "
        "through schema, artifact, and run-state metadata."
    ),
    "redaction_mistakes": (
        "Design a critique prompt that detects redaction-risk signals using only "
        "counts, confidence states, and artifact IDs."
    ),
    "api_drift_reasoning": (
        "Design a critique prompt that explains API drift from value-free "
        "inventory, route, and drift metadata."
    ),
    "mutation_fuzz_readiness": (
        "Design a critique prompt that separates mutation/fuzz readiness from "
        "actual mutation or fuzz execution."
    ),
    "cross_surface_handoff_quality": (
        "Design a critique prompt that checks whether CLI, PR, desktop, cloud, "
        "mobile, and agent handoff metadata is sufficient."
    ),
}

_PROMPT_INPUTS_FORBIDDEN: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    eval_id: (
        "raw_url",
        "query_values",
        "headers",
        "cookies",
        "tokens",
        "request_body",
        "response_body",
        "source_hurl_content",
        "raw_report_content",
        "prompt_for_execution",
        "provider_output",
        "environment_values",
    )
    for eval_id in _PROMPT_OBJECTIVES
}

_EXPECTED_OUTPUT_FIELDS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    eval_id: (
        "case_id",
        "risk_level",
        "finding_summary",
        "evidence_ids",
        "recommended_follow_up",
        "deterministic_check",
    )
    for eval_id in _PROMPT_OBJECTIVES
}

_DETERMINISTIC_ACCEPTANCE_SIGNALS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    "weak_test_detection": (
        "References stable generated-test quality or test-pyramid evidence IDs.",
        "Separates coverage volume from assertion strength.",
    ),
    "missing_gate_discovery": (
        "References stable gate, policy, or gate-coverage evidence IDs.",
        "Preserves QAnstitution as pass/fail authority.",
    ),
    "unsafe_generated_hurl": (
        "References stable generated-test or mutation-readiness evidence IDs.",
        "Keeps Hurl syntax, semantic strength, and source immutability separate.",
    ),
    "bogus_evidence": (
        "References artifact state, checksum state, schema version, or review state.",
        "Rejects unsupported evidence claims without relying on model summaries.",
    ),
    "redaction_mistakes": (
        "References unsafe counts, confidence states, or redaction evidence IDs.",
        "Does not reveal sensitive values while explaining the redaction risk.",
    ),
    "api_drift_reasoning": (
        "References operation IDs, path templates, drift categories, or inventory IDs.",
        "Separates inventory, drift, and runtime failure evidence.",
    ),
    "mutation_fuzz_readiness": (
        "References deterministic seed or mutation-readiness evidence IDs.",
        "Keeps proposed fuzzing separate from executed proof.",
    ),
    "cross_surface_handoff_quality": (
        "References surface, evidence anchor, or handoff state metadata.",
        "Moves curated evidence metadata rather than mutable worktree state.",
    ),
}

_NEGATIVE_CONTROLS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    "weak_test_detection": (
        "Do not reward generic confidence or long prose without evidence IDs.",
        "Do not treat high coverage as proof of assertion strength.",
    ),
    "missing_gate_discovery": (
        "Do not invent QAnstitution gates that are not present in local evidence.",
        "Do not weaken final gates to make a case pass.",
    ),
    "unsafe_generated_hurl": (
        "Do not accept Python HTTP-client execution as Hurl proof.",
        "Do not accept source-Hurl mutation as a repair signal.",
    ),
    "bogus_evidence": (
        "Do not accept claims that lack artifact paths and schema versions.",
        "Do not treat model summaries as source of truth.",
    ),
    "redaction_mistakes": (
        "Do not expose secrets, cookies, headers, bodies, prompts, or raw traffic.",
        "Do not call provider output safe without deterministic redaction evidence.",
    ),
    "api_drift_reasoning": (
        "Do not infer endpoint behavior from raw URLs, query values, or bodies.",
        "Do not collapse drift, inventory, and runtime failures into one label.",
    ),
    "mutation_fuzz_readiness": (
        "Do not run hidden fuzzing or mutations from this report.",
        "Do not accept unreproducible seeds as eval evidence.",
    ),
    "cross_surface_handoff_quality": (
        "Do not sync repos, vaults, traffic, secrets, source Hurl, or mutable worktrees.",
        "Do not treat phone, desktop, cloud, or CLI handoff as write authority.",
    ),
}

_SAFETY_NOTES: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    eval_id: (
        "Use value-free local metadata only.",
        "Treat prompt-plan rows as future prompt design metadata, not executable prompts.",
        "Do not embed raw traffic, source Hurl, prompt text for execution, "
        "provider output, secrets, or environment values.",
    )
    for eval_id in _PROMPT_OBJECTIVES
}


class QaBrainPromptPlanError(ValueError):
    """Raised when a QA brain prompt-plan report cannot be generated safely."""


class QaBrainPromptPlanSummary(BaseModel):
    """Aggregate QA brain prompt-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainPromptPlanStatus
    prompts_total: int = Field(ge=0)
    prompts_ready: int = Field(ge=0)
    prompts_missing: int = Field(ge=0)
    prompts_attention: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainPromptPlanRow(BaseModel):
    """One deterministic future QA brain prompt-plan row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainEvalCaseReadiness
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    retrieval_category: QaBrainRetrievalCategory
    prompt_objective: str
    prompt_inputs_allowed: tuple[str, ...]
    prompt_inputs_forbidden: tuple[str, ...]
    expected_output_fields: tuple[str, ...]
    deterministic_acceptance_signals: tuple[str, ...]
    negative_controls: tuple[str, ...]
    safety_notes: tuple[str, ...]
    next_action: str


class QaBrainPromptPlanNextAction(BaseModel):
    """Action needed before future QA brain prompt design."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainPromptPlanPacket(BaseModel):
    """Schema-versioned local QA brain prompt-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-prompt-plan.v1"] = (
        QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    retrieval_plan_schema_version: Literal["entroping.qa-brain-retrieval-plan.v1"]
    summary: QaBrainPromptPlanSummary
    prompt_plans: tuple[QaBrainPromptPlanRow, ...]
    next_actions: tuple[QaBrainPromptPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainPromptPlanResult:
    """Result of writing one QA brain prompt-plan packet."""

    output_path: Path
    packet: QaBrainPromptPlanPacket


@dataclass(frozen=True, slots=True)
class _PromptCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_prompt_plan_report(
    *,
    project_root: Path,
    output: QaBrainPromptPlanOutput,
    output_path: Path | None = None,
) -> QaBrainPromptPlanResult:
    """Write a deterministic local QA brain prompt-plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-prompt-plan output: {output}"
        raise QaBrainPromptPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_prompt_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain prompt plan contains secret-like content"
        raise QaBrainPromptPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain prompt plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainPromptPlanError(str(exc)) from exc
    return QaBrainPromptPlanResult(output_path=written, packet=packet)


def build_qa_brain_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
    """Build future QA brain prompt metadata from local retrieval-plan readiness."""

    root = project_root.expanduser().resolve()
    try:
        retrieval_plan = build_qa_brain_retrieval_plan(project_root=root)
    except QaBrainRetrievalPlanError as exc:
        raise QaBrainPromptPlanError(str(exc)) from exc
    prompt_plans = tuple(
        _row_from_retrieval_plan(plan) for plan in retrieval_plan.retrieval_plans
    )
    next_actions = _next_actions(prompt_plans)
    return QaBrainPromptPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        retrieval_plan_schema_version=QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
        summary=_summary(prompt_plans=prompt_plans, next_actions=next_actions),
        prompt_plans=prompt_plans,
        next_actions=next_actions,
    )


def render_qa_brain_prompt_plan_markdown(packet: QaBrainPromptPlanPacket) -> str:
    """Render a human-readable, value-free QA brain prompt-plan packet."""

    lines = [
        "# Entroping QA Brain Prompt Plan",
        "",
        "Deterministic local prompt-plan metadata for future Entroping QA Brain "
        "prompt and model-evaluation design. This report does not execute Hurl, "
        "run tests, call providers, create embeddings, use a vector database, "
        "retrieve documents, fine-tune models, upload artifacts, parse traffic "
        "state, run mutations, execute prompts, or render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Generated at: `{_inline_code(packet.generated_at)}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Retrieval-plan schema: `{packet.retrieval_plan_schema_version}`",
        "- Prompt plans: "
        f"`{packet.summary.prompts_ready}/{packet.summary.prompts_total}` ready, "
        f"`{packet.summary.prompts_missing}` missing, "
        f"`{packet.summary.prompts_attention}` attention",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Prompt Plans",
        "",
        "| ID | Label | Readiness | Category | Sources | Objective | Allowed Inputs | "
        "Forbidden Inputs | Expected Outputs | Acceptance Signals |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for plan in packet.prompt_plans:
        lines.append(
            "| "
            f"{_markdown_cell(plan.case_id)} | "
            f"{_markdown_cell(plan.label)} | "
            f"{_markdown_cell(plan.readiness)} | "
            f"{_markdown_cell(plan.retrieval_category)} | "
            f"{_markdown_cell(', '.join(plan.source_ids) or 'n/a')} | "
            f"{_markdown_cell(plan.prompt_objective)} | "
            f"{_markdown_cell(', '.join(plan.prompt_inputs_allowed))} | "
            f"{_markdown_cell(', '.join(plan.prompt_inputs_forbidden))} | "
            f"{_markdown_cell(', '.join(plan.expected_output_fields))} | "
            f"{_markdown_cell(' '.join(plan.deterministic_acceptance_signals))} |"
        )
    lines.extend(["", "## Negative Controls", ""])
    for plan in packet.prompt_plans:
        lines.append(f"### {_markdown_heading(plan.label)}")
        for control in plan.negative_controls:
            lines.append(f"- {_markdown_text(control)}")
        lines.append("")
    lines.extend(["## Safety Notes", ""])
    for plan in packet.prompt_plans:
        lines.append(f"### {_markdown_heading(plan.label)}")
        for note in plan.safety_notes:
            lines.append(f"- {_markdown_text(note)}")
        lines.append("")
    lines.extend(["## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain prompt-plan actions are currently needed.")
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
    packet: QaBrainPromptPlanPacket,
    *,
    output: QaBrainPromptPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_prompt_plan_markdown(packet)


def _row_from_retrieval_plan(plan: QaBrainRetrievalPlanRow) -> QaBrainPromptPlanRow:
    return QaBrainPromptPlanRow(
        case_id=plan.case_id,
        label=plan.label,
        readiness=plan.readiness,
        source_ids=plan.source_ids,
        source_paths=plan.source_paths,
        retrieval_category=plan.retrieval_category,
        prompt_objective=_metadata_text(
            mapping=_PROMPT_OBJECTIVES,
            case_id=plan.case_id,
            field="prompt_objective",
        ),
        prompt_inputs_allowed=_prompt_inputs_allowed(plan),
        prompt_inputs_forbidden=_metadata_tuple(
            mapping=_PROMPT_INPUTS_FORBIDDEN,
            case_id=plan.case_id,
            field="prompt_inputs_forbidden",
        ),
        expected_output_fields=_metadata_tuple(
            mapping=_EXPECTED_OUTPUT_FIELDS,
            case_id=plan.case_id,
            field="expected_output_fields",
        ),
        deterministic_acceptance_signals=_metadata_tuple(
            mapping=_DETERMINISTIC_ACCEPTANCE_SIGNALS,
            case_id=plan.case_id,
            field="deterministic_acceptance_signals",
        ),
        negative_controls=_metadata_tuple(
            mapping=_NEGATIVE_CONTROLS,
            case_id=plan.case_id,
            field="negative_controls",
        ),
        safety_notes=_metadata_tuple(
            mapping=_SAFETY_NOTES,
            case_id=plan.case_id,
            field="safety_notes",
        ),
        next_action=_plan_next_action(plan),
    )


def _prompt_inputs_allowed(plan: QaBrainRetrievalPlanRow) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                "case_id",
                "label",
                "readiness",
                "source_ids",
                "source_paths",
                "retrieval_category",
                "retrieval_intent",
                *plan.allowed_fields,
            )
        )
    )


def _metadata_text(
    *,
    mapping: Mapping[QaBrainEvalSliceId, str],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> str:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain prompt plan is missing {field} metadata for {case_id}"
        raise QaBrainPromptPlanError(msg) from exc


def _metadata_tuple(
    *,
    mapping: Mapping[QaBrainEvalSliceId, tuple[str, ...]],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> tuple[str, ...]:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain prompt plan is missing {field} metadata for {case_id}"
        raise QaBrainPromptPlanError(msg) from exc


def _plan_next_action(plan: QaBrainRetrievalPlanRow) -> str:
    if plan.readiness == "ready":
        return f"Use value-free local evidence for {plan.label} prompt design."
    if plan.readiness == "attention":
        return (
            f"Repair invalid or unsafe local evidence before {plan.label} "
            "prompt design."
        )
    return f"Add value-free local evidence before {plan.label} prompt design."


def _next_actions(
    prompt_plans: tuple[QaBrainPromptPlanRow, ...],
) -> tuple[QaBrainPromptPlanNextAction, ...]:
    actions: list[QaBrainPromptPlanNextAction] = []
    for plan in prompt_plans:
        if plan.readiness == "ready":
            continue
        priority: QaBrainNextActionPriority = (
            "high" if plan.readiness == "attention" else "medium"
        )
        actions.append(
            QaBrainPromptPlanNextAction(
                priority=priority,
                action=plan.next_action,
                case_ids=(plan.case_id,),
            )
        )
    return tuple(actions)


def _summary(
    *,
    prompt_plans: tuple[QaBrainPromptPlanRow, ...],
    next_actions: tuple[QaBrainPromptPlanNextAction, ...],
) -> QaBrainPromptPlanSummary:
    counts = _prompt_counts(prompt_plans)
    return QaBrainPromptPlanSummary(
        status=_status(counts=counts, total=len(prompt_plans)),
        prompts_total=len(prompt_plans),
        prompts_ready=counts.ready,
        prompts_missing=counts.missing,
        prompts_attention=counts.attention,
        next_actions_total=len(next_actions),
    )


def _prompt_counts(prompt_plans: tuple[QaBrainPromptPlanRow, ...]) -> _PromptCounts:
    return _PromptCounts(
        ready=sum(1 for plan in prompt_plans if plan.readiness == "ready"),
        missing=sum(1 for plan in prompt_plans if plan.readiness == "missing"),
        attention=sum(1 for plan in prompt_plans if plan.readiness == "attention"),
    )


def _status(*, counts: _PromptCounts, total: int) -> QaBrainPromptPlanStatus:
    if total and counts.ready == total:
        return "ready"
    if counts.ready or counts.attention:
        return "partial"
    return "insufficient"


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _markdown_text(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_heading(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")
