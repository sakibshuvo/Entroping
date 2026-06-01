#!/usr/bin/env python3
"""Aggregate alpha launch-readiness evidence without overclaiming stability."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = "entroping.alpha-launch-readiness.v1"

CheckStatus = Literal["present", "missing", "marker-missing", "not-executable"]


@dataclass(frozen=True)
class EvidenceCheck:
    """One alpha launch evidence surface."""

    key: str
    path: str
    marker: str
    description: str
    executable: bool = False


EVIDENCE_CHECKS = (
    EvidenceCheck(
        key="readme_checkout_demo",
        path="README.md",
        marker="scripts/demo.sh",
        description="README exposes the friendly checkout demo entrypoint.",
    ),
    EvidenceCheck(
        key="readme_ai_regression_demo",
        path="README.md",
        marker="examples/ai-regression-demo",
        description="README links the AI-regression failure proof.",
    ),
    EvidenceCheck(
        key="release_check",
        path="scripts/release_check.sh",
        marker="scripts/launch_readiness.py --strict",
        description="Release gate runs the alpha launch-readiness check.",
        executable=True,
    ),
    EvidenceCheck(
        key="demo_matrix",
        path="scripts/demo_matrix.sh",
        marker="scripts/ai_regression_demo.sh",
        description="Maintainer launch rehearsal ties happy path and failure proof together.",
        executable=True,
    ),
    EvidenceCheck(
        key="policy_pack_smoke",
        path="scripts/policy_pack_smoke.py",
        marker="entroping.policy-pack-smoke.v1",
        description="Policy-pack import evidence is locally reproducible.",
    ),
    EvidenceCheck(
        key="stable_core_readiness",
        path="scripts/stable_core_readiness.py",
        marker="entroping.stable-core-readiness.v1",
        description="Stable-core blockers remain explicit.",
    ),
    EvidenceCheck(
        key="public_claims_audit",
        path="scripts/public_claims_audit.py",
        marker="Public claims audit OK",
        description="Public launch claims reject unsupported production/security language.",
    ),
    EvidenceCheck(
        key="backlog_health",
        path="scripts/backlog_health.py",
        marker="Backlog health OK",
        description="Open issues remain labeled, prioritized, statused, and milestone-backed.",
    ),
    EvidenceCheck(
        key="release_checklist",
        path="docs/meta/RELEASE_CHECKLIST.md",
        marker="scripts/demo_matrix.sh",
        description="Release checklist points maintainers to launch rehearsal evidence.",
    ),
    EvidenceCheck(
        key="test_strategy",
        path="docs/meta/TEST_STRATEGY.md",
        marker="scripts/policy_pack_smoke.py",
        description="Test strategy documents the policy-pack and launch-readiness proof layer.",
    ),
    EvidenceCheck(
        key="roadmap_v04",
        path="ROADMAP.md",
        marker="Current: v0.4.0-alpha Integrations",
        description="Roadmap keeps the current integration milestone visible.",
    ),
    EvidenceCheck(
        key="roadmap_stable_boundary",
        path="ROADMAP.md",
        marker="project stable just because",
        description="Roadmap separates alpha readiness from stable-core claims.",
    ),
)

STABLE_CORE_BLOCKERS = (
    "stable-core still requires package-index proof",
    "stable-core still requires compatibility discipline across real releases",
    "stable-core still requires real-user feedback",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize alpha launch evidence and fail when required files drift."
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
        help="Exit non-zero when required alpha launch evidence is missing.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    payload = _build_payload(root)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    failures = _failure_messages(payload)
    if args.strict and failures:
        print("alpha launch-readiness check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


def _build_payload(root: Path) -> dict[str, object]:
    checks: dict[str, dict[str, str]] = {}
    for check in EVIDENCE_CHECKS:
        target = root / check.path
        status = _check_status(target, check)
        checks[check.key] = {
            "path": check.path,
            "status": status,
            "description": check.description,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "alpha_launch_ready": all(entry["status"] == "present" for entry in checks.values()),
        "stable_core_ready": False,
        "stable_core_blockers": list(STABLE_CORE_BLOCKERS),
        "checks": checks,
    }


def _check_status(target: Path, check: EvidenceCheck) -> CheckStatus:
    if not target.is_file():
        return "missing"
    if check.executable and not target.stat().st_mode & 0o111:
        return "not-executable"
    content = target.read_text(encoding="utf-8", errors="replace")
    if check.marker not in content:
        return "marker-missing"
    return "present"


def _failure_messages(payload: dict[str, object]) -> list[str]:
    checks = payload["checks"]
    assert isinstance(checks, dict)
    failures: list[str] = []
    for entry in checks.values():
        assert isinstance(entry, dict)
        if entry["status"] != "present":
            failures.append(f"{entry['path']}: {entry['status']}")
    return failures


def _render_markdown(payload: dict[str, object]) -> str:
    checks = payload["checks"]
    assert isinstance(checks, dict)
    lines = [
        "# Alpha Launch Readiness",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Alpha launch ready: `{str(payload['alpha_launch_ready']).lower()}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        "",
        "## Stable-Core Blockers",
        "",
    ]
    blockers = payload["stable_core_blockers"]
    assert isinstance(blockers, list)
    lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(["", "## Checks", ""])
    for key, raw_entry in checks.items():
        assert isinstance(raw_entry, dict)
        lines.append(
            f"- `{key}`: {raw_entry['status']} ({raw_entry['path']}) - "
            f"{raw_entry['description']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
