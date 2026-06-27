"""Deterministic local QA brain model-packaging plan reports."""

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
from entroping.core.qa_brain_fine_tune_readiness import (
    QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessRow,
    build_qa_brain_fine_tune_readiness,
)
from entroping.core.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION: Final = (
    "entroping.qa-brain-model-packaging-plan.v1"
)

QaBrainModelPackagingPlanOutput = Literal["md", "json"]
QaBrainModelPackagingPlanStatus = Literal["ready", "partial", "insufficient"]
QaBrainModelPackagingStage = Literal[
    "packaging_ready",
    "needs_readiness_evidence",
    "needs_boundary_repair",
]
QaBrainDeploymentMode = Literal["hosted", "local", "enterprise"]

_DEFAULT_OUTPUTS: Final[dict[QaBrainModelPackagingPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-model-packaging-plan.md",
    "json": Path("reports") / "qa-brain-model-packaging-plan.json",
}

_PACKAGING_STAGES: Final[dict[QaBrainEvalCaseReadiness, QaBrainModelPackagingStage]] = {
    "ready": "packaging_ready",
    "missing": "needs_readiness_evidence",
    "attention": "needs_boundary_repair",
}

_DEPLOYMENT_MODES: Final[
    dict[QaBrainEvalSliceId, tuple[QaBrainDeploymentMode, ...]]
] = {
    "weak_test_detection": ("hosted", "local", "enterprise"),
    "missing_gate_discovery": ("hosted", "local", "enterprise"),
    "unsafe_generated_hurl": ("hosted", "local", "enterprise"),
    "bogus_evidence": ("hosted", "local", "enterprise"),
    "redaction_mistakes": ("hosted", "local", "enterprise"),
    "api_drift_reasoning": ("hosted", "local", "enterprise"),
    "mutation_fuzz_readiness": ("hosted", "local", "enterprise"),
    "cross_surface_handoff_quality": ("hosted", "local", "enterprise"),
}

_ENDPOINT_BOUNDARIES: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "OpenAI-compatible endpoint planning only; this report does not start a "
        "server, gateway, hosted endpoint, SDK adapter, or inference process."
    )
    for eval_id in _DEPLOYMENT_MODES
}

_LITELLM_ROUTING_BOUNDARIES: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "Future routing must stay behind LiteLLM or an OpenAI-compatible surface; "
        "this packet does not change LiteLLM configuration or provider selection."
    )
    for eval_id in _DEPLOYMENT_MODES
}

_ARTIFACT_BOUNDARIES: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "No model weights, adapters, containers, datasets, embeddings, vector "
        "indexes, prompt transcripts, eval outputs, or provider artifacts are "
        "produced by this report."
    )
    for eval_id in _DEPLOYMENT_MODES
}

_ACCESS_CONTROL_AUDIT: Final[dict[QaBrainEvalSliceId, str]] = {
    eval_id: (
        "Hosted, local, and enterprise packaging would need explicit access "
        "control, audit logging, retention, and tenant-boundary evidence before "
        "implementation."
    )
    for eval_id in _DEPLOYMENT_MODES
}


class QaBrainModelPackagingPlanError(ValueError):
    """Raised when a QA brain model-packaging plan cannot be generated safely."""


class QaBrainModelPackagingPlanSummary(BaseModel):
    """Aggregate QA brain model-packaging plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainModelPackagingPlanStatus
    plans_total: int = Field(ge=0)
    plans_ready: int = Field(ge=0)
    plans_missing: int = Field(ge=0)
    plans_attention: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainModelPackagingPlanRow(BaseModel):
    """One deterministic future QA brain model-packaging plan row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainEvalCaseReadiness
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    packaging_stage: QaBrainModelPackagingStage
    endpoint_boundary: str
    litellm_routing_boundary: str
    deployment_modes: tuple[QaBrainDeploymentMode, ...]
    artifact_boundary: str
    access_control_audit: str
    blockers: tuple[str, ...] = ()
    next_action: str


