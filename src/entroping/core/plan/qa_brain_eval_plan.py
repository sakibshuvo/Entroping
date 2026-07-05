"""Deterministic local QA brain eval-plan packet reports."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import contains_unredacted_evidence_secret
from entroping.core.evidence_packet_base import write_evidence_packet_report
from entroping.core.plan.qa_brain_seed import (
    QA_BRAIN_SEED_SCHEMA_VERSION,
    QaBrainEvalSlice,
    QaBrainEvalSliceId,
    QaBrainEvalSliceStatus,
    QaBrainNextActionPriority,
    QaBrainSeedCategory,
    QaBrainSeedError,
    QaBrainSeedSource,
    QaBrainSeedSourceState,
    build_qa_brain_seed,
)

QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION: Final = "entroping.qa-brain-eval-plan.v1"

QaBrainEvalPlanOutput = Literal["md", "json"]
QaBrainEvalPlanStatus = Literal["ready", "partial", "insufficient"]
QaBrainEvalCaseReadiness = QaBrainEvalSliceStatus
QaBrainEvalCatalogSourceState = QaBrainSeedSourceState
QaBrainEvalCatalogCategory = QaBrainSeedCategory
QaBrainEvalMissingReason = Literal[
    "artifact_missing",
    "artifact_invalid",
    "artifact_unsafe",
]

_DEFAULT_OUTPUTS: Final[dict[QaBrainEvalPlanOutput, Path]] = {
    "md": Path("reports") / "qa-brain-eval-plan.md",
    "json": Path("reports") / "qa-brain-eval-plan.json",
}

_INPUT_CONTRACTS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "Value-free generated-test quality and test-pyramid evidence rows."
    ),
    "missing_gate_discovery": "Value-free policy, gate coverage, and gate injection rows.",
    "unsafe_generated_hurl": (
        "Value-free generated-test quality and mutation-readiness evidence rows."
    ),
    "bogus_evidence": "Value-free artifact integrity, run, drift, and review evidence rows.",
    "redaction_mistakes": "Value-free redaction summary evidence rows.",
    "api_drift_reasoning": "Value-free API inventory and drift evidence rows.",
    "mutation_fuzz_readiness": (
        "Value-free mutation-readiness and generated-test quality evidence rows."
    ),
    "cross_surface_handoff_quality": (
        "Value-free handoff, runtime-card, notification, observability, and evidence-index rows."
    ),
}

_OUTPUT_CONTRACTS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "schema-valid QA critique result for weak assertions and missing negative paths"
    ),
    "missing_gate_discovery": (
        "schema-valid QA critique result for missing QAnstitution gate coverage"
    ),
    "unsafe_generated_hurl": (
        "schema-valid QA critique result for unsafe or overbroad generated Hurl"
    ),
    "bogus_evidence": "schema-valid QA critique result for unsupported evidence claims",
    "redaction_mistakes": "schema-valid QA critique result for redaction-risk signals",
    "api_drift_reasoning": "schema-valid QA critique result for API drift explanations",
    "mutation_fuzz_readiness": (
        "schema-valid QA critique result for mutation and fuzz readiness gaps"
    ),
    "cross_surface_handoff_quality": (
        "schema-valid QA critique result for incomplete cross-surface handoff evidence"
    ),
}

_ACCEPTANCE_SIGNALS: Final[dict[QaBrainEvalSliceId, str]] = {
    "weak_test_detection": (
        "Flags shallow generated tests without using raw report contents or acting "
        + "as pass/fail authority."
    ),
    "missing_gate_discovery": (
        "Identifies absent policy or gate evidence while preserving QAnstitution as authority."
    ),
    "unsafe_generated_hurl": (
        "Rejects unsafe generated-test patterns through deterministic follow-up evidence."
    ),
    "bogus_evidence": (
        "Challenges unsupported evidence claims using only local artifact state "
        + "and schema metadata."
    ),
    "redaction_mistakes": (
        "Surfaces redaction risk without rendering headers, bodies, cookies, or tokens."
    ),
    "api_drift_reasoning": (
        "Explains API drift from value-free inventory and drift rows only."
    ),
    "mutation_fuzz_readiness": (
        "Separates mutation/fuzz readiness from actual mutation or fuzz execution."
    ),
    "cross_surface_handoff_quality": (
        "Checks whether handoff metadata is sufficient for CLI, PR, desktop, "
        + "cloud, and mobile surfaces."
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

_MISSING_REASON_BY_STATE: Final[
    dict[QaBrainEvalCatalogSourceState, QaBrainEvalMissingReason | None]
] = {
    "present": None,
    "missing": "artifact_missing",
    "invalid": "artifact_invalid",
    "unsafe": "artifact_unsafe",
}
_MISSING_REASON_ORDER: Final[tuple[QaBrainEvalMissingReason, ...]] = (
    "artifact_unsafe",
    "artifact_invalid",
    "artifact_missing",
)


class QaBrainEvalPlanError(ValueError):
    """Raised when a QA brain eval-plan report cannot be generated safely."""


class QaBrainEvalPlanSummary(BaseModel):
    """Aggregate QA brain eval-plan readiness."""

    model_config = ConfigDict(extra="forbid")

    status: QaBrainEvalPlanStatus
    cases_total: int = Field(ge=0)
    cases_ready: int = Field(ge=0)
    cases_missing: int = Field(ge=0)
    cases_attention: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class QaBrainEvalCatalogSource(BaseModel):
    """One value-free source row in a future QA brain eval-case catalog."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: QaBrainEvalCatalogSourceState
    category: QaBrainEvalCatalogCategory
    schema_version: str | None = None
    missing_reason: QaBrainEvalMissingReason | None = None


