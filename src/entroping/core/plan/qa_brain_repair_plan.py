"""Deterministic local QA brain repair-plan reports."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal, cast

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
from entroping.core.plan.qa_brain_routing_plan import (
    QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
    QaBrainRepairAcceptanceGateId,
)
from entroping.core.plan.qa_brain_seed import QaBrainEvalSliceId, QaBrainNextActionPriority
from entroping.core.safe_write import SafeWriteError, safe_write_text

QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION: Final = "entroping.qa-brain-repair-plan.v1"

QaBrainRepairPlanOutput = Literal["md", "json"]
QaBrainRepairPlanStatus = Literal["ready", "partial", "insufficient"]
QaBrainRepairPlanReadiness = Literal["ready", "missing", "attention"]
QaBrainRepairIntent = Literal["generate", "repair", "review"]
QaBrainRepairProposalDryRunPrerequisiteStatus = Literal["ready", "partial", "missing"]
QaBrainRepairProposalDryRunGateStatus = Literal["ready", "missing"]
QaBrainRepairAcceptanceGateFamily = Literal[
    "parser",
    "hurl",
    "policy",
    "evidence",
    "redaction",
    "review",
]
QaBrainRepairAcceptanceReviewer = Literal["codex_or_human"]
QaBrainRepairPlanSourceState = EvidenceArtifactState
QaBrainRepairPlanSourceId = Literal[
    "test-quality-json",
    "mutation-readiness-json",
    "evidence-action-plan-json",
    "qa-brain-routing-plan-json",
    "evidence-index-json",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainRepairPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-repair-plan.md",
    "json": Path("reports") / "qa-brain-repair-plan.json",
}
_SOURCE_IDS: Final[tuple[QaBrainRepairPlanSourceId, ...]] = (
    "test-quality-json",
    "mutation-readiness-json",
    "evidence-action-plan-json",
    "qa-brain-routing-plan-json",
    "evidence-index-json",
)
_SOURCE_LABELS: Final[dict[QaBrainRepairPlanSourceId, str]] = {
    "test-quality-json": "Generated-Test Quality JSON",
    "mutation-readiness-json": "Mutation Readiness JSON",
    "evidence-action-plan-json": "Evidence Action Plan JSON",
    "qa-brain-routing-plan-json": "QA Brain Routing Plan JSON",
    "evidence-index-json": "Evidence Index JSON",
}
_SOURCE_PATHS: Final[dict[QaBrainRepairPlanSourceId, str]] = {
    "test-quality-json": "reports/test-quality.json",
    "mutation-readiness-json": "reports/mutation-readiness.json",
    "evidence-action-plan-json": "reports/evidence-action-plan.json",
    "qa-brain-routing-plan-json": "reports/qa-brain-routing-plan.json",
    "evidence-index-json": "reports/evidence-index.json",
}
_REPAIR_SOURCE_IDS: Final[
    dict[QaBrainEvalSliceId, tuple[QaBrainRepairPlanSourceId, ...]]
] = {
    "weak_test_detection": (
        "test-quality-json",
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
    ),
    "missing_gate_discovery": (
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ),
    "unsafe_generated_hurl": (
        "test-quality-json",
        "mutation-readiness-json",
        "qa-brain-routing-plan-json",
    ),
    "bogus_evidence": (
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ),
    "redaction_mistakes": (
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ),
    "api_drift_reasoning": (
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ),
    "mutation_fuzz_readiness": (
        "test-quality-json",
        "mutation-readiness-json",
        "qa-brain-routing-plan-json",
    ),
    "cross_surface_handoff_quality": (
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ),
}
_REPAIR_LABELS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": "Weak-test detection",
    "missing_gate_discovery": "Missing-gate discovery",
    "unsafe_generated_hurl": "Unsafe generated Hurl",
    "bogus_evidence": "Bogus evidence",
    "redaction_mistakes": "Redaction mistakes",
    "api_drift_reasoning": "API drift reasoning",
    "mutation_fuzz_readiness": "Mutation/fuzz readiness",
    "cross_surface_handoff_quality": "Cross-surface handoff quality",
}
_REPAIR_INTENTS: Final[dict[QaBrainEvalSliceId, QaBrainRepairIntent]] = {
    "weak_test_detection": "review",
    "missing_gate_discovery": "generate",
    "unsafe_generated_hurl": "repair",
    "bogus_evidence": "repair",
    "redaction_mistakes": "repair",
    "api_drift_reasoning": "review",
    "mutation_fuzz_readiness": "review",
    "cross_surface_handoff_quality": "review",
}
_READY_ACTIONS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": "Use quality and routing evidence to review weak generated tests.",
    "missing_gate_discovery": "Use action-plan and routing evidence to propose missing gates.",
    "unsafe_generated_hurl": "Use quality, mutation, and routing evidence to repair unsafe Hurl.",
    "bogus_evidence": "Use action-plan and evidence-index signals to repair bogus evidence.",
    "redaction_mistakes": "Use action-plan and evidence-index signals to repair redaction gaps.",
    "api_drift_reasoning": (
        "Use action-plan and evidence-index signals to review API drift repairs."
    ),
    "mutation_fuzz_readiness": (
        "Use mutation-readiness signals to review mutation/fuzz repair needs."
    ),
    "cross_surface_handoff_quality": (
        "Use evidence-index and action-plan signals to review handoff repairs."
    ),
}
_GATE_ID_RE: Final = re.compile(
    "^("
    + "parser_validation|hurl_execution|qanstitution_governance|deterministic_evidence|"
    + "secret_redaction|codex_human_review"
    + ")$"
)
_NON_REDACTION_GATE_FAMILIES: Final[
    dict[QaBrainRepairAcceptanceGateId, QaBrainRepairAcceptanceGateFamily]
] = {
    "parser_validation": "parser",
    "hurl_execution": "hurl",
    "qanstitution_governance": "policy",
    "deterministic_evidence": "evidence",
    "codex_human_review": "review",
}
_NON_REDACTION_FORBIDDEN_SHORTCUTS: Final[dict[QaBrainRepairAcceptanceGateId, str]] = {
    "parser_validation": (
        "Do not accept provider output that skips parser-backed Hurl validation."
    ),
    "hurl_execution": (
        "Do not replace Hurl execution with Python HTTP clients or model claims."
    ),
    "qanstitution_governance": (
        "Do not bypass QAnstitution gates or weaken policy to pass repair."
    ),
    "deterministic_evidence": (
        "Do not invent evidence IDs, raw fields, or unverified report contents."
    ),
    "codex_human_review": (
        "Do not self-merge repair proposals without Codex/human review."
    ),
}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)


class QaBrainRepairPlanError(ValueError):
    """Raised when a QA brain repair plan cannot be generated safely."""


class QaBrainRepairPlanSummary(BaseModel):
    """Aggregate QA brain repair-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainRepairPlanStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    repair_plans_total: int = Field(ge=0)
    repair_plans_ready: int = Field(ge=0)
    repair_plans_missing: int = Field(ge=0)
    repair_plans_attention: int = Field(ge=0)
    blockers_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainRepairPlanSource(BaseModel):
    """One local value-free source row for repair-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    id: QaBrainRepairPlanSourceId
    label: str
    path: str
    state: QaBrainRepairPlanSourceState
    schema_version: str | None = None
    summary: str


class QaBrainRepairPlanRow(BaseModel):
    """One deterministic future QA brain repair-plan row."""

    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainRepairPlanReadiness
    repair_intent: QaBrainRepairIntent
    source_ids: tuple[QaBrainRepairPlanSourceId, ...] = ()
    source_paths: tuple[str, ...] = ()
    acceptance_gate_ids: tuple[QaBrainRepairAcceptanceGateId, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str


class QaBrainRepairPlanNextAction(BaseModel):
    """Action needed before future QA brain repair proposals."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainRepairProposalDryRunArtifactStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: QaBrainRepairPlanSourceId
    status: QaBrainRepairPlanSourceState


class QaBrainRepairProposalDryRunChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    prerequisite_status: QaBrainRepairProposalDryRunPrerequisiteStatus
    readiness: QaBrainRepairPlanReadiness
    artifact_statuses: tuple[QaBrainRepairProposalDryRunArtifactStatus, ...]
    acceptance_gate_status: QaBrainRepairProposalDryRunGateStatus
    next_action_label: str


class QaBrainRepairAcceptanceChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: QaBrainEvalSliceId
    gate_id: QaBrainRepairAcceptanceGateId
    gate_family: QaBrainRepairAcceptanceGateFamily
    source_evidence_ids: tuple[QaBrainRepairPlanSourceId, ...]
    required_reviewer: QaBrainRepairAcceptanceReviewer
    forbidden_shortcut_notes: tuple[str, ...]


class QaBrainRepairPlanPacket(BaseModel):
    """Schema-versioned local QA brain repair-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-repair-plan.v1"] = (
        QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    routing_plan_schema_version: Literal["entroping.qa-brain-routing-plan.v1"]
    summary: QaBrainRepairPlanSummary
    sources: tuple[QaBrainRepairPlanSource, ...]
    repair_plans: tuple[QaBrainRepairPlanRow, ...]
    repair_proposal_dry_run_checklist: tuple[
        QaBrainRepairProposalDryRunChecklistItem, ...
    ] = ()
    repair_acceptance_checklist: tuple[QaBrainRepairAcceptanceChecklistItem, ...] = ()
    next_actions: tuple[QaBrainRepairPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainRepairPlanResult:
    """Result of writing one QA brain repair-plan packet."""

    output_path: Path
    packet: QaBrainRepairPlanPacket


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _RepairCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_repair_plan_report(
    *,
    project_root: Path,
    output: QaBrainRepairPlanOutput,
    output_path: Path | None = None,
) -> QaBrainRepairPlanResult:
    """Write a deterministic local QA brain repair-plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-repair-plan output: {output}"
        raise QaBrainRepairPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_repair_plan(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_packet_secret_like_value(content):
        msg = "QA brain repair plan contains secret-like content"
        raise QaBrainRepairPlanError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="QA brain repair plan",
            root=root,
        )
    except SafeWriteError as exc:
        raise QaBrainRepairPlanError(str(exc)) from exc
    return QaBrainRepairPlanResult(output_path=written, packet=packet)


