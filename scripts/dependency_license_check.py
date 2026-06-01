#!/usr/bin/env python3
"""Check direct dependency license policy coverage."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEPENDENCY_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class DependencyRef:
    """One direct dependency declared in pyproject.toml."""

    group: str
    name: str
    spec: str

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"


@dataclass(frozen=True)
class PolicyEntry:
    """One reviewed dependency-license policy entry."""

    group: str
    name: str
    license_family: str
    spdx: str
    notes: str

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify every direct dependency has a reviewed allowed license policy entry."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to check.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    try:
        declared = _declared_dependencies(root / "pyproject.toml")
        allowed, entries = _load_policy(root / "docs" / "meta" / "dependency-license-policy.json")
    except ValueError as exc:
        print(f"Dependency license policy failed: {exc}", file=sys.stderr)
        return 1

    failures = _policy_failures(declared, allowed, entries)
    if failures:
        print("Dependency license policy failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Dependency license policy OK: {len(declared)} direct dependencies reviewed")
    for dependency in declared:
        entry = entries[dependency.key]
        print(f"reviewed: {dependency.key} ({entry.spdx})")
    return 0


def _declared_dependencies(pyproject_path: Path) -> tuple[DependencyRef, ...]:
    if not pyproject_path.is_file():
        msg = f"missing {pyproject_path}"
        raise ValueError(msg)
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies: list[DependencyRef] = []

    project = _mapping(data.get("project"), "project")
    for spec in _string_list(project.get("dependencies"), "project.dependencies"):
        dependencies.append(
            DependencyRef(group="dependencies/default", name=_dependency_name(spec), spec=spec)
        )

    optional_dependencies = _mapping(
        project.get("optional-dependencies"),
        "project.optional-dependencies",
    )
    for group_name, specs in sorted(optional_dependencies.items()):
        for spec in _string_list(specs, f"project.optional-dependencies.{group_name}"):
            dependencies.append(
                DependencyRef(
                    group=f"optional-dependencies/{group_name}",
                    name=_dependency_name(spec),
                    spec=spec,
                )
            )

    dependency_groups = _mapping(data.get("dependency-groups"), "dependency-groups")
    for group_name, specs in sorted(dependency_groups.items()):
        for spec in _string_list(specs, f"dependency-groups.{group_name}"):
            dependencies.append(
                DependencyRef(
                    group=f"dependency-groups/{group_name}",
                    name=_dependency_name(spec),
                    spec=spec,
                )
            )
    return tuple(dependencies)


def _load_policy(path: Path) -> tuple[set[str], dict[str, PolicyEntry]]:
    if not path.is_file():
        msg = f"missing {path}"
        raise ValueError(msg)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dependency license policy must be a JSON object")
    allowed = payload.get("allowed_license_families")
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise ValueError("allowed_license_families must be a string list")
    if not isinstance(payload.get("reviewed_at"), str) or not payload["reviewed_at"]:
        raise ValueError("reviewed_at must be set")

    raw_entries = payload.get("dependencies")
    if not isinstance(raw_entries, list):
        raise ValueError("dependencies must be a list")
    entries: dict[str, PolicyEntry] = {}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"dependencies[{index}] must be an object")
        entry = PolicyEntry(
            group=_required_string(raw_entry, "group", index),
            name=_normalize_name(_required_string(raw_entry, "name", index)),
            license_family=_required_string(raw_entry, "license_family", index),
            spdx=_required_string(raw_entry, "spdx", index),
            notes=_required_string(raw_entry, "notes", index),
        )
        if entry.key in entries:
            raise ValueError(f"duplicate dependency policy entry {entry.key}")
        entries[entry.key] = entry
    return set(allowed), entries


def _policy_failures(
    declared: tuple[DependencyRef, ...],
    allowed: set[str],
    entries: dict[str, PolicyEntry],
) -> tuple[str, ...]:
    failures: list[str] = []
    for dependency in declared:
        entry = entries.get(dependency.key)
        if entry is None:
            failures.append(f"unreviewed direct dependency {dependency.key}")
            continue
        if entry.license_family not in allowed:
            failures.append(
                f"{dependency.key}: disallowed license family {entry.license_family}"
            )
    declared_keys = {dependency.key for dependency in declared}
    for key in sorted(entries):
        if key not in declared_keys:
            failures.append(f"stale dependency policy entry {key}")
    return tuple(failures)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        msg = f"{path} must be a mapping"
        raise ValueError(msg)
    return value


def _string_list(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{path} must be a string list"
        raise ValueError(msg)
    return tuple(value)


def _dependency_name(spec: str) -> str:
    match = DEPENDENCY_NAME_RE.match(spec)
    if match is None:
        msg = f"could not parse dependency spec {spec!r}"
        raise ValueError(msg)
    return _normalize_name(match.group(1))


def _normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()


def _required_string(raw_entry: dict[str, Any], key: str, index: int) -> str:
    value = raw_entry.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"dependencies[{index}].{key} must be a non-empty string"
        raise ValueError(msg)
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
