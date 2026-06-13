#!/usr/bin/env python3
"""Audit tracked Markdown for stale context and corruption markers."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

STALE_REPO_PATH = "/Users/sakibshuvo/Documents/Entroping"
DEPRECATED_COMMAND_PATTERNS = (
    re.compile(r"`entroping\s+chaos(?:\s|`|$)"),
    re.compile(r"`entroping\s+gen(?:\s|`|$)"),
    re.compile(r"`entroping\s+fix(?:\s|`|$)"),
    re.compile(r"`entroping\s+scan(?:\s|`|$)"),
    re.compile(r"`entroping\s+report\s+--type(?:\s|`|$)"),
)
UNSUPPORTED_CLAIMS = (
    "production-ready",
    "production ready",
    "stable-core ready",
    "stable core ready",
    "enterprise ready",
    "guaranteed secure",
    "guaranteed safe",
    "100% secure",
    "zero risk",
    "unbreakable",
)
PLACEHOLDER_PATTERN = re.compile(r"\b(todo|fixme|tbd)\b", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
EXCLUDED_DIRS = {
    ".git",
    ".entroping",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "dist",
    "htmlcov",
    "node_modules",
    "reports",
    "site",
}


@dataclass(frozen=True)
class Finding:
    """One Markdown freshness finding."""

    path: Path
    line_number: int | None
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit current Markdown for stale paths, broken local links, "
            "unsupported claims, placeholders, and corruption markers."
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
    findings = _audit_files(root=root, files=files)
    if findings:
        print("Markdown freshness failed:", file=sys.stderr)
        for finding in findings:
            relative = _display_path(finding.path, root)
            if finding.line_number is None:
                print(f"  {relative}: {finding.message}", file=sys.stderr)
            else:
                print(
                    f"  {relative}:{finding.line_number}: {finding.message}",
                    file=sys.stderr,
                )
        return 1

    print(f"Markdown freshness OK: {len(files)} tracked Markdown files checked")
    return 0


def _markdown_files(root: Path) -> tuple[Path, ...]:
    tracked = _git_tracked_markdown(root)
    if tracked is not None:
        return tracked
    if not root.exists():
        return ()
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return tuple(sorted(files))


def _git_tracked_markdown(root: Path) -> tuple[Path, ...] | None:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.md"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    files = [root / line for line in result.stdout.splitlines() if line]
    return tuple(sorted(files))


def _audit_files(*, root: Path, files: tuple[Path, ...]) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in files:
        findings.extend(_audit_file(root=root, path=path))
    return tuple(findings)


def _audit_file(*, root: Path, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    data = path.read_bytes()
    if b"\0" in data:
        findings.append(Finding(path=path, line_number=None, message="contains NUL byte"))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [
            *findings,
            Finding(path=path, line_number=None, message="invalid UTF-8"),
        ]

    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        context = _nearby_context(lines, line_number)
        normalized_context = context.lower()
        normalized_line = line.lower()

        if _is_merge_conflict_marker(line):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="merge conflict marker",
                )
            )

        if STALE_REPO_PATH.lower() in normalized_line and not _is_stale_path_warning(
            normalized_context
        ):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message=(
                        "stale active-repo path reference; use "
                        "/Users/sakibshuvo/projects/Entroping or mark the path as stale"
                    ),
                )
            )

        if _contains_deprecated_command(line) and not _is_deprecation_context(
            normalized_context
        ):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="deprecated command literal without deprecation context",
                )
            )

        if _contains_unsupported_claim(normalized_line) and not _is_claim_guardrail_context(
            normalized_context
        ):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="unsupported readiness/security claim",
                )
            )

        if PLACEHOLDER_PATTERN.search(line):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="placeholder marker TODO/FIXME/TBD",
                )
            )

        for target in _local_markdown_link_targets(line):
            if not _local_link_exists(root=root, source=path, target=target):
                findings.append(
                    Finding(
                        path=path,
                        line_number=line_number,
                        message=f"broken local Markdown link: {target}",
                    )
                )

    return findings


def _nearby_context(lines: list[str], line_number: int) -> str:
    start = max(0, line_number - 2)
    end = min(len(lines), line_number + 1)
    return "\n".join(lines[start:end])


def _is_merge_conflict_marker(line: str) -> bool:
    stripped = line.strip()
    return (
        line.startswith("<<<<<<< ")
        or line.startswith(">>>>>>> ")
        or stripped == "======="
    )


def _is_stale_path_warning(normalized_context: str) -> bool:
    return "stale path" in normalized_context or "is stale" in normalized_context


def _contains_deprecated_command(line: str) -> bool:
    return any(pattern.search(line) for pattern in DEPRECATED_COMMAND_PATTERNS)


def _is_deprecation_context(normalized_context: str) -> bool:
    accepted_markers = (
        "old docs",
        "older ",
        "not v4.1",
        "not primary",
        "alias only if needed",
        "removes it",
        "deprecated",
    )
    return any(marker in normalized_context for marker in accepted_markers)


def _contains_unsupported_claim(normalized_line: str) -> bool:
    return any(phrase in normalized_line for phrase in UNSUPPORTED_CLAIMS)


def _is_claim_guardrail_context(normalized_context: str) -> bool:
    accepted_markers = (
        "should fail",
        "does not make",
        "not ",
        "unsupported",
        "reject",
        "avoid",
        "before stable-core claims",
    )
    return any(marker in normalized_context for marker in accepted_markers)


def _local_markdown_link_targets(line: str) -> tuple[str, ...]:
    targets: list[str] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(line):
        raw_target = match.group(1).strip()
        target = _normalize_link_target(raw_target)
        if not target:
            continue
        if _is_external_or_special_link(target):
            continue
        targets.append(target)
    return tuple(targets)


def _normalize_link_target(raw_target: str) -> str:
    target = raw_target
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split("#", maxsplit=1)[0].strip()
    return unquote(target)


def _is_external_or_special_link(target: str) -> bool:
    if target.startswith("#"):
        return True
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target))


def _local_link_exists(*, root: Path, source: Path, target: str) -> bool:
    target_path = Path(target)
    if target_path.is_absolute():
        return target_path.exists()
    return (source.parent / target_path).exists() or (root / target_path).exists()


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