def build_qa_brain_repair_plan(*, project_root: Path) -> QaBrainRepairPlanPacket:
    """Build repair-plan metadata from local value-free source evidence."""

    root = project_root.expanduser().resolve()
    sources, gates_by_case = _sources_and_routing_gates(root=root)
    repair_plans = _repair_plan_rows(sources=sources, gates_by_case=gates_by_case)
    checklist = _repair_proposal_dry_run_checklist(
        sources=sources,
        repair_plans=repair_plans,
    )
    acceptance_checklist = _repair_acceptance_checklist(repair_plans)
    next_actions = _next_actions(repair_plans)
    packet = QaBrainRepairPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        routing_plan_schema_version=QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
        summary=_summary(
            sources=sources,
            repair_plans=repair_plans,
            next_actions=next_actions,
        ),
        sources=sources,
        repair_plans=repair_plans,
        repair_proposal_dry_run_checklist=checklist,
        repair_acceptance_checklist=acceptance_checklist,
        next_actions=next_actions,
    )
    if _contains_unredacted_packet_secret_like_value(packet.model_dump_json()):
        msg = "QA brain repair plan contains secret-like content"
        raise QaBrainRepairPlanError(msg)
    return packet


def render_qa_brain_repair_plan_markdown(packet: QaBrainRepairPlanPacket) -> str:
    """Render a human-readable, value-free QA brain repair plan."""

    lines = [
        "# Entroping QA Brain Repair Plan",
        "",
        (
            "Deterministic local planning metadata for future Entroping QA Brain "
            + "repair proposals. This report does not execute Hurl, run tests, run "
            + "mutations or fuzzers, call providers, invoke models, change LiteLLM "
            + "configuration, generate or repair tests, mutate source Hurl or policy, "
            + "upload artifacts, create embeddings, retrieve documents, fine-tune "
            + "models, export datasets, mutate tickets or chat, or render raw report "
            + "contents."
        ),
        "",
        "## Summary",
        "",
        f"- Schema: `{packet.schema_version}`",
        f"- Status: `{packet.summary.status}`",
        f"- Generated at: `{_inline_code(packet.generated_at)}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Routing plan schema: `{packet.routing_plan_schema_version}`",
        (
            f"- Sources: `{packet.summary.sources_present}/"
            + f"{packet.summary.sources_total}` present, "
            + f"`{packet.summary.sources_missing}` missing, "
            + f"`{packet.summary.sources_invalid}` invalid, "
            + f"`{packet.summary.sources_unsafe}` unsafe"
        ),
        (
            f"- Repair plans: `{packet.summary.repair_plans_ready}/"
            + f"{packet.summary.repair_plans_total}` ready, "
            + f"`{packet.summary.repair_plans_missing}` missing, "
            + f"`{packet.summary.repair_plans_attention}` attention"
        ),
        f"- Blockers: `{packet.summary.blockers_total}`",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Repair Plans",
        "",
        "| ID | Label | Readiness | Intent | Sources | Acceptance Gates | Blockers | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in packet.repair_plans:
        lines.append(
            "| "
            f"{_markdown_cell(row.case_id)} | "
            f"{_markdown_cell(row.label)} | "
            f"{_markdown_cell(row.readiness)} | "
            f"{_markdown_cell(row.repair_intent)} | "
            f"{_markdown_cell(', '.join(row.source_ids) or 'n/a')} | "
            f"{_markdown_cell(', '.join(row.acceptance_gate_ids) or 'n/a')} | "
            f"{_markdown_cell('; '.join(row.blockers) or 'none')} | "
            f"{_markdown_cell(row.next_action)} |"
        )
    lines.extend(
        [
            "",
            "## Repair Proposal Dry-Run Checklist",
            "",
            "| ID | Status | Readiness | Artifacts | Gates | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for dry_run_item in packet.repair_proposal_dry_run_checklist:
        lines.append(
            "| "
            f"{_markdown_cell(dry_run_item.case_id)} | "
            f"{_markdown_cell(dry_run_item.prerequisite_status)} | "
            f"{_markdown_cell(dry_run_item.readiness)} | "
            f"{_markdown_cell(_artifact_statuses_label(dry_run_item.artifact_statuses))} | "
            f"{_markdown_cell(dry_run_item.acceptance_gate_status)} | "
            f"{_markdown_cell(dry_run_item.next_action_label)} |"
        )
    lines.extend(
        [
            "",
            "## Repair Acceptance Checklist",
            "",
        ]
    )
    if not packet.repair_acceptance_checklist:
        lines.append(
            "No repair acceptance gates are available until routing-plan inputs are present."
        )
    else:
        lines.extend(
            [
                "| Case | Gate | Family | Source Evidence | Reviewer | Forbidden Shortcuts |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for acceptance_item in packet.repair_acceptance_checklist:
            lines.append(
                "| "
                f"{_markdown_cell(acceptance_item.case_id)} | "
                f"{_markdown_cell(acceptance_item.gate_id)} | "
                f"{_markdown_cell(acceptance_item.gate_family)} | "
                f"{_markdown_cell(', '.join(acceptance_item.source_evidence_ids) or 'n/a')} | "
                f"{_markdown_cell(acceptance_item.required_reviewer)} | "
                f"{_markdown_cell('; '.join(acceptance_item.forbidden_shortcut_notes))} |"
            )
    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| ID | Label | State | Path | Schema | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.id)} | "
            f"{_markdown_cell(source.label)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(source.schema_version or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain repair-plan actions are currently needed.")
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
    packet: QaBrainRepairPlanPacket,
    *,
    output: QaBrainRepairPlanOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_qa_brain_repair_plan_markdown(packet)


def _sources_and_routing_gates(
    *,
    root: Path,
) -> tuple[
    tuple[QaBrainRepairPlanSource, ...],
    dict[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]],
]:
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    sources: list[QaBrainRepairPlanSource] = []
    gates_by_case: dict[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]] = {}
    for source_id in _SOURCE_IDS:
        if source_id == "qa-brain-routing-plan-json":
            source, gates_by_case = _routing_plan_source(root=root)
            sources.append(source)
        else:
            sources.append(_indexed_source(source_id, indexed.get(source_id)))
    return tuple(sources), gates_by_case


