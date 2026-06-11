#!/usr/bin/env python3
"""Emit a deterministic taxonomy of the Entroping test suite."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "entroping.test-taxonomy.v1"
GENERATED_BY = "scripts/test_taxonomy.py"


@dataclass(frozen=True)
class Category:
    name: str
    description: str


@dataclass(frozen=True)
class TestFileSummary:
    path: str
    static_test_count: int
    markers: tuple[str, ...]
    categories: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(
        "behavior",
        "Runtime, domain, adapter, and compiler behavior tests for product code.",
    ),
    Category(
        "docs-compliance",
        "Tests that keep public docs, roadmap, release evidence, and claims honest.",
    ),
    Category(
        "script-integrity",
        "Tests that protect maintainer scripts, CI helpers, and local automation.",
    ),
    Category(
        "integration",
        "Cross-subsystem tests, installed CLI paths, and end-to-end local workflows.",
    ),
    Category("smoke", "Boot, demo, install, and fast confidence checks."),
    Category(
        "regression",
        "Tests preserving fragile behavior, compatibility promises, or fixed bugs.",
    ),
    Category(
        "security",
        "Negative tests for secrets, redaction, path handling, subprocess, and policy risk.",
    ),
)

REQUIRED_CATEGORIES = tuple(category.name for category in CATEGORIES)

PYTEST_MARKER_TO_CATEGORY = {
    "unit": "behavior",
    "adapter": "behavior",
    "integration": "integration",
    "smoke": "smoke",
    "regression": "regression",
    "security": "security",
}

DOCS_TOKENS = (
    "docs",
    "documentation",
    "readme",
    "release_docs",
    "release_evidence",
    "launch_readiness",
    "stable_core_readiness",
    "public_claims",
    "ci_workflow",
)

SCRIPT_TOKENS = (
    "script",
    "scripts",
    "repo_hygiene",
    "shell_quality",
    "audit_quality",
    "backlog_health",
    "dependency_license",
    "deepseek_worker",
    "opencode_worker",
    "ai_jobs",
    "release_check",
    "release_evidence",
    "performance_smoke",
    "policy_pack_smoke",
    "downstream_smoke",
    "local_wheel_install_smoke",
)

INTEGRATION_TOKENS = (
    "integration",
    "e2e",
    "downstream",
    "local_wheel_install",
    "cli_real_hurl",
)

SMOKE_TOKENS = (
    "smoke",
    "demo",
    "cli_real_hurl",
    "local_wheel_install",
    "downstream",
)

REGRESSION_TOKENS = (
    "regression",
    "architecture_boundaries",
    "compatibility",
    "schema_contract",
    "release_docs",
    "stable_core_readiness",
)

SECURITY_TOKENS = (
    "security",
    "redaction",
    "secret",
    "path_safety",
    "safe_write",
    "hurl_runner",
    "hurl_validator",
    "traffic_redactor",
    "policy_pack_vendor",
    "litellm_client",
    "config_writer",
)


def _marker_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not isinstance(target, ast.Attribute):
        return None
    marker = target.attr
    mark_value = target.value
    if (
        isinstance(mark_value, ast.Attribute)
        and mark_value.attr == "mark"
        and isinstance(mark_value.value, ast.Name)
        and mark_value.value.id == "pytest"
    ):
        return marker
    return None


def _test_count(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    )


def _markers(tree: ast.AST) -> tuple[str, ...]:
    markers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                marker = _marker_name(decorator)
                if marker:
                    markers.add(marker)
    return tuple(sorted(markers))


def _contains(path: str, tokens: tuple[str, ...]) -> bool:
    return any(token in path for token in tokens)


def _categories(path: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    lowered = path.lower().replace("-", "_")
    categories: set[str] = set()

    for marker in markers:
        category = PYTEST_MARKER_TO_CATEGORY.get(marker)
        if category:
            categories.add(category)

    if _contains(lowered, DOCS_TOKENS):
        categories.add("docs-compliance")
    if _contains(lowered, SCRIPT_TOKENS):
        categories.add("script-integrity")
    if _contains(lowered, INTEGRATION_TOKENS):
        categories.add("integration")
    if _contains(lowered, SMOKE_TOKENS):
        categories.add("smoke")
    if _contains(lowered, REGRESSION_TOKENS):
        categories.add("regression")
    if _contains(lowered, SECURITY_TOKENS):
        categories.add("security")

    if "docs-compliance" not in categories and "script-integrity" not in categories:
        categories.add("behavior")

    return tuple(category for category in REQUIRED_CATEGORIES if category in categories)


def _declared_pytest_markers(repo_root: Path) -> tuple[str, ...]:
    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    raw_markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get(
        "markers", ()
    )
    declared: list[str] = []
    if isinstance(raw_markers, list):
        for raw_marker in raw_markers:
            if isinstance(raw_marker, str):
                declared.append(raw_marker.split(":", maxsplit=1)[0].strip())
    return tuple(sorted(marker for marker in declared if marker))


def collect_test_files(repo_root: Path) -> tuple[TestFileSummary, ...]:
    tests_root = repo_root / "tests"
    summaries: list[TestFileSummary] = []
    for path in sorted(tests_root.glob("test_*.py")):
        relative = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        count = _test_count(tree)
        markers = _markers(tree)
        summaries.append(
            TestFileSummary(
                path=relative,
                static_test_count=count,
                markers=markers,
                categories=_categories(relative, markers),
            )
        )
    return tuple(summaries)


def build_report(repo_root: Path) -> dict[str, object]:
    files = collect_test_files(repo_root)
    categories: dict[str, dict[str, object]] = {}
    for category in CATEGORIES:
        category_files = [
            file_summary for file_summary in files if category.name in file_summary.categories
        ]
        categories[category.name] = {
            "description": category.description,
            "file_count": len(category_files),
            "static_test_count": sum(
                file_summary.static_test_count for file_summary in category_files
            ),
            "files": [
                {
                    "path": file_summary.path,
                    "static_test_count": file_summary.static_test_count,
                    "markers": list(file_summary.markers),
                }
                for file_summary in category_files
            ],
        }

    marker_usage: dict[str, int] = {}
    for file_summary in files:
        for marker in file_summary.markers:
            marker_usage[marker] = marker_usage.get(marker, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "test_file_count": len(files),
        "static_test_count": sum(file_summary.static_test_count for file_summary in files),
        "required_categories": list(REQUIRED_CATEGORIES),
        "declared_pytest_markers": list(_declared_pytest_markers(repo_root)),
        "used_pytest_markers": {
            marker: marker_usage[marker] for marker in sorted(marker_usage)
        },
        "categories": categories,
    }


def _summary_lines(report: dict[str, object]) -> list[str]:
    categories = report["categories"]
    if not isinstance(categories, dict):
        raise TypeError("invalid taxonomy categories")
    lines = [
        (
            f"Test taxonomy: {report['test_file_count']} files, "
            f"{report['static_test_count']} static tests"
        )
    ]
    for category in REQUIRED_CATEGORIES:
        entry = categories[category]
        if not isinstance(entry, dict):
            raise TypeError(f"invalid taxonomy category: {category}")
        lines.append(
            f"{category}: {entry['file_count']} files, "
            f"{entry['static_test_count']} static tests"
        )
    return lines


def _validate_strict(report: dict[str, object]) -> list[str]:
    categories = report["categories"]
    if not isinstance(categories, dict):
        return ["taxonomy categories must be a mapping"]
    failures: list[str] = []
    for category in REQUIRED_CATEGORIES:
        entry = categories.get(category)
        if not isinstance(entry, dict):
            failures.append(f"missing taxonomy category: {category}")
            continue
        if int(entry.get("file_count", 0)) <= 0:
            failures.append(f"taxonomy category has no files: {category}")
        if int(entry.get("static_test_count", 0)) <= 0:
            failures.append(f"taxonomy category has no static tests: {category}")
    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/test-taxonomy.json"),
        help="JSON artifact path to write.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the taxonomy summary without writing the JSON artifact.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when required taxonomy categories have no file or test evidence.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = repo_root / output

    report = build_report(repo_root)
    for line in _summary_lines(report):
        print(line)

    failures = _validate_strict(report) if args.strict else []
    if failures:
        for failure in failures:
            print(f"test taxonomy failed: {failure}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would write test taxonomy: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote test taxonomy: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
