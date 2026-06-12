#!/usr/bin/env python3
"""Append, validate, and summarize local software-factory metrics."""

from __future__ import annotations

import argparse
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
DEFAULT_LEDGER = Path(".entroping") / "factory-metrics" / "events.jsonl"
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


def _safe_ledger_path(repo_root: Path, ledger: str | None) -> Path:
    raw_path = Path(ledger).expanduser() if ledger else DEFAULT_LEDGER
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = _lexical_absolute(path)
    factory_root = _lexical_absolute(repo_root / ".entroping" / "factory-metrics")
    try:
        resolved.relative_to(factory_root)
    except ValueError as exc:
        raise FactoryMetricsError(
            "ledger path must be under .entroping/factory-metrics/"
        ) from exc
    _ensure_no_symlink_components(repo_root, resolved, "ledger path")
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


def _load_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
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
                errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
                continue
            if not isinstance(value, dict):
                errors.append(f"line {line_number}: event must be an object")
                continue
            errors.extend(
                f"line {line_number}: {message}" for message in _validate_event(value)
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
        elif _contains_secret_like(value):
            errors.append(f"{field} contains unredacted secret-like value")

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
    except FactoryMetricsError as exc:
        parser.exit(2, f"{exc}\n")

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
