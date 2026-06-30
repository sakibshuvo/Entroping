"""CLI adapter for factory metrics commands."""

from __future__ import annotations

from .commands import (  # noqa: F401
    _append_command as _append_command,
)
from .commands import (
    _context_scorecard_command as _context_scorecard_command,
)
from .commands import (
    _context_scorecard_report_command as _context_scorecard_report_command,
)
from .commands import (
    _context_scorecard_validate_command as _context_scorecard_validate_command,
)
from .commands import (
    _readiness_command as _readiness_command,
)
from .commands import (
    _report_command as _report_command,
)
from .commands import (
    _summary_command as _summary_command,
)
from .commands import (
    _validate_command as _validate_command,
)
from .common import FactoryMetricsError, _repo_root
from .parser import _add_common_output_args as _add_common_output_args  # noqa: F401
from .parser import build_parser as build_parser


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
        if args.command == "readiness":
            return _readiness_command(repo_root, args)
        if args.command == "context-scorecard":
            return _context_scorecard_command(repo_root, args)
    except FactoryMetricsError as exc:
        parser.exit(2, f"{exc}\n")

    parser.error(f"unsupported command: {args.command}")
    return 2
