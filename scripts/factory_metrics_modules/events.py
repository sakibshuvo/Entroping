"""Factory metrics event construction, validation, and ledger I/O."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from .common import (
    _contains_control_character,
    _contains_secret_like,
    _redact_text,
    _resolve_context_file,
    _validate_note,
)
from .schema import (
    ALL_METRICS,
    ALLOWED_EVENT_KEYS,
    ALLOWED_METRIC_KEYS,
    DECISIONS,
    EVENT_SCHEMA_VERSION,
    EVENT_TYPES,
    OUTCOMES,
    ROLES,
    TEXT_FIELDS,
    UTC_TZ,
)


def _validate_non_negative(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    for metric in ALL_METRICS:
        value = getattr(args, metric, None)
        if value is not None and value < 0:
            parser.error(f"--{metric.replace('_', '-')} must be greater than or equal to 0")


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
    from .storage import append_bounded

    payload = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    append_bounded(path, payload + b"\n")


def _load_events(path: Path, *, error_prefix: str = "") -> tuple[list[dict[str, Any]], list[str]]:
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
                errors.append(f"{error_prefix}line {line_number}: invalid JSON: {exc.msg}")
                continue
            if not isinstance(value, dict):
                errors.append(f"{error_prefix}line {line_number}: event must be an object")
                continue
            errors.extend(
                f"{error_prefix}line {line_number}: {message}" for message in _validate_event(value)
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
                errors.append(f"{field}[{index}] contains unredacted secret-like value")

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


def validate_event(event: dict[str, object]) -> list[str]:
    return _validate_event(cast(dict[str, Any], event))
