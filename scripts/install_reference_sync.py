#!/usr/bin/env python3
"""Check or sync public GitHub install references from release evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

INSTALL_PREFIX = "git+https://github.com/sakibshuvo/Entroping.git@"
INSTALL_SPEC_RE = re.compile(
    r"git\+https://github\.com/sakibshuvo/Entroping\.git@"
    r"(?P<tag>v[0-9][A-Za-z0-9._-]*)",
)

INSTALL_REFERENCE_PATHS = (
    Path("README.md"),
    Path("docs/technical/TDS.md"),
    Path("docs/user/USER_GUIDE.md"),
    Path("docs/user/CI_PROVIDER_RECIPES.md"),
    Path("docs/user/GITHUB_ACTIONS_STARTER.md"),
    Path("docs/meta/DISTRIBUTION_RECOMMENDATION.md"),
)


@dataclass(frozen=True)
class ReferenceFinding:
    path: Path
    tags: tuple[str, ...]


def latest_release_tag(root: Path) -> str:
    evidence_path = root / "docs/meta/release-evidence.json"
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing canonical release evidence: {evidence_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {evidence_path}: {exc}") from exc

    releases = payload.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ValueError("release-evidence.json must contain at least one release")

    first_release = releases[0]
    if not isinstance(first_release, dict):
        raise ValueError("latest release entry must be an object")

    tag = first_release.get("tag")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("latest release tag must be a string starting with 'v'")
    return tag


def find_references(root: Path) -> list[ReferenceFinding]:
    findings: list[ReferenceFinding] = []
    for relative_path in INSTALL_REFERENCE_PATHS:
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"missing install-reference surface: {relative_path}") from exc

        tags = tuple(match.group("tag") for match in INSTALL_SPEC_RE.finditer(text))
        if not tags:
            raise ValueError(f"{relative_path} has no pinned GitHub install reference")
        findings.append(ReferenceFinding(path=relative_path, tags=tags))
    return findings


def mismatched_references(
    findings: list[ReferenceFinding],
    expected_tag: str,
) -> list[ReferenceFinding]:
    return [
        finding
        for finding in findings
        if any(tag != expected_tag for tag in finding.tags)
    ]


def sync_references(root: Path, expected_tag: str) -> int:
    expected_spec = f"{INSTALL_PREFIX}{expected_tag}"
    updated = 0
    for relative_path in INSTALL_REFERENCE_PATHS:
        path = root / relative_path
        original = path.read_text(encoding="utf-8")
        synced = INSTALL_SPEC_RE.sub(expected_spec, original)
        if synced != original:
            write_text_atomic(path, synced)
            updated += 1
    return updated


def write_text_atomic(path: Path, text: str) -> None:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(text)
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _format_tags(tags: tuple[str, ...]) -> str:
    return ", ".join(sorted(set(tags)))


def check_references(root: Path, expected_tag: str) -> int:
    findings = find_references(root)
    mismatches = mismatched_references(findings, expected_tag)
    if mismatches:
        print("Install reference check failed:", file=sys.stderr)
        print(
            f"  expected GitHub install tag from release evidence: {expected_tag}",
            file=sys.stderr,
        )
        for finding in mismatches:
            print(
                f"  {finding.path}: found {_format_tags(finding.tags)}",
                file=sys.stderr,
            )
        return 1

    total_references = sum(len(finding.tags) for finding in findings)
    print(
        "Install references OK: "
        f"{len(findings)} file(s), {total_references} pinned reference(s), {expected_tag}",
    )
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check or rewrite public GitHub install references from "
            "docs/meta/release-evidence.json."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current working directory.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Fail if public pinned install references diverge.",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Rewrite public pinned install references to the latest release tag.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()

    try:
        expected_tag = latest_release_tag(root)
        if args.write:
            find_references(root)
            updated = sync_references(root, expected_tag)
            print(f"Updated {updated} file(s) to {INSTALL_PREFIX}{expected_tag}")
            return 0
        return check_references(root, expected_tag)
    except ValueError as exc:
        print(f"Install reference check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
