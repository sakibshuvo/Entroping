#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

SCHEMA_VERSION = "entroping.quality-hotspot-report.v1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a long-file hotspot report from local Python files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports") / "long-file-hotspots.json",
        help="Output JSON artifact path.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=500,
        help="Only report files with at least this many lines.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum hotspots to include in report.",
    )
    parser.add_argument(
        "--path-prefix",
        default=("src", "tests"),
        nargs="*",
        help="Path prefixes to include while scanning from root.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    output = args.output
    try:
        payload = build_payload(root, max_lines=args.max_lines, limit=args.limit, prefixes=args.path_prefix)
    except ValueError as exc:
        print(f"quality-hotspot report failed: {exc}", flush=True)
        return 2

    output = output.expanduser()
    if not output.is_absolute():
        output = (root / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"wrote quality hotspot report: {output.as_posix()}")
    return 0


def build_payload(
    root: Path,
    *,
    max_lines: int,
    limit: int,
    prefixes: tuple[str, ...] | list[str],
) -> dict[str, object]:
    if max_lines <= 0:
        raise ValueError("max-lines must be positive")
    if limit <= 0:
        raise ValueError("limit must be positive")
    for prefix in prefixes:
        if not prefix:
            raise ValueError("path-prefix must be non-empty")

    entries = [
        hotspot
        for hotspot in _find_hotspots(root, prefixes, max_lines=max_lines)
        if hotspot is not None
    ]
    entries.sort(key=lambda item: (-item["lines"], item["path"]))
    selected = entries[:limit]

    return {
        "schema_version": SCHEMA_VERSION,
        "max_lines_threshold": max_lines,
        "limit": limit,
        "hotspot_count": len(entries),
        "hotspots": selected,
    }


def _find_hotspots(
    root: Path,
    prefixes: tuple[str, ...] | list[str],
    *,
    max_lines: int,
) -> list[dict[str, object]]:
    files = _iter_python_files(root, prefixes)
    hotspots: list[dict[str, object]] = []
    for path in files:
        line_count = _line_count(path)
        if line_count >= max_lines:
            hotspots.append(
                {
                    "path": path.as_posix(),
                    "lines": line_count,
                }
            )
    return hotspots


def _iter_python_files(root: Path, prefixes: tuple[str, ...] | list[str]) -> list[Path]:
    candidate_roots: list[Path] = []
    for prefix in prefixes:
        candidate = root / prefix
        if candidate.is_dir():
            candidate_roots.append(candidate)
    files: list[Path] = []
    for candidate in candidate_roots:
        files.extend(candidate.rglob("*.py"))
    return files


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