class QaBrainEvalCaseCatalog(BaseModel):
    """Value-free evidence catalog metadata for one future QA brain eval case."""

    model_config = ConfigDict(extra="forbid")

    expected_sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    categories: tuple[QaBrainEvalCatalogCategory, ...] = ()
    missing_reasons: tuple[QaBrainEvalMissingReason, ...] = ()
    sources: tuple[QaBrainEvalCatalogSource, ...] = ()


def _empty_evidence_catalog() -> QaBrainEvalCaseCatalog:
    return QaBrainEvalCaseCatalog(
        expected_sources_total=0,
        sources_present=0,
        sources_missing=0,
        sources_invalid=0,
        sources_unsafe=0,
    )


class QaBrainEvalCase(BaseModel):
    """One deterministic future QA brain evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: QaBrainEvalSliceId
    label: str
    readiness: QaBrainEvalCaseReadiness
    source_ids: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    input_contract: str
    output_contract: str
    acceptance_signal: str
    negative_controls: tuple[str, ...]
    next_action: str
    evidence_catalog: QaBrainEvalCaseCatalog = Field(default_factory=_empty_evidence_catalog)


class QaBrainEvalPlanNextAction(BaseModel):
    """Action needed before future QA brain eval execution."""

    model_config = ConfigDict(extra="forbid")

    priority: QaBrainNextActionPriority
    action: str
    case_ids: tuple[QaBrainEvalSliceId, ...]


class QaBrainEvalPlanPacket(BaseModel):
    """Schema-versioned local QA brain eval-plan packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.qa-brain-eval-plan.v1"] = (
        QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    seed_schema_version: Literal["entroping.qa-brain-seed.v1"]
    summary: QaBrainEvalPlanSummary
    cases: tuple[QaBrainEvalCase, ...]
    next_actions: tuple[QaBrainEvalPlanNextAction, ...]


@dataclass(frozen=True, slots=True)
class QaBrainEvalPlanResult:
    """Result of writing one QA brain eval-plan packet."""

    output_path: Path
    packet: QaBrainEvalPlanPacket


@dataclass(frozen=True, slots=True)
class _CaseCounts:
    ready: int
    missing: int
    attention: int


