"""Markdown rendering for context-tool scorecard reports."""

from __future__ import annotations

from typing import Any

from .common import _markdown_cell


def _render_context_scorecard_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Context Tool Scorecard Report",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Scorecard: `{report['scorecard_id']}`",
        f"- Baseline: {report['baseline']}",
        f"- Total tools: {report['total_tools']}",
        f"- Total trials: {report['total_trials']}",
        "",
        "## Baseline Components",
        "",
    ]
    lines.extend(f"- `{component}`" for component in report["baseline_components"])
    lines.extend(
        [
            "",
            "## Tool Decisions",
            "",
            "| Tool | Setup | Proof | Recommendation | Trials | Evidence | Best issue | "
            + "Improvements | Regressions | Improved metrics |",
            "| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )

    for tool in report["tools"]:
        best_trial = tool["best_trial"] if isinstance(tool["best_trial"], dict) else {}
        setup = tool["setup"] if isinstance(tool["setup"], dict) else {}
        row = [
            tool["tool"],
            setup.get("status", "not_recorded"),
            tool["proof_status"],
            tool["recommended_status"],
            tool["trial_count"],
            tool["evidence_count"],
            best_trial.get("issue", "-"),
            tool["strongest_improvement_count"],
            tool["strongest_regression_count"],
            ", ".join(best_trial.get("improved_metrics", [])) or "-",
        ]
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")

    lines.extend(
        [
            "",
            "## Trial Comparisons",
            "",
            "| Tool | Issue | Workflow | Improvements | Regressions | "
            + "Improved metrics | Regressed metrics |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for tool in report["tools"]:
        for trial in tool["trials"]:
            row = [
                tool["tool"],
                trial["issue"],
                trial["workflow"],
                trial["improvement_count"],
                trial["regression_count"],
                ", ".join(trial["improved_metrics"]) or "-",
                ", ".join(trial["regressed_metrics"]) or "-",
            ]
            lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")

    lines.append("")
    return "\n".join(lines)
