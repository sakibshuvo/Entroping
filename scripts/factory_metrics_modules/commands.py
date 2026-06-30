"""Factory metrics command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    FactoryMetricsError,
    _print_payload,
    _safe_context_scorecard_input_path,
    _safe_ledger_path,
    _safe_report_label,
    _safe_report_path,
    _write_report_output,
)
from .context_scorecard import (
    _context_scorecard_report,
    _load_context_scorecard,
    _render_context_scorecard_markdown,
    _validate_context_tool_scorecard,
)
from .events import _append_jsonl, _event_from_args, _load_events, _validate_event
from .reporting import (
    _load_report_events,
    _readiness_report,
    _render_readiness_markdown,
    _render_report_markdown,
    _report,
    _summary,
)
from .schema import (
    CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION,
    CONTEXT_SCORECARD_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
    READINESS_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)


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


def _readiness_command(repo_root: Path, args: argparse.Namespace) -> int:
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

    issue = _safe_report_label(args.issue)
    if issue is None:
        raise FactoryMetricsError("issue must be a non-empty string")

    report = _readiness_report(events, issue)
    if args.format == "json":
        content = json.dumps(report, sort_keys=True)
    else:
        content = _render_readiness_markdown(report)

    if args.output:
        output_path = _safe_report_path(repo_root, args.output)
        _write_report_output(output_path, content)
        _print_payload(
            {
                "status": "written",
                "output_path": str(output_path),
                "schema_version": READINESS_SCHEMA_VERSION,
                "readiness_status": report["status"],
            },
            False,
        )
        return 1 if report["status"] != "pass" else 0

    print(content)
    return 1 if report["status"] != "pass" else 0


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
