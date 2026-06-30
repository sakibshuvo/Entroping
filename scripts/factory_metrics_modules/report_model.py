"""Per-issue report aggregation for factory metrics events."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .common import _counter_dict, _safe_report_label, _unknown_safe_report_label
from .schema import ALL_METRICS, REPORT_SCHEMA_VERSION


def _empty_metric_totals() -> dict[str, int | float]:
    return {metric: 0 for metric in ALL_METRICS}


def _add_metrics(target: dict[str, int | float], metrics: object) -> None:
    if not isinstance(metrics, dict):
        return
    for metric in ALL_METRICS:
        value = metrics.get(metric)
        if isinstance(value, (int, float)):
            target[metric] += value


def _issue_label(event: dict[str, Any]) -> str:
    issue = _safe_report_label(event.get("issue"))
    if issue is not None:
        return issue
    return "unassigned"


def _provider_model_label(event: dict[str, Any]) -> str | None:
    provider = _safe_report_label(event.get("provider"))
    model = _safe_report_label(event.get("model"))
    if provider is not None and model is not None:
        return f"{provider}/{model}"
    return None


def _report_bucket(issue: str) -> dict[str, Any]:
    return {
        "issue": issue,
        "events": 0,
        "metrics": _empty_metric_totals(),
        "event_types": Counter(),
        "roles": Counter(),
        "agents": Counter(),
        "providers": Counter(),
        "models": Counter(),
        "provider_models": Counter(),
        "outcomes": Counter(),
        "decisions": Counter(),
        "model_comparison": {},
    }


def _record_model_comparison(
    bucket: dict[str, Any],
    event: dict[str, Any],
    *,
    issue: str,
) -> None:
    role = _unknown_safe_report_label(event.get("role"))
    provider_lane = _unknown_safe_report_label(event.get("provider"))
    model_id = _unknown_safe_report_label(event.get("model"))
    key = (issue, role, provider_lane, model_id)
    rows = bucket["model_comparison"]
    if key not in rows:
        rows[key] = {
            "issue": issue,
            "role": role,
            "provider_lane": provider_lane,
            "model_id": model_id,
            "events": 0,
            "metrics": _empty_metric_totals(),
            "known_metric_counts": Counter(),
            "outcomes": Counter(),
            "decisions": Counter(),
        }

    row = rows[key]
    row["events"] += 1
    metrics = event.get("metrics")
    _add_metrics(row["metrics"], metrics)
    if isinstance(metrics, dict):
        for metric in ALL_METRICS:
            if isinstance(metrics.get(metric), (int, float)):
                row["known_metric_counts"][metric] += 1

    for event_field, bucket_field in (
        ("outcome", "outcomes"),
        ("decision", "decisions"),
    ):
        value = _safe_report_label(event.get(event_field))
        if value is not None:
            row[bucket_field][value] += 1


def _record_report_counters(
    bucket: dict[str, Any],
    event: dict[str, Any],
    *,
    comparison_issue: str | None = None,
) -> None:
    bucket["events"] += 1
    _add_metrics(bucket["metrics"], event.get("metrics"))

    for event_field, bucket_field in (
        ("event_type", "event_types"),
        ("role", "roles"),
        ("agent", "agents"),
        ("provider", "providers"),
        ("model", "models"),
        ("outcome", "outcomes"),
        ("decision", "decisions"),
    ):
        value = _safe_report_label(event.get(event_field))
        if value is not None:
            bucket[bucket_field][value] += 1

    provider_model = _provider_model_label(event)
    if provider_model is not None:
        bucket["provider_models"][provider_model] += 1

    _record_model_comparison(
        bucket,
        event,
        issue=comparison_issue or bucket["issue"],
    )


def _finalize_model_comparison(
    rows: dict[tuple[str, str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for key in sorted(rows):
        row = rows[key]
        known_metric_counts = Counter(row["known_metric_counts"])
        unknown_metric_counts = {
            metric: row["events"] - known_metric_counts.get(metric, 0) for metric in ALL_METRICS
        }
        decisions = Counter(row["decisions"])
        accepted = decisions.get("accepted", 0)
        rejected = decisions.get("rejected", 0)
        denominator = accepted + rejected
        accepted_output_ratio = accepted / denominator if denominator else None
        finalized.append(
            {
                "issue": row["issue"],
                "role": row["role"],
                "provider_lane": row["provider_lane"],
                "model_id": row["model_id"],
                "events": row["events"],
                "metrics": row["metrics"],
                "known_metric_counts": {
                    metric: known_metric_counts.get(metric, 0) for metric in ALL_METRICS
                },
                "unknown_metric_counts": unknown_metric_counts,
                "outcomes": _counter_dict(row["outcomes"]),
                "decisions": _counter_dict(decisions),
                "accepted_output_ratio": accepted_output_ratio,
            }
        )
    return finalized


def _finalize_report_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue": bucket["issue"],
        "events": bucket["events"],
        "metrics": bucket["metrics"],
        "event_types": _counter_dict(bucket["event_types"]),
        "roles": _counter_dict(bucket["roles"]),
        "agents": _counter_dict(bucket["agents"]),
        "providers": _counter_dict(bucket["providers"]),
        "models": _counter_dict(bucket["models"]),
        "provider_models": _counter_dict(bucket["provider_models"]),
        "outcomes": _counter_dict(bucket["outcomes"]),
        "decisions": _counter_dict(bucket["decisions"]),
        "model_comparison": _finalize_model_comparison(bucket["model_comparison"]),
    }


def _issue_sort_key(issue: str) -> tuple[bool, str]:
    return issue == "unassigned", issue


def _report(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals = _empty_metric_totals()
    rollups = _report_bucket("all")
    issues: dict[str, dict[str, Any]] = {}

    for event in events:
        issue = _issue_label(event)
        if issue not in issues:
            issues[issue] = _report_bucket(issue)

        _add_metrics(totals, event.get("metrics"))
        _record_report_counters(rollups, event, comparison_issue=issue)
        _record_report_counters(issues[issue], event, comparison_issue=issue)

    finalized_issues = [
        _finalize_report_bucket(issues[issue]) for issue in sorted(issues, key=_issue_sort_key)
    ]
    finalized_rollups = _finalize_report_bucket(rollups)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "total_events": len(events),
        "totals": totals,
        "roles": finalized_rollups["roles"],
        "agents": finalized_rollups["agents"],
        "providers": finalized_rollups["providers"],
        "models": finalized_rollups["models"],
        "provider_models": finalized_rollups["provider_models"],
        "outcomes": finalized_rollups["outcomes"],
        "decisions": finalized_rollups["decisions"],
        "model_comparison": finalized_rollups["model_comparison"],
        "issues": finalized_issues,
    }
