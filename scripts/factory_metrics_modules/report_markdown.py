"""Markdown rendering for factory metrics reports."""

from __future__ import annotations

from typing import Any

from .common import _markdown_cell


def _format_counter_values(values: dict[str, int]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{key}: {value}" for key, value in sorted(values.items()))


def _format_unknown_metric_counts(values: dict[str, int]) -> str:
    unknowns = {key: value for key, value in values.items() if value}
    return _format_counter_values(unknowns)


def _format_ratio(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return "unknown"


def _render_report_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "# Factory Metrics Report",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Total events: {report['total_events']}",
        f"- Estimated tokens: {totals['estimated_tokens']}",
        f"- Cost USD: {totals['cost_usd']:.2f}",
        f"- Duration seconds: {totals['duration_seconds']:.2f}",
        "",
        "| Issue | Events | Estimated tokens | Cost USD | Duration s | "
        + "Files read | Files touched | Tests | Gates | Outcomes | Decisions | "
        + "Roles | Agents | Provider/models |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        + "--- | --- | --- | --- | --- |",
    ]

    for issue in report["issues"]:
        metrics = issue["metrics"]
        row = [
            issue["issue"],
            issue["events"],
            metrics["estimated_tokens"],
            f"{metrics['cost_usd']:.2f}",
            f"{metrics['duration_seconds']:.2f}",
            metrics["files_read"],
            metrics["files_touched"],
            metrics["tests_run"],
            metrics["gates_run"],
            _format_counter_values(issue["outcomes"]),
            _format_counter_values(issue["decisions"]),
            _format_counter_values(issue["roles"]),
            _format_counter_values(issue["agents"]),
            _format_counter_values(issue["provider_models"]),
        ]
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")

    lines.extend(
        [
            "",
            "## Model Comparison",
            "",
            "| Issue | Role | Provider lane | Model ID | Events | Estimated tokens | "
            + "Cost USD | Duration s | Unknown metrics | Outcomes | Decisions | "
            + "Accepted ratio |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: |",
        ]
    )
    for row in report["model_comparison"]:
        metrics = row["metrics"]
        values = [
            row["issue"],
            row["role"],
            row["provider_lane"],
            row["model_id"],
            row["events"],
            metrics["estimated_tokens"],
            f"{metrics['cost_usd']:.2f}",
            f"{metrics['duration_seconds']:.2f}",
            _format_unknown_metric_counts(row["unknown_metric_counts"]),
            _format_counter_values(row["outcomes"]),
            _format_counter_values(row["decisions"]),
            _format_ratio(row["accepted_output_ratio"]),
        ]
        lines.append("| " + " | ".join(_markdown_cell(value) for value in values) + " |")

    lines.append("")
    return "\n".join(lines)
