#!/usr/bin/env python3
"""Build a small advisory context manifest from local graph-tool outputs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "entroping.agent-context-probe.v1"
OUTPUT_ROOT = "agent-context-out"
SUPPORTED_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
MAX_ARTIFACTS_PER_TOOL = 32
MAX_BYTES_PER_ARTIFACT = 128_000
MAX_CANDIDATES_PER_TOOL = 12
SNIPPET_LIMIT = 280

CONTEXT_TOOLS = (
    ("Graphify", "graphify-out"),
    ("CodeGraph", "codegraph-out"),
)

GUARDRAILS = (
    "Graph output is retrieval evidence, not authority.",
    (
        "GitHub Issues, PRs, CI, source files, tests, ADRs, and "
        "QAnstitution/Hurl evidence remain authoritative."
    ),
    "Generated graph evidence must stay local unless promoted through normal review.",
)

VERIFICATION_WARNINGS = (
    "Verify every candidate against source files and tests before patching.",
    "Do not use graph evidence to downgrade Tier B/Tier C work into autonomous Tier A work.",
    "Skip the probe when local graph outputs are absent, stale, noisy, or secrets-sensitive.",
)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]*", re.IGNORECASE)
PATH_RE = re.compile(
    r"(?:(?:src|tests|docs|scripts|examples|decisions|prompts|agents|suites|"
    r"envs|\.github)/[A-Za-z0-9_.@+/\-]+|AGENTS\.md|README\.md|ROADMAP\.md|"
    r"pyproject\.toml)"
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)([\"'=:\s]+)([^\s\"']{6,})"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize local Graphify/CodeGraph outputs for agent context.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to inspect. Defaults to the current git root.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Issue title, symbol, path, or review focus to match against graph output.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Must be under agent-context-out/.",
    )
    args = parser.parse_args(argv)

    repo_root = _resolve_repo_root(args.repo_root)
    query_terms = _query_terms(args.query)
    manifest = build_manifest(repo_root=repo_root, query_terms=query_terms)

    rendered = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_text(manifest)
    )

    if args.output is not None:
        output_path = _safe_output_path(repo_root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return 0


def build_manifest(repo_root: Path, query_terms: list[str]) -> dict[str, Any]:
    generated_context: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for tool, relative_dir in CONTEXT_TOOLS:
        tool_root = repo_root / relative_dir
        tool_candidates = _collect_tool_candidates(
            tool=tool,
            tool_root=tool_root,
            repo_root=repo_root,
            query_terms=query_terms,
        )
        status, artifact_count = _tool_status(tool_root)
        generated_context.append(
            {
                "tool": tool,
                "path": f"{relative_dir}/",
                "status": status,
                "artifact_count": artifact_count,
                "candidate_count": len(tool_candidates),
            }
        )
        candidates.extend(tool_candidates)

    return {
        "schema_version": SCHEMA_VERSION,
        "query_terms": query_terms,
        "guardrails": list(GUARDRAILS),
        "verification_warnings": list(VERIFICATION_WARNINGS),
        "generated_context": generated_context,
        "candidates": candidates,
    }


def render_text(manifest: dict[str, Any]) -> str:
    lines = [
        "## Optional Graph-Assisted Agent Context",
        "",
        f"schema: {manifest['schema_version']}",
        "advisory_only: true",
        f"optional_output: {OUTPUT_ROOT}/",
        "",
        "### Query Terms",
    ]
    query_terms = manifest["query_terms"]
    lines.append("- " + ", ".join(query_terms) if query_terms else "- none supplied")
    lines.extend(["", "### Guardrails"])
    lines.extend(f"- {guardrail}" for guardrail in manifest["guardrails"])
    lines.extend(["", "### Generated Context Tool Status"])
    for entry in manifest["generated_context"]:
        lines.append(
            (
                "- {tool}: {status} "
                "({path}; artifacts={artifact_count}; candidates={candidate_count})"
            ).format(
                **entry
            )
        )
    lines.extend(["", "### Candidate Evidence"])
    if manifest["candidates"]:
        for candidate in manifest["candidates"]:
            references = ", ".join(candidate["referenced_paths"]) or "no path found"
            lines.append(
                "- {tool} {artifact_path}:{line} [{terms}] -> {references}: {snippet}".format(
                    tool=candidate["tool"],
                    artifact_path=candidate["artifact_path"],
                    line=candidate["line"] or "-",
                    terms=", ".join(candidate["matched_terms"]) or "no query match",
                    references=references,
                    snippet=candidate["snippet"],
                )
            )
    else:
        lines.append("- none")
    lines.extend(["", "### Verification Warnings"])
    lines.extend(f"- {warning}" for warning in manifest["verification_warnings"])
    lines.append("")
    return "\n".join(lines)


def _resolve_repo_root(explicit_root: Path | None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()
    return Path(result.stdout.strip()).resolve()


def _query_terms(queries: Iterable[str]) -> list[str]:
    terms: list[str] = []
    for query in queries:
        for match in TOKEN_RE.findall(query.lower()):
            if len(match) < 2:
                continue
            if match not in terms:
                terms.append(match)
    return terms


def _tool_status(tool_root: Path) -> tuple[str, int]:
    if not tool_root.exists():
        return "missing", 0
    artifacts = list(_iter_artifacts(tool_root))
    if not artifacts:
        return "empty", 0
    return "present", len(artifacts)


def _collect_tool_candidates(
    *,
    tool: str,
    tool_root: Path,
    repo_root: Path,
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not tool_root.exists():
        return []

    candidates: list[dict[str, Any]] = []
    for artifact in _iter_artifacts(tool_root):
        if artifact.stat().st_size > MAX_BYTES_PER_ARTIFACT:
            continue
        rel_artifact = _relative_to_repo(artifact, repo_root)
        for line, text in _artifact_records(artifact):
            matched_terms = _matched_terms(text, query_terms)
            if not _is_candidate_match(matched_terms, query_terms):
                continue
            snippet = _clean_snippet(text)
            candidates.append(
                {
                    "tool": tool,
                    "artifact_path": rel_artifact,
                    "line": line,
                    "snippet": snippet,
                    "matched_terms": matched_terms,
                    "referenced_paths": _referenced_paths(snippet),
                }
            )
            if len(candidates) >= MAX_CANDIDATES_PER_TOOL:
                return candidates
    return candidates


def _iter_artifacts(tool_root: Path) -> Iterable[Path]:
    artifacts = (
        path
        for path in sorted(tool_root.rglob("*"))
        if not path.is_symlink()
        and path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    for index, artifact in enumerate(artifacts):
        if index >= MAX_ARTIFACTS_PER_TOOL:
            break
        yield artifact


def _artifact_records(path: Path) -> Iterable[tuple[int | None, str]]:
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        yield from _json_records(data)
        return

    if path.suffix.lower() == ".jsonl":
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line_number, line in enumerate(lines, start=1):
            yield line_number, line
        return

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line_number, line in enumerate(lines, start=1):
        yield line_number, line


def _json_records(value: Any) -> Iterable[tuple[int | None, str]]:
    if isinstance(value, dict):
        list_values = [item for item in value.values() if isinstance(item, list)]
        if list_values:
            for item in list_values[0]:
                yield None, _json_text(item)
            return
        yield None, _json_text(value)
        return
    if isinstance(value, list):
        for item in value:
            yield None, _json_text(item)
        return
    yield None, _json_text(value)


def _json_text(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                parts.append(f"{key}: {item}")
            else:
                parts.append(f"{key}: {_json_text(item)}")
        return "; ".join(parts)
    if isinstance(value, list):
        return "; ".join(_json_text(item) for item in value)
    return str(value)


def _matched_terms(text: str, query_terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in query_terms if term in lowered]


def _is_candidate_match(matched_terms: list[str], query_terms: list[str]) -> bool:
    if not query_terms:
        return False
    required_matches = min(2, len(query_terms))
    return len(matched_terms) >= required_matches


def _clean_snippet(text: str) -> str:
    snippet = " ".join(text.split())
    for pattern in SECRET_PATTERNS:
        snippet = pattern.sub(lambda match: _redacted(match), snippet)
    if len(snippet) > SNIPPET_LIMIT:
        return snippet[: SNIPPET_LIMIT - 3] + "..."
    return snippet


def _redacted(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        prefix = "".join(group or "" for group in match.groups()[:-1])
        return f"{prefix}<redacted>"
    return "<redacted>"


def _referenced_paths(snippet: str) -> list[str]:
    references: list[str] = []
    for match in PATH_RE.findall(snippet):
        reference = match.rstrip(".,;:)]}")
        if reference not in references:
            references.append(reference)
    return references


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _safe_output_path(repo_root: Path, output: Path) -> Path:
    output_path = output if output.is_absolute() else repo_root / output
    output_path = output_path.resolve()
    output_root = (repo_root / OUTPUT_ROOT).resolve()
    try:
        output_path.relative_to(output_root)
    except ValueError:
        print(
            f"agent_context_probe: output path must be under {OUTPUT_ROOT}/",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    return output_path


if __name__ == "__main__":
    raise SystemExit(main())
