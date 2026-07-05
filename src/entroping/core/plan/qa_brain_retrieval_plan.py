"""Deterministic local QA brain retrieval-plan packet reports."""

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
from entroping.core.plan.qa_brain_eval_plan import (
    QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
    QaBrainEvalCase,
    QaBrainEvalCaseReadiness,
    QaBrainEvalPlanError,
    build_qa_brain_eval_plan,
)
from entroping.core.plan.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION: Final = (
    "entroping.qa-brain-retrieval-plan.v1"
)

QaBrainRetrievalPlanOutput = Literal["md", "json"]
QaBrainRetrievalPlanStatus = Literal["ready", "partial", "insufficient"]
QaBrainRetrievalCategory = Literal[
    "test_quality",
    "policy_governance",
    "generated_hurl_safety",
    "evidence_integrity",
    "redaction_safety",
    "api_drift",
    "mutation_fuzz",
    "cross_surface_handoff",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainRetrievalPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-retrieval-plan.md",
    "json": Path("reports") / "qa-brain-retrieval-plan.json",
}

_RETRIEVAL_CATEGORIES: Final[dict[QaBrainEvalSliceId, QaBrainRetrievalCategory]] = {
    "weak_test_detection": "test_quality",
    "missing_gate_discovery": "policy_governance",
    "unsafe_generated_hurl": "generated_hurl_safety",
    "bogus_evidence": "evidence_integrity",
    "redaction_mistakes": "redaction_safety",
    "api_drift_reasoning": "api_drift",
    "mutation_fuzz_readiness": "mutation_fuzz",
    "cross_surface_handoff_quality": "cross_surface_handoff",
}

_RETRIEVAL_INTENTS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "Find generated-test quality signals for weak assertions, shallow coverage, "
        + "and missing negative paths by stable artifact ID."
    ),
    "missing_gate_discovery": (
        "Find policy and gate evidence that shows missing or under-covered "
        + "QAnstitution checks by stable gate and artifact IDs."
    ),
    "unsafe_generated_hurl": (
        "Find generated-Hurl safety signals for overbroad, brittle, or unsafe "
        + "test proposals without reading source Hurl contents."
    ),
    "bogus_evidence": (
        "Find artifact integrity and run-state signals that challenge unsupported "
        + "evidence claims through schema and artifact metadata."
    ),
    "redaction_mistakes": (
        "Find redaction-risk signals from counts and state metadata without "
        + "rendering headers, cookies, bodies, or tokens."
    ),
    "api_drift_reasoning": (
        "Find API inventory and drift signals that explain behavior changes from "
        + "value-free route and schema metadata."
    ),
    "mutation_fuzz_readiness": (
        "Find mutation and fuzz readiness signals from deterministic seed and "
        + "coverage metadata without running fuzzers or mutations."
    ),
    "cross_surface_handoff_quality": (
        "Find handoff and evidence-index signals that show whether CLI, PR, "
        + "desktop, cloud, mobile, and agent surfaces share enough context."
    ),
}

_ALLOWED_FIELDS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    "weak_test_detection": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "state",
        "quality_score",
        "finding_counts",
    ),
    "missing_gate_discovery": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "gate_id",
        "gate_counts",
        "policy_status",
    ),
    "unsafe_generated_hurl": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "generated_test_counts",
        "mutation_category",
        "safety_state",
    ),
    "bogus_evidence": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "state",
        "checksum_status",
        "review_status",
    ),
    "redaction_mistakes": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "redaction_state",
        "unsafe_counts",
        "confidence_counts",
    ),
    "api_drift_reasoning": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "operation_id",
        "path_template",
        "drift_category",
    ),
    "mutation_fuzz_readiness": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "seed_state",
        "mutation_category",
        "readiness_state",
    ),
    "cross_surface_handoff_quality": (
        "schema_version",
        "artifact_id",
        "relative_path",
        "surface",
        "handoff_state",
        "evidence_anchor",
    ),
}