def _indexed_source(
    source_id: QaBrainRepairPlanSourceId,
    artifact: LocalEvidenceArtifact | None,
) -> QaBrainRepairPlanSource:
    if artifact is None:
        return _source(
            source_id=source_id,
            state="missing",
            schema_version=None,
            summary="Artifact missing.",
        )
    return _source(
        source_id=source_id,
        state=artifact.state,
        schema_version=artifact.schema_version,
        summary=artifact.summary,
    )


def _routing_plan_source(
    *,
    root: Path,
) -> tuple[
    QaBrainRepairPlanSource,
    dict[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]],
]:
    path = root / _SOURCE_PATHS["qa-brain-routing-plan-json"]
    if not path.exists() and not path.is_symlink():
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state="missing",
                schema_version=None,
                summary="Artifact missing.",
            ),
            {},
        )
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(path, root=root)
    if raw_bytes is None:
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state=_load_failure_state(load_error),
                schema_version=None,
                summary=safe_evidence_text(load_error or "unreadable"),
            ),
            {},
        )
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state="invalid",
                schema_version=None,
                summary="invalid JSON",
            ),
            {},
        )
    if contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text)):
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state="unsafe",
                schema_version=None,
                summary="secret-like content",
            ),
            {},
        )
    document = _parse_json_object(raw_text)
    if document is None:
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state="invalid",
                schema_version=None,
                summary="invalid JSON",
            ),
            {},
        )
    if document.get("schema_version") != QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION:
        return (
            _source(
                source_id="qa-brain-routing-plan-json",
                state="invalid",
                schema_version=None,
                summary="schema mismatch",
            ),
            {},
        )
    return (
        _source(
            source_id="qa-brain-routing-plan-json",
            state="present",
            schema_version=QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
            summary=_routing_summary(document),
        ),
        _routing_gates_by_case(document),
    )