class QaBrainModelPackagingPlanNextAction(BaseModel):
    """Action needed before future QA brain model packaging."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainModelPackagingPlanPacket(BaseModel):
    """Schema-versioned local QA brain model-packaging plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-model-packaging-plan.v1"] = (
        QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    fine_tune_readiness_schema_version: Literal[
        "entroping.qa-brain-fine-tune-readiness.v1"
    ]
    summary: QaBrainModelPackagingPlanSummary
    packaging_plans: tuple[QaBrainModelPackagingPlanRow, ...]
    next_actions: tuple[QaBrainModelPackagingPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainModelPackagingPlanResult:
    """Result of writing one QA brain model-packaging plan packet."""

    output_path: Path
    packet: QaBrainModelPackagingPlanPacket


@dataclass(frozen=True, slots=True)
class _PlanCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_model_packaging_plan_report(
    *,
    project_root: Path,
    output: QaBrainModelPackagingPlanOutput,
    output_path: Path | None = None,
) -> QaBrainModelPackagingPlanResult:
    """Write a deterministic local QA brain model-packaging plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-model-packaging-plan output: {output}"
        raise QaBrainModelPackagingPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_model_packaging_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "QA brain model packaging plan contains secret-like content"
        raise QaBrainModelPackagingPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain model packaging plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainModelPackagingPlanError(str(exc)) from exc
    return QaBrainModelPackagingPlanResult(output_path=written, packet=packet)


def build_qa_brain_model_packaging_plan(
    *,
    project_root: Path,
) -> QaBrainModelPackagingPlanPacket:
    """Build model-packaging plan metadata from fine-tune readiness metadata."""

    root = project_root.expanduser().resolve()
    try:
        readiness = build_qa_brain_fine_tune_readiness(project_root=root)
    except QaBrainFineTuneReadinessError as exc:
        raise QaBrainModelPackagingPlanError(str(exc)) from exc
    packaging_plans = tuple(_row_from_readiness(row) for row in readiness.readiness_rows)
    next_actions = _next_actions(packaging_plans)
    packet = QaBrainModelPackagingPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        fine_tune_readiness_schema_version=QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
        summary=_summary(packaging_plans=packaging_plans, next_actions=next_actions),
        packaging_plans=packaging_plans,
        next_actions=next_actions,
    )
    if contains_unredacted_evidence_secret(packet.model_dump_json()):
        msg = "QA brain model packaging plan contains secret-like content"
        raise QaBrainModelPackagingPlanError(msg)
    return packet


def render_qa_brain_model_packaging_plan_markdown(
    packet: QaBrainModelPackagingPlanPacket,
) -> str:
    """Render a human-readable, value-free QA brain model-packaging plan."""

    lines = [
        "# Entroping QA Brain Model Packaging Plan",
        "",
        "Deterministic local planning metadata for future Entroping QA Brain Pro "
        "hosted, local, and enterprise model packaging. This report does not "
        "execute Hurl, run tests, call providers, start an endpoint, implement a "
        "gateway, package models, build containers, export datasets, train or "
        "fine-tune models, create embeddings, use a vector database, retrieve "
        "documents, execute prompts, upload artifacts, parse traffic state, run "
        "mutations, or render raw report contents.",
        "",
        "## Summary",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Generated at: `{_inline_code(packet.generated_at)}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Fine-tune readiness schema: "
        f"`{packet.fine_tune_readiness_schema_version}`",
        "- Packaging plans: "
        f"`{packet.summary.plans_ready}/{packet.summary.plans_total}` ready, "
        f"`{packet.summary.plans_missing}` missing, "
        f"`{packet.summary.plans_attention}` attention",
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Packaging Plans",
        "",
        "| ID | Label | Readiness | Stage | Source IDs | Source Paths | "
        "Endpoint Boundary | LiteLLM Routing | Deployment Modes | "
        "Artifact Boundary | Access Control And Audit | Blockers | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in packet.packaging_plans:
        lines.append(
            "| "
            f"{_markdown_cell(row.case_id)} | "
            f"{_markdown_cell(row.label)} | "
            f"{_markdown_cell(row.readiness)} | "
            f"{_markdown_cell(row.packaging_stage)} | "
            f"{_markdown_cell(', '.join(row.source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(row.source_paths) or 'n/a')} | "
            f"{_markdown_cell(row.endpoint_boundary)} | "
            f"{_markdown_cell(row.litellm_routing_boundary)} | "
            f"{_markdown_cell(', '.join(row.deployment_modes))} | "
            f"{_markdown_cell(row.artifact_boundary)} | "
            f"{_markdown_cell(row.access_control_audit)} | "
            f"{_markdown_cell('; '.join(row.blockers) or 'none')} | "
            f"{_markdown_cell(row.next_action)} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain model-packaging plan actions are currently needed.")
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
    packet: QaBrainModelPackagingPlanPacket,
    *,
    output: QaBrainModelPackagingPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_model_packaging_plan_markdown(packet)


def _row_from_readiness(
    row: QaBrainFineTuneReadinessRow,
) -> QaBrainModelPackagingPlanRow:
    return QaBrainModelPackagingPlanRow(
        case_id=row.case_id,
        label=row.label,
        readiness=row.readiness,
        source_ids=row.source_ids,
        source_paths=row.source_paths,
        packaging_stage=_packaging_stage(row),
        endpoint_boundary=_metadata_by_case(
            mapping=_ENDPOINT_BOUNDARIES,
            case_id=row.case_id,
            field="endpoint_boundary",
        ),
        litellm_routing_boundary=_metadata_by_case(
            mapping=_LITELLM_ROUTING_BOUNDARIES,
            case_id=row.case_id,
            field="litellm_routing_boundary",
        ),
        deployment_modes=_metadata_by_case(
            mapping=_DEPLOYMENT_MODES,
            case_id=row.case_id,
            field="deployment_modes",
        ),
        artifact_boundary=_metadata_by_case(
            mapping=_ARTIFACT_BOUNDARIES,
            case_id=row.case_id,
            field="artifact_boundary",
        ),
        access_control_audit=_metadata_by_case(
            mapping=_ACCESS_CONTROL_AUDIT,
            case_id=row.case_id,
            field="access_control_audit",
        ),
        blockers=_blockers(row),
        next_action=_plan_next_action(row),
    )


def _packaging_stage(row: QaBrainFineTuneReadinessRow) -> QaBrainModelPackagingStage:
    if row.readiness == "ready" and row.blockers:
        return "needs_boundary_repair"
    return _metadata_by_readiness(
        mapping=_PACKAGING_STAGES,
        readiness=row.readiness,
        field="packaging_stage",
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
        msg = f"QA brain model packaging plan is missing {field} metadata for {readiness}"
        raise QaBrainModelPackagingPlanError(msg) from exc


def _metadata_by_case[T](
    *,
    mapping: Mapping[QaBrainEvalSliceId, T],
    case_id: QaBrainEvalSliceId,
    field: str,
) -> T:
    try:
        return mapping[case_id]
    except KeyError as exc:
        msg = f"QA brain model packaging plan is missing {field} metadata for {case_id}"
        raise QaBrainModelPackagingPlanError(msg) from exc


def _blockers(row: QaBrainFineTuneReadinessRow) -> tuple[str, ...]:
    blockers = list(row.blockers)
    if row.readiness == "missing":
        blockers.append(
            "Add fine-tune readiness evidence before model packaging design."
        )
    elif row.readiness == "attention":
        blockers.append(
            "Repair fine-tune readiness evidence before model packaging design."
        )
    return tuple(blockers)


def _plan_next_action(row: QaBrainFineTuneReadinessRow) -> str:
    if row.readiness == "ready" and not row.blockers:
        return (
            f"Use {row.label} readiness metadata for future hosted, local, and "
            "enterprise model-packaging design without producing model artifacts."
        )
    if row.readiness == "attention":
        return (
            f"Repair {row.label} readiness evidence before future model-packaging "
            "design."
        )
    if row.readiness == "missing":
        return (
            f"Add {row.label} readiness evidence before future model-packaging "
            "design."
        )
    return f"Resolve {row.label} blockers before future model-packaging design."


def _next_actions(
    packaging_plans: tuple[QaBrainModelPackagingPlanRow, ...],
) -> tuple[QaBrainModelPackagingPlanNextAction, ...]:
    actions: list[QaBrainModelPackagingPlanNextAction] = []
    seen_case_ids: set[QaBrainEvalSliceId] = set()
    for row in packaging_plans:
        if row.readiness == "ready" and not row.blockers:
            continue
        if row.case_id in seen_case_ids:
            continue
        seen_case_ids.add(row.case_id)
        priority: QaBrainNextActionPriority = (
            "high" if row.readiness == "attention" else "medium"
        )
        actions.append(
            QaBrainModelPackagingPlanNextAction(
                priority=priority,
                action=row.next_action,
                case_ids=(row.case_id,),
            )
        )
    return tuple(actions)


def _summary(
    *,
    packaging_plans: tuple[QaBrainModelPackagingPlanRow, ...],
    next_actions: tuple[QaBrainModelPackagingPlanNextAction, ...],
) -> QaBrainModelPackagingPlanSummary:
    counts = _plan_counts(packaging_plans)
    blockers_total = len(
        {blocker for row in packaging_plans for blocker in row.blockers}
    )
    return QaBrainModelPackagingPlanSummary(
        status=_status(
            counts=counts,
            total=len(packaging_plans),
            blockers_total=blockers_total,
        ),
        plans_total=len(packaging_plans),
        plans_ready=counts.ready,
        plans_missing=counts.missing,
        plans_attention=counts.attention,
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _plan_counts(
    packaging_plans: tuple[QaBrainModelPackagingPlanRow, ...],
) -> _PlanCounts:
    return _PlanCounts(
        ready=sum(1 for row in packaging_plans if row.readiness == "ready"),
        missing=sum(1 for row in packaging_plans if row.readiness == "missing"),
        attention=sum(1 for row in packaging_plans if row.readiness == "attention"),
    )


def _status(
    *,
    counts: _PlanCounts,
    total: int,
    blockers_total: int,
) -> QaBrainModelPackagingPlanStatus:
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