_FORBIDDEN_FIELDS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    eval_id: (
        "raw_url",
        "query_values",
        "headers",
        "cookies",
        "tokens",
        "request_body",
        "response_body",
        "source_hurl_content",
        "prompt",
        "provider_output",
        "environment_values",
    )
    for eval_id in _RETRIEVAL_CATEGORIES
}

_QUERY_HINTS: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    "weak_test_detection": (
        "Find weak-test detection evidence by artifact ID, schema version, and quality state.",
        "Prefer rows that distinguish coverage volume from assertion strength.",
    ),
    "missing_gate_discovery": (
        "Find missing-gate discovery evidence by gate ID, final-gate state, and coverage counts.",
        "Prefer rows that preserve QAnstitution as pass/fail authority.",
    ),
    "unsafe_generated_hurl": (
        "Find unsafe generated-Hurl evidence by generated-test category and safety state.",
        "Prefer rows that separate Hurl syntax, semantic strength, and source immutability.",
    ),
    "bogus_evidence": (
        "Find bogus-evidence signals by artifact state, checksum status, and review state.",
        "Prefer rows that cite artifact IDs instead of model summaries.",
    ),
    "redaction_mistakes": (
        "Find redaction-mistake signals by unsafe counts and confidence state.",
        "Prefer rows that prove sensitive values were not rendered.",
    ),
    "api_drift_reasoning": (
        "Find API-drift reasoning evidence by operation ID, path template, and drift category.",
        "Prefer rows that separate inventory, drift, and runtime failure signals.",
    ),
    "mutation_fuzz_readiness": (
        "Find mutation/fuzz readiness evidence by deterministic seed and mutation category.",
        "Prefer rows that keep proposed fuzzing separate from executed proof.",
    ),
    "cross_surface_handoff_quality": (
        "Find cross-surface handoff evidence by surface, evidence anchor, and handoff state.",
        "Prefer rows that move curated evidence metadata, not mutable worktrees.",
    ),
}

_SAFETY_NOTES: Final[dict[QaBrainEvalSliceId, tuple[str, ...]]] = {
    eval_id: (
        "Use value-free local metadata only.",
        (
            "Do not embed raw traffic, source Hurl, prompts, provider output, "
            + "secrets, or environment values."
        ),
        "Treat retrieval rows as future model context candidates, not pass/fail authority.",
    )
    for eval_id in _RETRIEVAL_CATEGORIES
}


class QaBrainRetrievalPlanError(ValueError):
    """Raised when a QA brain retrieval-plan report cannot be generated safely."""


class QaBrainRetrievalPlanSummary(BaseModel):
    """Aggregate QA brain retrieval-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainRetrievalPlanStatus
    plans_total: int = Field(ge=0)
    plans_ready: int = Field(ge=0)
    plans_missing: int = Field(ge=0)
    plans_attention: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainRetrievalPlanRow(BaseModel):
    """One deterministic future QA brain retrieval-plan row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainEvalCaseReadiness
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    retrieval_category: QaBrainRetrievalCategory
    retrieval_intent: str
    allowed_fields: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    query_hints: tuple[str, ...]
    safety_notes: tuple[str, ...]
    next_action: str


