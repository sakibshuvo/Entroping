"""Local design-partner pilot cohort rollups from explicit outcome packets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence.evidence_index import (
    EvidenceArtifactState,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.evidence.pilot_outcome import (
    PILOT_OUTCOME_SCHEMA_VERSION,
    PilotOutcomePacket,
)
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

PILOT_COHORT_SCHEMA_VERSION: Final = "entroping.pilot-cohort.v1"
PILOT_COHORT_MANIFEST_SCHEMA_VERSION: Final = "entroping.pilot-cohort-manifest.v1"

PilotCohortOutput = Literal["md", "json"]
PilotCohortStatus = Literal["ready", "partial", "insufficient"]
PilotCohortSourceState = EvidenceArtifactState
PilotCohortPriority = Literal["high", "medium", "low"]
PilotCohortActionCategory = Literal["generate", "repair", "collect", "review"]
PilotCohortSignalId = Literal["hosted_aggregation", "premium_policy_packs"]
PilotCohortReadinessId = Literal[
    "design_partner_feedback",
    "pilot_metrics",
    "runtime_card",
    "evidence_cloud",
    "work_item_import",
]

_DEFAULT_OUTPUTS: Final[dict[PilotCohortOutput, Path]] = {
    "md": Path("reports") / "pilot-cohort.md",
    "json": Path("reports") / "pilot-cohort.json",
}
_READINESS_SIGNAL_IDS: Final[tuple[PilotCohortReadinessId, ...]] = (
    "design_partner_feedback",
    "pilot_metrics",
    "runtime_card",
    "evidence_cloud",
    "work_item_import",
)
_KNOWN_READINESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"ready", "pass", "partial", "insufficient", "missing", "invalid", "unsafe"}
)
_FORBIDDEN_PATH_COMPONENTS: Final = {".entroping", "envs"}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _ManifestEntry:
    id: str
    path: Path


@dataclass(frozen=True, slots=True)
class _LoadedOutcome:
    source: PilotCohortOutcome
    packet: PilotOutcomePacket | None


@dataclass(frozen=True, slots=True)
class _OutcomeCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int
    ready: int
    partial: int
    insufficient: int
    manual_input_gaps_total: int


@dataclass(frozen=True, slots=True)
class _ActionCounts:
    high: int
    medium: int
    low: int


@dataclass(frozen=True, slots=True)
class _ActionGroups:
    repair: tuple[str, ...]
    generate: tuple[str, ...]
    collect: tuple[str, ...]
    partial_review: tuple[str, ...]


class PilotCohortError(ValueError):
    """Raised when the pilot cohort packet cannot be generated safely."""


class PilotCohortSummary(BaseModel):
    """Aggregate local design-partner pilot cohort state."""

    model_config = ConfigDict(extra="forbid")

    status: PilotCohortStatus
    outcomes_total: int = Field(ge=0)
    outcomes_present: int = Field(ge=0)
    outcomes_missing: int = Field(ge=0)
    outcomes_invalid: int = Field(ge=0)
    outcomes_unsafe: int = Field(ge=0)
    pilots_ready: int = Field(ge=0)
    pilots_partial: int = Field(ge=0)
    pilots_insufficient: int = Field(ge=0)
    manual_input_gaps_total: int = Field(ge=0)
    actions_total: int = Field(ge=0)
    actions_high: int = Field(ge=0)
    actions_medium: int = Field(ge=0)
    actions_low: int = Field(ge=0)


class PilotCohortOutcome(BaseModel):
    """One explicit pilot outcome packet source considered for aggregation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    state: PilotCohortSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    project: str | None = None
    status: PilotCohortStatus | None = None
    manual_input_gaps: int = Field(default=0, ge=0)
    summary: str


class PilotCohortMonetizationSignal(BaseModel):
    """Aggregate monetization signal counts across pilot outcomes."""

    model_config = ConfigDict(extra="forbid")

    id: PilotCohortSignalId
    yes: int = Field(ge=0)
    no: int = Field(ge=0)
    unclear: int = Field(ge=0)


