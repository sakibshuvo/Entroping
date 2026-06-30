"""Field-level validation helpers for context-tool scorecards."""

from __future__ import annotations

from .common import _contains_control_character, _contains_secret_like
from .context_schema import (
    CONTEXT_SCORECARD_ALLOWED_SOURCE_TYPES,
    CONTEXT_SCORECARD_EVIDENCE_KEYS,
    CONTEXT_SCORECARD_FORBIDDEN_SOURCE_TYPES,
    CONTEXT_SCORECARD_INTEGER_METRICS,
    CONTEXT_SCORECARD_RATE_METRICS,
    CONTEXT_SCORECARD_REQUIRED_METRICS,
    CONTEXT_SCORECARD_SETUP_KEYS,
    CONTEXT_SCORECARD_SETUP_STATUSES,
    CONTEXT_SCORECARD_TRIAL_KEYS,
)
from .event_schema import NOTE_FORBIDDEN_PATTERN


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _scorecard_metric_value(value: object) -> int | float | None:
    return value if _is_number(value) else None


def _validate_scorecard_text(
    value: object,
    path: str,
    errors: list[str],
    *,
    required: bool = True,
) -> None:
    if value is None:
        if required:
            errors.append(f"{path} is required")
        return
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return
    if _contains_control_character(value):
        errors.append(f"{path} must not contain control characters")
    if _contains_secret_like(value):
        errors.append(f"{path} contains unredacted secret-like value")
    if NOTE_FORBIDDEN_PATTERN.search(value):
        errors.append(f"{path} must not contain raw prompt or transcript material")


def _validate_scorecard_string_list(
    value: object,
    path: str,
    errors: list[str],
    *,
    required_values: set[str] | None = None,
) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} must be a non-empty list")
        return

    seen_values: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        _validate_scorecard_text(item, item_path, errors)
        if isinstance(item, str):
            seen_values.add(item)

    if required_values is not None:
        for required_value in sorted(required_values - seen_values):
            errors.append(f"{path} must include {required_value}")


def _validate_context_scorecard_metrics(
    metrics: object,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(metrics, dict):
        errors.append(f"{path} must be an object")
        return

    for key in sorted(set(metrics) - set(CONTEXT_SCORECARD_REQUIRED_METRICS)):
        errors.append(f"{path}.{key} is not a supported metric")

    for metric in CONTEXT_SCORECARD_REQUIRED_METRICS:
        metric_path = f"{path}.{metric}"
        value = metrics.get(metric)
        if value is None:
            errors.append(f"{metric_path} is required")
            continue
        if metric in CONTEXT_SCORECARD_INTEGER_METRICS:
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{metric_path} must be an integer")
                continue
        elif not _is_number(value):
            errors.append(f"{metric_path} must be numeric")
            continue
        if value < 0:
            errors.append(f"{metric_path} must be greater than or equal to 0")
        if metric in CONTEXT_SCORECARD_RATE_METRICS and value > 1:
            errors.append(f"{metric_path} must be between 0 and 1")


def _validate_context_scorecard_evidence(
    evidence_sources: object,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(evidence_sources, list) or not evidence_sources:
        errors.append(f"{path} must not be empty")
        return

    for index, source in enumerate(evidence_sources):
        source_path = f"{path}[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{source_path} must be an object")
            continue
        for key in sorted(set(source) - CONTEXT_SCORECARD_EVIDENCE_KEYS):
            errors.append(f"{source_path}.{key} is not supported")

        source_type = source.get("source_type")
        _validate_scorecard_text(source_type, f"{source_path}.source_type", errors)
        if isinstance(source_type, str):
            if source_type in CONTEXT_SCORECARD_FORBIDDEN_SOURCE_TYPES:
                errors.append(f"{source_path}.source_type {source_type} is not accepted evidence")
            elif source_type not in CONTEXT_SCORECARD_ALLOWED_SOURCE_TYPES:
                errors.append(f"{source_path}.source_type {source_type} is not supported")

        _validate_scorecard_text(source.get("reference"), f"{source_path}.reference", errors)
        _validate_scorecard_text(source.get("summary"), f"{source_path}.summary", errors)


def _validate_context_scorecard_setup(
    setup: object,
    path: str,
    errors: list[str],
) -> None:
    if setup is None:
        return
    if not isinstance(setup, dict):
        errors.append(f"{path} must be an object")
        return

    for key in sorted(set(setup) - CONTEXT_SCORECARD_SETUP_KEYS):
        errors.append(f"{path}.{key} is not supported")

    status = setup.get("status")
    _validate_scorecard_text(status, f"{path}.status", errors)
    if isinstance(status, str) and status not in CONTEXT_SCORECARD_SETUP_STATUSES:
        errors.append(f"{path}.status is not supported")

    duration_seconds = setup.get("duration_seconds")
    if duration_seconds is not None:
        if not _is_number(duration_seconds):
            errors.append(f"{path}.duration_seconds must be numeric")
        elif duration_seconds < 0:
            errors.append(f"{path}.duration_seconds must be greater than or equal to 0")

    _validate_scorecard_text(
        setup.get("command"),
        f"{path}.command",
        errors,
        required=False,
    )
    _validate_scorecard_text(
        setup.get("failure_reason"),
        f"{path}.failure_reason",
        errors,
        required=False,
    )


def _validate_context_scorecard_trial(
    trial: object,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(trial, dict):
        errors.append(f"{path} must be an object")
        return

    for key in sorted(set(trial) - CONTEXT_SCORECARD_TRIAL_KEYS):
        errors.append(f"{path}.{key} is not supported")

    for field in ("issue", "packet_type", "workflow", "baseline_workflow"):
        _validate_scorecard_text(trial.get(field), f"{path}.{field}", errors)
    _validate_scorecard_text(
        trial.get("evidence_summary"),
        f"{path}.evidence_summary",
        errors,
        required=False,
    )
    _validate_context_scorecard_metrics(trial.get("metrics"), f"{path}.metrics", errors)
    _validate_context_scorecard_metrics(
        trial.get("baseline_metrics"),
        f"{path}.baseline_metrics",
        errors,
    )