def run_qa_brain_eval_plan_report(
    *,
    project_root: Path,
    output: QaBrainEvalPlanOutput,
    output_path: Path | None = None,
) -> QaBrainEvalPlanResult:
    """Write a deterministic local QA brain eval-plan packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported qa-brain-eval-plan output: {output}"
        raise QaBrainEvalPlanError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_qa_brain_eval_plan(project_root=root)
    result = write_evidence_packet_report(
        project_root=root,
        output=output,
        output_path=destination,
        packet=packet,
        render_markdown=render_qa_brain_eval_plan_markdown,
        has_secret_content=contains_unredacted_evidence_secret,
        unsafe_content_message="QA brain eval plan contains secret-like content",
        artifact="QA brain eval plan",
        error_type=QaBrainEvalPlanError,
    )
    return QaBrainEvalPlanResult(output_path=result.output_path, packet=result.packet)


def build_qa_brain_eval_plan(*, project_root: Path) -> QaBrainEvalPlanPacket:
    """Build future QA brain eval-plan metadata from local seed readiness."""

    root = project_root.expanduser().resolve()
    try:
        seed = build_qa_brain_seed(project_root=root)
    except QaBrainSeedError as exc:
        raise QaBrainEvalPlanError(str(exc)) from exc
    catalogs = _evidence_catalogs(seed.sources)
    cases = tuple(
        _case_from_seed_slice(
            eval_slice=eval_slice,
            evidence_catalog=catalogs.get(eval_slice.id, _empty_evidence_catalog()),
        )
        for eval_slice in seed.eval_slices
    )
    next_actions = _next_actions(cases)
    return QaBrainEvalPlanPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        seed_schema_version=QA_BRAIN_SEED_SCHEMA_VERSION,
        summary=_summary(cases=cases, next_actions=next_actions),
        cases=cases,
        next_actions=next_actions,
    )


def render_qa_brain_eval_plan_markdown(packet: QaBrainEvalPlanPacket) -> str:
    """Render a human-readable, value-free QA brain eval-plan packet."""

    lines = [
        "# Entroping QA Brain Eval Plan",
        "",
        (
            "Deterministic local eval-plan metadata for future Entroping QA Brain "
            + "retrieval, prompt, and model-evaluation design. This report does not "
            + "execute Hurl, run tests, call providers, fine-tune models, retrieve "
            + "documents, upload artifacts, parse traffic state, run mutations, or "
            + "render raw report contents."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Seed schema: `{packet.seed_schema_version}`",
        (
            f"- Cases: `{packet.summary.cases_ready}/{packet.summary.cases_total}` ready, "
            + f"`{packet.summary.cases_missing}` missing, "
            + f"`{packet.summary.cases_attention}` attention"
        ),
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Eval Cases",
        "",
        (
            "| ID | Label | Readiness | Sources | Input Contract | Output Contract | "
            + "Acceptance Signal |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in packet.cases:
        lines.append(
            "| "
            f"{_markdown_cell(case.id)} | "
            f"{_markdown_cell(case.label)} | "
            f"{_markdown_cell(case.readiness)} | "
            f"{_markdown_cell(', '.join(case.source_ids) or 'n/a')} | "
            f"{_markdown_cell(case.input_contract)} | "
            f"{_markdown_cell(case.output_contract)} | "
            f"{_markdown_cell(case.acceptance_signal)} |"
        )
    lines.extend(
        [
            "",
            "## Eval Case Catalog",
            "",
            (
                "| ID | Expected Sources | Present | Missing | Invalid | Unsafe | "
                + "Categories | Missing Reasons |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in packet.cases:
        catalog = case.evidence_catalog
        lines.append(
            "| "
            f"{_markdown_cell(case.id)} | "
            f"{catalog.expected_sources_total} | "
            f"{catalog.sources_present} | "
            f"{catalog.sources_missing} | "
            f"{catalog.sources_invalid} | "
            f"{catalog.sources_unsafe} | "
            f"{_markdown_cell(', '.join(catalog.categories) or 'n/a')} | "
            f"{_markdown_cell(', '.join(catalog.missing_reasons) or 'n/a')} |"
        )
    lines.extend(
        [
            "",
            "## Eval Case Catalog Sources",
            "",
            "| Case ID | Source ID | State | Category | Schema | Missing Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in packet.cases:
        for source in case.evidence_catalog.sources:
            lines.append(
                "| "
                f"{_markdown_cell(case.id)} | "
                f"{_markdown_cell(source.id)} | "
                f"{_markdown_cell(source.state)} | "
                f"{_markdown_cell(source.category)} | "
                f"{_markdown_cell(source.schema_version or 'n/a')} | "
                f"{_markdown_cell(source.missing_reason or 'n/a')} |"
            )
    lines.extend(["", "## Negative Controls", ""])
    for case in packet.cases:
        lines.append(f"### {_markdown_heading(case.label)}")
        for control in case.negative_controls:
            lines.append(f"- {_markdown_text(control)}")
        lines.append("")
    lines.extend(["## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No QA brain eval-plan actions are currently needed.")
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


def _case_from_seed_slice(
    *,
    eval_slice: QaBrainEvalSlice,
    evidence_catalog: QaBrainEvalCaseCatalog,
) -> QaBrainEvalCase:
    return QaBrainEvalCase(
        id=eval_slice.id,
        label=eval_slice.label,
        readiness=eval_slice.status,
        source_ids=eval_slice.source_ids,
        source_paths=eval_slice.source_paths,
        input_contract=_metadata_text(
            mapping=_INPUT_CONTRACTS,
            eval_id=eval_slice.id,
            field="input_contract",
        ),
        output_contract=_metadata_text(
            mapping=_OUTPUT_CONTRACTS,
            eval_id=eval_slice.id,
            field="output_contract",
        ),
        acceptance_signal=_metadata_text(
            mapping=_ACCEPTANCE_SIGNALS,
            eval_id=eval_slice.id,
            field="acceptance_signal",
        ),
        negative_controls=_metadata_tuple(
            mapping=_NEGATIVE_CONTROLS,
            eval_id=eval_slice.id,
            field="negative_controls",
        ),
        next_action=_case_next_action(eval_slice),
        evidence_catalog=evidence_catalog,
    )


def _evidence_catalogs(
    sources: tuple[QaBrainSeedSource, ...],
) -> dict[QaBrainEvalSliceId, QaBrainEvalCaseCatalog]:
    catalogs: dict[QaBrainEvalSliceId, QaBrainEvalCaseCatalog] = {}
    for eval_id in _INPUT_CONTRACTS:
        case_sources = tuple(source for source in sources if eval_id in source.eval_slices)
        catalogs[eval_id] = _evidence_catalog(case_sources)
    return catalogs


def _evidence_catalog(
    sources: tuple[QaBrainSeedSource, ...],
) -> QaBrainEvalCaseCatalog:
    catalog_sources = tuple(_catalog_source(source) for source in sources)
    return QaBrainEvalCaseCatalog(
        expected_sources_total=len(catalog_sources),
        sources_present=sum(1 for source in catalog_sources if source.state == "present"),
        sources_missing=sum(1 for source in catalog_sources if source.state == "missing"),
        sources_invalid=sum(1 for source in catalog_sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in catalog_sources if source.state == "unsafe"),
        categories=_ordered_unique(source.category for source in catalog_sources),
        missing_reasons=_missing_reasons(catalog_sources),
        sources=catalog_sources,
    )


def _catalog_source(source: QaBrainSeedSource) -> QaBrainEvalCatalogSource:
    return QaBrainEvalCatalogSource(
        id=source.id,
        state=source.state,
        category=source.category,
        schema_version=source.schema_version,
        missing_reason=_MISSING_REASON_BY_STATE[source.state],
    )


def _ordered_unique[T](values: Iterable[T]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))


def _missing_reasons(
    sources: tuple[QaBrainEvalCatalogSource, ...],
) -> tuple[QaBrainEvalMissingReason, ...]:
    reasons = frozenset(
        source.missing_reason
        for source in sources
        if source.missing_reason is not None
    )
    return tuple(reason for reason in _MISSING_REASON_ORDER if reason in reasons)


def _metadata_text(
    *,
    mapping: dict[QaBrainEvalSliceId, str],
    eval_id: QaBrainEvalSliceId,
    field: str,
) -> str:
    try:
        return mapping[eval_id]
    except KeyError as exc:
        msg = f"QA brain eval plan is missing {field} metadata for {eval_id}"
        raise QaBrainEvalPlanError(msg) from exc


def _metadata_tuple(
    *,
    mapping: dict[QaBrainEvalSliceId, tuple[str, ...]],
    eval_id: QaBrainEvalSliceId,
    field: str,
) -> tuple[str, ...]:
    try:
        return mapping[eval_id]
    except KeyError as exc:
        msg = f"QA brain eval plan is missing {field} metadata for {eval_id}"
        raise QaBrainEvalPlanError(msg) from exc


def _case_next_action(eval_slice: QaBrainEvalSlice) -> str:
    if eval_slice.status == "ready":
        return f"Use value-free local evidence for {eval_slice.label} eval design."
    if eval_slice.status == "attention":
        return f"Repair invalid or unsafe local evidence before {eval_slice.label} evals."
    return f"Add value-free local evidence before {eval_slice.label} evals."


def _next_actions(cases: tuple[QaBrainEvalCase, ...]) -> tuple[QaBrainEvalPlanNextAction, ...]:
    actions: list[QaBrainEvalPlanNextAction] = []
    for case in cases:
        if case.readiness == "ready":
            continue
        priority: QaBrainNextActionPriority = (
            "high" if case.readiness == "attention" else "medium"
        )
        actions.append(
            QaBrainEvalPlanNextAction(
                priority=priority,
                action=case.next_action,
                case_ids=(case.id,),
            )
        )
    return tuple(actions)


def _summary(
    *,
    cases: tuple[QaBrainEvalCase, ...],
    next_actions: tuple[QaBrainEvalPlanNextAction, ...],
) -> QaBrainEvalPlanSummary:
    counts = _case_counts(cases)
    return QaBrainEvalPlanSummary(
        status=_status(counts=counts, total=len(cases)),
        cases_total=len(cases),
        cases_ready=counts.ready,
        cases_missing=counts.missing,
        cases_attention=counts.attention,
        next_actions_total=len(next_actions),
    )


def _case_counts(cases: tuple[QaBrainEvalCase, ...]) -> _CaseCounts:
    return _CaseCounts(
        ready=sum(1 for case in cases if case.readiness == "ready"),
        missing=sum(1 for case in cases if case.readiness == "missing"),
        attention=sum(1 for case in cases if case.readiness == "attention"),
    )


def _status(*, counts: _CaseCounts, total: int) -> QaBrainEvalPlanStatus:
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
