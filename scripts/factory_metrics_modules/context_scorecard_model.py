"""Context-tool scorecard comparison and report model builders."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .common import _counter_dict, _safe_report_label
from .context_schema import (
    CONTEXT_SCORECARD_HIGHER_IS_BETTER,
    CONTEXT_SCORECARD_REQUIRED_METRICS,
)
from .context_scorecard_fields import _is_number, _scorecard_metric_value
from .event_schema import CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION


def _compare_metric(
    metric: str,
    value: int | float,
    baseline_value: int | float,
) -> str:
    if value == baseline_value:
        return "unchanged"
    if metric in CONTEXT_SCORECARD_HIGHER_IS_BETTER:
        return "improved" if value > baseline_value else "regressed"
    return "improved" if value < baseline_value else "regressed"


def _compare_context_tool_trial(trial: dict[str, Any]) -> dict[str, Any]:
    metrics = trial.get("metrics")
    baseline_metrics = trial.get("baseline_metrics")
    improved_metrics: list[str] = []
    regressed_metrics: list[str] = []
    unchanged_metrics: list[str] = []
    deltas: dict[str, int | float] = {}

    if not isinstance(metrics, dict) or not isinstance(baseline_metrics, dict):
        metrics = {}
        baseline_metrics = {}

    for metric in CONTEXT_SCORECARD_REQUIRED_METRICS:
        value = _scorecard_metric_value(metrics.get(metric))
        baseline_value = _scorecard_metric_value(baseline_metrics.get(metric))
        if value is None or baseline_value is None:
            continue
        deltas[metric] = value - baseline_value
        comparison = _compare_metric(metric, value, baseline_value)
        if comparison == "improved":
            improved_metrics.append(metric)
        elif comparison == "regressed":
            regressed_metrics.append(metric)
        else:
            unchanged_metrics.append(metric)

    return {
        "issue": _safe_report_label(trial.get("issue")) or "unknown",
        "packet_type": _safe_report_label(trial.get("packet_type")) or "unknown",
        "workflow": _safe_report_label(trial.get("workflow")) or "unknown",
        "baseline_workflow": (_safe_report_label(trial.get("baseline_workflow")) or "unknown"),
        "improvement_count": len(improved_metrics),
        "regression_count": len(regressed_metrics),
        "improved_metrics": improved_metrics,
        "regressed_metrics": regressed_metrics,
        "unchanged_metrics": unchanged_metrics,
        "deltas": deltas,
    }


def _context_tool_missing_metrics(evaluation: dict[str, Any]) -> list[str]:
    missing: set[str] = set()
    trials = evaluation.get("trials")
    if not isinstance(trials, list):
        return list(CONTEXT_SCORECARD_REQUIRED_METRICS)

    for trial in trials:
        if not isinstance(trial, dict):
            missing.update(CONTEXT_SCORECARD_REQUIRED_METRICS)
            continue
        for field in ("metrics", "baseline_metrics"):
            metrics = trial.get(field)
            if not isinstance(metrics, dict):
                missing.update(CONTEXT_SCORECARD_REQUIRED_METRICS)
                continue
            for metric in CONTEXT_SCORECARD_REQUIRED_METRICS:
                if metric not in metrics:
                    missing.add(metric)

    return sorted(missing)


def _context_tool_source_counts(evaluation: dict[str, Any]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    evidence_sources = evaluation.get("evidence_sources")
    if isinstance(evidence_sources, list):
        for source in evidence_sources:
            if not isinstance(source, dict):
                continue
            source_type = _safe_report_label(source.get("source_type"))
            if source_type is not None:
                counter[source_type] += 1
    return _counter_dict(counter)


def _context_tool_setup_entry(evaluation: dict[str, Any]) -> dict[str, Any]:
    setup = evaluation.get("setup")
    if not isinstance(setup, dict):
        return {
            "status": "not_recorded",
            "duration_seconds": None,
            "command": None,
            "failure_reason": None,
        }

    duration_seconds = setup.get("duration_seconds")
    if duration_seconds is not None and not _is_number(duration_seconds):
        duration_seconds = None

    return {
        "status": _safe_report_label(setup.get("status")) or "unknown",
        "duration_seconds": duration_seconds,
        "command": _safe_report_label(setup.get("command")),
        "failure_reason": _safe_report_label(setup.get("failure_reason")),
    }


def _best_context_trial(
    trial_comparisons: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not trial_comparisons:
        return None
    return max(
        trial_comparisons,
        key=lambda trial: (
            int(trial["improvement_count"]),
            -int(trial["regression_count"]),
            str(trial["issue"]),
        ),
    )


def _context_tool_report_entry(evaluation: dict[str, Any]) -> dict[str, Any]:
    trials = evaluation.get("trials")
    valid_trials = (
        [trial for trial in trials if isinstance(trial, dict)] if isinstance(trials, list) else []
    )
    trial_comparisons = [_compare_context_tool_trial(trial) for trial in valid_trials]
    best_trial = _best_context_trial(trial_comparisons)

    return {
        "tool": _safe_report_label(evaluation.get("tool")) or "unknown",
        "tool_layer": _safe_report_label(evaluation.get("tool_layer")) or "unknown",
        "proof_status": (_safe_report_label(evaluation.get("proof_status")) or "unknown"),
        "status_before": (_safe_report_label(evaluation.get("status_before")) or "unknown"),
        "recommended_status": (
            _safe_report_label(evaluation.get("recommended_status")) or "unknown"
        ),
        "trial_count": len(valid_trials),
        "setup": _context_tool_setup_entry(evaluation),
        "evidence_count": len(evaluation.get("evidence_sources", []))
        if isinstance(evaluation.get("evidence_sources"), list)
        else 0,
        "source_type_counts": _context_tool_source_counts(evaluation),
        "missing_required_metrics": _context_tool_missing_metrics(evaluation),
        "trials": trial_comparisons,
        "strongest_improvement_count": int(best_trial["improvement_count"]) if best_trial else 0,
        "strongest_regression_count": int(best_trial["regression_count"]) if best_trial else 0,
        "best_trial": best_trial,
    }


def _context_scorecard_report(scorecard: dict[str, Any]) -> dict[str, Any]:
    tool_entries = [
        _context_tool_report_entry(evaluation)
        for evaluation in scorecard.get("tool_evaluations", [])
        if isinstance(evaluation, dict)
    ]
    recommendations = Counter(str(entry["recommended_status"]) for entry in tool_entries)
    proof_statuses = Counter(str(entry["proof_status"]) for entry in tool_entries)
    setup_statuses = Counter(str(entry["setup"]["status"]) for entry in tool_entries)
    baseline = scorecard.get("baseline", {})
    baseline_components = baseline.get("components") if isinstance(baseline, dict) else []

    return {
        "schema_version": CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION,
        "scorecard_id": _safe_report_label(scorecard.get("scorecard_id")) or "unknown",
        "baseline": _safe_report_label(baseline.get("name"))
        if isinstance(baseline, dict)
        else "unknown",
        "baseline_components": baseline_components if isinstance(baseline_components, list) else [],
        "required_metrics": list(CONTEXT_SCORECARD_REQUIRED_METRICS),
        "total_tools": len(tool_entries),
        "total_trials": sum(int(entry["trial_count"]) for entry in tool_entries),
        "tools_by_recommendation": _counter_dict(recommendations),
        "tools_by_proof_status": _counter_dict(proof_statuses),
        "tools_by_setup_status": _counter_dict(setup_statuses),
        "tools": tool_entries,
    }
