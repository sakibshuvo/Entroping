#!/usr/bin/env python3
"""Inventory tracked Markdown and enforce the default agent context budget."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "entroping.docs-inventory.v1"
DEFAULT_AGENT_CONTEXT_BUDGET = 5
DEFAULT_AGENT_CONTEXT_PATHS = frozenset(
    {
        "AGENTS.md",
        ".context/plan.md",
        "docs/meta/PROJECT_PROGRESS.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
    }
)
CANONICAL_PATHS = frozenset(
    {
        "AGENTS.md",
        "README.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/pull_request_template.md",
        "docs/meta/DOCS_GOVERNANCE.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "docs/meta/PROJECT_PROGRESS.md",
        "docs/meta/VAULT_INDEX.md",
        ".context/plan.md",
        ".context/changelog.md",
        ".context/lessons-learned.md",
    }
)
EVOLUTION_DOC_STATUS_REQUIRES_CLASSIFICATION = frozenset(
    {
        "archive",
        "historical",
        "superseded",
        "deprecated",
        "obsolete",
        "stable",
    }
)
PUBLIC_ROOT_PATHS = frozenset(
    {
        "README.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
    }
)
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
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)
LLM_WIKI_RE = re.compile(r"\b(?:LLM wiki|llm-wiki)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownEntry:
    """One tracked Markdown file in the documentation inventory."""

    path: str
    title: str
    tier: str
    owner: str
    audience: str
    canonical: bool
    default_agent_context: bool
    frontmatter_type: str | None
    frontmatter_status: str | None
    line_count: int
    stale_risk: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "tier": self.tier,
            "owner": self.owner,
            "audience": self.audience,
            "canonical": self.canonical,
            "default_agent_context": self.default_agent_context,
            "frontmatter_type": self.frontmatter_type,
            "frontmatter_status": self.frontmatter_status,
            "line_count": self.line_count,
            "stale_risk": list(self.stale_risk),
        }


@dataclass(frozen=True)
class PruneCandidate:
    """One non-destructive documentation prune/archive review candidate."""

    path: str
    category: str
    action: str
    reason: str
    evidence_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "category": self.category,
            "action": self.action,
            "reason": self.reason,
            "evidence_paths": list(self.evidence_paths),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report tracked Markdown by active/reference/archive tier and "
            "enforce the default agent context budget."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to inventory.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "md"),
        default="json",
        help="Output format. Defaults to JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when the default agent context budget or active-doc guards fail.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    entries = _inventory(root)
    report = _build_report(entries)
    findings = _strict_findings(entries, report) if args.strict else ()
    if findings:
        print("Documentation inventory failed:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_markdown(report))
    return 0


def _inventory(root: Path) -> tuple[MarkdownEntry, ...]:
    entries = [
        _entry_for_path(root=root, path=path)
        for path in _markdown_files(root)
        if path.exists()
    ]
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _markdown_files(root: Path) -> tuple[Path, ...]:
    tracked = _git_tracked_markdown(root)
    if tracked is not None:
        return tracked
    if not root.exists():
        return ()
    files: list[Path] = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
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
    return tuple(sorted(root / line for line in result.stdout.splitlines() if line))


def _entry_for_path(*, root: Path, path: Path) -> MarkdownEntry:
    relative_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    metadata = _frontmatter(text)
    title = _title_for(text=text, metadata=metadata, fallback=path.stem)
    default_agent_context = relative_path in DEFAULT_AGENT_CONTEXT_PATHS
    archive = _is_archive(relative_path)
    tier = _tier(archive=archive, default_agent_context=default_agent_context)
    audience = _audience(relative_path=relative_path, archive=archive)
    owner = _owner(relative_path)
    canonical = relative_path in CANONICAL_PATHS or relative_path.startswith("decisions/")
    stale_risk = _stale_risk(
        relative_path=relative_path,
        text=text,
        metadata=metadata,
        tier=tier,
    )

    return MarkdownEntry(
        path=relative_path,
        title=title,
        tier=tier,
        owner=owner,
        audience=audience,
        canonical=canonical,
        default_agent_context=default_agent_context,
        frontmatter_type=metadata.get("type"),
        frontmatter_status=metadata.get("status"),
        line_count=len(text.splitlines()),
        stale_risk=stale_risk,
    )


def _frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key in {"title", "type", "status"} and value:
            metadata[key] = value
    return metadata


def _title_for(*, text: str, metadata: dict[str, str], fallback: str) -> str:
    if metadata.get("title"):
        return metadata["title"]
    match = TITLE_RE.search(text)
    if match:
        return match.group("title").strip().strip("`")
    return fallback


def _tier(*, archive: bool, default_agent_context: bool) -> str:
    if archive:
        return "archive"
    if default_agent_context:
        return "active"
    return "reference"


def _is_archive(relative_path: str) -> bool:
    parts = relative_path.split("/")
    return (
        "archive" in parts
        or relative_path.startswith("docs/evolution/")
        or relative_path.startswith("sources/")
    )


def _audience(*, relative_path: str, archive: bool) -> str:
    if archive:
        return "archive"
    if relative_path in PUBLIC_ROOT_PATHS:
        return "public"
    if relative_path == "docs/index.md":
        return "public"
    if relative_path.startswith(
        (
            "docs/user/",
            "docs/product/",
            "docs/technical/",
            "docs/architecture/",
            "docs/assets/",
            "examples/",
            "decisions/",
        )
    ):
        return "public"
    return "maintainer"


def _owner(relative_path: str) -> str:
    if relative_path == "AGENTS.md":
        return "agent-rules"
    if relative_path.startswith(".context/"):
        return "handoff"
    if relative_path.startswith(".github/"):
        return "github"
    if relative_path in PUBLIC_ROOT_PATHS:
        return "root"
    if relative_path.startswith("decisions/"):
        return "adr"
    if relative_path.startswith("docs/meta/prompt-library/"):
        return "prompt-library"
    if relative_path.startswith("docs/meta/archive/"):
        return "meta-archive"
    if relative_path.startswith("docs/meta/"):
        return "meta"
    if relative_path.startswith("docs/user/"):
        return "user-docs"
    if relative_path.startswith("docs/technical/"):
        return "technical-docs"
    if relative_path.startswith("docs/product/"):
        return "product-docs"
    if relative_path.startswith("docs/architecture/"):
        return "architecture-docs"
    if relative_path.startswith("docs/evolution/"):
        return "product-history"
    if relative_path.startswith("docs/assets/"):
        return "docs-assets"
    if relative_path.startswith("examples/"):
        return "examples"
    if relative_path.startswith("prompts/"):
        return "model-prompts"
    if relative_path.startswith("sources/"):
        return "source-map"
    return "other"


def _stale_risk(
    *,
    relative_path: str,
    text: str,
    metadata: dict[str, str],
    tier: str,
) -> tuple[str, ...]:
    risks: list[str] = []
    if relative_path.startswith("docs/meta/") and not metadata:
        risks.append("missing-frontmatter")
    if relative_path.startswith("docs/evolution/") and (
        metadata.get("status") not in EVOLUTION_DOC_STATUS_REQUIRES_CLASSIFICATION
    ):
        risks.append("evolution-doc-needs-archive-classification")
    if tier == "archive":
        risks.append("archive")
    if LLM_WIKI_RE.search(text) and tier == "active":
        risks.append("llm-wiki-in-active-context")
    return tuple(risks)


def _build_report(entries: tuple[MarkdownEntry, ...]) -> dict[str, Any]:
    by_tier = Counter(entry.tier for entry in entries)
    by_owner = Counter(entry.owner for entry in entries)
    by_audience = Counter(entry.audience for entry in entries)
    prune_candidates = _prune_candidates(entries)
    by_prune_candidate_category = Counter(
        candidate.category for candidate in prune_candidates
    )
    active_title_groups = _active_title_groups(entries)
    duplicate_active_titles = {
        title: paths for title, paths in active_title_groups.items() if len(paths) > 1
    }
    llm_wiki_active_count = sum(
        1
        for entry in entries
        if "llm-wiki-in-active-context" in entry.stale_risk
    )
    default_agent_context_count = sum(
        1 for entry in entries if entry.default_agent_context
    )
    return {
        "schema": SCHEMA,
        "summary": {
            "total_markdown_files": len(entries),
            "by_tier": dict(sorted(by_tier.items())),
            "by_owner": dict(sorted(by_owner.items())),
            "by_audience": dict(sorted(by_audience.items())),
            "default_agent_context_budget": DEFAULT_AGENT_CONTEXT_BUDGET,
            "default_agent_context_count": default_agent_context_count,
            "llm_wiki_active_count": llm_wiki_active_count,
            "duplicate_active_title_count": len(duplicate_active_titles),
            "duplicate_active_titles": duplicate_active_titles,
            "prune_candidate_count": len(prune_candidates),
            "by_prune_candidate_category": dict(
                sorted(by_prune_candidate_category.items())
            ),
        },
        "files": [entry.to_dict() for entry in entries],
        "prune_candidates": [candidate.to_dict() for candidate in prune_candidates],
    }


def _prune_candidates(entries: tuple[MarkdownEntry, ...]) -> list[PruneCandidate]:
    candidates: list[PruneCandidate] = []
    for entry in entries:
        if entry.default_agent_context and (entry.stale_risk or not entry.canonical):
            candidates.append(
                PruneCandidate(
                    path=entry.path,
                    category="default-agent-risk",
                    action="review-default-agent-context",
                    reason=(
                        "Default agent context file has stale-risk markers or "
                        "is not canonical; review before keeping it in the "
                        "default agent context pack."
                    ),
                    evidence_paths=(entry.path,),
                )
            )
        if entry.tier == "reference" and entry.stale_risk:
            candidates.append(
                PruneCandidate(
                    path=entry.path,
                    category="stale-reference",
                    action="review-for-archive-or-canonical-update",
                    reason=(
                        "Reference doc has stale-risk markers; compare against "
                        "canonical docs before promoting, pruning, or archiving."
                    ),
                    evidence_paths=("docs/meta/DOCS_GOVERNANCE.md",),
                )
            )
        if "evolution-doc-needs-archive-classification" in entry.stale_risk:
            candidates.append(
                PruneCandidate(
                    path=entry.path,
                    category="evolution-archive-status",
                    action="review-evolution-archive-status",
                    reason=(
                        "Evolution docs are intended as historical context and "
                        "must be explicitly marked as archive-compatible before "
                        "any public docs cleanup or nav changes."
                    ),
                    evidence_paths=("docs/meta/DOCS_GOVERNANCE.md",),
                )
            )
        if entry.tier == "archive":
            candidates.append(
                PruneCandidate(
                    path=entry.path,
                    category="archive-reference",
                    action="keep-out-of-default-context",
                    reason=(
                        "Document is already archive/source status; keep it out "
                        "of default agent context unless a current issue, ADR, "
                        "or canonical doc cites it."
                    ),
                    evidence_paths=(entry.path,),
                )
            )

    candidates.extend(_duplicate_title_candidates(entries))
    return sorted(
        candidates,
        key=lambda candidate: (candidate.category, candidate.path, candidate.action),
    )


def _duplicate_title_candidates(
    entries: tuple[MarkdownEntry, ...],
) -> list[PruneCandidate]:
    candidates: list[PruneCandidate] = []
    for title, grouped_entries in _title_groups(entries).items():
        if len(grouped_entries) <= 1:
            continue
        canonical_paths = sorted(entry.path for entry in grouped_entries if entry.canonical)
        for entry in grouped_entries:
            if canonical_paths and entry.path in canonical_paths:
                continue
            evidence_paths = tuple(
                canonical_paths
                or sorted(other.path for other in grouped_entries if other.path != entry.path)
            )
            candidates.append(
                PruneCandidate(
                    path=entry.path,
                    category="duplicate-title",
                    action="review-duplicate-title",
                    reason=(
                        f"Markdown title {title!r} is duplicated; compare "
                        "against canonical docs or the listed peer paths before "
                        "pruning or archiving."
                    ),
                    evidence_paths=evidence_paths,
                )
            )
    return candidates


def _active_title_groups(entries: tuple[MarkdownEntry, ...]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.tier == "active":
            grouped[entry.title].append(entry.path)
    return dict(sorted(grouped.items()))


def _title_groups(entries: tuple[MarkdownEntry, ...]) -> dict[str, list[MarkdownEntry]]:
    grouped: dict[str, list[MarkdownEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.title].append(entry)
    return dict(sorted(grouped.items()))


def _strict_findings(
    entries: tuple[MarkdownEntry, ...],
    report: dict[str, Any],
) -> tuple[str, ...]:
    entry_paths = {entry.path for entry in entries}
    findings: list[str] = []
    for required_path in sorted(DEFAULT_AGENT_CONTEXT_PATHS):
        if required_path not in entry_paths:
            findings.append(f"missing default agent context path: {required_path}")

    summary = report["summary"]
    default_count = summary["default_agent_context_count"]
    if default_count > DEFAULT_AGENT_CONTEXT_BUDGET:
        findings.append(
            "default agent context budget exceeded: "
            f"{default_count}/{DEFAULT_AGENT_CONTEXT_BUDGET}"
        )
    if summary["llm_wiki_active_count"]:
        findings.append(
            "LLM wiki references are present in active default agent context"
        )
    for title, paths in summary["duplicate_active_titles"].items():
        findings.append(
            "duplicate active Markdown title: "
            f"{title} ({', '.join(sorted(paths))})"
        )
    return tuple(findings)


def _format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Documentation Inventory",
        "",
        f"Schema: `{report['schema']}`",
        "",
        (
            "Default agent context budget: "
            f"{summary['default_agent_context_count']}/"
            f"{summary['default_agent_context_budget']}"
        ),
        "",
        "## Counts",
        "",
        "| Group | Count |",
        "| --- | ---: |",
    ]
    for tier, count in summary["by_tier"].items():
        lines.append(f"| {tier} | {count} |")
    lines.extend(
        [
            "",
            "## Prune Candidates",
            "",
        ]
    )
    prune_candidates = report["prune_candidates"]
    if prune_candidates:
        lines.extend(
            [
                "| Path | Category | Action | Reason | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for candidate in prune_candidates:
            evidence = ", ".join(
                f"`{path}`" for path in candidate["evidence_paths"]
            )
            lines.append(
                f"| `{candidate['path']}` | {candidate['category']} | "
                f"{candidate['action']} | {_markdown_cell(candidate['reason'])} | "
                f"{evidence} |"
            )
    else:
        lines.append("No prune candidates reported.")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "| Path | Tier | Owner | Audience | Default Agent Context | Canonical | Stale Risk |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in report["files"]:
        default_context = "yes" if entry["default_agent_context"] else "no"
        canonical = "yes" if entry["canonical"] else "no"
        risks = ", ".join(entry["stale_risk"]) if entry["stale_risk"] else "-"
        lines.append(
            f"| `{entry['path']}` | {entry['tier']} | {entry['owner']} | "
            f"{entry['audience']} | {default_context} | {canonical} | {risks} |"
        )
    return "\n".join(lines)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


if __name__ == "__main__":
    sys.exit(main())
