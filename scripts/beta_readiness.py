#!/usr/bin/env python3
"""Compose beta readiness from alpha launch, stable-core, and package-index signals."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

SchemaStatus = Literal["present", "missing", "warn", "fail", "error"]
OutputFormat = Literal["md", "json"]

SCHEMA_VERSION = "entroping.beta-readiness.v1"
LAUNCH_SCRIPT = "scripts/launch_readiness.py"
STABLE_CORE_SCRIPT = "scripts/stable_core_readiness.py"
PACKAGE_INDEX_SCRIPT = "scripts/package_index_readiness.py"


@dataclass(frozen=True)
class ReadyBlock:
    """Aggregated blocker summary for a readiness surface."""

    key: str
    status: bool
    blockers: tuple[str, ...]
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class BetaReadinessPayload:
    """Result envelope for local beta readiness composition."""

    alpha: dict[str, Any]
    stable_core: dict[str, Any]
    package_index: dict[str, Any]
    blockers: tuple[str, ...]
    beta_ready: bool


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate local alpha-launch, stable-core, and package-index readiness."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when beta readiness is blocked.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    payload = build_beta_readiness_payload(root=root)

    if args.format == "json":
        print(json.dumps(_serialize_payload(payload), indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict and not payload.beta_ready:
        print("beta readiness check failed", file=sys.stderr)
        for blocker in payload.blockers:
            print(f"  {blocker}", file=sys.stderr)
        return 1
    return 0


def build_beta_readiness_payload(*, root: Path) -> BetaReadinessPayload:
    launch = run_readiness_script(LAUNCH_SCRIPT, root)
    stable_core = run_readiness_script(STABLE_CORE_SCRIPT, root)
    package_index = run_readiness_script(PACKAGE_INDEX_SCRIPT, root)

    alpha_blockers = tuple(
        f"alpha:{key}: {status}"
        for key, status in _launch_blockers(launch).items()
        if status != "present"
    )

    stable_core_blockers = tuple(_stable_core_blockers(stable_core))
    package_index_blockers = tuple(_package_index_blockers(package_index))

    blockers = tuple(
        item
        for group in (alpha_blockers, stable_core_blockers, package_index_blockers)
        for item in group
    )

    alpha_ready = bool(launch.get("alpha_launch_ready", False))
    stable_core_ready = bool(stable_core.get("stable_core_ready", False))
    package_ready = bool(package_index.get("package_index_ready", False))
    repo_guardrails_ready = bool(package_index.get("repo_guardrails_ready", False))

    return BetaReadinessPayload(
        alpha={
            "ready": alpha_ready,
            "blockers": list(alpha_blockers),
            "checks": launch,
        },
        stable_core={
            "ready": stable_core_ready,
            "blockers": list(stable_core_blockers),
            "checks": stable_core,
        },
        package_index={
            "ready": package_ready,
            "repo_guardrails_ready": bool(
                package_index.get("repo_guardrails_ready", False)
            ),
            "blockers": list(package_index_blockers),
            "checks": package_index,
        },
        blockers=blockers,
        beta_ready=(
            alpha_ready
            and stable_core_ready
            and package_ready
            and repo_guardrails_ready
        ),
    )


def _launch_blockers(payload: dict[str, object]) -> dict[str, SchemaStatus]:
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return {}

    values: dict[str, SchemaStatus] = {}
    for key, raw_check in checks.items():
        if not isinstance(raw_check, dict):
            continue
        status = raw_check.get("status")
        if isinstance(status, str):
            values[key] = cast(SchemaStatus, status)
    return values


def _stable_core_blockers(payload: dict[str, object]) -> list[str]:
    if payload.get("stable_core_ready") is True:
        return []
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        return ["stable_core: blockers metadata unavailable"]

    return [f"stable_core:{blocker}" for blocker in blockers if isinstance(blocker, str)]


def _package_index_blockers(payload: dict[str, object]) -> list[str]:
    if payload.get("package_index_ready") is True and payload.get("repo_guardrails_ready") is True:
        return []

    blockers: list[str] = []
    if payload.get("package_index_ready") is not True:
        blockers.append("package_index: package index proof not complete")
    if payload.get("repo_guardrails_ready") is not True:
        blockers.append("package_index: repo guardrails not ready")

    checks = payload.get("repo_failures")
    if isinstance(checks, list):
        for failure in checks:
            if isinstance(failure, str):
                blockers.append(f"package_index: {failure}")

    return blockers


def run_readiness_script(script: str, root: Path) -> dict[str, Any]:
    command = (
        sys.executable,
        str(root / script),
        "--root",
        str(root),
        "--format",
        "json",
    )
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"error": "script execution failed"}

    if result.returncode != 0:
        return {"error": f"{script} failed: {result.stderr.strip()[:200]}"}

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"{script} did not emit JSON"}

    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    return {"error": f"{script} output was not a JSON object"}


def _serialize_payload(payload: BetaReadinessPayload) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "beta_ready": payload.beta_ready,
        "alpha": payload.alpha,
        "stable_core": payload.stable_core,
        "package_index": payload.package_index,
        "blockers": list(payload.blockers),
    }


def _render_markdown(payload: BetaReadinessPayload) -> str:
    lines = [
        "# Beta Readiness",
        "",
        f"- Schema: `{SCHEMA_VERSION}`",
        f"- Alpha launch ready: `{str(payload.alpha['ready']).lower()}`",
        f"- Stable-core ready: `{str(payload.stable_core['ready']).lower()}`",
        f"- Package-index ready: `{str(payload.package_index['ready']).lower()}`",
        f"- Beta ready: `{str(payload.beta_ready).lower()}`",
        "",
        "## Blocker separation",
        "",
    ]

    lines.append("### Alpha blockers")
    if payload.alpha["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload.alpha["blockers"])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("### Stable-core blockers")
    if payload.stable_core["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload.stable_core["blockers"])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("### Package-index blockers")
    if payload.package_index["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload.package_index["blockers"])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Stability contract")
    lines.append("- Beta readiness requires all three surfaces to report ready.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
