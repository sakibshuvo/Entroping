#!/usr/bin/env python3
"""Report local agent CLI tool availability and safe-use policy.

The probe is intentionally read-only: it performs PATH lookup only. It does not
run scanners, read provider config, inspect secrets, download databases, or
contact services.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Callable
from typing import Any

SCHEMA_VERSION = "entroping.agent-toolchain.v1"
PROBE_MODE = "path_lookup_only"

POLICIES = ("safe_default", "guarded_local_only", "manual_explicit")
MODES = ("implementation", "review", "security", "maintenance")

TOOL_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "command": "fd",
        "package": "fd",
        "policy": "safe_default",
        "purpose": "Fast path discovery before targeted reads.",
        "recommended_modes": ("implementation", "review", "maintenance"),
    },
    {
        "command": "sg",
        "package": "ast-grep",
        "policy": "safe_default",
        "purpose": "AST-aware search and scoped structural rewrites.",
        "recommended_modes": ("implementation", "review"),
    },
    {
        "command": "delta",
        "package": "git-delta",
        "policy": "safe_default",
        "purpose": "Readable syntax-highlighted diffs for local review.",
        "recommended_modes": ("implementation", "review", "maintenance"),
    },
    {
        "command": "difft",
        "package": "difftastic",
        "policy": "safe_default",
        "purpose": "Syntax-aware diffs for complex reviews.",
        "recommended_modes": ("review",),
    },
    {
        "command": "jq",
        "package": "jq",
        "policy": "safe_default",
        "purpose": "Structured JSON inspection without ad hoc parsing.",
        "recommended_modes": ("implementation", "review", "security", "maintenance"),
    },
    {
        "command": "yq",
        "package": "yq",
        "policy": "safe_default",
        "purpose": "Structured YAML inspection for workflows and metadata.",
        "recommended_modes": ("implementation", "review", "security", "maintenance"),
    },
    {
        "command": "tokei",
        "package": "tokei",
        "policy": "safe_default",
        "purpose": "Fast context-size and language footprint checks.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "scc",
        "package": "scc",
        "policy": "safe_default",
        "purpose": "Fast code counts and rough complexity/size signals.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "dust",
        "package": "dust",
        "policy": "safe_default",
        "purpose": "Find local artifact and dependency bloat.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "ncdu",
        "package": "ncdu",
        "policy": "safe_default",
        "purpose": "Interactive local disk-usage inspection.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "git-sizer",
        "package": "git-sizer",
        "policy": "safe_default",
        "purpose": "Detect repository growth risks.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "hyperfine",
        "package": "hyperfine",
        "policy": "safe_default",
        "purpose": "Measure command/runtime improvements instead of guessing.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "watchexec",
        "package": "watchexec",
        "policy": "safe_default",
        "purpose": "Run scoped local TDD loops on file changes.",
        "recommended_modes": ("implementation",),
    },
    {
        "command": "jless",
        "package": "jless",
        "policy": "safe_default",
        "purpose": "Inspect large JSON artifacts locally.",
        "recommended_modes": ("review", "maintenance"),
    },
    {
        "command": "fx",
        "package": "fx",
        "policy": "safe_default",
        "purpose": "Inspect JSON artifacts locally.",
        "recommended_modes": ("review", "maintenance"),
    },
    {
        "command": "jc",
        "package": "jc",
        "policy": "safe_default",
        "purpose": "Convert supported command output to JSON for analysis.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "actionlint",
        "package": "actionlint",
        "policy": "guarded_local_only",
        "purpose": "Lint GitHub Actions workflow syntax locally.",
        "recommended_modes": ("review", "security"),
    },
    {
        "command": "zizmor",
        "package": "zizmor",
        "policy": "guarded_local_only",
        "purpose": "Audit GitHub Actions security posture locally.",
        "recommended_modes": ("review", "security"),
    },
    {
        "command": "gitleaks",
        "package": "gitleaks",
        "policy": "guarded_local_only",
        "purpose": "Scan repository history or working tree for secrets.",
        "recommended_modes": ("review", "security"),
    },
    {
        "command": "detect-secrets",
        "package": "detect-secrets",
        "policy": "guarded_local_only",
        "purpose": "Scan tracked files for secret-like values.",
        "recommended_modes": ("review", "security"),
    },
    {
        "command": "osv-scanner",
        "package": "osv-scanner",
        "policy": "guarded_local_only",
        "purpose": "Check dependency manifests against OSV advisories.",
        "recommended_modes": ("security",),
    },
    {
        "command": "pip-audit",
        "package": "pip-audit",
        "policy": "guarded_local_only",
        "purpose": "Audit Python dependency vulnerabilities.",
        "recommended_modes": ("security",),
    },
    {
        "command": "lychee",
        "package": "lychee",
        "policy": "guarded_local_only",
        "purpose": "Check documentation links with explicit scope.",
        "recommended_modes": ("review", "maintenance"),
    },
    {
        "command": "markdownlint-cli2",
        "package": "markdownlint-cli2",
        "policy": "guarded_local_only",
        "purpose": "Lint Markdown when docs-governance changes require it.",
        "recommended_modes": ("review", "maintenance"),
    },
    {
        "command": "shfmt",
        "package": "shfmt",
        "policy": "guarded_local_only",
        "purpose": "Format shell scripts after reviewing diff impact.",
        "recommended_modes": ("implementation", "review"),
    },
    {
        "command": "shellcheck",
        "package": "shellcheck",
        "policy": "guarded_local_only",
        "purpose": "Lint shell scripts through repo shell-quality gates.",
        "recommended_modes": ("implementation", "review", "security"),
    },
    {
        "command": "hadolint",
        "package": "hadolint",
        "policy": "guarded_local_only",
        "purpose": "Lint Dockerfiles when container surfaces change.",
        "recommended_modes": ("review", "security"),
    },
    {
        "command": "dot",
        "package": "graphviz",
        "policy": "guarded_local_only",
        "purpose": "Render repo-owned DOT graphs, never untrusted graph input.",
        "recommended_modes": ("maintenance",),
    },
    {
        "command": "act",
        "package": "act",
        "policy": "manual_explicit",
        "purpose": "Run GitHub Actions locally; may execute workflow commands and containers.",
        "recommended_modes": ("security",),
    },
    {
        "command": "trufflehog",
        "package": "trufflehog",
        "policy": "manual_explicit",
        "purpose": "Deep secret scanning; verification can contact external services.",
        "recommended_modes": ("security",),
    },
    {
        "command": "semgrep",
        "package": "semgrep",
        "policy": "manual_explicit",
        "purpose": "Run focused static-analysis rules without cloud upload.",
        "recommended_modes": ("security",),
    },
    {
        "command": "trivy",
        "package": "trivy",
        "policy": "manual_explicit",
        "purpose": "Vulnerability scanning that may download/update databases.",
        "recommended_modes": ("security",),
    },
    {
        "command": "syft",
        "package": "syft",
        "policy": "manual_explicit",
        "purpose": "Generate local SBOMs for scoped release/security work.",
        "recommended_modes": ("security",),
    },
    {
        "command": "grype",
        "package": "grype",
        "policy": "manual_explicit",
        "purpose": "Vulnerability scanning that may download/update databases.",
        "recommended_modes": ("security",),
    },
)

AGENT_RULES = {
    "safe_default": (
        "May be used during normal agent work for targeted local discovery, "
        "inspection, diff review, and measurement."
    ),
    "guarded_local_only": (
        "Use through a repo gate or an explicit focused command. Keep scope to "
        "the repo/worktree and do not scan home directories, provider config, "
        "raw traffic, .entroping artifacts, or local secret stores."
    ),
    "manual_explicit": (
        "Do not run automatically. Use only with explicit human/Codex approval, "
        "a narrow scope, and a documented reason because the tool can execute "
        "workflow code, contact services, download databases, or traverse broad "
        "sensitive surfaces."
    ),
}


def build_report(
    *,
    mode: str,
    require_recommended: bool,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")

    tools: list[dict[str, Any]] = []
    for policy in TOOL_POLICIES:
        command = str(policy["command"])
        found_path = which(command)
        recommended = mode in policy["recommended_modes"]
        tools.append(
            {
                "command": command,
                "package": policy["package"],
                "policy": policy["policy"],
                "purpose": policy["purpose"],
                "recommended": recommended,
                "available": found_path is not None,
                "path": found_path,
                "probe": PROBE_MODE,
                "agent_rule": AGENT_RULES[str(policy["policy"])],
            }
        )

    missing_recommended = [
        str(tool["command"]) for tool in tools if tool["recommended"] and not tool["available"]
    ]
    unavailable = [str(tool["command"]) for tool in tools if not tool["available"]]
    if require_recommended and missing_recommended:
        overall_status = "fail"
    elif missing_recommended:
        overall_status = "warn"
    else:
        overall_status = "pass"

    policy_counts = {
        policy: sum(1 for tool in tools if tool["policy"] == policy) for policy in POLICIES
    }
    available_policy_counts = {
        policy: sum(
            1 for tool in tools if tool["policy"] == policy and bool(tool["available"])
        )
        for policy in POLICIES
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "overall_status": overall_status,
        "probe_mode": PROBE_MODE,
        "scanner_execution": False,
        "network_execution": False,
        "local_config_read": False,
        "provider_config_read": False,
        "require_recommended": require_recommended,
        "tool_count": len(tools),
        "available_count": sum(1 for tool in tools if tool["available"]),
        "policy_counts": policy_counts,
        "available_policy_counts": available_policy_counts,
        "missing_recommended": missing_recommended,
        "unavailable": unavailable,
        "tools": tools,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report Entroping agent CLI toolchain availability and safe-use "
            "policy. The probe only performs PATH lookup."
        )
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="implementation",
        help="Workflow mode used to decide which tools are recommended.",
    )
    parser.add_argument(
        "--require-recommended",
        action="store_true",
        help="Exit nonzero when tools recommended for the selected mode are missing.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    report = build_report(mode=args.mode, require_recommended=args.require_recommended)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 1 if report["overall_status"] == "fail" else 0


def _print_text(report: dict[str, Any]) -> None:
    print(f"Agent toolchain: {report['overall_status']} ({report['mode']})")
    print(
        "Probe: PATH lookup only; scanners, network calls, provider config, "
        "and local secret stores were not touched."
    )
    for policy in POLICIES:
        count = report["available_policy_counts"][policy]
        total = report["policy_counts"][policy]
        print(f"{policy}: {count}/{total} available")
    if report["missing_recommended"]:
        print("Missing recommended tools: " + ", ".join(report["missing_recommended"]))

    for tool in report["tools"]:
        marker = "ok" if tool["available"] else "missing"
        recommended = " recommended" if tool["recommended"] else ""
        print(
            f"- {tool['command']} ({tool['policy']}{recommended}): "
            f"{marker}; {tool['purpose']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