def _source(
    *,
    source_id: QaBrainRepairPlanSourceId,
    state: QaBrainRepairPlanSourceState,
    schema_version: str | None,
    summary: str,
) -> QaBrainRepairPlanSource:
    return QaBrainRepairPlanSource(
        id=source_id,
        label=_SOURCE_LABELS[source_id],
        path=_SOURCE_PATHS[source_id],
        state=state,
        schema_version=schema_version,
        summary=safe_evidence_text(summary) or "unknown",
    )


def _repair_plan_rows(
    *,
    sources: tuple[QaBrainRepairPlanSource, ...],
    gates_by_case: Mapping[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]],
) -> tuple[QaBrainRepairPlanRow, ...]:
    sources_by_id = {source.id: source for source in sources}
    rows: list[QaBrainRepairPlanRow] = []
    for case_id, source_ids in _REPAIR_SOURCE_IDS.items():
        relevant = tuple(
            source for source_id in source_ids if (source := sources_by_id.get(source_id))
        )
        problem_sources = tuple(
            source for source in relevant if source.state in {"invalid", "unsafe"}
        )
        present_sources = tuple(source for source in relevant if source.state == "present")
        non_routing_present = tuple(
            source for source in present_sources if source.id != "qa-brain-routing-plan-json"
        )
        gate_ids = gates_by_case.get(case_id, ())
        blockers = _blockers(
            problem_sources=problem_sources,
            non_routing_present=non_routing_present,
            gate_ids=gate_ids,
        )
        readiness = _readiness(problem_sources=problem_sources, blockers=blockers)
        ready_sources = present_sources + problem_sources
        rows.append(
            QaBrainRepairPlanRow(
                case_id=case_id,
                label=_REPAIR_LABELS[case_id],
                readiness=readiness,
                repair_intent=_REPAIR_INTENTS[case_id],
                source_ids=tuple(source.id for source in ready_sources),
                source_paths=tuple(source.path for source in ready_sources),
                acceptance_gate_ids=gate_ids,
                blockers=blockers,
                next_action=_next_action(case_id=case_id, readiness=readiness),
            )
        )
    return tuple(rows)


