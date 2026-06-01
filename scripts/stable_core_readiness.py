#!/usr/bin/env python3
"""Report stable-core readiness evidence without overclaiming stability."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = "entroping.stable-core-readiness.v1"
CheckStatus = Literal["present", "missing", "marker-missing", "invalid"]


@dataclass(frozen=True)
class EvidenceCheck:
    """One required stable-core evidence surface."""

    key: str
    path: str
    marker: str
    description: str


EVIDENCE_CHECKS = (
    EvidenceCheck(
        key="readme_alpha_boundary",
        path="README.md",
        marker="Still alpha",
        description="README keeps alpha boundaries visible.",
    ),
    EvidenceCheck(
        key="roadmap_stable_core",
        path="ROADMAP.md",
        marker="Future: v1.0 Stable Core",
        description="Roadmap separates current alpha work from stable-core proof.",
    ),
    EvidenceCheck(
        key="release_check",
        path="scripts/release_check.sh",
        marker="scripts/regression.sh --security",
        description="Release gate includes security regression evidence.",
    ),
    EvidenceCheck(
        key="quality_audit",
        path="scripts/audit_quality.sh",
        marker="pytest-cov",
        description="Quality audit enforces coverage and maintenance checks.",
    ),
    EvidenceCheck(
        key="security_threat_model",
        path="docs/technical/THREAT_MODEL.md",
        marker="Before stable-core claims",
        description="Threat model defines security evidence before stable-core claims.",
    ),
    EvidenceCheck(
        key="cli_compatibility",
        path="docs/technical/CLI_COMPATIBILITY_AUDIT.md",
        marker="Locked alpha",
        description="CLI compatibility policy is explicit before stability promises.",
    ),
    EvidenceCheck(
        key="install_smoke_matrix",
        path="docs/meta/INSTALL_SMOKE_MATRIX.md",
        marker="install-smoke",
        description="Install/support claims are tied to platform evidence.",
    ),
    EvidenceCheck(
        key="performance_smoke",
        path="scripts/performance_smoke.py",
        marker="performance",
        description="Performance smoke evidence exists for scale claims.",
    ),
    EvidenceCheck(
        key="dependency_license_policy",
        path="docs/meta/dependency-license-policy.json",
        marker="allowed_license_families",
        description="Direct dependencies require reviewed license policy entries.",
    ),
    EvidenceCheck(
        key="public_claims_audit",
        path="scripts/public_claims_audit.py",
        marker="Public claims audit OK",
        description="Public claims are checked for unsupported production/security language.",
    ),
    EvidenceCheck(
        key="release_evidence_ledger",
        path="docs/meta/release-evidence.json",
        marker="entroping.release-evidence.v1",
        description=(
            "Release evidence ledger records alpha releases, recorded main CI, "
            "and stable-core blockers."
        ),
    ),
)

STABLE_CORE_BLOCKERS = (
    "repeated release evidence",
    "package-index proof",
    "real downstream user feedback",
    "stable-core compatibility decision",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize stable-core evidence and fail only when required evidence is missing."
        )
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
        help="Exit non-zero when required evidence files or markers are missing.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    payload = _build_payload(root)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    missing = [
        f"{entry['path']}: {entry['status']}"
        for entry in payload["evidence"].values()
        if entry["status"] != "present"
    ]
    if args.strict and missing:
        print("stable-core evidence check failed:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


def _build_payload(root: Path) -> dict[str, object]:
    evidence: dict[str, dict[str, str]] = {}
    for check in EVIDENCE_CHECKS:
        status = _check_evidence(root, check)
        evidence[check.key] = {
            "path": check.path,
            "status": status,
            "description": check.description,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "stable_core_ready": False,
        "blockers": list(STABLE_CORE_BLOCKERS),
        "evidence": evidence,
    }


def _check_evidence(root: Path, check: EvidenceCheck) -> CheckStatus:
    target = root / check.path
    if not target.is_file():
        return "missing"
    content = target.read_text(encoding="utf-8", errors="replace")
    if check.marker not in content:
        return "marker-missing"
    if check.key != "release_evidence_ledger":
        return "present"

    release_evidence_script = root / "scripts" / "release_evidence.py"
    if not release_evidence_script.is_file():
        return "invalid"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(release_evidence_script),
                "--root",
                str(root),
                "--strict",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "invalid"
    return "present" if result.returncode == 0 else "invalid"


def _render_markdown(payload: dict[str, object]) -> str:
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    lines = [
        "# Stable-Core Readiness",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = payload["blockers"]
    assert isinstance(blockers, list)
    lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(["", "## Evidence", ""])
    for key, raw_entry in evidence.items():
        assert isinstance(raw_entry, dict)
        lines.append(
            f"- `{key}`: {raw_entry['status']} ({raw_entry['path']}) - "
            f"{raw_entry['description']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
