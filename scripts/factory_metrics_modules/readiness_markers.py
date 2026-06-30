"""Evidence marker detection for factory issue readiness."""

from __future__ import annotations

from typing import Any

from .common import _safe_report_label
from .readiness_schema import NO_PROVIDER_MARKERS, QUALITY_MARKERS, SECURITY_MARKERS


def _numeric_metric(event: dict[str, Any], metric: str) -> int | float | None:
    metrics = event.get("metrics")
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(metric)
    return value if isinstance(value, (int, float)) else None


def _positive_event(event: dict[str, Any]) -> bool:
    outcome = _safe_report_label(event.get("outcome"))
    decision = _safe_report_label(event.get("decision"))
    return outcome not in {"blocked", "failure", "inconclusive"} and decision not in {
        "escalated",
        "rejected",
    }


def _event_text_values(event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("event_type", "role", "tool", "provider", "model"):
        value = _safe_report_label(event.get(key))
        if value is not None:
            values.append(value)
    for field in ("gates", "checks"):
        raw_values = event.get(field)
        if not isinstance(raw_values, list):
            continue
        for raw_value in raw_values:
            value = _safe_report_label(raw_value)
            if value is not None:
                values.append(value)
    return values


def _matched_markers(event: dict[str, Any], markers: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for value in _event_text_values(event):
        lowered = value.lower()
        if any(marker in lowered for marker in markers):
            matched.append(value)
    return matched


def _readiness_quality_markers(event: dict[str, Any]) -> list[str]:
    markers = _matched_markers(event, QUALITY_MARKERS)
    tests_run = _numeric_metric(event, "tests_run")
    gates_run = _numeric_metric(event, "gates_run")
    if tests_run is not None and tests_run > 0:
        markers.append(f"tests_run:{int(tests_run)}")
    if gates_run is not None and gates_run > 0 and markers:
        markers.append(f"gates_run:{int(gates_run)}")
    if _safe_report_label(event.get("event_type")) == "gate_run" and markers:
        markers.append("event_type:gate_run")
    return sorted(set(markers))


def _readiness_security_markers(event: dict[str, Any]) -> list[str]:
    markers = _matched_markers(event, SECURITY_MARKERS)
    if _safe_report_label(event.get("role")) == "security_agent":
        markers.append("role:security_agent")
    return sorted(set(markers))


def _readiness_context_markers(event: dict[str, Any]) -> list[str]:
    if _safe_report_label(event.get("event_type")) != "context_pack":
        return []
    context_bytes = _numeric_metric(event, "context_bytes")
    estimated_tokens = _numeric_metric(event, "estimated_tokens")
    candidate_files = _numeric_metric(event, "candidate_files")
    files_read = _numeric_metric(event, "files_read")
    if (
        context_bytes is None
        or context_bytes <= 0
        or estimated_tokens is None
        or estimated_tokens <= 0
        or (
            (candidate_files is None or candidate_files <= 0)
            and (files_read is None or files_read <= 0)
        )
    ):
        return []

    markers = [
        "event_type:context_pack",
        f"context_bytes:{int(context_bytes)}",
        f"estimated_tokens:{int(estimated_tokens)}",
    ]
    if candidate_files is not None and candidate_files > 0:
        markers.append(f"candidate_files:{int(candidate_files)}")
    if files_read is not None and files_read > 0:
        markers.append(f"files_read:{int(files_read)}")
    return markers


def _readiness_token_markers(event: dict[str, Any]) -> list[str]:
    markers = _matched_markers(event, NO_PROVIDER_MARKERS)
    if markers:
        return sorted(set(markers))

    estimated_tokens = _numeric_metric(event, "estimated_tokens")
    cost_usd = _numeric_metric(event, "cost_usd")
    provider = _safe_report_label(event.get("provider"))
    model = _safe_report_label(event.get("model"))
    has_provider_model = provider is not None and model is not None
    if (
        estimated_tokens is not None
        and estimated_tokens > 0
        and (has_provider_model or cost_usd is not None)
    ):
        if provider is not None:
            markers.append(f"provider:{provider}")
        if model is not None:
            markers.append(f"model:{model}")
        markers.append(f"estimated_tokens:{int(estimated_tokens)}")
        if cost_usd is not None:
            markers.append(f"cost_usd:{cost_usd:.4f}")
    return sorted(set(markers))


def _readiness_gate_markers(event: dict[str, Any], gate: str) -> list[str]:
    if not _positive_event(event):
        return []
    if gate == "quality":
        return _readiness_quality_markers(event)
    if gate == "security":
        return _readiness_security_markers(event)
    if gate == "context_preservation":
        return _readiness_context_markers(event)
    if gate == "token_cost_efficiency":
        return _readiness_token_markers(event)
    return []
