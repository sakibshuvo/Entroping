"""Sanitized design-partner feedback artifact generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence.evidence_bundle import EvidenceBundleReport
from entroping.core.evidence.pilot_metrics import PilotMetricsReport
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.runtime_card import RuntimeCardReport
from entroping.core.safe_write import SafeWriteError, safe_write_text

DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION: Final = "entroping.design-partner-feedback.v1"

DesignPartnerEvidenceBundleStatus = Literal[
    "ready",
    "not_ready",
    "missing",
    "invalid",
    "unsafe",
    "not_collected",
]
DesignPartnerRuntimeCardStatus = Literal[
    "pass",
    "attention",
    "fail",
    "missing",
    "not_collected",
]
DesignPartnerPilotMetricsStatus = Literal[
    "complete",
    "partial",
    "insufficient",
    "missing",
    "invalid",
    "unsafe",
    "not_collected",
]
DesignPartnerPaySignalAnswer = Literal["yes", "no", "unclear"]
_SourceState = Literal["present", "missing", "invalid", "unsafe"]

_DEFAULT_OUTPUT_PATH: Final = Path("reports") / "design-partner-feedback.json"
_EVIDENCE_BUNDLE_PATH: Final = Path("reports") / "evidence-bundle.json"
_RUNTIME_CARD_PATH: Final = Path("reports") / "runtime-card.json"
_PILOT_METRICS_PATH: Final = Path("reports") / "pilot-metrics.json"
_MAX_FEEDBACK_SOURCE_BYTES: Final = 10 * 1024 * 1024
_MANUAL_INPUT_REQUIRED: Final = "manual input required"


class DesignPartnerFeedbackError(ValueError):
    """Raised when a design-partner feedback artifact cannot be written safely."""


class DesignPartnerPilot(BaseModel):
    """Sanitized design-partner pilot context."""

    model_config = ConfigDict(extra="forbid")

    repo_or_service: str = Field(max_length=1000)
    ai_assisted_change_type: str = Field(max_length=1000)


class DesignPartnerEvidence(BaseModel):
    """Value-free local evidence pointers for the feedback artifact."""

    model_config = ConfigDict(extra="forbid")

    entroping_commands_run: tuple[str, ...]
    evidence_bundle_status: DesignPartnerEvidenceBundleStatus
    runtime_card_status: DesignPartnerRuntimeCardStatus
    pilot_metrics_status: DesignPartnerPilotMetricsStatus | None = None
    evidence_paths: tuple[str, ...] = ()


class DesignPartnerFeedbackFields(BaseModel):
    """Manual sanitized feedback categories."""

    model_config = ConfigDict(extra="forbid")

    blocked_regression_or_useful_failure: str | None = Field(
        default=None,
        max_length=1000,
    )
    false_positive_or_noisy_gate: str | None = Field(default=None, max_length=1000)
    missing_evidence: str | None = Field(default=None, max_length=1000)
    setup_friction: str | None = Field(default=None, max_length=1000)
    security_privacy_concern: str | None = Field(default=None, max_length=1000)


class DesignPartnerPaySignal(BaseModel):
    """One value-free monetization signal answer."""

    model_config = ConfigDict(extra="forbid")

    answer: DesignPartnerPaySignalAnswer
    reason: str = Field(max_length=1000)


class DesignPartnerMonetizationSignals(BaseModel):
    """Manual product-learning monetization signals."""

    model_config = ConfigDict(extra="forbid")

    hosted_aggregation: DesignPartnerPaySignal
    premium_policy_packs: DesignPartnerPaySignal


class DesignPartnerFollowUp(BaseModel):
    """Follow-up pointer without embedding private discussion."""

    model_config = ConfigDict(extra="forbid")

    github_issue: str | None = Field(default=None, max_length=120)
    summary: str = Field(max_length=1000)


class DesignPartnerFeedbackReport(BaseModel):
    """Schema-versioned sanitized design-partner feedback artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.design-partner-feedback.v1"] = (
        DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION
    )
    recorded_at: str
    pilot: DesignPartnerPilot
    evidence: DesignPartnerEvidence
    feedback: DesignPartnerFeedbackFields
    monetization_signals: DesignPartnerMonetizationSignals
    follow_up: DesignPartnerFollowUp


@dataclass(frozen=True, slots=True)
class DesignPartnerFeedbackResult:
    """Result of writing one design-partner feedback artifact."""

    output_path: Path
    feedback: DesignPartnerFeedbackReport


