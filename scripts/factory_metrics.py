#!/usr/bin/env python3
"""Append, validate, and summarize local software-factory metrics."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

EVENT_SCHEMA_VERSION = "entroping.factory-metrics.v1"
SUMMARY_SCHEMA_VERSION = "entroping.factory-metrics-summary.v1"
REPORT_SCHEMA_VERSION = "entroping.factory-metrics-report.v1"
CONTEXT_SCORECARD_SCHEMA_VERSION = "entroping.context-tool-scorecard.v1"
CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION = "entroping.context-tool-scorecard-report.v1"
DEFAULT_LEDGER = Path(".entroping") / "factory-metrics" / "events.jsonl"
FINISHED_ISSUES_DIR = Path(".entroping") / "factory-metrics" / "finished-issues"
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.

ROLES = {
    "product_manager",
    "architect",
    "dev_agent",
    "qa_agent",
    "code_review_agent",
    "security_agent",
    "monitoring_agent",
    "integrator",
}

EVENT_TYPES = {
    "context_pack",
    "graph_probe",
    "worker_job",
    "gate_run",
    "code_review",
    "pr_check",
    "outcome",
}

OUTCOMES = {"success", "failure", "skipped", "blocked", "inconclusive"}
DECISIONS = {"accepted", "rejected", "needs_review", "escalated", "not_applicable"}

INTEGER_METRICS = (
    "context_bytes",
    "estimated_tokens",
    "candidate_files",
    "files_read",
    "files_touched",
    "tests_run",
    "gates_run",
)
FLOAT_METRICS = ("duration_seconds", "cost_usd")
ALL_METRICS = INTEGER_METRICS + FLOAT_METRICS
ALLOWED_METRIC_KEYS = set(ALL_METRICS)
ALLOWED_EVENT_KEYS = {
    "schema_version",
    "event_id",
    "recorded_at",
    "event_type",
    "role",
    "agent",
    "tool",
    "provider",
    "model",
    "issue",
    "pr",
    "worktree",
    "metrics",
    "gates",
    "checks",
    "outcome",
    "decision",
    "note",
}
CONTEXT_SCORECARD_REQUIRED_METRICS = (
    "grounded_file_hit_rate",
    "nonexistent_reference_count",
    "forbidden_scope_incidents",
    "retrieval_precision",
    "retrieval_recall",
    "stale_claim_count",
    "context_recovery_time_seconds",
    "review_correction_count",
    "human_steering_count",
    "accepted_output_ratio",
    "context_bytes",
    "estimated_tokens",
)
CONTEXT_SCORECARD_HIGHER_IS_BETTER = {
    "grounded_file_hit_rate",
    "retrieval_precision",
    "retrieval_recall",
    "accepted_output_ratio",
}
CONTEXT_SCORECARD_RATE_METRICS = {
    "grounded_file_hit_rate",
    "retrieval_precision",
    "retrieval_recall",
    "accepted_output_ratio",
}
CONTEXT_SCORECARD_INTEGER_METRICS = {
    "nonexistent_reference_count",
    "forbidden_scope_incidents",
    "stale_claim_count",
    "review_correction_count",
    "human_steering_count",
    "context_bytes",
    "estimated_tokens",
}
CONTEXT_SCORECARD_RECOMMENDATIONS = {
    "active",
    "optional_manual",
    "probation",
    "discard",
}
CONTEXT_SCORECARD_PROOF_STATUSES = {
    "measured",
    "not_measured",
    "baseline_component",
    "insufficient",
}
CONTEXT_SCORECARD_SETUP_STATUSES = {
    "available",
    "blocked",
    "failed",
    "installed",
    "missing",
    "not_applicable",
}
CONTEXT_SCORECARD_ALLOWED_SOURCE_TYPES = {
    "repo_source",
    "test",
    "github_issue",
    "github_pr",
    "ci_check",
    "decision_registry",
    "adr",
    "curated_markdown",
    "generated_graph",
    "generated_wiki",
    "generated_codegraph",
    "generated_headroom",
    "generated_understand_anything",
    "factory_metrics",
}
CONTEXT_SCORECARD_FORBIDDEN_SOURCE_TYPES = {
    "obsidian_workspace_state",
    "obsidian_plugin_cache",
    "provider_transcript",
    "raw_prompt",
    "raw_traffic",
    "product_runtime_evidence",
}
CONTEXT_SCORECARD_REQUIRED_BASELINE_COMPONENTS = {
    "rg",
    "scripts/context_pack.sh",
    "docs/meta/DECISION_REGISTRY.yaml",
}
CONTEXT_SCORECARD_ALLOWED_KEYS = {
    "schema_version",
    "scorecard_id",
    "recorded_at",
    "baseline",
    "tool_evaluations",
}
CONTEXT_SCORECARD_BASELINE_KEYS = {"name", "components"}
CONTEXT_SCORECARD_EVALUATION_KEYS = {
    "tool",
    "tool_layer",
    "proof_status",
    "status_before",
    "recommended_status",
    "setup",
    "evidence_sources",
    "trials",
}
CONTEXT_SCORECARD_EVIDENCE_KEYS = {"source_type", "reference", "summary"}
CONTEXT_SCORECARD_SETUP_KEYS = {
    "status",
    "duration_seconds",
    "command",
    "failure_reason",
}
CONTEXT_SCORECARD_TRIAL_KEYS = {
    "issue",
    "packet_type",
    "workflow",
    "baseline_workflow",
    "metrics",
    "baseline_metrics",
    "evidence_summary",
}
TEXT_FIELDS = {
    "agent",
    "tool",
    "provider",
    "model",
    "issue",
    "pr",
    "worktree",
    "note",
}
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

SECRET_REDACTIONS = (
    (
        re.compile(
            r"(?i)\b(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]{8,})"
        ),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?key|"
            r"access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|"
            r"password|credential|cookie)[A-Za-z0-9_.-]*)(\s*[:=]\s*)"
            r"([^\s,;]+)"
        ),
        r"\1\2<redacted>",
    ),
    (
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})\b"),
        "<redacted>",
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "<redacted>",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
        "<redacted>",
    ),
)
NOTE_MAX_LENGTH = 512
NOTE_FORBIDDEN_PATTERN = re.compile(
    r"(?i)(\braw[\s_-]+prompt\b|\bprompt[\s_-]+text\b|"
    r"\bprovider[\s_-]+transcript\b|\braw[\s_-]+traffic\b|"
    r"\brequest[\s_-]+body\b|\bresponse[\s_-]+body\b|"
    r"(?<![A-Za-z0-9_])[\"']?(prompt|transcript|stdout|stderr)[\"']?\s*[:=])"
)

class FactoryMetricsError(Exception):
    """User-facing metrics CLI error."""


def _redact_text(value: str | None) -> str | None:
    if value is None:
        return None

    redacted = value
    for pattern, replacement in SECRET_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _contains_secret_like(value: str) -> bool:
    return _redact_text(value) != value


def _contains_control_character(value: str) -> bool:
    return CONTROL_CHARACTER_PATTERN.search(value) is not None


def _validate_note(value: str) -> list[str]:
    errors: list[str] = []
    if len(value) > NOTE_MAX_LENGTH:
        errors.append(f"note must be {NOTE_MAX_LENGTH} characters or fewer")
    if NOTE_FORBIDDEN_PATTERN.search(value):
        errors.append("note must not contain raw prompt or transcript material")
    return errors


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _ensure_no_symlink_components(repo_root: Path, path: Path, subject: str) -> None:
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return

    current = repo_root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise FactoryMetricsError(f"{subject} must not use symlink components")


def _repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()
    return Path(completed.stdout.strip()).resolve()


def _safe_factory_metrics_path(repo_root: Path, raw_path: Path, subject: str) -> Path:
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = _lexical_absolute(path)
    factory_root = _lexical_absolute(repo_root / ".entroping" / "factory-metrics")
    try:
        resolved.relative_to(factory_root)
    except ValueError as exc:
        raise FactoryMetricsError(
            f"{subject} must be under .entroping/factory-metrics/"
        ) from exc
    _ensure_no_symlink_components(repo_root, resolved, subject)
    return resolved


def _safe_ledger_path(repo_root: Path, ledger: str | None) -> Path:
    raw_path = Path(ledger).expanduser() if ledger else DEFAULT_LEDGER
    return _safe_factory_metrics_path(repo_root, raw_path, "ledger path")


def _finished_issues_root(repo_root: Path) -> Path:
    return _lexical_absolute(repo_root / FINISHED_ISSUES_DIR)


def _finished_issue_ledger_label(repo_root: Path, ledger: Path) -> str:
    factory_root = _lexical_absolute(repo_root / ".entroping" / "factory-metrics")
    try:
        return ledger.relative_to(factory_root).as_posix()
    except ValueError:
        return ledger.as_posix()


def _iter_finished_issue_ledgers(repo_root: Path) -> list[Path]:
    archive_root = _finished_issues_root(repo_root)
    if (
        not archive_root.exists()
        or archive_root.is_symlink()
        or not archive_root.is_dir()
    ):
        return []

    ledgers: list[Path] = []
    for current_root, dirnames, filenames in os.walk(archive_root, followlinks=False):
        current = Path(current_root)
        dirnames[:] = sorted(
            dirname for dirname in dirnames if not (current / dirname).is_symlink()
        )
        for filename in sorted(filenames):
            candidate = current / filename
            if (
                candidate.suffix == ".jsonl"
                and not candidate.is_symlink()
                and candidate.is_file()
            ):
                ledgers.append(candidate)

    return sorted(
        ledgers,
        key=lambda ledger: ledger.relative_to(archive_root).as_posix(),
    )


def _load_report_events(
    repo_root: Path, ledger: Path, *, include_finished_issues: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    events, errors = _load_events(ledger)
    if not include_finished_issues:
        return events, errors

    active_ledger = _lexical_absolute(ledger)
    for archived_ledger in _iter_finished_issue_ledgers(repo_root):
        if archived_ledger == active_ledger:
            continue
        label = _finished_issue_ledger_label(repo_root, archived_ledger)
        archived_events, archived_errors = _load_events(
            archived_ledger,
            error_prefix=f"{label}: ",
        )
        events.extend(archived_events)
        errors.extend(archived_errors)

    return events, errors


def _safe_report_path(repo_root: Path, output: str) -> Path:
    return _safe_factory_metrics_path(
        repo_root, Path(output).expanduser(), "report path"
    )


def _safe_context_scorecard_input_path(repo_root: Path, raw_input: str) -> Path:
    raw_path = Path(raw_input).expanduser()
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = _lexical_absolute(path)
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise FactoryMetricsError("scorecard input must be under repo root") from exc
    _ensure_no_symlink_components(repo_root, resolved, "scorecard input")
    if not resolved.is_file():
        raise FactoryMetricsError("scorecard input must be an existing file")
    return resolved


def _resolve_context_file(repo_root: Path, path: str | None) -> Path | None:
    if not path:
        return None
    context_path = Path(path).expanduser()
    if not context_path.is_absolute():
        context_path = repo_root / context_path
    resolved = context_path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise FactoryMetricsError("context file must be under repo root") from exc
    return resolved


def _validate_non_negative(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    for metric in ALL_METRICS:
        value = getattr(args, metric, None)
        if value is not None and value < 0:
            parser.error(
                f"--{metric.replace('_', '-')} must be greater than or equal to 0"
            )


def _context_metrics(
    repo_root: Path, args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[int | None, int | None]:
    context_bytes = args.context_bytes
    estimated_tokens = args.estimated_tokens
    context_file = _resolve_context_file(repo_root, args.context_file)

    if context_file:
        if not context_file.exists() or not context_file.is_file():
            parser.error(f"context file does not exist: {context_file}")
        file_bytes = context_file.read_bytes()
        context_bytes = len(file_bytes)
        if estimated_tokens is None:
            estimated_tokens = max(1, (context_bytes + 3) // 4)

    return context_bytes, estimated_tokens


def _event_from_args(
    repo_root: Path, args: argparse.Namespace, parser: argparse.ArgumentParser
) -> dict[str, Any]:
    _validate_non_negative(args, parser)
    context_bytes, estimated_tokens = _context_metrics(repo_root, args, parser)

    metrics: dict[str, int | float | None] = {
        "context_bytes": context_bytes,
        "estimated_tokens": estimated_tokens,
        "candidate_files": args.candidate_files,
        "files_read": args.files_read,
        "files_touched": args.files_touched,
        "tests_run": args.tests_run,
        "gates_run": args.gates_run,
        "duration_seconds": args.duration_seconds,
        "cost_usd": args.cost_usd,
    }

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "recorded_at": datetime.now(UTC_TZ).isoformat().replace("+00:00", "Z"),
        "event_type": args.event_type,
        "role": args.role,
        "agent": _redact_text(args.agent),
        "tool": _redact_text(args.tool),
        "provider": _redact_text(args.provider),
        "model": _redact_text(args.model),
        "issue": _redact_text(args.issue),
        "pr": _redact_text(args.pr),
        "worktree": _redact_text(args.worktree),
        "metrics": metrics,
        "gates": [_redact_text(item) for item in args.gate],
        "checks": [_redact_text(item) for item in args.check],
        "outcome": args.outcome,
        "decision": args.decision,
        "note": _redact_text(args.note),
    }


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def _load_events(
    path: Path, *, error_prefix: str = ""
) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return events, errors

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(
                    f"{error_prefix}line {line_number}: invalid JSON: {exc.msg}"
                )
                continue
            if not isinstance(value, dict):
                errors.append(
                    f"{error_prefix}line {line_number}: event must be an object"
                )
                continue
            errors.extend(
                f"{error_prefix}line {line_number}: {message}"
                for message in _validate_event(value)
            )
            events.append(value)
    return events, errors


def _validate_event(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in sorted(set(event) - ALLOWED_EVENT_KEYS):
        errors.append(f"unexpected field {key}")

    required = {
        "schema_version",
        "event_id",
        "recorded_at",
        "event_type",
        "role",
        "agent",
        "metrics",
    }
    for key in sorted(required):
        if key not in event:
            errors.append(f"missing {key}")

    if event.get("schema_version") != EVENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVENT_SCHEMA_VERSION}")
    if event.get("role") not in ROLES:
        errors.append("role is not registered")
    if event.get("event_type") not in EVENT_TYPES:
        errors.append("event_type is not supported")
    if event.get("outcome") is not None and event.get("outcome") not in OUTCOMES:
        errors.append("outcome is not supported")
    if event.get("decision") is not None and event.get("decision") not in DECISIONS:
        errors.append("decision is not supported")

    for field in sorted(TEXT_FIELDS):
        value = event.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{field} must be a string")
        elif _contains_control_character(value):
            errors.append(f"{field} must not contain control characters")
        elif _contains_secret_like(value):
            errors.append(f"{field} contains unredacted secret-like value")
        elif field == "note":
            errors.extend(_validate_note(value))

    for field in ("checks", "gates"):
        values = event.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            errors.append(f"{field} must be a list")
            continue
        for index, value in enumerate(values):
            if not isinstance(value, str):
                errors.append(f"{field}[{index}] must be a string")
            elif _contains_control_character(value):
                errors.append(f"{field}[{index}] must not contain control characters")
            elif _contains_secret_like(value):
                errors.append(
                    f"{field}[{index}] contains unredacted secret-like value"
                )

    metrics = event.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
        return errors

    for metric in sorted(set(metrics) - ALLOWED_METRIC_KEYS):
        errors.append(f"unexpected metric {metric}")

    for metric in ALL_METRICS:
        value = metrics.get(metric)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"metrics.{metric} must be numeric")
        elif value < 0:
            errors.append(f"metrics.{metric} must be greater than or equal to 0")

    return errors


def _load_context_scorecard(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FactoryMetricsError(f"scorecard input is invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise FactoryMetricsError("scorecard input must be a JSON object")
    return value


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
                errors.append(
                    f"{source_path}.source_type {source_type} is not accepted evidence"
                )
            elif source_type not in CONTEXT_SCORECARD_ALLOWED_SOURCE_TYPES:
                errors.append(
                    f"{source_path}.source_type {source_type} is not supported"
                )

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
            errors.append(
                f"{path}.duration_seconds must be greater than or equal to 0"
            )

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


def _context_trial_improvement_count(trial: object) -> int:
    if not isinstance(trial, dict):
        return 0
    metrics = trial.get("metrics")
    baseline_metrics = trial.get("baseline_metrics")
    if not isinstance(metrics, dict) or not isinstance(baseline_metrics, dict):
        return 0
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


def _empty_metric_totals() -> dict[str, int | float]:
    return {metric: 0 for metric in ALL_METRICS}


def _add_metrics(
    target: dict[str, int | float], metrics: object
) -> None:
    if not isinstance(metrics, dict):
        return
    for metric in ALL_METRICS:
        value = metrics.get(metric)
        if isinstance(value, (int, float)):
            target[metric] += value


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _safe_report_label(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    redacted = _redact_text(value)
    if not redacted.strip():
        return None
    return redacted


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
    }


def _record_report_counters(bucket: dict[str, Any], event: dict[str, Any]) -> None:
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
        _record_report_counters(rollups, event)
        _record_report_counters(issues[issue], event)

    finalized_issues = [
        _finalize_report_bucket(issues[issue])
        for issue in sorted(issues, key=_issue_sort_key)
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
        "issues": finalized_issues,
    }


def _markdown_cell(value: object) -> str:
    text = str(value)
    escaped = html.escape(text, quote=False)
    return escaped.replace("\n", " ").replace("|", r"\|").replace("`", r"\`")


def _format_counter_values(values: dict[str, int]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{key}: {value}" for key, value in sorted(values.items()))


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
        "Files read | Files touched | Tests | Gates | Outcomes | Decisions | "
        "Roles | Agents | Provider/models |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "--- | --- | --- | --- | --- |",
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

    lines.append("")
    return "\n".join(lines)


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
        "baseline_workflow": (
            _safe_report_label(trial.get("baseline_workflow")) or "unknown"
        ),
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
        [trial for trial in trials if isinstance(trial, dict)]
        if isinstance(trials, list)
        else []
    )
    trial_comparisons = [_compare_context_tool_trial(trial) for trial in valid_trials]
    best_trial = _best_context_trial(trial_comparisons)

    return {
        "tool": _safe_report_label(evaluation.get("tool")) or "unknown",
        "tool_layer": _safe_report_label(evaluation.get("tool_layer")) or "unknown",
        "proof_status": (
            _safe_report_label(evaluation.get("proof_status")) or "unknown"
        ),
        "status_before": (
            _safe_report_label(evaluation.get("status_before")) or "unknown"
        ),
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
        "strongest_improvement_count": int(best_trial["improvement_count"])
        if best_trial
        else 0,
        "strongest_regression_count": int(best_trial["regression_count"])
        if best_trial
        else 0,
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
        "baseline_components": baseline_components
        if isinstance(baseline_components, list)
        else [],
        "required_metrics": list(CONTEXT_SCORECARD_REQUIRED_METRICS),
        "total_tools": len(tool_entries),
        "total_trials": sum(int(entry["trial_count"]) for entry in tool_entries),
        "tools_by_recommendation": _counter_dict(recommendations),
        "tools_by_proof_status": _counter_dict(proof_statuses),
        "tools_by_setup_status": _counter_dict(setup_statuses),
        "tools": tool_entries,
    }


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
            "Improvements | Regressions | Improved metrics |",
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
            "Improved metrics | Regressed metrics |",
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


def _write_report_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return

    for key, value in payload.items():
        print(f"{key}: {value}")


def _append_command(
    repo_root: Path, args: argparse.Namespace, parser: argparse.ArgumentParser
) -> int:
    ledger = _safe_ledger_path(repo_root, args.ledger)
    event = _event_from_args(repo_root, args, parser)
    event_errors = _validate_event(event)
    if event_errors:
        raise FactoryMetricsError("; ".join(event_errors))

    _append_jsonl(ledger, event)
    _print_payload(
        {
            "status": "recorded",
            "ledger_path": str(ledger),
            "event_id": event["event_id"],
            "schema_version": EVENT_SCHEMA_VERSION,
        },
        args.json,
    )
    return 0


def _validate_command(repo_root: Path, args: argparse.Namespace) -> int:
    ledger = _safe_ledger_path(repo_root, args.ledger)
    events, errors = _load_events(ledger)
    payload = {
        "status": "invalid" if errors else "valid",
        "ledger_path": str(ledger),
        "events": len(events),
        "errors": errors,
    }
    _print_payload(payload, args.json)
    return 1 if errors else 0


def _summary_command(repo_root: Path, args: argparse.Namespace) -> int:
    ledger = _safe_ledger_path(repo_root, args.ledger)
    events, errors = _load_events(ledger)
    if errors:
        payload = {
            "status": "invalid",
            "ledger_path": str(ledger),
            "events": len(events),
            "errors": errors,
        }
        _print_payload(payload, args.json)
        return 1
    _print_payload(_summary(events), args.json)
    return 0


def _report_command(repo_root: Path, args: argparse.Namespace) -> int:
    ledger = _safe_ledger_path(repo_root, args.ledger)
    events, errors = _load_report_events(
        repo_root,
        ledger,
        include_finished_issues=args.include_finished_issues,
    )
    if errors:
        payload = {
            "status": "invalid",
            "ledger_path": str(ledger),
            "events": len(events),
            "errors": errors,
        }
        _print_payload(payload, args.format == "json")
        return 1

    report = _report(events)
    if args.format == "json":
        content = json.dumps(report, sort_keys=True)
    else:
        content = _render_report_markdown(report)

    if args.output:
        output_path = _safe_report_path(repo_root, args.output)
        _write_report_output(output_path, content)
        _print_payload(
            {
                "status": "written",
                "output_path": str(output_path),
                "schema_version": REPORT_SCHEMA_VERSION,
            },
            False,
        )
        return 0

    print(content)
    return 0


def _context_scorecard_validate_command(repo_root: Path, args: argparse.Namespace) -> int:
    input_path = _safe_context_scorecard_input_path(repo_root, args.input)
    scorecard = _load_context_scorecard(input_path)
    errors = _validate_context_tool_scorecard(scorecard)
    tool_evaluations = scorecard.get("tool_evaluations")
    payload = {
        "status": "invalid" if errors else "valid",
        "input_path": str(input_path),
        "schema_version": CONTEXT_SCORECARD_SCHEMA_VERSION,
        "tools": len(tool_evaluations) if isinstance(tool_evaluations, list) else 0,
        "errors": errors,
    }
    _print_payload(payload, args.json)
    return 1 if errors else 0


def _context_scorecard_report_command(repo_root: Path, args: argparse.Namespace) -> int:
    input_path = _safe_context_scorecard_input_path(repo_root, args.input)
    scorecard = _load_context_scorecard(input_path)
    errors = _validate_context_tool_scorecard(scorecard)
    if errors:
        payload = {
            "status": "invalid",
            "input_path": str(input_path),
            "schema_version": CONTEXT_SCORECARD_SCHEMA_VERSION,
            "errors": errors,
        }
        _print_payload(payload, args.format == "json")
        return 1

    report = _context_scorecard_report(scorecard)
    if args.format == "json":
        content = json.dumps(report, sort_keys=True)
    else:
        content = _render_context_scorecard_markdown(report)

    if args.output:
        output_path = _safe_report_path(repo_root, args.output)
        _write_report_output(output_path, content)
        _print_payload(
            {
                "status": "written",
                "output_path": str(output_path),
                "schema_version": CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION,
            },
            False,
        )
        return 0

    print(content)
    return 0


def _context_scorecard_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.scorecard_command == "validate":
        return _context_scorecard_validate_command(repo_root, args)
    if args.scorecard_command == "report":
        return _context_scorecard_report_command(repo_root, args)
    raise FactoryMetricsError(f"unsupported context-scorecard command: {args.scorecard_command}")


def _add_common_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", help="JSONL ledger under .entroping/factory-metrics/")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Record local, ignored metrics for Entroping's portable "
            "software-factory workflow."
        )
    )
    parser.add_argument("--repo-root", help="Repository root. Defaults to git root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append = subparsers.add_parser("append", help="Append one metrics event.")
    append.add_argument("--event-type", required=True, choices=sorted(EVENT_TYPES))
    append.add_argument("--role", required=True, choices=sorted(ROLES))
    append.add_argument("--agent", required=True)
    append.add_argument("--tool")
    append.add_argument("--provider")
    append.add_argument("--model")
    append.add_argument("--issue")
    append.add_argument("--pr")
    append.add_argument("--worktree")
    append.add_argument("--context-file")
    append.add_argument("--context-bytes", type=int)
    append.add_argument("--estimated-tokens", type=int)
    append.add_argument("--candidate-files", type=int)
    append.add_argument("--files-read", type=int)
    append.add_argument("--files-touched", type=int)
    append.add_argument("--tests-run", type=int)
    append.add_argument("--gates-run", type=int)
    append.add_argument("--duration-seconds", type=float)
    append.add_argument("--cost-usd", type=float)
    append.add_argument("--gate", action="append", default=[])
    append.add_argument("--check", action="append", default=[])
    append.add_argument("--outcome", choices=sorted(OUTCOMES))
    append.add_argument("--decision", choices=sorted(DECISIONS))
    append.add_argument("--note")
    _add_common_output_args(append)

    validate = subparsers.add_parser("validate", help="Validate a metrics ledger.")
    _add_common_output_args(validate)

    summary = subparsers.add_parser("summary", help="Summarize a metrics ledger.")
    _add_common_output_args(summary)

    report = subparsers.add_parser(
        "report", help="Render a per-issue factory metrics report."
    )
    report.add_argument("--ledger", help="JSONL ledger under .entroping/factory-metrics/")
    report.add_argument(
        "--format",
        choices=("json", "md"),
        default="md",
        help="Report format. Defaults to Markdown.",
    )
    report.add_argument(
        "--output",
        help="Optional report path under .entroping/factory-metrics/.",
    )
    report.add_argument(
        "--include-finished-issues",
        action="store_true",
        help=(
            "Include archived finished-issue ledgers under "
            ".entroping/factory-metrics/finished-issues/."
        ),
    )

    scorecard = subparsers.add_parser(
        "context-scorecard",
        help="Validate or report context-tool proof/discard scorecards.",
    )
    scorecard_subparsers = scorecard.add_subparsers(
        dest="scorecard_command",
        required=True,
    )

    scorecard_validate = scorecard_subparsers.add_parser(
        "validate",
        help="Validate a context-tool scorecard.",
    )
    scorecard_validate.add_argument("--input", required=True, help="Scorecard JSON file.")
    scorecard_validate.add_argument("--json", action="store_true", help="Emit JSON output.")

    scorecard_report = scorecard_subparsers.add_parser(
        "report",
        help="Render a context-tool scorecard report.",
    )
    scorecard_report.add_argument("--input", required=True, help="Scorecard JSON file.")
    scorecard_report.add_argument(
        "--format",
        choices=("json", "md"),
        default="md",
        help="Report format. Defaults to Markdown.",
    )
    scorecard_report.add_argument(
        "--output",
        help="Optional report path under .entroping/factory-metrics/.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = _repo_root(args.repo_root)

    try:
        if args.command == "append":
            return _append_command(repo_root, args, parser)
        if args.command == "validate":
            return _validate_command(repo_root, args)
        if args.command == "summary":
            return _summary_command(repo_root, args)
        if args.command == "report":
            return _report_command(repo_root, args)
        if args.command == "context-scorecard":
            return _context_scorecard_command(repo_root, args)
    except FactoryMetricsError as exc:
        parser.exit(2, f"{exc}\n")

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
