"""Value-free Markdown projection for provider scorecards."""
# ruff: noqa: E501

from __future__ import annotations

from .common import contains_secret_like, markdown_cell
from .errors import FactoryMetricsError
from .provider_scorecard_report_schema import ProviderScorecardReport


def render_provider_scorecard_markdown(report: ProviderScorecardReport) -> str:
    """Render a compact escaped Markdown projection with no evidence values."""

    scorecards = report.scorecards
    lines = [
        "# Provider Scorecard",
        "",
        f"As of: `{markdown_cell(report.as_of)}`",
        "",
        "| Task type | Provider lane | Model | Autonomy tier | Verification lane | Samples | Accepted | Rejected | Inconclusive | Age days | Stale | Drift | Regressions | Reverts | Cost known/unknown/average | Confidence | Manual eligible | Manual promotion |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for entry in scorecards:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                markdown_cell(entry.task_type),
                markdown_cell(entry.provider_lane_id),
                markdown_cell(entry.model_id),
                markdown_cell(entry.autonomy_tier),
                markdown_cell(entry.verification_lane),
                entry.sample_size,
                entry.accepted,
                entry.rejected,
                entry.inconclusive,
                entry.age_days,
                markdown_cell(entry.stale),
                markdown_cell(entry.model_drift_detected),
                entry.later_regressions,
                entry.later_reverts,
                markdown_cell(
                    f"{entry.known_cost_samples}/{entry.unknown_cost_samples}/{entry.average_cost_usd}"
                ),
                markdown_cell(entry.confidence),
                markdown_cell(entry.manual_promotion_eligible),
                markdown_cell(entry.manual_promotion_required),
            )
        )
    content = "\n".join(lines) + "\n"
    if contains_secret_like(content):
        raise FactoryMetricsError("provider scorecard report contains secret-like content")
    return content