def run_design_partner_feedback_report(
    *,
    project_root: Path,
    output_path: Path | None = None,
) -> DesignPartnerFeedbackResult:
    """Write a sanitized local design-partner feedback template artifact."""

    root = project_root.expanduser().resolve()
    feedback = build_design_partner_feedback_report(project_root=root)
    content = json.dumps(feedback.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    try:
        written = safe_write_text(
            output_path or _DEFAULT_OUTPUT_PATH,
            content,
            artifact="design-partner feedback artifact",
            root=root,
        )
    except SafeWriteError as exc:
        raise DesignPartnerFeedbackError(str(exc)) from exc
    return DesignPartnerFeedbackResult(output_path=written, feedback=feedback)


def build_design_partner_feedback_report(*, project_root: Path) -> DesignPartnerFeedbackReport:
    """Build a value-free feedback template from sanitized local report metadata."""

    root = project_root.expanduser().resolve()
    evidence_bundle_status, evidence_bundle_path = _evidence_bundle_status(root)
    runtime_card_status, runtime_card_path = _runtime_card_status(root)
    pilot_metrics_status, pilot_metrics_path = _pilot_metrics_status(root)
    evidence_paths = tuple(
        path
        for path in (evidence_bundle_path, runtime_card_path, pilot_metrics_path)
        if path is not None
    )
    return DesignPartnerFeedbackReport(
        recorded_at=datetime.now(UTC).isoformat(),
        pilot=DesignPartnerPilot(
            repo_or_service=_MANUAL_INPUT_REQUIRED,
            ai_assisted_change_type=_MANUAL_INPUT_REQUIRED,
        ),
        evidence=DesignPartnerEvidence(
            entroping_commands_run=(_MANUAL_INPUT_REQUIRED,),
            evidence_bundle_status=evidence_bundle_status,
            runtime_card_status=runtime_card_status,
            pilot_metrics_status=pilot_metrics_status,
            evidence_paths=evidence_paths,
        ),
        feedback=DesignPartnerFeedbackFields(),
        monetization_signals=DesignPartnerMonetizationSignals(
            hosted_aggregation=DesignPartnerPaySignal(
                answer="unclear",
                reason=_MANUAL_INPUT_REQUIRED,
            ),
            premium_policy_packs=DesignPartnerPaySignal(
                answer="unclear",
                reason=_MANUAL_INPUT_REQUIRED,
            ),
        ),
        follow_up=DesignPartnerFollowUp(
            github_issue=None,
            summary=_MANUAL_INPUT_REQUIRED,
        ),
    )


def _evidence_bundle_status(
    root: Path,
) -> tuple[DesignPartnerEvidenceBundleStatus, str | None]:
    payload, state = _load_json_document(root / _EVIDENCE_BUNDLE_PATH, root=root)
    if state != "present":
        return state, None
    try:
        report = EvidenceBundleReport.model_validate(payload)
    except ValidationError:
        return "invalid", None
    return report.summary.status, _EVIDENCE_BUNDLE_PATH.as_posix()


def _runtime_card_status(root: Path) -> tuple[DesignPartnerRuntimeCardStatus, str | None]:
    payload, state = _load_json_document(root / _RUNTIME_CARD_PATH, root=root)
    if state == "missing":
        return "missing", None
    if state != "present":
        # The feedback schema has no runtime-card invalid/unsafe states.
        return "not_collected", None
    try:
        report = RuntimeCardReport.model_validate(payload)
    except ValidationError:
        return "not_collected", None
    return report.summary.status, _RUNTIME_CARD_PATH.as_posix()


def _pilot_metrics_status(
    root: Path,
) -> tuple[DesignPartnerPilotMetricsStatus, str | None]:
    payload, state = _load_json_document(root / _PILOT_METRICS_PATH, root=root)
    if state != "present":
        return state, None
    try:
        report = PilotMetricsReport.model_validate(payload)
    except ValidationError:
        return "invalid", None
    return report.summary.status, _PILOT_METRICS_PATH.as_posix()


def _load_json_document(
    path: Path,
    *,
    root: Path,
) -> tuple[dict[str, object] | None, _SourceState]:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return None, "unsafe"
    if symlink_path is not None:
        return None, "unsafe"
    if not path.exists():
        return None, "missing"
    if not path.is_file():
        return None, "unsafe"
    try:
        with path.open("rb") as handle:
            raw_content = handle.read(_MAX_FEEDBACK_SOURCE_BYTES + 1)
    except OSError:
        return None, "invalid"
    if len(raw_content) > _MAX_FEEDBACK_SOURCE_BYTES:
        return None, "invalid"
    try:
        payload = json.loads(raw_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"
    if not isinstance(payload, dict):
        return None, "invalid"
    return payload, "present"
