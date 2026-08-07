"""Provider-scorecard CLI handlers isolated from legacy factory metrics commands."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from .common import (
    print_payload,
    safe_provider_scorecard_input_path,
    safe_report_path,
    write_report_output,
)
from .errors import FactoryMetricsError
from .provider_scorecard_io import load_provider_scorecard
from .provider_scorecard_markdown import render_provider_scorecard_markdown
from .provider_scorecard_reporting import provider_scorecard_report, validate_provider_scorecard
from .provider_scorecard_schema import (
    PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION,
    PROVIDER_SCORECARD_SCHEMA_VERSION,
)


@dataclass(frozen=True, slots=True)
class ProviderScorecardArgs:
    command: Literal["validate", "report"]
    input_path: str
    json: bool
    as_of: str | None
    output_format: Literal["json", "md"]
    output: str | None


def provider_scorecard_command(repo_root: Path, args: argparse.Namespace) -> int:
    """Route validated provider-scorecard subcommands."""

    parsed = _parse_args(args)
    if parsed.command == "validate":
        return _validate(repo_root, parsed)
    if parsed.command == "report":
        return _report(repo_root, parsed)
    raise FactoryMetricsError("unsupported provider-scorecard command")


def _validate(repo_root: Path, args: ProviderScorecardArgs) -> int:
    try:
        evidence = load_provider_scorecard(
            safe_provider_scorecard_input_path(repo_root, args.input_path)
        )
        validate_provider_scorecard(evidence)
    except FactoryMetricsError as exc:
        print_payload(
            {
                "status": "invalid",
                "schema_version": PROVIDER_SCORECARD_SCHEMA_VERSION,
                "errors": [str(exc)],
            },
            args.json,
        )
        return 1
    print_payload(
        {
            "status": "valid",
            "schema_version": PROVIDER_SCORECARD_SCHEMA_VERSION,
            "cases": len(evidence.cases),
        },
        args.json,
    )
    return 0


def _report(repo_root: Path, args: ProviderScorecardArgs) -> int:
    try:
        if args.as_of is None:
            raise FactoryMetricsError("--as-of must be a timezone-aware ISO-8601 timestamp")
        as_of = _parse_as_of(args.as_of)
        evidence = load_provider_scorecard(
            safe_provider_scorecard_input_path(repo_root, args.input_path)
        )
        validate_provider_scorecard(evidence)
        scorecard = provider_scorecard_report(evidence, as_of=as_of)
    except FactoryMetricsError as exc:
        print_payload(
            {
                "status": "invalid",
                "schema_version": PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION,
                "errors": [str(exc)],
            },
            args.output_format == "json",
        )
        return 1
    content = (
        scorecard.model_dump_json()
        if args.output_format == "json"
        else render_provider_scorecard_markdown(scorecard)
    )
    if args.output:
        write_report_output(safe_report_path(repo_root, args.output), content)
        print_payload(
            {"status": "written", "schema_version": PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION}, False
        )
        return 0
    print(content)
    return 0


def _parse_args(args: argparse.Namespace) -> ProviderScorecardArgs:
    raw = cast(dict[str, object], vars(args))
    command = raw.get("provider_scorecard_command")
    input_path = raw.get("input")
    output_format = raw.get("format", "md")
    if command not in ("validate", "report") or not isinstance(input_path, str):
        raise FactoryMetricsError("unsupported provider-scorecard command")
    if output_format not in ("json", "md"):
        raise FactoryMetricsError("unsupported provider-scorecard report format")
    as_of = raw.get("as_of")
    output = raw.get("output")
    return ProviderScorecardArgs(
        command=command,
        input_path=input_path,
        json=raw.get("json") is True,
        as_of=as_of if isinstance(as_of, str) else None,
        output_format=output_format,
        output=output if isinstance(output, str) else None,
    )


def _parse_as_of(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise FactoryMetricsError("--as-of must be a timezone-aware ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FactoryMetricsError("--as-of must be a timezone-aware ISO-8601 timestamp")
    return parsed
