"""Local design-partner pilot outcome packets from sanitized evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence.evidence_index import (
    EvidenceArtifactState,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

PILOT_OUTCOME_SCHEMA_VERSION: Final = "entroping.pilot-outcome.v1"

PilotOutcomeOutput = Literal["md", "json"]
PilotOutcomeStatus = Literal["ready", "partial", "insufficient"]
PilotOutcomeSourceState = EvidenceArtifactState
PilotOutcomePriority = Literal["high", "medium", "low"]
PilotOutcomeActionCategory = Literal["generate", "repair", "collect", "review"]
PilotOutcomeSourceId = Literal[
    "design-partner-feedback-json",
    "pilot-metrics-json",
    "runtime-card-json",
    "evidence-cloud-dashboard-json",
    "work-item-import-bundle-json",
]
PilotOutcomeSignalId = Literal["hosted_aggregation", "premium_policy_packs"]
PilotOutcomeSignalAnswer = Literal["yes", "no", "unclear"]

_DEFAULT_OUTPUTS: Final[dict[PilotOutcomeOutput, Path]] = {
    "md": Path("reports") / "pilot-outcome.md",
    "json": Path("reports") / "pilot-outcome.json",
}
_MANUAL_INPUT_REQUIRED: Final = "manual input required"
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: PilotOutcomeSourceId
    label: str
    path: Path
    schema_version: str


_SOURCE_DEFINITIONS: Final[tuple[_SourceDefinition, ...]] = (
    _SourceDefinition(
        id="design-partner-feedback-json",
        label="Design-partner feedback",
        path=Path("reports") / "design-partner-feedback.json",
        schema_version="entroping.design-partner-feedback.v1",
    ),
    _SourceDefinition(
        id="pilot-metrics-json",
        label="Pilot metrics",
        path=Path("reports") / "pilot-metrics.json",
        schema_version="entroping.pilot-metrics.v1",
    ),
    _SourceDefinition(
        id="runtime-card-json",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version="entroping.runtime-card.v1",
    ),
    _SourceDefinition(
        id="evidence-cloud-dashboard-json",
        label="Evidence Cloud dashboard",
        path=Path("reports") / "evidence-cloud-dashboard.json",
        schema_version="entroping.evidence-cloud-dashboard.v1",
    ),
    _SourceDefinition(
        id="work-item-import-bundle-json",
        label="Work item import bundle",
        path=Path("reports") / "work-item-import-bundle.json",
        schema_version="entroping.work-item-import-bundle.v1",
    ),
)


class PilotOutcomeError(ValueError):
    """Raised when the pilot outcome packet cannot be generated safely."""


class PilotOutcomeSummary(BaseModel):
    """Aggregate design-partner pilot outcome state."""

    model_config = ConfigDict(extra="forbid")

    status: PilotOutcomeStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    manual_input_gaps: int = Field(ge=0)
    monetization_yes: int = Field(ge=0)
    monetization_no: int = Field(ge=0)
    monetization_unclear: int = Field(ge=0)
    actions_total: int = Field(ge=0)
    actions_high: int = Field(ge=0)
    actions_medium: int = Field(ge=0)
    actions_low: int = Field(ge=0)


class PilotOutcomeSource(BaseModel):
    """One sanitized source artifact summarized for pilot outcome review."""

    model_config = ConfigDict(extra="forbid")

    id: PilotOutcomeSourceId
    label: str
    path: str
    state: PilotOutcomeSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    status: str | None = None


class PilotOutcomeReadiness(BaseModel):
    """Value-free pilot readiness signals derived from source summaries."""

    model_config = ConfigDict(extra="forbid")

    design_partner_feedback_status: str | None = None
    pilot_metrics_status: str | None = None
    runtime_card_status: str | None = None
    evidence_cloud_status: str | None = None
    work_item_import_status: str | None = None


class PilotOutcomeMonetizationSignal(BaseModel):
    """One value-free monetization signal answer."""

    model_config = ConfigDict(extra="forbid")

    id: PilotOutcomeSignalId
    answer: PilotOutcomeSignalAnswer
    manual_reason_required: bool


class PilotOutcomeAction(BaseModel):
    """One local follow-up action for pilot outcome readiness."""

    model_config = ConfigDict(extra="forbid")

    priority: PilotOutcomePriority
    category: PilotOutcomeActionCategory
    action: str
    source_ids: tuple[PilotOutcomeSourceId, ...] = ()
    field_paths: tuple[str, ...] = ()
    status: str | None = None


class PilotOutcomePacket(BaseModel):
    """Schema-versioned local pilot outcome packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.pilot-outcome.v1"] = PILOT_OUTCOME_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: PilotOutcomeSummary
    sources: tuple[PilotOutcomeSource, ...]
    pilot_evidence_readiness: PilotOutcomeReadiness
    manual_input_gaps: tuple[str, ...]
    monetization_signals: tuple[PilotOutcomeMonetizationSignal, ...]
    actions: tuple[PilotOutcomeAction, ...]


