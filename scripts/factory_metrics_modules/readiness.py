"""Factory issue readiness scorecard aggregation and rendering."""

from __future__ import annotations

from typing import Any

from .common import _markdown_cell, _safe_report_label
from .readiness_markers import (  # noqa: F401
    _event_text_values as _event_text_values,
)
from .readiness_markers import (
    _matched_markers as _matched_markers,
)
from .readiness_markers import (
    _numeric_metric as _numeric_metric,
)
from .readiness_markers import (
    _positive_event as _positive_event,
)
from .readiness_markers import (
    _readiness_context_markers as _readiness_context_markers,
)
from .readiness_markers import (
    _readiness_gate_markers,
)
from .readiness_markers import (
    _readiness_quality_markers as _readiness_quality_markers,
)
from .readiness_markers import (
    _readiness_security_markers as _readiness_security_markers,
)
from .readiness_markers import (
    _readiness_token_markers as _readiness_token_markers,
)
from .readiness_schema import READINESS_GATES, READINESS_MISSING_MESSAGES
from .schema import READINESS_SCHEMA_VERSION


def _readiness_evidence_entry(
    event: dict[str, Any],
    markers: list[str],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "event_id": _safe_report_label(event.get("event_id")) or "unknown",
        "event_type": _safe_report_label(event.get("event_type")) or "unknown",
        "role": _safe_report_label(event.get("role")) or "unknown",
        "agent": _safe_report_label(event.get("agent")) or "unknown",
        "markers": markers,
    }
    provider = _safe_report_label(event.get("provider"))
    model = _safe_report_label(event.get("model"))
    if provider is not None:
        entry["provider"] = provider
    if model is not None:
        entry["model"] = model
    return entry


def _readiness_gate_result(
    events: list[dict[str, Any]],
    gate: str,
) -> dict[str, Any]:
    evidence = []
    for event in events:
        markers = _readiness_gate_markers(event, gate)
        if markers:
            evidence.append(_readiness_evidence_entry(event, markers))

    return {
        "status": "pass" if evidence else "fail",
        "evidence_count": len(evidence),
        "evidence": evidence,
        "missing": [] if evidence else [READINESS_MISSING_MESSAGES[gate]],
    }


def _readiness_report(events: list[dict[str, Any]], issue: str) -> dict[str, Any]:
    issue_events = [event for event in events if _safe_report_label(event.get("issue")) == issue]
    gates = {gate: _readiness_gate_result(issue_events, gate) for gate in READINESS_GATES}
    missing_gates = [gate for gate in READINESS_GATES if gates[gate]["status"] != "pass"]
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "issue": issue,
        "status": "fail" if missing_gates else "pass",
        "events_considered": len(issue_events),
        "required_gates": list(READINESS_GATES),
        "missing_gates": missing_gates,
        "gates": gates,
    }


def _render_readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Factory Readiness Scorecard",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Issue: `{report['issue']}`",
        f"- Status: `{report['status']}`",
        f"- Events considered: {report['events_considered']}",
        "",
        "| Gate | Status | Evidence | Missing |",
        "| --- | --- | ---: | --- |",
    ]

    for gate in report["required_gates"]:
        result = report["gates"][gate]
        missing = "; ".join(result["missing"]) if result["missing"] else "-"
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    gate,
                    result["status"],
                    result["evidence_count"],
                    missing,
                )
            )
            + " |"
        )

    lines.extend(["", "## Evidence", ""])
    for gate in report["required_gates"]:
        result = report["gates"][gate]
        lines.extend([f"### {gate}", ""])
        if not result["evidence"]:
            lines.extend(["- No accepted evidence.", ""])
            continue
        for evidence in result["evidence"]:
            provider = evidence.get("provider")
            model = evidence.get("model")
            provider_model_parts = []
            if provider is not None:
                provider_model_parts.append(f"provider={provider}")
            if model is not None:
                provider_model_parts.append(f"model={model}")
            provider_model = " " + " ".join(provider_model_parts) if provider_model_parts else ""
            markers = ", ".join(evidence["markers"])
            lines.append(
                "- "
                f"`{_markdown_cell(evidence['event_id'])}` "
                f"{_markdown_cell(evidence['event_type'])} "
                f"role={_markdown_cell(evidence['role'])} "
                f"agent={_markdown_cell(evidence['agent'])}"
                f"{_markdown_cell(provider_model)} "
                f"markers={_markdown_cell(markers)}"
            )
        lines.append("")

    return "\n".join(lines)
