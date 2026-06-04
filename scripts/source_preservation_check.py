#!/usr/bin/env python3
"""Validate lossless context-preservation anchors and decision-registry links."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path("docs/meta/DECISION_REGISTRY.yaml")
REQUIRED_ANCHORS = (
    Path("sources/SOURCE_MAP.md"),
    Path("docs/evolution/REQUIREMENTS_ANALYSIS.md"),
    Path("docs/evolution/EVOLUTION_TIMELINE.md"),
    Path("docs/evolution/CREATOR_INTENT_AUDIT.md"),
    Path("docs/meta/VAULT_INDEX.md"),
    Path("docs/meta/CONTEXT_MANAGEMENT.md"),
    Path("docs/meta/KNOWLEDGE_BASE_WORKFLOW.md"),
)
DECISION_ID_PATTERN = re.compile(r"^ENT-DEC-[0-9]{4}$")
ISSUE_PATTERN = re.compile(r"^#[1-9][0-9]*$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the Entroping decision registry, local source-history "
            "anchors, and registry links."
        )
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to validate. Defaults to the current directory.",
    )
    parser.add_argument(
        "--source-root",
        default=None,
        help=(
            "Optional external entroping-specs root. When provided, external "
            "registry source links are validated relative to this directory."
        ),
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    source_root = Path(args.source_root).resolve() if args.source_root else None
    failures = validate(root=root, source_root=source_root)

    if failures:
        print("Source preservation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    registry = _load_yaml(root / REGISTRY_PATH)
    decisions = registry.get("decisions", []) if isinstance(registry, Mapping) else []
    print(
        "Source preservation OK: "
        f"{REGISTRY_PATH}; {len(decisions)} decisions; {len(REQUIRED_ANCHORS)} anchors"
    )
    return 0


def validate(*, root: Path, source_root: Path | None = None) -> list[str]:
    failures: list[str] = []
    _validate_required_anchors(root=root, failures=failures)

    registry_path = root / REGISTRY_PATH
    if not registry_path.is_file():
        failures.append(f"{REGISTRY_PATH}: missing or not a file")
        return failures

    registry = _load_yaml(registry_path)
    if not isinstance(registry, Mapping):
        return [*failures, f"{REGISTRY_PATH}: expected a YAML mapping"]

    _validate_preservation_policy(registry=registry, failures=failures)
    decisions = registry.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        failures.append(f"{REGISTRY_PATH}: decisions must be a non-empty list")
        return failures

    seen_ids: set[str] = set()
    for index, raw_decision in enumerate(decisions, start=1):
        if not isinstance(raw_decision, Mapping):
            failures.append(f"{REGISTRY_PATH}: decisions[{index}] must be a mapping")
            continue
        _validate_decision(
            root=root,
            source_root=source_root,
            decision=raw_decision,
            seen_ids=seen_ids,
            failures=failures,
        )

    return failures


def _validate_required_anchors(*, root: Path, failures: list[str]) -> None:
    for relative_path in REQUIRED_ANCHORS:
        path = root / relative_path
        if not path.is_file():
            failures.append(f"{relative_path}: missing or not a file")
            continue
        if path.stat().st_size == 0:
            failures.append(f"{relative_path}: empty source/history anchor")


def _validate_preservation_policy(
    *,
    registry: Mapping[str, Any],
    failures: list[str],
) -> None:
    if registry.get("schema_version") != "entroping.decision-registry.v1":
        failures.append(f"{REGISTRY_PATH}: invalid schema_version")

    policy = registry.get("preservation_policy")
    if not isinstance(policy, Mapping):
        failures.append(f"{REGISTRY_PATH}: preservation_policy must be a mapping")
        return
    if policy.get("archive_means") != "lower-default-reading-priority":
        failures.append(f"{REGISTRY_PATH}: archive_means must preserve data")
    if policy.get("summaries_replace_sources") is not False:
        failures.append(f"{REGISTRY_PATH}: summaries_replace_sources must be false")
    if policy.get("raw_sources_retained") is not True:
        failures.append(f"{REGISTRY_PATH}: raw_sources_retained must be true")


def _validate_decision(
    *,
    root: Path,
    source_root: Path | None,
    decision: Mapping[str, Any],
    seen_ids: set[str],
    failures: list[str],
) -> None:
    decision_id = decision.get("id")
    if not isinstance(decision_id, str) or not DECISION_ID_PATTERN.match(decision_id):
        failures.append(f"{REGISTRY_PATH}: decision id is invalid: {decision_id!r}")
        decision_id = "<unknown>"
    elif decision_id in seen_ids:
        failures.append(f"{REGISTRY_PATH}: duplicate decision id: {decision_id}")
    else:
        seen_ids.add(decision_id)

    for key in (
        "title",
        "status",
        "date",
        "summary",
        "tags",
        "source_links",
        "related_docs",
        "related_issues",
        "supersedes",
        "superseded_by",
    ):
        if key not in decision:
            failures.append(f"{REGISTRY_PATH}: {decision_id} missing {key}")

    if decision.get("status") not in {"accepted", "superseded", "proposed", "deferred"}:
        failures.append(f"{REGISTRY_PATH}: {decision_id} has invalid status")
    if not _non_empty_string(decision.get("title")):
        failures.append(f"{REGISTRY_PATH}: {decision_id} title is empty")
    if not _non_empty_string(decision.get("summary")):
        failures.append(f"{REGISTRY_PATH}: {decision_id} summary is empty")

    tags = decision.get("tags")
    if not isinstance(tags, list) or not tags or not all(_non_empty_string(tag) for tag in tags):
        failures.append(f"{REGISTRY_PATH}: {decision_id} tags must be non-empty strings")

    _validate_source_links(
        root=root,
        source_root=source_root,
        decision_id=decision_id,
        source_links=decision.get("source_links"),
        failures=failures,
    )
    _validate_related_docs(
        root=root,
        decision_id=decision_id,
        related_docs=decision.get("related_docs"),
        failures=failures,
    )
    _validate_related_issues(
        decision_id=decision_id,
        related_issues=decision.get("related_issues"),
        failures=failures,
    )


def _validate_source_links(
    *,
    root: Path,
    source_root: Path | None,
    decision_id: str,
    source_links: Any,
    failures: list[str],
) -> None:
    if not isinstance(source_links, list) or not source_links:
        failures.append(f"{REGISTRY_PATH}: {decision_id} source_links must be non-empty")
        return

    for index, source_link in enumerate(source_links, start=1):
        if not isinstance(source_link, Mapping):
            failures.append(
                f"{REGISTRY_PATH}: {decision_id} source_links[{index}] must be a mapping"
            )
            continue
        path_value = source_link.get("path")
        if not _non_empty_string(path_value):
            failures.append(f"{REGISTRY_PATH}: {decision_id} source_links[{index}] missing path")
            continue
        if not _non_empty_string(source_link.get("role")):
            failures.append(f"{REGISTRY_PATH}: {decision_id} source_links[{index}] missing role")

        if source_link.get("external") is True:
            if source_root is not None and not (source_root / path_value).is_file():
                failures.append(
                    f"{REGISTRY_PATH}: {decision_id} external source missing: {path_value}"
                )
            continue

        if _looks_unsafe_relative_path(path_value):
            failures.append(f"{REGISTRY_PATH}: {decision_id} unsafe source path: {path_value}")
            continue
        if not (root / path_value).is_file():
            failures.append(f"{REGISTRY_PATH}: {decision_id} source missing: {path_value}")


def _validate_related_docs(
    *,
    root: Path,
    decision_id: str,
    related_docs: Any,
    failures: list[str],
) -> None:
    if not isinstance(related_docs, list):
        failures.append(f"{REGISTRY_PATH}: {decision_id} related_docs must be a list")
        return

    for path_value in related_docs:
        if not _non_empty_string(path_value):
            failures.append(f"{REGISTRY_PATH}: {decision_id} related_docs contains a non-string")
            continue
        if _looks_unsafe_relative_path(path_value):
            failures.append(f"{REGISTRY_PATH}: {decision_id} unsafe related doc path: {path_value}")
            continue
        if not (root / path_value).is_file():
            failures.append(f"{REGISTRY_PATH}: {decision_id} related doc missing: {path_value}")


def _validate_related_issues(
    *,
    decision_id: str,
    related_issues: Any,
    failures: list[str],
) -> None:
    if not isinstance(related_issues, list):
        failures.append(f"{REGISTRY_PATH}: {decision_id} related_issues must be a list")
        return
    for issue in related_issues:
        if not isinstance(issue, str) or not ISSUE_PATTERN.match(issue):
            failures.append(f"{REGISTRY_PATH}: {decision_id} invalid related issue: {issue!r}")


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _looks_unsafe_relative_path(path_value: str) -> bool:
    path = Path(path_value)
    return path.is_absolute() or ".." in path.parts


if __name__ == "__main__":
    raise SystemExit(main())