class QaBrainRetrievalPlanNextAction(BaseModel):
    """Action needed before future QA brain retrieval indexing."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainRetrievalPlanPacket(BaseModel):
    """Schema-versioned local QA brain retrieval-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-retrieval-plan.v1"] = (
        QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    eval_plan_schema_version: Literal["entroping.qa-brain-eval-plan.v1"]
    summary: QaBrainRetrievalPlanSummary
    retrieval_plans: tuple[QaBrainRetrievalPlanRow, ...]
    next_actions: tuple[QaBrainRetrievalPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainRetrievalPlanResult:
    """Result of writing one QA brain retrieval-plan packet."""

    output_path: Path
    packet: QaBrainRetrievalPlanPacket


@dataclass(frozen=True, slots=True)
class _PlanCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_retrieval_plan_report(
    *,
    project_root: Path,
    output: QaBrainRetrievalPlanOutput,
    output_path: Path | None = None,
) -> QaBrainRetrievalPlanResult:
    """Write a deterministic local QA brain retrieval-plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-retrieval-plan output: {output}"
        raise QaBrainRetrievalPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_retrieval_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain retrieval plan contains secret-like content"
        raise QaBrainRetrievalPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain retrieval plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainRetrievalPlanError(str(exc)) from exc
    return QaBrainRetrievalPlanResult(output_path=written, packet=packet)


def build_qa_brain_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
    """Build future QA brain retrieval metadata from local eval-plan readiness."""

    root = project_root.expanduser().resolve()
    try:
        eval_plan = build_qa_brain_eval_plan(project_root=root)
    except QaBrainEvalPlanError as exc:
        raise QaBrainRetrievalPlanError(str(exc)) from exc
    retrieval_plans = tuple(_row_from_eval_case(eval_case) for eval_case in eval_plan.cases)
    next_actions = _next_actions(retrieval_plans)
    return QaBrainRetrievalPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        eval_plan_schema_version=QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
        summary=_summary(retrieval_plans=retrieval_plans, next_actions=next_actions),
        retrieval_plans=retrieval_plans,
        next_actions=next_actions,
    )


def render_qa_brain_retrieval_plan_markdown(
    packet: QaBrainRetrievalPlanPacket,
) -> str:
    """Render a human-readable, value-free QA brain retrieval-plan packet."""

    lines = [
        "# Entroping QA Brain Retrieval Plan",
        "",
        (
            "Deterministic local retrieval-plan metadata for future Entroping QA Brain "
            + "retrieval, prompt, and model-evaluation design. This report does not "
            + "execute Hurl, run tests, call providers, create embeddings, use a "
            + "vector database, fine-tune models, upload artifacts, parse traffic "
            + "state, run mutations, or render raw report contents."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Eval-plan schema: `{packet.eval_plan_schema_version}`",
        (
            f"- Retrieval plans: `{packet.summary.plans_ready}/"
            + f"{packet.summary.plans_total}` ready, "
            + f"`{packet.summary.plans_missing}` missing, "
            + f"`{packet.summary.plans_attention}` attention"
        ),
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Retrieval Plans",
        "",
        (
            "| ID | Label | Readiness | Category | Sources | Intent | "
            + "Allowed Fields | Forbidden Fields | Query Hints |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for plan in packet.retrieval_plans:
        lines.append(
            "| "
            f"{_markdown_cell(plan.case_id)} | "
            f"{_markdown_cell(plan.label)} | "
            f"{_markdown_cell(plan.readiness)} | "
            f"{_markdown_cell(plan.retrieval_category)} | "
            f"{_markdown_cell(', '.join(plan.source_ids) or 'n/a')} | "
            f"{_markdown_cell(plan.retrieval_intent)} | "
            f"{_markdown_cell(', '.join(plan.allowed_fields))} | "
            f"{_markdown_cell(', '.join(plan.forbidden_fields))} | "
            f"{_markdown_cell(' '.join(plan.query_hints))} |"
        )
    lines.extend(["", "## Safety Notes", ""])
    for plan in packet.retrieval_plans:
        lines.append(f"### {_markdown_heading(plan.label)}")
        for note in plan.safety_notes:
            lines.append(f"- {_markdown_text(note)}")
        lines.append("")
    lines.extend(["## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain retrieval-plan actions are currently needed.")
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
    packet: QaBrainRetrievalPlanPacket,
    *,
    output: QaBrainRetrievalPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_retrieval_plan_markdown(packet)


def _row_from_eval_case(eval_case: QaBrainEvalCase) -> QaBrainRetrievalPlanRow:
    return QaBrainRetrievalPlanRow(
        case_id=eval_case.id,
        label=eval_case.label,
        readiness=eval_case.readiness,
        source_ids=eval_case.source_ids,
        source_paths=eval_case.source_paths,
        retrieval_category=_metadata_category(
            mapping=_RETRIEVAL_CATEGORIES,
            case_id=eval_case.id,
            field="retrieval_category",
        ),
        retrieval_intent=_metadata_text(
            mapping=_RETRIEVAL_INTENTS,
            case_id=eval_case.id,
            field="retrieval_intent",
        ),
        allowed_fields=_metadata_tuple(
            mapping=_ALLOWED_FIELDS,
            case_id=eval_case.id,
            field="allowed_fields",
        ),
        forbidden_fields=_metadata_tuple(
            mapping=_FORBIDDEN_FIELDS,
            case_id=eval_case.id,
            field="forbidden_fields",
        ),
        query_hints=_metadata_tuple(
            mapping=_QUERY_HINTS,
            case_id=eval_case.id,
            field="query_hints",
        ),
        safety_notes=_metadata_tuple(
            mapping=_SAFETY_NOTES,
            case_id=eval_case.id,
            field="safety_notes",
        ),
        next_action=_plan_next_action(eval_case),
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
        msg = f"QA brain retrieval plan is missing {field} metadata for {case_id}"
        raise QaBrainRetrievalPlanError(msg) from exc


def _metadata_category(
    *,
    mapping: Mapping[QaBrainEvalSliceId, QaBrainRetrievalCategory],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> QaBrainRetrievalCategory:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain retrieval plan is missing {field} metadata for {case_id}"
        raise QaBrainRetrievalPlanError(msg) from exc


def _metadata_tuple(
    *,
    mapping: Mapping[QaBrainEvalSliceId, tuple[str, ...]],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> tuple[str, ...]:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain retrieval plan is missing {field} metadata for {case_id}"
        raise QaBrainRetrievalPlanError(msg) from exc


def _plan_next_action(eval_case: QaBrainEvalCase) -> str:
    if eval_case.readiness == "ready":
        return f"Use value-free local evidence for {eval_case.label} retrieval design."
    if eval_case.readiness == "attention":
        return (
            f"Repair invalid or unsafe local evidence before {eval_case.label} retrieval indexing."
        )
    return f"Add value-free local evidence before {eval_case.label} retrieval indexing."


def _next_actions(
    retrieval_plans: tuple[QaBrainRetrievalPlanRow, ...],
) -> tuple[QaBrainRetrievalPlanNextAction, ...]:
    actions: list[QaBrainRetrievalPlanNextAction] = []
    for plan in retrieval_plans:
        if plan.readiness == "ready":
            continue
        priority: QaBrainNextActionPriority = (
            "high" if plan.readiness == "attention" else "medium"
        )
        actions.append(
            QaBrainRetrievalPlanNextAction(
                priority=priority,
                action=plan.next_action,
                case_ids=(plan.case_id,),
            )
        )
    return tuple(actions)


def _summary(
    *,
    retrieval_plans: tuple[QaBrainRetrievalPlanRow, ...],
    next_actions: tuple[QaBrainRetrievalPlanNextAction, ...],
) -> QaBrainRetrievalPlanSummary:
    counts = _plan_counts(retrieval_plans)
    return QaBrainRetrievalPlanSummary(
        status=_status(counts=counts, total=len(retrieval_plans)),
        plans_total=len(retrieval_plans),
        plans_ready=counts.ready,
        plans_missing=counts.missing,
        plans_attention=counts.attention,
        next_actions_total=len(next_actions),
    )


def _plan_counts(retrieval_plans: tuple[QaBrainRetrievalPlanRow, ...]) -> _PlanCounts:
    return _PlanCounts(
        ready=sum(1 for plan in retrieval_plans if plan.readiness == "ready"),
        missing=sum(1 for plan in retrieval_plans if plan.readiness == "missing"),
        attention=sum(1 for plan in retrieval_plans if plan.readiness == "attention"),
    )


def _status(*, counts: _PlanCounts, total: int) -> QaBrainRetrievalPlanStatus:
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
