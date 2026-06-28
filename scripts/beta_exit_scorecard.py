#!/usr/bin/env python3
"""Beta exit scorecard: compose readiness evidence for beta-critical issues.

Lists pass/fail evidence for #303, #304, #305, #306, #308, and optional #587.
Alpha-ready and beta-ready claims remain clearly separated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

SCHEMA_VERSION = "entroping.beta-exit-scorecard.v1"
GateStatus = Literal["pass", "fail", "blocked", "not-applicable"]


@dataclass(frozen=True)
class BetaGate:
    """One beta-exit gate that must be proven before beta claims."""

    key: str
    issue_number: int
    label: str
    alpha_gate: bool
    readiness_script: str
    required_marker: str
    description: str
    optional: bool = False


BETA_GATES = (
    BetaGate(
        key="testpypi_trusted_publisher",
        issue_number=303,
        label="TestPyPI Trusted Publisher configured",
        alpha_gate=True,
        readiness_script="scripts/package_index_readiness.py",
        required_marker="external_requirements",
        description="Trusted Publisher or token-based publish path is configured for TestPyPI.",
    ),
    BetaGate(
        key="testpypi_alpha_publish",
        issue_number=304,
        label="TestPyPI alpha published and smoke-installed",
        alpha_gate=True,
        readiness_script="scripts/package_index_readiness.py",
        required_marker="package_index_ready",
        description="At least one TestPyPI alpha was published and installed from a fresh venv.",
    ),
    BetaGate(
        key="pypi_alpha_publish",
        issue_number=305,
        label="PyPI alpha published after TestPyPI proof",
        alpha_gate=False,
        readiness_script="scripts/package_index_readiness.py",
        required_marker="package_index_ready",
        description="A PyPI alpha was published after TestPyPI smoke proved the publish path.",
    ),
    BetaGate(
        key="downstream_feedback",
        issue_number=306,
        label="Real downstream user feedback collected",
        alpha_gate=False,
        readiness_script="scripts/stable_core_readiness.py",
        required_marker="downstream",
        description="At least one real downstream user or external project has provided feedback.",
    ),
    BetaGate(
        key="compatibility_decision",
        issue_number=308,
        label="Stable-core compatibility graduation decided",
        alpha_gate=False,
        readiness_script="scripts/stable_core_readiness.py",
        required_marker="compatibility",
        description="A documented compatibility decision separates alpha from stable-core promises.",
    ),
    BetaGate(
        key="homebrew_tap",
        issue_number=587,
        label="Homebrew tap formula ready",
        alpha_gate=False,
        readiness_script="scripts/package_index_readiness.py",
        required_marker="homebrew",
        description="Homebrew tap formula is ready for publish after package-index proof.",
        optional=True,
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose beta-exit evidence from readiness gates."
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
        help="Exit non-zero when any non-optional beta gate is not passing.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    payload = _build_payload(root)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict:
        gates_list = cast(list[dict[str, object]], payload["gates"])
        non_optional = [g for g in gates_list if not g["optional"]]
        failing = [g for g in non_optional if g["status"] != "pass"]
        if failing:
            print("beta exit scorecard failed:", file=sys.stderr)
            for gate in failing:
                print(f"  #{cast(object, gate['issue_number'])} {cast(object, gate['label'])}: {cast(object, gate['status'])} - {cast(object, gate['detail'])}", file=sys.stderr)
            return 1
    return 0


def _build_payload(root: Path) -> dict[str, object]:
    gates: list[dict[str, object]] = []
    for gate in BETA_GATES:
        status, detail = _evaluate_gate(root, gate)
        gates.append({
            "key": gate.key,
            "issue_number": gate.issue_number,
            "issue_url": f"https://github.com/sakibshuvo/Entroping/issues/{gate.issue_number}",
            "label": gate.label,
            "alpha_gate": gate.alpha_gate,
            "optional": gate.optional,
            "status": status,
            "detail": detail,
            "description": gate.description,
        })

    alpha_passing = all(
        g["status"] == "pass" for g in gates if g["alpha_gate"] and not g["optional"]
    )
    beta_passing = all(
        g["status"] == "pass" for g in gates if not g["optional"]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "alpha_ready": alpha_passing,
        "beta_ready": beta_passing,
        "gates": gates,
    }


def _evaluate_gate(root: Path, gate: BetaGate) -> tuple[GateStatus, str]:
    """Evaluate one beta-exit gate against local repo evidence."""
    script_path = root / gate.readiness_script

    if not script_path.is_file():
        return "fail", f"readiness script not found: {gate.readiness_script}"

    # Run the readiness script in JSON mode and inspect its output for the
    # required marker.
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--root", str(root), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "fail", f"could not run {gate.readiness_script}: {exc}"

    if result.returncode != 0:
        return "fail", f"{gate.readiness_script} exited {result.returncode}"

    # Parse the JSON output and check for the required marker key.
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "fail", f"{gate.readiness_script} produced invalid JSON"

    # For package_index_readiness, gate passes when repo_guardrails_ready
    # is true AND the required marker is present in the payload keys.
    if "repo_guardrails_ready" in data:
        guardrails = bool(data.get("repo_guardrails_ready"))
        has_marker = gate.required_marker in data
        if guardrails and has_marker:
            # Still externally blocked – mark blocked not pass.
            pkg_ready = bool(data.get("package_index_ready", False))
            if not pkg_ready:
                external_reqs = data.get("external_requirements", [])
                return (
                    "blocked",
                    "external requirements pending: " + "; ".join(external_reqs)
                    if external_reqs
                    else "external package-index evidence not yet proven",
                )
            return "pass", "repo guardrails pass and package-index evidence present"
        return "fail", f"repo guardrails: {guardrails}, marker '{gate.required_marker}': {has_marker}"

    # For stable_core_readiness, examine blocker_issue_map for the relevant
    # issue status.
    if "blocker_issue_map" in data:
        blocker_map = data["blocker_issue_map"]
        for _blocker, issues in blocker_map.items():
            for issue in issues:
                if issue.get("number") == gate.issue_number:
                    status = issue.get("status", "unknown")
                    if status == "done":
                        return "pass", f"#{gate.issue_number} marked done"
                    return "blocked", f"#{gate.issue_number} status: {status}"
        return "fail", f"#{gate.issue_number} not found in blocker issue map"

    # Generic check: does the required marker appear in any top-level key?
    marker_found = gate.required_marker in data or any(
        gate.required_marker in str(v).lower() for v in data.values()
    )
    if marker_found:
        return "pass", f"evidence marker '{gate.required_marker}' found"
    return "fail", f"evidence marker '{gate.required_marker}' not found in {gate.readiness_script} output"


def _render_markdown(payload: dict[str, object]) -> str:
    gates = cast(list[dict[str, object]], payload["gates"])

    lines = [
        "# Beta Exit Scorecard",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Alpha ready: `{str(payload['alpha_ready']).lower()}`",
        f"- Beta ready: `{str(payload['beta_ready']).lower()}`",
        "",
        "## Alpha Gates (must pass before alpha launch)",
        "",
    ]

    alpha_gates = [g for g in gates if g["alpha_gate"]]
    for gate in alpha_gates:
        lines.append(_gate_line(gate))

    lines.extend(["", "## Beta Gates (must pass before beta claims)", ""])

    beta_gates = [g for g in gates if not g["alpha_gate"]]
    for gate in beta_gates:
        lines.append(_gate_line(gate))

    return "\n".join(lines)


def _gate_line(gate: dict[str, object]) -> str:
    optional_mark = " (optional)" if gate["optional"] else ""
    status_icon = {
        "pass": "✅",
        "fail": "❌",
        "blocked": "🔒",
        "not-applicable": "—",
    }.get(str(gate["status"]), "?")
    return (
        f"- {status_icon} [#{gate['issue_number']}]({gate['issue_url']}) "
        f"{gate['label']}{optional_mark}: `{gate['status']}` — {gate['detail']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
