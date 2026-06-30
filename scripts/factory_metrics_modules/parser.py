"""Argument parser construction for factory metrics commands."""

from __future__ import annotations

import argparse

from .schema import DECISIONS, EVENT_TYPES, OUTCOMES, ROLES


def _add_common_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", help="JSONL ledger under .entroping/factory-metrics/")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Record local, ignored metrics for Entroping's portable software-factory workflow."
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

    report = subparsers.add_parser("report", help="Render a per-issue factory metrics report.")
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

    readiness = subparsers.add_parser(
        "readiness",
        help="Evaluate whether an issue has quality, security, context, and cost evidence.",
    )
    readiness.add_argument("--issue", required=True, help="Issue number or label.")
    readiness.add_argument(
        "--ledger",
        help="JSONL ledger under .entroping/factory-metrics/",
    )
    readiness.add_argument(
        "--format",
        choices=("json", "md"),
        default="md",
        help="Report format. Defaults to Markdown.",
    )
    readiness.add_argument(
        "--output",
        help="Optional report path under .entroping/factory-metrics/.",
    )
    readiness.add_argument(
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