class PilotCohortReadinessSignal(BaseModel):
    """Aggregate value-free readiness status counts across pilot outcomes."""

    model_config = ConfigDict(extra="forbid")

    id: PilotCohortReadinessId
    ready: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    partial: int = Field(ge=0)
    insufficient: int = Field(ge=0)
    missing: int = Field(ge=0)
    invalid: int = Field(ge=0)
    unsafe: int = Field(ge=0)
    other: int = Field(ge=0)


class PilotCohortAction(BaseModel):
    """One local action needed before design-partner cohort review."""

    model_config = ConfigDict(extra="forbid")

    priority: PilotCohortPriority
    category: PilotCohortActionCategory
    action: str
    outcome_ids: tuple[str, ...] = ()
    status: str | None = None


class PilotCohortPacket(BaseModel):
    """Schema-versioned local pilot cohort packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.pilot-cohort.v1"] = PILOT_COHORT_SCHEMA_VERSION
    generated_at: str
    project: str
    manifest_path: str
    summary: PilotCohortSummary
    outcomes: tuple[PilotCohortOutcome, ...]
    monetization_signals: tuple[PilotCohortMonetizationSignal, ...]
    readiness_signals: tuple[PilotCohortReadinessSignal, ...]
    actions: tuple[PilotCohortAction, ...]


@dataclass(frozen=True, slots=True)
class PilotCohortResult:
    """Result of writing a local pilot cohort packet."""

    output_path: Path
    packet: PilotCohortPacket


def run_pilot_cohort_report(
    *,
    project_root: Path,
    manifest: Path,
    output: PilotCohortOutput,
    output_path: Path | None = None,
) -> PilotCohortResult:
    """Write a local design-partner pilot cohort packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported pilot-cohort output: {output}"
        raise PilotCohortError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_pilot_cohort_packet(project_root=root, manifest=manifest)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_pilot_cohort_secret(content):
        msg = "pilot cohort packet contains secret-like content"
        raise PilotCohortError(msg)
    try:
        written = safe_write_text(destination, content, artifact="pilot cohort", root=root)
    except SafeWriteError as exc:
        raise PilotCohortError(str(exc)) from exc
    return PilotCohortResult(output_path=written, packet=packet)


def build_pilot_cohort_packet(*, project_root: Path, manifest: Path) -> PilotCohortPacket:
    """Build a value-free local pilot cohort packet."""

    root = project_root.expanduser().resolve()
    manifest_path = _resolve_manifest_path(manifest, root=root)
    entries = _manifest_entries(manifest_path, root=root)
    loaded = tuple(_load_outcome(entry, root=root) for entry in entries)
    outcomes = tuple(item.source for item in loaded)
    signals = _monetization_signals(loaded)
    readiness = _readiness_signals(loaded)
    actions = _actions(outcomes=outcomes, signals=signals)
    return PilotCohortPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=safe_evidence_text(root.name),
        manifest_path=_relative_path(manifest_path, root=root),
        summary=_summary(outcomes=outcomes, actions=actions, signals=signals),
        outcomes=outcomes,
        monetization_signals=signals,
        readiness_signals=readiness,
        actions=actions,
    )


