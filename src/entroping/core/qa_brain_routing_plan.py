"""Deterministic local QA brain routing-plan reports."""

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
from entroping.core.qa_brain_model_packaging_plan import (
    QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION,
    QaBrainDeploymentMode,
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanRow,
    QaBrainModelPackagingStage,
    build_qa_brain_model_packaging_plan,
)
from entroping.core.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION: Final = "entroping.qa-brain-routing-plan.v1"

QaBrainRoutingPlanOutput = Literal["md", "json"]
QaBrainRoutingPlanStatus = Literal["ready", "partial", "insufficient"]
QaBrainRoutingStage = Literal[
    "routing_design_ready",
    "needs_packaging_evidence",
    "needs_boundary_repair",
]
QaBrainAllowedUseCase = Literal[
    "critique",
    "generation",
    "prioritization",
    "repair_proposals",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainRoutingPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-routing-plan.md",
    "json": Path("reports") / "qa-brain-routing-plan.json",
}

_ROUTING_STAGES: Final[dict[QaBrainModelPackagingStage, QaBrainRoutingStage]] = {
    "packaging_ready": "routing_design_ready",
    "needs_readiness_evidence": "needs_packaging_evidence",
    "needs_boundary_repair": "needs_boundary_repair",
}

_ALLOWED_USE_CASES: Final[
    dict[QaBrainEvalSliceId, tuple[QaBrainAllowedUseCase, ...]]
] = {
    "weak_test_detection": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "missing_gate_discovery": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "unsafe_generated_hurl": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "bogus_evidence": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "redaction_mistakes": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "api_drift_reasoning": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "mutation_fuzz_readiness": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
    "cross_surface_handoff_quality": (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ),
}

_FORBIDDEN_AUTHORITY: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "Future QA Brain routing can support critique, generation, "
        "prioritization, and repair proposals only; Hurl/QAnstitution remains "
        "the pass/fail authority for entroping run."
    )
    for eval_id in _ALLOWED_USE_CASES
}

_ACTION_PRIORITY_RANK: Final[dict[QaBrainNextActionPriority, int]] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


class QaBrainRoutingPlanError(ValueError):
    """Raised when a QA brain routing plan cannot be generated safely."""


class QaBrainRoutingPlanSummary(BaseModel):
    """Aggregate QA brain routing-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainRoutingPlanStatus
    routes_total: int = Field(ge=0)
    routes_ready: int = Field(ge=0)
    routes_missing: int = Field(ge=0)
    routes_attention: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainRoutingPlanRow(BaseModel):
    """One deterministic future QA brain routing-plan row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: Literal["ready", "missing", "attention"]
    packaging_stage: QaBrainModelPackagingStage
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    routing_stage: QaBrainRoutingStage
    litellm_boundary: str
    endpoint_boundary: str
    deployment_modes: tuple[QaBrainDeploymentMode, ...]
    allowed_use_cases: tuple[QaBrainAllowedUseCase, ...]
    forbidden_authority: str
    access_control_audit: str
    blockers: tuple[str, ...] = ()
    next_action: str


