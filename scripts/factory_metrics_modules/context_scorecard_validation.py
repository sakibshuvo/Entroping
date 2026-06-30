"""Top-level validation for context-tool scorecards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import FactoryMetricsError
from .context_schema import (
    CONTEXT_SCORECARD_ALLOWED_KEYS,
    CONTEXT_SCORECARD_BASELINE_KEYS,
    CONTEXT_SCORECARD_EVALUATION_KEYS,
    CONTEXT_SCORECARD_PROOF_STATUSES,
    CONTEXT_SCORECARD_RECOMMENDATIONS,
    CONTEXT_SCORECARD_REQUIRED_BASELINE_COMPONENTS,
)
from .context_scorecard_fields import (
    _validate_context_scorecard_evidence,
    _validate_context_scorecard_setup,
    _validate_context_scorecard_trial,
    _validate_scorecard_string_list,
    _validate_scorecard_text,
)
from .event_schema import CONTEXT_SCORECARD_SCHEMA_VERSION


def _load_context_scorecard(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FactoryMetricsError(f"scorecard input is invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise FactoryMetricsError("scorecard input must be a JSON object")
    return value


def _context_trial_improvement_count(trial: object) -> int:
    if not isinstance(trial, dict):
        return 0
    metrics = trial.get("metrics")
    baseline_metrics = trial.get("baseline_metrics")
    if not isinstance(metrics, dict) or not isinstance(baseline_metrics, dict):
        return 0
    from .context_scorecard_model import _compare_context_tool_trial

    comparison = _compare_context_tool_trial(trial)
    return int(comparison["improvement_count"])


def _validate_context_scorecard_evaluation(
    evaluation: object,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(evaluation, dict):
        errors.append(f"{path} must be an object")
        return

    for key in sorted(set(evaluation) - CONTEXT_SCORECARD_EVALUATION_KEYS):
        errors.append(f"{path}.{key} is not supported")

    for field in ("tool", "tool_layer", "status_before"):
        _validate_scorecard_text(evaluation.get(field), f"{path}.{field}", errors)

    proof_status = evaluation.get("proof_status")
    _validate_scorecard_text(proof_status, f"{path}.proof_status", errors)
    if isinstance(proof_status, str) and proof_status not in CONTEXT_SCORECARD_PROOF_STATUSES:
        errors.append(f"{path}.proof_status is not supported")

    recommended_status = evaluation.get("recommended_status")
    _validate_scorecard_text(
        recommended_status,
        f"{path}.recommended_status",
        errors,
    )
    if (
        isinstance(recommended_status, str)
        and recommended_status not in CONTEXT_SCORECARD_RECOMMENDATIONS
    ):
        errors.append(f"{path}.recommended_status is not supported")

    _validate_context_scorecard_setup(evaluation.get("setup"), f"{path}.setup", errors)
    _validate_context_scorecard_evidence(
        evaluation.get("evidence_sources"),
        f"{path}.evidence_sources",
        errors,
    )

    trials = evaluation.get("trials")
    if not isinstance(trials, list):
        errors.append(f"{path}.trials must be a list")
        trials = []
    for index, trial in enumerate(trials):
        _validate_context_scorecard_trial(trial, f"{path}.trials[{index}]", errors)

    if proof_status == "measured" and not trials:
        errors.append(f"{path}.proof_status measured requires at least one trial")
    if recommended_status == "active" and not trials:
        errors.append(f"{path} cannot recommend active without measured trials")
    elif recommended_status == "active":
        best_improvement_count = max(
            (_context_trial_improvement_count(trial) for trial in trials),
            default=0,
        )
        if best_improvement_count < 2:
            errors.append(
                f"{path} cannot recommend active without at least two measured improvements"
            )


def _validate_context_tool_scorecard(scorecard: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in sorted(set(scorecard) - CONTEXT_SCORECARD_ALLOWED_KEYS):
        errors.append(f"{key} is not supported")

    if scorecard.get("schema_version") != CONTEXT_SCORECARD_SCHEMA_VERSION:
        errors.append(f"schema_version must be {CONTEXT_SCORECARD_SCHEMA_VERSION}")

    _validate_scorecard_text(scorecard.get("scorecard_id"), "scorecard_id", errors)
    _validate_scorecard_text(scorecard.get("recorded_at"), "recorded_at", errors)

    baseline = scorecard.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("baseline must be an object")
    else:
        for key in sorted(set(baseline) - CONTEXT_SCORECARD_BASELINE_KEYS):
            errors.append(f"baseline.{key} is not supported")
        _validate_scorecard_text(baseline.get("name"), "baseline.name", errors)
        _validate_scorecard_string_list(
            baseline.get("components"),
            "baseline.components",
            errors,
            required_values=CONTEXT_SCORECARD_REQUIRED_BASELINE_COMPONENTS,
        )

    tool_evaluations = scorecard.get("tool_evaluations")
    if not isinstance(tool_evaluations, list) or not tool_evaluations:
        errors.append("tool_evaluations must be a non-empty list")
        return errors

    for index, evaluation in enumerate(tool_evaluations):
        _validate_context_scorecard_evaluation(
            evaluation,
            f"tool_evaluations[{index}]",
            errors,
        )

    return errors
