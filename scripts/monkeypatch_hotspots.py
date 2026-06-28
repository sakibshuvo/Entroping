#!/usr/bin/env python3
"""Monkeypatch hotspot quality report — deterministic measurement only.

Counts monkeypatch usage by test file and highlights top hotspots for
future public-surface test replacement. Does not rewrite tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

SCHEMA_VERSION = "entroping.monkeypatch-hotspot-report.v1"

EXCLUDED_DIRS = frozenset({
    ".venv", ".git", ".entroping", "dist", "htmlcov",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "__pycache__", "reports", "node_modules",
})


@dataclass(frozen=True)
class Hotspot:
    file: str
    count: int
    rank: int


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count monkeypatch usage by test file and highlight hotspots."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top hotspots to show (default 10).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when no monkeypatch usage is found (sanity check).",
    )
    args = parser.parse_args()
    root = args.root.expanduser().resolve()

    payload = _build_payload(root, args.top)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict and not payload["hotspots"]:
        print("monkeypatch hotspot check: no monkeypatch usage found", file=sys.stderr)
        return 1
    return 0


def _build_payload(root: Path, top_n: int) -> dict[str, object]:
    test_dir = root / "tests"
    counts: dict[str, int] = defaultdict(int)

    if test_dir.is_dir():
        for py_file in test_dir.rglob("*.py"):
            rel = py_file.relative_to(root).as_posix()
            parts = py_file.parts[len(test_dir.parts):]
            if any(d in EXCLUDED_DIRS for d in parts):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            count = content.count("monkeypatch")
            if count > 0:
                counts[rel] = count

    sorted_files = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    hotspots: list[dict[str, object]] = []
    total_count = 0
    total_files = len(sorted_files)

    for rank, (file_path, count) in enumerate(sorted_files, start=1):
        total_count += count
        if rank <= top_n:
            hotspots.append({
                "rank": rank,
                "file": file_path,
                "count": count,
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "total_monkeypatch_uses": total_count,
        "files_with_monkeypatch": total_files,
        "hotspots": hotspots,
    }


def _render_markdown(payload: dict[str, object]) -> str:
    hotspots = cast(list[dict[str, object]], payload["hotspots"])
    lines = [
        "# Monkeypatch Hotspot Report",
        "",
        f"- Total monkeypatch uses: {payload['total_monkeypatch_uses']}",
        f"- Files with monkeypatch: {payload['files_with_monkeypatch']}",
        f"- Schema: `{payload['schema_version']}`",
        "",
        "## Top Hotspots",
        "",
        "| Rank | File | Count |",
        "|------|------|-------|",
    ]
    for h in hotspots:
        lines.append(f"| {h['rank']} | `{h['file']}` | {h['count']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
