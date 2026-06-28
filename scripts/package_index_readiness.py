from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from package_index_readiness_checks import build_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate repo-owned package-index publishing readiness guardrails."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when repo-owned package-index guardrails are invalid.",
    )
    args = parser.parse_args()

    payload = build_payload(args.root.expanduser().resolve())
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    repo_failures = cast(list[str], payload["repo_failures"])
    if args.strict and repo_failures:
        print("package-index readiness check failed:", file=sys.stderr)
        for failure in repo_failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


def _render_markdown(payload: dict[str, object]) -> str:
    checks = cast(dict[str, dict[str, object]], payload["checks"])
    lines = [
        "# Package Index Readiness",
        "",
        f"- Repo guardrails ready: `{str(payload['repo_guardrails_ready']).lower()}`",
        f"- Package index ready: `{str(payload['package_index_ready']).lower()}`",
        "",
        "## Checks",
    ]
    for key, check in checks.items():
        lines.append(f"- {key}: `{check['status']}` - {check['detail']}")
        for failure in cast(list[str], check["failures"]):
            lines.append(f"  - {failure}")
    lines.append("")
    lines.append("## External Requirements")
    for requirement in cast(list[str], payload["external_requirements"]):
        lines.append(f"- {requirement}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