class QaBrainRoutingPlanNextAction(BaseModel):
    """Action needed before future QA brain routing design."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainRoutingPlanPacket(BaseModel):
    """Schema-versioned local QA brain routing-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-routing-plan.v1"] = (
        QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    model_packaging_plan_schema_version: Literal[
        "entroping.qa-brain-model-packaging-plan.v1"
    ]
    summary: QaBrainRoutingPlanSummary
    routing_plans: tuple[QaBrainRoutingPlanRow, ...]
    next_actions: tuple[QaBrainRoutingPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainRoutingPlanResult:
    """Result of writing one QA brain routing-plan packet."""

    output_path: Path
    packet: QaBrainRoutingPlanPacket


@dataclass(frozen=True, slots=True)
class _RouteCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_routing_plan_report(
    *,
    project_root: Path,
    output: QaBrainRoutingPlanOutput,
    output_path: Path | None = None,
) -> QaBrainRoutingPlanResult:
    """Write a deterministic local QA brain routing-plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-routing-plan output: {output}"
        raise QaBrainRoutingPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_routing_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain routing plan contains secret-like content"
        raise QaBrainRoutingPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain routing plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainRoutingPlanError(str(exc)) from exc
    return QaBrainRoutingPlanResult(output_path=written, packet=packet)


def build_qa_brain_routing_plan(*, project_root: Path) -> QaBrainRoutingPlanPacket:
    """Build routing-plan metadata from model-packaging plan metadata."""

    root = project_root.expanduser().resolve()
    try:
        packaging = build_qa_brain_model_packaging_plan(project_root=root)
    except QaBrainModelPackagingPlanError as exc:
        raise QaBrainRoutingPlanError(str(exc)) from exc
    routing_plans = tuple(_row_from_packaging(row) for row in packaging.packaging_plans)
    next_actions = _next_actions(routing_plans)
    packet = QaBrainRoutingPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        model_packaging_plan_schema_version=(
            QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION
        ),
        summary=_summary(routing_plans=routing_plans, next_actions=next_actions),
        routing_plans=routing_plans,
        next_actions=next_actions,
    )
    if contains_unredacted_evidence_secret(packet.model_dump_json()):
        msg = "QA brain routing plan contains secret-like content"
        raise QaBrainRoutingPlanError(msg)
    return packet


def render_qa_brain_routing_plan_markdown(packet: QaBrainRoutingPlanPacket) -> str:
    """Render a human-readable, value-free QA brain routing plan."""

    lines = [
        "# Entroping QA Brain Routing Plan",
        "",
        "Deterministic local planning metadata for future Entroping QA Brain Pro "
        "LiteLLM and OpenAI-compatible routing across hosted, local, and "
        "enterprise deployment modes. This report does not execute Hurl, run "
        "tests, call providers, read provider keys, change LiteLLM "
        "configuration, start endpoints, implement gateways, package models, "
        "build containers, export datasets, train or fine-tune models, create "
        "embeddings, use vector databases, retrieve documents, execute prompts, "
        "upload artifacts, parse traffic state, or render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Generated at: `{_inline_code(packet.generated_at)}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Model-packaging plan schema: "
        f"`{packet.model_packaging_plan_schema_version}`",
        "- Routing plans: "
        f"`{packet.summary.routes_ready}/{packet.summary.routes_total}` ready, "
        f"`{packet.summary.routes_missing}` missing, "
        f"`{packet.summary.routes_attention}` attention",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Routing Plans",
        "",
        "| ID | Label | Readiness | Packaging Stage | Routing Stage | "
        "Source IDs | Source Paths | LiteLLM Boundary | Endpoint Boundary | "
        "Deployment Modes | Allowed Use Cases | Forbidden Authority | "
        "Access Control And Audit | Blockers | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
        "--- | --- | --- |",
    ]
    for row in packet.routing_plans:
        lines.append(
            "| "
            f"{_markdown_cell(row.case_id)} | "
            f"{_markdown_cell(row.label)} | "
            f"{_markdown_cell(row.readiness)} | "
            f"{_markdown_cell(row.packaging_stage)} | "
            f"{_markdown_cell(row.routing_stage)} | "
            f"{_markdown_cell(', '.join(row.source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(row.source_paths) or 'n/a')} | "
            f"{_markdown_cell(row.litellm_boundary)} | "
            f"{_markdown_cell(row.endpoint_boundary)} | "
            f"{_markdown_cell(', '.join(row.deployment_modes))} | "
            f"{_markdown_cell(', '.join(row.allowed_use_cases))} | "
            f"{_markdown_cell(row.forbidden_authority)} | "
            f"{_markdown_cell(row.access_control_audit)} | "
            f"{_markdown_cell('; '.join(row.blockers) or 'none')} | "
            f"{_markdown_cell(row.next_action)} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain routing-plan actions are currently needed.")
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
    packet: QaBrainRoutingPlanPacket,
    *,
    output: QaBrainRoutingPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_routing_plan_markdown(packet)


def _row_from_packaging(row: QaBrainModelPackagingPlanRow) -> QaBrainRoutingPlanRow:
    routing_stage = _routing_stage(row)
    return QaBrainRoutingPlanRow(
        case_id=row.case_id,
        label=row.label,
        readiness=row.readiness,
        packaging_stage=row.packaging_stage,
        source_ids=row.source_ids,
        source_paths=row.source_paths,
        routing_stage=routing_stage,
        litellm_boundary=row.litellm_routing_boundary,
        endpoint_boundary=row.endpoint_boundary,
        deployment_modes=row.deployment_modes,
        allowed_use_cases=_metadata_by_case(
            mapping=_ALLOWED_USE_CASES,
            case_id=row.case_id,
            field="allowed_use_cases",
        ),
        forbidden_authority=_metadata_by_case(
            mapping=_FORBIDDEN_AUTHORITY,
            case_id=row.case_id,
            field="forbidden_authority",
        ),
        access_control_audit=row.access_control_audit,
        blockers=_blockers(row=row, routing_stage=routing_stage),
        next_action=_plan_next_action(row=row, routing_stage=routing_stage),
    )


def _routing_stage(row: QaBrainModelPackagingPlanRow) -> QaBrainRoutingStage:
    if row.packaging_stage == "packaging_ready" and row.blockers:
        return "needs_boundary_repair"
    return _metadata_by_stage(
        mapping=_ROUTING_STAGES,
        packaging_stage=row.packaging_stage,
        field="routing_stage",
    )


def _metadata_by_stage[T](
    *,
    mapping: Mapping[QaBrainModelPackagingStage, T],
    packaging_stage: QaBrainModelPackagingStage,
    field: str,
) -> T:
    try:
        return mapping[packaging_stage]
    except KeyError as exc:
        msg = (
            "QA brain routing plan is missing "
            f"{field} metadata for {packaging_stage}"
        )
        raise QaBrainRoutingPlanError(msg) from exc


def _metadata_by_case[T](
    *,
    mapping: Mapping[QaBrainEvalSliceId, T],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> T:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain routing plan is missing {field} metadata for {case_id}"
        raise QaBrainRoutingPlanError(msg) from exc


def _blockers(
    *,
    row: QaBrainModelPackagingPlanRow,
    routing_stage: QaBrainRoutingStage,
) -> tuple[str, ...]:
    blockers = list(row.blockers)
    if routing_stage == "needs_packaging_evidence":
        blockers.append("Add model-packaging evidence before routing design.")
    elif routing_stage == "needs_boundary_repair" and not row.blockers:
        blockers.append("Repair model-packaging boundaries before routing design.")
    return tuple(blockers)


def _plan_next_action(
    *,
    row: QaBrainModelPackagingPlanRow,
    routing_stage: QaBrainRoutingStage,
) -> str:
    if routing_stage == "routing_design_ready" and not row.blockers:
        return (
            f"Use {row.label} packaging metadata for future LiteLLM and "
            "OpenAI-compatible routing design without changing runtime "
            "configuration or calling providers."
        )
    if routing_stage == "needs_boundary_repair":
        return (
            f"Repair {row.label} model-packaging boundaries before future "
            "routing design."
        )
    if routing_stage == "needs_packaging_evidence":
        return (
            f"Add {row.label} model-packaging evidence before future routing "
            "design."
        )
    return f"Resolve {row.label} blockers before future routing design."


def _next_actions(
    routing_plans: tuple[QaBrainRoutingPlanRow, ...],
) -> tuple[QaBrainRoutingPlanNextAction, ...]:
    actions_by_case: dict[QaBrainEvalSliceId, QaBrainRoutingPlanNextAction] = {}
    case_order: list[QaBrainEvalSliceId] = []
    for row in routing_plans:
        if row.routing_stage == "routing_design_ready" and not row.blockers:
            continue
        priority: QaBrainNextActionPriority = (
            "high" if row.routing_stage == "needs_boundary_repair" else "medium"
        )
        action = QaBrainRoutingPlanNextAction(
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
    routing_plans: tuple[QaBrainRoutingPlanRow, ...],
    next_actions: tuple[QaBrainRoutingPlanNextAction, ...],
) -> QaBrainRoutingPlanSummary:
    counts = _route_counts(routing_plans)
    blockers_total = sum(len(row.blockers) for row in routing_plans)
    return QaBrainRoutingPlanSummary(
        status=_status(
            counts=counts,
            total=len(routing_plans),
            blockers_total=blockers_total,
        ),
        routes_total=len(routing_plans),
        routes_ready=counts.ready,
        routes_missing=counts.missing,
        routes_attention=counts.attention,
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _route_counts(
    routing_plans: tuple[QaBrainRoutingPlanRow, ...],
) -> _RouteCounts:
    return _RouteCounts(
        ready=sum(
            1 for row in routing_plans if row.routing_stage == "routing_design_ready"
        ),
        missing=sum(
            1 for row in routing_plans if row.routing_stage == "needs_packaging_evidence"
        ),
        attention=sum(
            1 for row in routing_plans if row.routing_stage == "needs_boundary_repair"
        ),
    )


def _status(
    *,
    counts: _RouteCounts,
    total: int,
    blockers_total: int,
) -> QaBrainRoutingPlanStatus:
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