@dataclass(frozen=True, slots=True)
class PilotOutcomeResult:
    """Result of writing a local pilot outcome packet."""

    output_path: Path
    packet: PilotOutcomePacket


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _MonetizationCounts:
    yes: int
    no: int
    unclear: int


@dataclass(frozen=True, slots=True)
class _ActionCounts:
    high: int
    medium: int
    low: int


def run_pilot_outcome_report(
    *,
    project_root: Path,
    output: PilotOutcomeOutput,
    output_path: Path | None = None,
) -> PilotOutcomeResult:
    """Write a local design-partner pilot outcome packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported pilot-outcome output: {output}"
        raise PilotOutcomeError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_pilot_outcome_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_pilot_outcome_secret(content):
        msg = "pilot outcome packet contains secret-like content"
        raise PilotOutcomeError(msg)
    try:
        written = safe_write_text(destination, content, artifact="pilot outcome", root=root)
    except SafeWriteError as exc:
        raise PilotOutcomeError(str(exc)) from exc
    return PilotOutcomeResult(output_path=written, packet=packet)


def build_pilot_outcome_packet(*, project_root: Path) -> PilotOutcomePacket:
    """Build a value-free local pilot outcome packet."""

    root = project_root.expanduser().resolve()
    loaded = tuple(
        _source_from_definition(definition, root=root)
        for definition in _SOURCE_DEFINITIONS
    )
    sources = tuple(source for source, _document in loaded)
    documents = {
        source.id: document
        for source, document in loaded
        if document is not None
    }
    readiness = _readiness_from_sources(sources)
    manual_gaps = _manual_input_gaps(documents.get("design-partner-feedback-json"))
    signals = _monetization_signals(documents.get("design-partner-feedback-json"))
    actions = _actions(sources=sources, manual_gaps=manual_gaps, signals=signals)
    return PilotOutcomePacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=documents.values()),
        summary=_summary(
            sources=sources,
            manual_gaps=manual_gaps,
            signals=signals,
            actions=actions,
        ),
        sources=sources,
        pilot_evidence_readiness=readiness,
        manual_input_gaps=manual_gaps,
        monetization_signals=signals,
        actions=actions,
    )


def render_pilot_outcome_markdown(packet: PilotOutcomePacket) -> str:
    """Render a value-free Markdown pilot outcome packet."""

    lines = [
        "# Entroping Pilot Outcome",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        f"- Sources: `{packet.summary.sources_present}/{packet.summary.sources_total}` present",
        f"- Manual input gaps: `{packet.summary.manual_input_gaps}`",
        "- Monetization signals: "
        f"`{packet.summary.monetization_yes}` yes, "
        f"`{packet.summary.monetization_no}` no, "
        f"`{packet.summary.monetization_unclear}` unclear",
        "",
        "## Readiness",
        "",
        "| Signal | Status |",
        "| --- | --- |",
    ]
    readiness = packet.pilot_evidence_readiness
    for label, status in (
        ("design_partner_feedback", readiness.design_partner_feedback_status),
        ("pilot_metrics", readiness.pilot_metrics_status),
        ("runtime_card", readiness.runtime_card_status),
        ("evidence_cloud", readiness.evidence_cloud_status),
        ("work_item_import", readiness.work_item_import_status),
    ):
        lines.append(f"| {_markdown_cell(label)} | {_markdown_cell(status or 'missing')} |")
    lines.extend(["", "## Manual Input Gaps", ""])
    lines.extend(f"- `{_inline_code(path)}`" for path in packet.manual_input_gaps)
    if not packet.manual_input_gaps:
        lines.append("- `none`")
    lines.extend(["", "## Monetization Signals", "", "| Signal | Answer |", "| --- | --- |"])
    for signal in packet.monetization_signals:
        lines.append(f"| {_markdown_cell(signal.id)} | {_markdown_cell(signal.answer)} |")
    lines.extend(["", "## Actions", "", "| Priority | Category | Action |", "| --- | --- | --- |"])
    for action in packet.actions:
        lines.append(
            "| "
            f"{_markdown_cell(action.priority)} | "
            f"{_markdown_cell(action.category)} | "
            f"{_markdown_cell(action.action)} |"
        )
    if not packet.actions:
        lines.append("| low | review | No local pilot outcome action required. |")
    return "\n".join(lines).rstrip() + "\n"


def _source_from_definition(
    definition: _SourceDefinition,
    *,
    root: Path,
) -> tuple[PilotOutcomeSource, dict[str, object] | None]:
    candidate = root / definition.path
    if not candidate.exists():
        return _source(definition, state="missing", summary="missing"), None
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(candidate, root=root)
    if raw_bytes is None:
        return (
            _source(
                definition,
                state=_state_from_load_error(load_error),
                summary=safe_evidence_text(load_error),
            ),
            None,
        )
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if _contains_unredacted_pilot_outcome_secret(raw_text):
        return _source(definition, state="unsafe", summary="secret-like content"), None
    document = _parse_document(raw_text)
    if document is None:
        return _source(definition, state="invalid", summary="invalid JSON"), None
    schema_version = _schema_version(document)
    if schema_version != definition.schema_version:
        return (
            _source(
                definition,
                state="invalid",
                schema_version=schema_version,
                summary=f"schema mismatch; expected {definition.schema_version}",
            ),
            None,
        )
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    status = _document_status(definition.id, document)
    return (
        _source(
            definition,
            state="present",
            schema_version=schema_version,
            sha256=sha256,
            summary=status or "present",
            status=status,
        ),
        document,
    )


def _source(
    definition: _SourceDefinition,
    *,
    state: PilotOutcomeSourceState,
    summary: str,
    schema_version: str | None = None,
    sha256: str | None = None,
    status: str | None = None,
) -> PilotOutcomeSource:
    return PilotOutcomeSource(
        id=definition.id,
        label=definition.label,
        path=definition.path.as_posix(),
        state=state,
        schema_version=safe_evidence_text(schema_version) if schema_version else None,
        sha256=sha256,
        summary=safe_evidence_text(summary),
        status=safe_evidence_text(status).lower() if status else None,
    )


def _summary(
    *,
    sources: tuple[PilotOutcomeSource, ...],
    manual_gaps: tuple[str, ...],
    signals: tuple[PilotOutcomeMonetizationSignal, ...],
    actions: tuple[PilotOutcomeAction, ...],
) -> PilotOutcomeSummary:
    source_counts = _source_counts(sources)
    monetization_counts = _monetization_counts(signals)
    action_counts = _action_counts(actions)
    return PilotOutcomeSummary(
        status=_status(sources=sources, manual_gaps=manual_gaps, signals=signals),
        sources_total=len(sources),
        sources_present=source_counts.present,
        sources_missing=source_counts.missing,
        sources_invalid=source_counts.invalid,
        sources_unsafe=source_counts.unsafe,
        manual_input_gaps=len(manual_gaps),
        monetization_yes=monetization_counts.yes,
        monetization_no=monetization_counts.no,
        monetization_unclear=monetization_counts.unclear,
        actions_total=len(actions),
        actions_high=action_counts.high,
        actions_medium=action_counts.medium,
        actions_low=action_counts.low,
    )


def _source_counts(sources: tuple[PilotOutcomeSource, ...]) -> _SourceCounts:
    return _SourceCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _monetization_counts(
    signals: tuple[PilotOutcomeMonetizationSignal, ...],
) -> _MonetizationCounts:
    return _MonetizationCounts(
        yes=sum(1 for signal in signals if signal.answer == "yes"),
        no=sum(1 for signal in signals if signal.answer == "no"),
        unclear=sum(1 for signal in signals if signal.answer == "unclear"),
    )


def _action_counts(actions: tuple[PilotOutcomeAction, ...]) -> _ActionCounts:
    return _ActionCounts(
        high=sum(1 for action in actions if action.priority == "high"),
        medium=sum(1 for action in actions if action.priority == "medium"),
        low=sum(1 for action in actions if action.priority == "low"),
    )


def _status(
    *,
    sources: tuple[PilotOutcomeSource, ...],
    manual_gaps: tuple[str, ...],
    signals: tuple[PilotOutcomeMonetizationSignal, ...],
) -> PilotOutcomeStatus:
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "missing" for source in sources):
        return "insufficient"
    if manual_gaps or any(signal.answer == "unclear" for signal in signals):
        return "partial"
    return "ready"


def _actions(
    *,
    sources: tuple[PilotOutcomeSource, ...],
    manual_gaps: tuple[str, ...],
    signals: tuple[PilotOutcomeMonetizationSignal, ...],
) -> tuple[PilotOutcomeAction, ...]:
    actions: list[PilotOutcomeAction] = []
    for source in sources:
        if source.state == "missing":
            actions.append(
                PilotOutcomeAction(
                    priority="medium",
                    category="generate",
                    action=f"Generate {source.label} before pilot outcome review.",
                    source_ids=(source.id,),
                    status=source.state,
                )
            )
        if source.state in {"invalid", "unsafe"}:
            actions.append(
                PilotOutcomeAction(
                    priority="high",
                    category="repair",
                    action=f"Repair {source.label} before pilot outcome review.",
                    source_ids=(source.id,),
                    status=source.state,
                )
            )
    if manual_gaps:
        actions.append(
            PilotOutcomeAction(
                priority="medium",
                category="collect",
                action="Collect sanitized manual design-partner pilot inputs.",
                field_paths=manual_gaps,
                status="manual_input_required",
            )
        )
    unclear = tuple(signal.id for signal in signals if signal.answer == "unclear")
    if unclear:
        actions.append(
            PilotOutcomeAction(
                priority="low",
                category="review",
                action="Review unclear monetization signals before commercial follow-up.",
                field_paths=unclear,
                status="unclear",
            )
        )
    return tuple(actions)


def _readiness_from_sources(sources: tuple[PilotOutcomeSource, ...]) -> PilotOutcomeReadiness:
    by_id = {source.id: source.status or source.state for source in sources}
    return PilotOutcomeReadiness(
        design_partner_feedback_status=by_id.get("design-partner-feedback-json"),
        pilot_metrics_status=by_id.get("pilot-metrics-json"),
        runtime_card_status=by_id.get("runtime-card-json"),
        evidence_cloud_status=by_id.get("evidence-cloud-dashboard-json"),
        work_item_import_status=by_id.get("work-item-import-bundle-json"),
    )


def _manual_input_gaps(document: dict[str, object] | None) -> tuple[str, ...]:
    if document is None:
        return ()
    gaps: list[str] = []
    for path in (
        "pilot.repo_or_service",
        "pilot.ai_assisted_change_type",
        "feedback.blocked_regression_or_useful_failure",
        "feedback.false_positive_or_noisy_gate",
        "feedback.missing_evidence",
        "feedback.setup_friction",
        "feedback.security_privacy_concern",
        "monetization_signals.hosted_aggregation.reason",
        "monetization_signals.premium_policy_packs.reason",
        "follow_up.summary",
    ):
        if _field(document, path) == _MANUAL_INPUT_REQUIRED:
            gaps.append(path)
    commands = _field(document, "evidence.entroping_commands_run")
    if isinstance(commands, list) and _MANUAL_INPUT_REQUIRED in commands:
        gaps.append("evidence.entroping_commands_run")
    return tuple(gaps)


def _monetization_signals(
    document: dict[str, object] | None,
) -> tuple[PilotOutcomeMonetizationSignal, ...]:
    if document is None:
        return ()
    signals: list[PilotOutcomeMonetizationSignal] = []
    for signal_id in ("hosted_aggregation", "premium_policy_packs"):
        answer = _signal_answer(_field(document, f"monetization_signals.{signal_id}.answer"))
        reason = _field(document, f"monetization_signals.{signal_id}.reason")
        signals.append(
            PilotOutcomeMonetizationSignal(
                id=signal_id,
                answer=answer,
                manual_reason_required=reason == _MANUAL_INPUT_REQUIRED,
            )
        )
    return tuple(signals)


def _signal_answer(value: object) -> PilotOutcomeSignalAnswer:
    if value == "yes":
        return "yes"
    if value == "no":
        return "no"
    return "unclear"


def _document_status(
    source_id: PilotOutcomeSourceId,
    document: dict[str, object],
) -> str | None:
    summary_status = _field(document, "summary.status")
    if isinstance(summary_status, str) and summary_status.strip():
        return safe_evidence_text(summary_status).lower()
    if source_id == "design-partner-feedback-json":
        evidence_status = _field(document, "evidence.pilot_metrics_status")
        if isinstance(evidence_status, str):
            return safe_evidence_text(evidence_status).lower()
        return "present"
    return "present"


def _project_from_documents(
    *,
    root: Path,
    documents: Iterable[dict[str, object]],
) -> str:
    for document in documents:
        if isinstance(document, dict):
            project = document.get("project")
            if isinstance(project, str) and project.strip():
                return safe_evidence_text(project)
            pilot = document.get("pilot")
            if isinstance(pilot, dict):
                service = pilot.get("repo_or_service")
                if (
                    isinstance(service, str)
                    and service.strip()
                    and service != _MANUAL_INPUT_REQUIRED
                ):
                    return safe_evidence_text(service)
    return safe_evidence_text(root.name)


def _field(document: dict[str, object], path: str) -> object:
    current: object = document
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return safe_evidence_text(value) if isinstance(value, str) else None


def _parse_document(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _state_from_load_error(load_error: str) -> PilotOutcomeSourceState:
    if load_error in {
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    }:
        return "unsafe"
    return "invalid"


def _render_packet_content(packet: PilotOutcomePacket, *, output: PilotOutcomeOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_pilot_outcome_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(
            raw_path,
            root=root,
            artifact="pilot outcome",
            forbid_components_anywhere=True,
        )
    except SafeWriteError as exc:
        raise PilotOutcomeError(str(exc)) from exc


def _contains_unredacted_pilot_outcome_secret(value: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", value))


def _inline_code(value: str) -> str:
    return safe_evidence_text(value).replace("`", "'")


def _markdown_cell(value: object) -> str:
    return safe_evidence_text(str(value)).replace("|", "\\|").replace("\n", " ")
