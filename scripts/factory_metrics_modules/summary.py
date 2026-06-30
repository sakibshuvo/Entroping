"""Summary aggregation for factory metrics events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .schema import ALL_METRICS, SUMMARY_SCHEMA_VERSION


def _summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, int | float] = {metric: 0 for metric in ALL_METRICS}
    by_role: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0})
    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0})
    outcomes: Counter[str] = Counter()
    decisions: Counter[str] = Counter()

    for event in events:
        role = str(event.get("role"))
        agent = str(event.get("agent"))
        by_role[role]["events"] += 1
        by_agent[agent]["events"] += 1

        if event.get("outcome"):
            outcomes[str(event["outcome"])] += 1
        if event.get("decision"):
            decisions[str(event["decision"])] += 1

        metrics = event.get("metrics", {})
        if isinstance(metrics, dict):
            for metric in ALL_METRICS:
                value = metrics.get(metric)
                if isinstance(value, (int, float)):
                    totals[metric] += value

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "total_events": len(events),
        "totals": totals,
        "by_role": dict(sorted(by_role.items())),
        "by_agent": dict(sorted(by_agent.items())),
        "outcomes": dict(sorted(outcomes.items())),
        "decisions": dict(sorted(decisions.items())),
    }