def render_pilot_cohort_markdown(packet: PilotCohortPacket) -> str:
    """Render a value-free Markdown pilot cohort packet."""

    lines = [
        "# Entroping Pilot Cohort",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Outcomes: `{packet.summary.outcomes_present}/{packet.summary.outcomes_total}` present",
        f"- Pilots: `{packet.summary.pilots_ready}` ready, "
        f"`{packet.summary.pilots_partial}` partial, "
        f"`{packet.summary.pilots_insufficient}` insufficient",
        f"- Manual input gaps: `{packet.summary.manual_input_gaps_total}`",
        "",
        "## Outcomes",
        "",
        "| ID | State | Project | Status | Path | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for outcome in packet.outcomes:
        lines.append(
            "| "
            f"{_md(outcome.id)} | {_md(outcome.state)} | "
            f"{_md(outcome.project or 'n/a')} | {_md(outcome.status or 'n/a')} | "
            f"{_md(outcome.path)} | {_md(outcome.sha256 or 'n/a')} | "
            f"{_md(outcome.summary)} |"
        )
    lines.extend(["", "## Monetization Signals", "", "| Signal | Yes | No | Unclear |"])
    lines.append("| --- | ---: | ---: | ---: |")
    for monetization_signal in packet.monetization_signals:
        lines.append(
            f"| {_md(monetization_signal.id)} | {monetization_signal.yes} | "
            f"{monetization_signal.no} | {monetization_signal.unclear} |"
        )
    lines.extend(
        [
            "",
            "## Readiness Signals",
            "",
            "| Signal | Ready | Pass | Partial | Insufficient | Missing | "
            + "Invalid | Unsafe | Other |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for readiness_signal in packet.readiness_signals:
        lines.append(
            "| "
            f"{_md(readiness_signal.id)} | {readiness_signal.ready} | "
            f"{readiness_signal.pass_count} | {readiness_signal.partial} | "
            f"{readiness_signal.insufficient} | {readiness_signal.missing} | "
            f"{readiness_signal.invalid} | {readiness_signal.unsafe} | "
            f"{readiness_signal.other} |"
        )
    lines.extend(["", "## Actions", "", "| Priority | Category | Action |"])
    lines.append("| --- | --- | --- |")
    for action in packet.actions:
        lines.append(
            "| "
            f"{_md(action.priority)} | {_md(action.category)} | {_md(action.action)} |"
        )
    if not packet.actions:
        lines.append("| low | review | No local pilot cohort action required. |")
    return "\n".join(lines).rstrip() + "\n"


def _manifest_entries(manifest_path: Path, *, root: Path) -> tuple[_ManifestEntry, ...]:
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(manifest_path, root=root)
    if raw_bytes is None:
        msg = f"Could not read pilot cohort manifest: {load_error}"
        raise PilotCohortError(msg)
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if _contains_unredacted_pilot_cohort_secret(raw_text):
        msg = "pilot cohort manifest contains secret-like content"
        raise PilotCohortError(msg)
    document = _parse_document(raw_text)
    if document is None:
        msg = "pilot cohort manifest must be a JSON object"
        raise PilotCohortError(msg)
    if document.get("schema_version") != PILOT_COHORT_MANIFEST_SCHEMA_VERSION:
        msg = f"pilot cohort manifest schema_version must be {PILOT_COHORT_MANIFEST_SCHEMA_VERSION}"
        raise PilotCohortError(msg)
    outcomes = document.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        msg = "pilot cohort manifest outcomes must be a non-empty list"
        raise PilotCohortError(msg)
    entries: list[_ManifestEntry] = []
    for index, item in enumerate(outcomes, start=1):
        if not isinstance(item, dict):
            msg = "pilot cohort manifest outcome entries must be objects"
            raise PilotCohortError(msg)
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            msg = "pilot cohort manifest outcome entries require path"
            raise PilotCohortError(msg)
        raw_id = item.get("id")
        entry_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else f"outcome-{index}"
        entries.append(
            _ManifestEntry(
                id=safe_evidence_text(entry_id),
                path=Path(raw_path),
            )
        )
    return tuple(entries)


def _load_outcome(entry: _ManifestEntry, *, root: Path) -> _LoadedOutcome:
    candidate, unsafe_summary = _resolve_source_path(entry.path, root=root)
    if unsafe_summary is not None:
        return _loaded_source(
            entry,
            path=entry.path,
            root=root,
            state="unsafe",
            summary=unsafe_summary,
        )
    if not candidate.exists():
        return _loaded_source(entry, path=candidate, root=root, state="missing", summary="missing")
    raw_bytes, load_error = read_local_evidence_json_artifact_bytes(candidate, root=root)
    if raw_bytes is None:
        return _loaded_source(
            entry,
            path=candidate,
            root=root,
            state=_state_from_load_error(load_error),
            summary=load_error,
        )
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if _contains_unredacted_pilot_cohort_secret(raw_text):
        return _loaded_source(
            entry,
            path=candidate,
            root=root,
            state="unsafe",
            summary="secret-like content",
        )
    document = _parse_document(raw_text)
    if document is None:
        return _loaded_source(
            entry,
            path=candidate,
            root=root,
            state="invalid",
            summary="invalid JSON",
        )
    if document.get("schema_version") != PILOT_OUTCOME_SCHEMA_VERSION:
        return _loaded_source(
            entry,
            path=candidate,
            root=root,
            state="invalid",
            schema_version=_schema_version(document),
            summary="schema mismatch",
        )
    try:
        packet = PilotOutcomePacket.model_validate(document)
    except ValidationError:
        return _loaded_source(
            entry,
            path=candidate,
            root=root,
            state="invalid",
            schema_version=_schema_version(document),
            summary="schema validation failed",
        )
    source = PilotCohortOutcome(
        id=entry.id,
        path=_relative_path(candidate, root=root),
        state="present",
        schema_version=PILOT_OUTCOME_SCHEMA_VERSION,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        project=safe_evidence_text(packet.project),
        status=packet.summary.status,
        manual_input_gaps=packet.summary.manual_input_gaps,
        summary=packet.summary.status,
    )
    return _LoadedOutcome(source=source, packet=packet)


def _loaded_source(
    entry: _ManifestEntry,
    *,
    path: Path,
    root: Path,
    state: PilotCohortSourceState,
    summary: str,
    schema_version: str | None = None,
) -> _LoadedOutcome:
    return _LoadedOutcome(
        source=PilotCohortOutcome(
            id=entry.id,
            path=_relative_path(path, root=root),
            state=state,
            schema_version=safe_evidence_text(schema_version) if schema_version else None,
            sha256=None,
            project=None,
            status=None,
            manual_input_gaps=0,
            summary=safe_evidence_text(summary),
        ),
        packet=None,
    )


def _summary(
    *,
    outcomes: tuple[PilotCohortOutcome, ...],
    actions: tuple[PilotCohortAction, ...],
    signals: tuple[PilotCohortMonetizationSignal, ...],
) -> PilotCohortSummary:
    outcome_counts = _outcome_counts(outcomes)
    action_counts = _action_counts(actions)
    return PilotCohortSummary(
        status=_status(outcomes=outcomes, signals=signals),
        outcomes_total=len(outcomes),
        outcomes_present=outcome_counts.present,
        outcomes_missing=outcome_counts.missing,
        outcomes_invalid=outcome_counts.invalid,
        outcomes_unsafe=outcome_counts.unsafe,
        pilots_ready=outcome_counts.ready,
        pilots_partial=outcome_counts.partial,
        pilots_insufficient=outcome_counts.insufficient,
        manual_input_gaps_total=outcome_counts.manual_input_gaps_total,
        actions_total=len(actions),
        actions_high=action_counts.high,
        actions_medium=action_counts.medium,
        actions_low=action_counts.low,
    )


def _outcome_counts(outcomes: tuple[PilotCohortOutcome, ...]) -> _OutcomeCounts:
    return _OutcomeCounts(
        present=sum(1 for outcome in outcomes if outcome.state == "present"),
        missing=sum(1 for outcome in outcomes if outcome.state == "missing"),
        invalid=sum(1 for outcome in outcomes if outcome.state == "invalid"),
        unsafe=sum(1 for outcome in outcomes if outcome.state == "unsafe"),
        ready=sum(1 for outcome in outcomes if outcome.status == "ready"),
        partial=sum(1 for outcome in outcomes if outcome.status == "partial"),
        insufficient=sum(1 for outcome in outcomes if outcome.status == "insufficient"),
        manual_input_gaps_total=sum(outcome.manual_input_gaps for outcome in outcomes),
    )


def _action_counts(actions: tuple[PilotCohortAction, ...]) -> _ActionCounts:
    return _ActionCounts(
        high=sum(1 for action in actions if action.priority == "high"),
        medium=sum(1 for action in actions if action.priority == "medium"),
        low=sum(1 for action in actions if action.priority == "low"),
    )


def _status(
    *,
    outcomes: tuple[PilotCohortOutcome, ...],
    signals: tuple[PilotCohortMonetizationSignal, ...],
) -> PilotCohortStatus:
    if any(outcome.state in {"invalid", "unsafe"} for outcome in outcomes):
        return "insufficient"
    if any(outcome.state == "missing" for outcome in outcomes):
        return "insufficient"
    if any(outcome.status in {"partial", "insufficient"} for outcome in outcomes):
        return "partial"
    if any(signal.unclear > 0 for signal in signals):
        return "partial"
    return "ready"


def _monetization_signals(
    loaded: tuple[_LoadedOutcome, ...],
) -> tuple[PilotCohortMonetizationSignal, ...]:
    return (
        _monetization_signal("hosted_aggregation", loaded),
        _monetization_signal("premium_policy_packs", loaded),
    )


def _monetization_signal(
    signal_id: PilotCohortSignalId,
    loaded: tuple[_LoadedOutcome, ...],
) -> PilotCohortMonetizationSignal:
    answers = [
        signal.answer
        for item in loaded
        if item.packet is not None
        for signal in item.packet.monetization_signals
        if signal.id == signal_id
    ]
    return PilotCohortMonetizationSignal(
        id=signal_id,
        yes=sum(1 for answer in answers if answer == "yes"),
        no=sum(1 for answer in answers if answer == "no"),
        unclear=sum(1 for answer in answers if answer == "unclear"),
    )


def _readiness_signals(
    loaded: tuple[_LoadedOutcome, ...],
) -> tuple[PilotCohortReadinessSignal, ...]:
    return tuple(
        _readiness_signal(readiness_id, loaded)
        for readiness_id in _READINESS_SIGNAL_IDS
    )


def _readiness_signal(
    readiness_id: PilotCohortReadinessId,
    loaded: tuple[_LoadedOutcome, ...],
) -> PilotCohortReadinessSignal:
    statuses = tuple(
        _readiness_status(item.packet, readiness_id)
        for item in loaded
        if item.packet is not None
    )
    return PilotCohortReadinessSignal(
        id=readiness_id,
        ready=sum(1 for status in statuses if status == "ready"),
        pass_count=sum(1 for status in statuses if status == "pass"),
        partial=sum(1 for status in statuses if status == "partial"),
        insufficient=sum(1 for status in statuses if status == "insufficient"),
        missing=sum(1 for status in statuses if status == "missing"),
        invalid=sum(1 for status in statuses if status == "invalid"),
        unsafe=sum(1 for status in statuses if status == "unsafe"),
        other=sum(
            1
            for status in statuses
            if status is not None and status not in _KNOWN_READINESS_STATUSES
        ),
    )


def _readiness_status(
    packet: PilotOutcomePacket,
    readiness_id: PilotCohortReadinessId,
) -> str | None:
    readiness = packet.pilot_evidence_readiness
    mapping = {
        "design_partner_feedback": readiness.design_partner_feedback_status,
        "pilot_metrics": readiness.pilot_metrics_status,
        "runtime_card": readiness.runtime_card_status,
        "evidence_cloud": readiness.evidence_cloud_status,
        "work_item_import": readiness.work_item_import_status,
    }
    status = mapping[readiness_id]
    return safe_evidence_text(status).lower() if isinstance(status, str) else None


def _actions(
    *,
    outcomes: tuple[PilotCohortOutcome, ...],
    signals: tuple[PilotCohortMonetizationSignal, ...],
) -> tuple[PilotCohortAction, ...]:
    actions: list[PilotCohortAction] = []
    groups = _action_groups(outcomes)
    if groups.repair:
        actions.append(
            PilotCohortAction(
                priority="high",
                category="repair",
                action="Repair invalid or unsafe pilot outcome packets before cohort review.",
                outcome_ids=groups.repair,
                status="repair_required",
            )
        )
    if groups.generate:
        actions.append(
            PilotCohortAction(
                priority="medium",
                category="generate",
                action="Generate missing pilot outcome packets before cohort review.",
                outcome_ids=groups.generate,
                status="missing",
            )
        )
    if groups.collect:
        actions.append(
            PilotCohortAction(
                priority="medium",
                category="collect",
                action="Collect sanitized manual inputs for partial pilot outcomes.",
                outcome_ids=groups.collect,
                status="manual_input_required",
            )
        )
    if groups.partial_review:
        actions.append(
            PilotCohortAction(
                priority="medium",
                category="review",
                action="Review partial or insufficient pilot outcomes before commercial follow-up.",
                outcome_ids=groups.partial_review,
                status="partial",
            )
        )
    if any(signal.unclear > 0 for signal in signals):
        actions.append(
            PilotCohortAction(
                priority="low",
                category="review",
                action="Review unclear monetization signals before commercial follow-up.",
                status="unclear",
            )
        )
    return tuple(actions)


def _action_groups(outcomes: tuple[PilotCohortOutcome, ...]) -> _ActionGroups:
    return _ActionGroups(
        repair=tuple(
            outcome.id for outcome in outcomes if outcome.state in {"invalid", "unsafe"}
        ),
        generate=tuple(outcome.id for outcome in outcomes if outcome.state == "missing"),
        collect=tuple(
            outcome.id
            for outcome in outcomes
            if outcome.state == "present" and outcome.manual_input_gaps > 0
        ),
        partial_review=tuple(
            outcome.id
            for outcome in outcomes
            if outcome.state == "present" and outcome.status in {"partial", "insufficient"}
        ),
    )


def _resolve_manifest_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "pilot cohort manifest path must stay under the project root"
        raise PilotCohortError(msg) from exc
    if symlink_path is not None:
        msg = "pilot cohort manifest path contains a symlinked component"
        raise PilotCohortError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "pilot cohort manifest path must stay under the project root"
        raise PilotCohortError(msg) from exc
    if any(part.lower() in _FORBIDDEN_PATH_COMPONENTS for part in relative_parts):
        msg = "pilot cohort manifest must not be read from .entroping or envs"
        raise PilotCohortError(msg)
    return resolved


def _resolve_source_path(raw_path: Path, *, root: Path) -> tuple[Path, str | None]:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return path.resolve(strict=False), "path outside project"
    if symlink_path is not None:
        return path.resolve(strict=False), "symlinked path component"
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError:
        return resolved, "path outside project"
    if any(part.lower() in _FORBIDDEN_PATH_COMPONENTS for part in relative_parts):
        return resolved, "path in forbidden directory"
    return resolved, None


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "pilot cohort output path must stay under the project root"
        raise PilotCohortError(msg) from exc
    if symlink_path is not None:
        msg = "pilot cohort output path contains a symlinked component"
        raise PilotCohortError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "pilot cohort output path must stay under the project root"
        raise PilotCohortError(msg) from exc
    if any(part.lower() in _FORBIDDEN_PATH_COMPONENTS for part in relative_parts):
        msg = "pilot cohort must not be written into .entroping or envs"
        raise PilotCohortError(msg)
    return resolved


def _state_from_load_error(load_error: str) -> PilotCohortSourceState:
    if load_error in {
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    }:
        return "unsafe"
    return "invalid"


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return safe_evidence_text(value) if isinstance(value, str) else None


def _parse_document(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _render_packet_content(packet: PilotCohortPacket, *, output: PilotCohortOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_pilot_cohort_markdown(packet)


def _contains_unredacted_pilot_cohort_secret(value: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", value))


def _relative_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _md(value: object) -> str:
    return safe_evidence_text(str(value)).replace("|", "\\|").replace("\n", " ")