def _blockers(
    *,
    problem_sources: tuple[QaBrainRepairPlanSource, ...],
    non_routing_present: tuple[QaBrainRepairPlanSource, ...],
    gate_ids: tuple[QaBrainRepairAcceptanceGateId, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if problem_sources:
        blockers.append("Repair invalid or unsafe local evidence before repair proposals.")
    if not non_routing_present:
        blockers.append("Add value-free local evidence before repair proposals.")
    if not gate_ids:
        blockers.append("Generate QA brain routing-plan acceptance gates before repair proposals.")
    return tuple(blockers)


def _readiness(
    *,
    problem_sources: tuple[QaBrainRepairPlanSource, ...],
    blockers: tuple[str, ...],
) -> QaBrainRepairPlanReadiness:
    if problem_sources:
        return "attention"
    if blockers:
        return "missing"
    return "ready"


def _next_action(
    *,
    case_id: QaBrainEvalSliceId,
    readiness: QaBrainRepairPlanReadiness,
) -> str:
    if readiness == "ready":
        return _READY_ACTIONS[case_id]
    if readiness == "attention":
        return (
            f"Repair invalid or unsafe local evidence for {_REPAIR_LABELS[case_id]} "
            + "before future QA Brain repair proposals."
        )
    return (
        f"Add value-free evidence and routing acceptance gates for "
        f"{_REPAIR_LABELS[case_id]} before future QA Brain repair proposals."
    )


def _next_actions(
    repair_plans: tuple[QaBrainRepairPlanRow, ...],
) -> tuple[QaBrainRepairPlanNextAction, ...]:
    actions: list[QaBrainRepairPlanNextAction] = []
    for row in repair_plans:
        if row.readiness == "ready":
            continue
        priority: QaBrainNextActionPriority = (
            "high" if row.readiness == "attention" else "medium"
        )
        action = QaBrainRepairPlanNextAction(
            priority=priority,
            action=row.next_action,
            case_ids=(row.case_id,),
        )
        actions.append(action)
    return tuple(actions)


def _repair_proposal_dry_run_checklist(
    *,
    sources: tuple[QaBrainRepairPlanSource, ...],
    repair_plans: tuple[QaBrainRepairPlanRow, ...],
) -> tuple[QaBrainRepairProposalDryRunChecklistItem, ...]:
    sources_by_id: dict[QaBrainRepairPlanSourceId, QaBrainRepairPlanSource] = {
        source.id: source for source in sources
    }
    return tuple(
        _repair_proposal_dry_run_checklist_item(row=row, sources_by_id=sources_by_id)
        for row in repair_plans
    )


def _repair_proposal_dry_run_checklist_item(
    *,
    row: QaBrainRepairPlanRow,
    sources_by_id: Mapping[QaBrainRepairPlanSourceId, QaBrainRepairPlanSource],
) -> QaBrainRepairProposalDryRunChecklistItem:
    artifact_statuses: list[QaBrainRepairProposalDryRunArtifactStatus] = []
    for source_id in _REPAIR_SOURCE_IDS[row.case_id]:
        source = sources_by_id.get(source_id)
        artifact_statuses.append(
            QaBrainRepairProposalDryRunArtifactStatus(
                source_id=source_id,
                status=source.state if source is not None else "missing",
            )
        )
    artifact_status_tuple = tuple(artifact_statuses)
    gate_status = _acceptance_gate_status(row)
    prerequisite_status = _prerequisite_status(
        artifact_statuses=artifact_status_tuple,
        acceptance_gate_status=gate_status,
    )
    return QaBrainRepairProposalDryRunChecklistItem(
        case_id=row.case_id,
        prerequisite_status=prerequisite_status,
        readiness=row.readiness,
        artifact_statuses=artifact_status_tuple,
        acceptance_gate_status=gate_status,
        next_action_label=_dry_run_next_action_label(
            prerequisite_status=prerequisite_status,
            artifact_statuses=artifact_status_tuple,
            acceptance_gate_status=gate_status,
        ),
    )


def _repair_acceptance_checklist(
    repair_plans: tuple[QaBrainRepairPlanRow, ...],
) -> tuple[QaBrainRepairAcceptanceChecklistItem, ...]:
    rows: list[QaBrainRepairAcceptanceChecklistItem] = []
    for row in repair_plans:
        for gate_id in row.acceptance_gate_ids:
            rows.append(
                QaBrainRepairAcceptanceChecklistItem(
                    case_id=row.case_id,
                    gate_id=gate_id,
                    gate_family=_gate_family(gate_id),
                    source_evidence_ids=row.source_ids,
                    required_reviewer="codex_or_human",
                    forbidden_shortcut_notes=(_forbidden_shortcut_note(gate_id),),
                )
            )
    return tuple(rows)


def _gate_family(
    gate_id: QaBrainRepairAcceptanceGateId,
) -> QaBrainRepairAcceptanceGateFamily:
    if gate_id == "secret_redaction":
        return "redaction"
    return _NON_REDACTION_GATE_FAMILIES[gate_id]


def _forbidden_shortcut_note(gate_id: QaBrainRepairAcceptanceGateId) -> str:
    if gate_id == "secret_redaction":
        return "Do not paste raw prompts, provider output, source Hurl, secrets, or traffic bodies."
    return _NON_REDACTION_FORBIDDEN_SHORTCUTS[gate_id]


def _acceptance_gate_status(
    row: QaBrainRepairPlanRow,
) -> QaBrainRepairProposalDryRunGateStatus:
    return "ready" if row.acceptance_gate_ids else "missing"


def _prerequisite_status(
    *,
    artifact_statuses: tuple[QaBrainRepairProposalDryRunArtifactStatus, ...],
    acceptance_gate_status: QaBrainRepairProposalDryRunGateStatus,
) -> QaBrainRepairProposalDryRunPrerequisiteStatus:
    if (
        all(artifact.status == "present" for artifact in artifact_statuses)
        and acceptance_gate_status == "ready"
    ):
        return "ready"
    if any(artifact.status != "missing" for artifact in artifact_statuses):
        return "partial"
    if acceptance_gate_status == "ready":
        return "partial"
    return "missing"


def _dry_run_next_action_label(
    *,
    prerequisite_status: QaBrainRepairProposalDryRunPrerequisiteStatus,
    artifact_statuses: tuple[QaBrainRepairProposalDryRunArtifactStatus, ...],
    acceptance_gate_status: QaBrainRepairProposalDryRunGateStatus,
) -> str:
    if any(artifact.status in {"invalid", "unsafe"} for artifact in artifact_statuses):
        return "repair-local-evidence"
    if prerequisite_status == "ready":
        return "repair-proposal-dry-run"
    if (
        prerequisite_status == "partial"
        and acceptance_gate_status == "missing"
        and any(artifact.status == "present" for artifact in artifact_statuses)
    ):
        return "add-routing-acceptance-gates"
    return "add-value-free-evidence"


def _summary(
    *,
    sources: tuple[QaBrainRepairPlanSource, ...],
    repair_plans: tuple[QaBrainRepairPlanRow, ...],
    next_actions: tuple[QaBrainRepairPlanNextAction, ...],
) -> QaBrainRepairPlanSummary:
    source_counts = _source_counts(sources)
    repair_counts = _repair_counts(repair_plans)
    blockers_total = len({blocker for row in repair_plans for blocker in row.blockers})
    return QaBrainRepairPlanSummary(
        status=_status(source_counts=source_counts, repair_counts=repair_counts),
        sources_total=len(sources),
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        repair_plans_total=len(repair_plans),
        repair_plans_ready=repair_counts.ready,
        repair_plans_missing=repair_counts.missing,
        repair_plans_attention=repair_counts.attention,
        blockers_total=blockers_total,
        next_actions_total=len(next_actions),
    )


def _source_counts(sources: tuple[QaBrainRepairPlanSource, ...]) -> _SourceCounts:
    return _SourceCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _repair_counts(
    repair_plans: tuple[QaBrainRepairPlanRow, ...],
) -> _RepairCounts:
    return _RepairCounts(
        ready=sum(1 for row in repair_plans if row.readiness == "ready"),
        missing=sum(1 for row in repair_plans if row.readiness == "missing"),
        attention=sum(1 for row in repair_plans if row.readiness == "attention"),
    )


def _status(
    *,
    source_counts: _SourceCounts,
    repair_counts: _RepairCounts,
) -> QaBrainRepairPlanStatus:
    if source_counts.invalid or source_counts.unsafe or repair_counts.attention:
        return "partial"
    if repair_counts.ready and not repair_counts.missing:
        return "ready"
    if source_counts.present or repair_counts.ready:
        return "partial"
    return "insufficient"


def _load_failure_state(load_error: str) -> QaBrainRepairPlanSourceState:
    if load_error in {"not a file", "path outside project", "symlinked path component"}:
        return "unsafe"
    return "invalid"


def _contains_unredacted_packet_secret_like_value(text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", text))


def _parse_json_object(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _routing_summary(document: dict[str, object]) -> str:
    summary = document.get("summary")
    if not isinstance(summary, dict):
        return "QA brain routing plan present"
    status = safe_evidence_text(str(summary.get("status", "unknown")))
    total = summary.get("routes_total")
    ready = summary.get("routes_ready")
    if isinstance(total, int) and isinstance(ready, int):
        return f"{status}, {ready}/{total} routes ready"
    return f"{status} routing plan"


def _routing_gates_by_case(
    document: dict[str, object],
) -> dict[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]]:
    plans = document.get("routing_plans")
    if not isinstance(plans, list):
        return {}
    gates_by_case: dict[QaBrainEvalSliceId, tuple[QaBrainRepairAcceptanceGateId, ...]] = {}
    for item in plans:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if case_id not in _REPAIR_SOURCE_IDS:
            continue
        gates_by_case[cast(QaBrainEvalSliceId, case_id)] = _repair_gate_ids(item)
    return gates_by_case


def _repair_gate_ids(item: dict[str, object]) -> tuple[QaBrainRepairAcceptanceGateId, ...]:
    gates = item.get("repair_acceptance_gates")
    if not isinstance(gates, list):
        return ()
    gate_ids: list[QaBrainRepairAcceptanceGateId] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        if isinstance(gate_id, str) and _GATE_ID_RE.match(gate_id) and gate_id not in gate_ids:
            gate_ids.append(cast(QaBrainRepairAcceptanceGateId, gate_id))
    return tuple(gate_ids)


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")


def _artifact_statuses_label(
    artifact_statuses: tuple[QaBrainRepairProposalDryRunArtifactStatus, ...],
) -> str:
    return ", ".join(
        f"{artifact.source_id}:{artifact.status}" for artifact in artifact_statuses
    )
