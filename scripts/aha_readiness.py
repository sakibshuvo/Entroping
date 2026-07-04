#!/usr/bin/env python3
"""Report local Aha-path readiness for deterministic onboarding checks.

The scorecard is intentionally local/offline and separates local blockers from
external prerequisite blockers such as package-index or installed CLI surface
gates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

SCHEMA_VERSION = "entroping.aha-readiness.v1"
MAX_READ_TEXT_BYTES = 1024 * 1024
CheckStatus = Literal["ready", "partial", "blocked"]


@dataclass(frozen=True)
class Check:
    key: str
    path: str
    category: Literal["local", "external"]
    description: str
    markers: tuple[str, ...]
    allow_marker_subset: bool = True


LOCAL_CHECKS = (
    Check(
        key="checkout_demo_entrypoint",
        path="scripts/demo.sh",
        category="local",
        description=(
            "Checkout Aha path delegates to the stable live smoke script and keeps "
            "proof command semantics stable in repo-local usage."
        ),
        markers=("scripts/live_demo_smoke.sh",),
    ),
    Check(
        key="failure_fixture_package",
        path="examples/aha-broken-endpoint/README.md",
        category="local",
        description="Failure-proof fixture is available for one-command checkout checks.",
        markers=("entroping run", "no_missing_product_endpoint"),
        allow_marker_subset=False,
    ),
    Check(
        key="failure_proof_readme",
        path="examples/ai-regression-demo/README.md",
        category="local",
        description=(
            "Failure-proof walkthrough explains deterministic gate failure and expected "
            "`request_id_header` behavior."
        ),
        markers=("request_id_header", "X-Request-Id", "scripts/ai_regression_demo.sh"),
    ),
    Check(
        key="failure_demo_script",
        path="scripts/ai_regression_demo.sh",
        category="local",
        description=(
            "Failure demo wrapper runs a deterministic API regression fixture and "
            "reports the expected policy-block result."
        ),
        markers=("request_id_header",),
        allow_marker_subset=False,
    ),
    Check(
        key="demo_generation_and_run_matrix",
        path="scripts/demo_matrix.sh",
        category="local",
        description=(
            "Launch matrix includes both happy-path checkout and failure proofs to "
            "exercise generation and run surfaces."
        ),
        markers=(
            "scripts/demo.sh",
            "scripts/ai_regression_demo.sh",
            "scripts/launch_readiness.py --strict",
        ),
    ),
)

EXTERNAL_CHECKS = (
    Check(
        key="package_install_command_surface",
        path="docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT.md",
        category="external",
        description=(
            "Package-installed entrypoint prerequisites are satisfied before claiming "
            "Aha ready."
        ),
        markers=("entroping demo --project",),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an Aha onboarding readiness scorecard."
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
        help="Exit non-zero when any check is not ready or not explicitly blocked.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    payload = _build_payload(root)

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict and payload["status"] != "ready":
        print("aha readiness check failed:", file=sys.stderr)
        for check in payload["checks"].values():
            if check["status"] != "ready":
                print(f"  {check['key']}: {check['status']}", file=sys.stderr)
        return 1

    return 0


def _build_payload(root: Path) -> dict[str, object]:
    checks: dict[str, dict[str, object]] = {}
    local_blockers: list[dict[str, str]] = []
    external_blockers: list[dict[str, str]] = []

    for check in _iter_checks():
        result = _evaluate_check(root, check)
        checks[check.key] = {
            "key": check.key,
            "category": check.category,
            "status": result.status,
            "path": str(check.path),
            "detail": result.detail,
            "description": check.description,
        }

        if result.status == "blocked":
            bucket = local_blockers if check.category == "local" else external_blockers
            bucket.append({"key": check.key, "reason": result.detail})

    overall = _aggregate_status(checks)
    ready_count = sum(1 for check in checks.values() if check["status"] == "ready")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": overall,
        "aha_ready": overall == "ready",
        "stable_core_ready": False,
        "ready_checks": ready_count,
        "total_checks": len(checks),
        "checks": checks,
        "local_blockers": local_blockers,
        "external_blockers": external_blockers,
    }


def _iter_checks() -> tuple[Check, ...]:
    return tuple((*LOCAL_CHECKS, *EXTERNAL_CHECKS))


def _evaluate_check(root: Path, check: Check) -> _Result:
    path = root / check.path
    if not path.exists():
        return _Result("blocked", f"Missing evidence file: {check.path}")

    content = _read_text_file_bounded(path)

    if check.category == "external" and "deferred" in content.lower():
        return _Result(
            "blocked",
            (
                "Package-installed Aha entrypoint is explicitly deferred in "
                "docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT.md"
            ),
        )

    normalized = content.lower()
    for marker in check.markers:
        if marker.lower() not in normalized:
            status: CheckStatus = "partial"
            if check.allow_marker_subset:
                return _Result(
                    status,
                    f"Evidence marker missing in {check.path}: {marker}",
                )
            return _Result(
                "blocked",
                f"Required evidence marker missing in {check.path}: {marker}",
            )

    return _Result("ready", "present")


@dataclass(frozen=True)
class _Result:
    status: CheckStatus
    detail: str


def _aggregate_status(checks: dict[str, dict[str, object]]) -> str:
    if any(entry["status"] == "blocked" for entry in checks.values()):
        return "blocked"
    if any(entry["status"] == "partial" for entry in checks.values()):
        return "partial"
    return "ready"


def _read_text_file_bounded(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(MAX_READ_TEXT_BYTES + 1)

    if len(data) > MAX_READ_TEXT_BYTES:
        raise ValueError(
            f"Refusing to read {path}: file exceeds "
            f"max_read_text_bytes={MAX_READ_TEXT_BYTES}"
        )
    return data.decode("utf-8", errors="replace")


def _render_markdown(payload: dict[str, object]) -> str:
    checks = cast(dict[str, dict[str, object]], payload["checks"])
    lines = [
        "# Aha Readiness Scorecard",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Status: `{payload['status']}`",
        f"- Aha ready: `{str(payload['aha_ready']).lower()}`",
        "- Stable core ready: `false`",
        f"- Local blockers: {len(payload['local_blockers'])}",
        f"- External blockers: {len(payload['external_blockers'])}",
        "",
        "## Checks",
    ]

    for check in checks.values():
        status = cast(str, check["status"])
        lines.append(f"- `{check['key']}` ({check['category']}): {status}")
        lines.append(f"  - {check['detail']}")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
