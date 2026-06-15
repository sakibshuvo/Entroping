#!/usr/bin/env python3
"""Audit public Markdown for unsupported production/security claims."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

UNSUPPORTED_CLAIMS = (
    "production-ready",
    "production ready",
    "guaranteed secure",
    "guaranteed safe",
    "100% secure",
    "zero risk",
    "unbreakable",
)

EXCLUDED_DIRS = {
    ".git",
    ".context",
    ".entroping",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".understand-anything",
    ".venv",
    "agent-context-out",
    "dist",
    "htmlcov",
    "llm-wiki-out",
    "node_modules",
    "reports",
    "understand-anything-out",
}


@dataclass(frozen=True)
class ClaimFinding:
    """One unsupported public-claim finding."""

    path: Path
    line_number: int
    phrase: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit public Markdown for unsupported production, stability, and security claims."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to audit.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    files = _markdown_files(root)
    findings = _audit_files(root, files)
    if findings:
        print("Public claims audit failed:", file=sys.stderr)
        for finding in findings:
            relative = _display_path(finding.path, root)
            print(
                f"  {relative}:{finding.line_number}: unsupported public claim "
                f"{finding.phrase!r}",
                file=sys.stderr,
            )
        return 1

    print(f"Public claims audit OK: {len(files)} Markdown files checked")
    for path in files:
        print(f"checked: {_display_path(path, root)}")
    return 0


def _markdown_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return tuple(sorted(files))


def _audit_files(root: Path, files: tuple[Path, ...]) -> tuple[ClaimFinding, ...]:
    findings: list[ClaimFinding] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            normalized = line.lower()
            for phrase in UNSUPPORTED_CLAIMS:
                if phrase in normalized:
                    findings.append(
                        ClaimFinding(
                            path=path,
                            line_number=line_number,
                            phrase=phrase,
                        )
                    )
    return tuple(findings)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
