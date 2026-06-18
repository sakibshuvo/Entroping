#!/usr/bin/env python3
"""Validate pull request body declarations."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SECTION_TITLE = "## Documentation Impact Declaration"
AGENT_AUTONOMY_SECTION_TITLE = "## Agent Autonomy Declaration"
OPENCODE_EVIDENCE_SECTION_TITLE = "## OpenCode Provider Lane Evidence"
VERIFICATION_LANE_LABEL = "Verification lane"

VERIFICATION_LANES = (
    "tiny-docs",
    "docs-guardrail",
    "tests-only",
    "normal-code",
    "security-runtime",
    "release-ci-architecture",
)
VERIFICATION_LANE_RANK = {lane: index for index, lane in enumerate(VERIFICATION_LANES)}

OPENCODE_EVIDENCE_LABELS = (
    "Provider lane",
    "Provider host",
    "Billing path",
    "Model id",
    "Autonomy tier",
    "Merge authority",
    "Commands run",
)
PROVIDER_LANES = (
    "deepseek-api/direct",
    "opencode/native-deepseek",
    "opencode-go/kimi-k2.7-code",
    "opencode-go/qwen3.7-max",
    "opencode-go/other",
    "local/offline",
)
AUTONOMY_TIERS = (
    "Tier A autonomous lane",
    "Tier B assisted lane",
    "Tier C restricted lane",
)
MERGE_AUTHORITIES = (
    "Tier A autonomous after gates and green CI",
    "Codex/human required",
    "no merge authority",
)
AMBIGUOUS_PROVIDER_RE = re.compile(r"\b(?:OpenCode|DeepSeek|Kimi)\b", re.IGNORECASE)
SECURITY_GATE_RE = re.compile(
    r"(?im)^\s*`?"
    r"scripts/(?:feature_gate\.sh --security|regression\.sh --security)"
    r"`?(?:\s|$)",
)
QUALITY_AUDIT_RE = re.compile(
    r"(?im)^\s*`?scripts/audit_quality\.sh`?(?:\s|$)",
)
DOC_GOVERNANCE_RE = re.compile(
    r"(?im)^\s*`?scripts/doc_governance_check\.sh`?(?:\s|$)",
)
FOCUSED_PYTEST_RE = re.compile(
    r"(?im)^\s*`?uv run pytest\s+tests/[^\n`]+`?(?:\s|$)",
)
STANDARD_GATE_RE = re.compile(
    r"(?im)^\s*`?scripts/"
    r"(?:feature_gate\.sh(?: --security)?|regression\.sh(?: --security)?)"
    r"`?(?:\s|$)",
)
CHECKED_ITEM_RE = re.compile(r"^\s*-\s*\[[xX]\]\s+(.+?)\s*$")
COMMANDS_RUN_RE = re.compile(
    r"^\s*(?:-\s*)?(?:\[[xX]\]\s*)?Commands run\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
SENSITIVE_SURFACE_PATTERNS = (
    (
        "hurl-runner",
        (
            "src/entroping/core/hurl_runner.py",
            "src/entroping/core/run_workflow.py",
            "src/entroping/cli/run.py",
            "tests/test_hurl_runner.py",
            "tests/test_run_workflow*.py",
            "tests/test_cli_run_command.py",
        ),
    ),
    (
        "redaction",
        (
            "src/entroping/core/redaction*.py",
            "src/entroping/eye/*",
            "src/entroping/bridge/traffic_*",
            "tests/test_traffic*.py",
            "tests/test_capture*.py",
        ),
    ),
    (
        "provider-boundary",
        (
            "src/entroping/brain/*",
            "src/entroping/core/litellm_client.py",
            "tests/test_litellm_client.py",
            "tests/test_brain_provider_setup_docs.py",
            "docs/user/AI_PROVIDER_SETUP.md",
        ),
    ),
    (
        "proxy-capture",
        (
            "src/entroping/eye/*",
            "tests/test_traffic_proxy.py",
            "docs/user/EYE*.md",
        ),
    ),
    (
        "report-evidence",
        (
            "src/entroping/core/report_writer.py",
            "src/entroping/cli/report.py",
            "src/entroping/reports/*",
            "tests/test_report*.py",
            "tests/test_*report*.py",
        ),
    ),
    (
        "ai-worker",
        (
            "scripts/opencode_worker.py",
            "scripts/deepseek_worker.py",
            "scripts/ai_jobs.py",
            "tests/test_opencode_worker.py",
            "tests/test_deepseek_worker.py",
            "tests/test_ai_jobs.py",
        ),
    ),
    (
        "secret-adjacent",
        (
            ".github/workflows/*",
            "SECURITY.md",
            ".env*",
            "*.env",
            "*.pem",
            "*.key",
            "*secret*",
            "*credential*",
        ),
    ),
)
QUALITY_GUARDRAIL_PATTERNS = (
    (
        "architecture-integrity",
        (
            "scripts/architecture_integrity.sh",
            "tests/test_architecture_boundaries.py",
            "tests/test_architecture_integrity_script.py",
            "tests/support/architecture_guard.py",
        ),
    ),
    (
        "delivery-gate",
        (
            "scripts/check.sh",
            "scripts/doc_governance_check.sh",
            "scripts/feature_gate.sh",
            "scripts/pr_body_check.py",
            "scripts/regression.sh",
            "scripts/repo_hygiene.sh",
            "tests/test_doc_governance_script.py",
        ),
    ),
    (
        "quality-audit",
        (
            ".github/workflows/ci.yml",
            "scripts/audit_quality.sh",
            "scripts/quality_trend_summary.py",
            "scripts/test_taxonomy.py",
            "tests/test_quality_trend_summary.py",
            "tests/test_test_taxonomy.py",
        ),
    ),
)
DOCS_GUARDRAIL_PATTERNS = (
    "AGENTS.md",
    "docs/meta/AGENT_CONTROL_PLANE.md",
    "docs/meta/CONTEXT_MANAGEMENT.md",
    "docs/meta/DOCS_GOVERNANCE.md",
    "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
    "docs/meta/AGENT_ROLE_REGISTRY.yaml",
    "docs/meta/prompt-library/*",
    "tests/test_agent_workflow_docs.py",
)


def _is_not_run_marker(line: str) -> bool:
    normalized = line.strip().lower()
    if not normalized:
        return False
    normalized = re.sub(r"^#+\s*", "", normalized)
    normalized = re.sub(r"^-\s*(?:\[[ xX]\]\s*)?", "", normalized)
    normalized = normalized.rstrip(":").strip()
    return normalized in (
        "commands not run",
        "commands not executed",
        "commands skipped",
        "not run",
        "not executed",
        "skipped",
        "skipped commands",
    )


def _iter_visible_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    in_fence = False
    skip_not_run_section = False

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()

        if FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence or raw_line.lstrip().startswith(">"):
            continue

        if stripped.startswith("## "):
            skip_not_run_section = _is_not_run_marker(stripped)
            continue
        if _is_not_run_marker(stripped):
            skip_not_run_section = True
            continue
        if skip_not_run_section:
            continue

        lines.append(raw_line)

    return lines


def _structured_evidence_text(body: str) -> str:
    lines: list[str] = []
    in_fence = False
    capture_fence = False
    commands_run_active = False
    skip_not_run_section = False

    for raw_line in body.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("## "):
            skip_not_run_section = _is_not_run_marker(stripped)
            commands_run_active = False
            continue
        if _is_not_run_marker(stripped):
            skip_not_run_section = True
            commands_run_active = False
            continue
        if skip_not_run_section:
            continue

        if raw_line.lstrip().startswith(">"):
            continue

        if FENCE_RE.match(raw_line):
            if in_fence:
                in_fence = False
                capture_fence = False
                commands_run_active = False
            else:
                in_fence = True
                capture_fence = commands_run_active
            continue

        if in_fence:
            if capture_fence and stripped:
                lines.append(stripped)
            continue

        command_match = COMMANDS_RUN_RE.match(raw_line)
        if command_match is not None:
            inline = command_match.group(1).strip()
            commands_run_active = True
            if inline:
                lines.append(inline)
            continue

        if commands_run_active:
            if not stripped:
                continue
            checked_match = CHECKED_ITEM_RE.match(raw_line)
            if checked_match is not None:
                lines.append(checked_match.group(1).strip())
            else:
                lines.append(stripped)
            continue

        checked_match = CHECKED_ITEM_RE.match(raw_line)
        if checked_match is not None:
            lines.append(checked_match.group(1).strip())

    return "\n".join(lines)


def _extract_section(body: str, title: str) -> str | None:
    marker_index = body.find(title)
    if marker_index == -1:
        return None

    section_start = marker_index + len(title)
    next_header = body.find("\n## ", section_start)
    if next_header == -1:
        return body[section_start:]
    return body[section_start:next_header]


def _checked_items(section: str) -> list[str]:
    checked_items: list[str] = []
    for line in _iter_visible_lines(section):
        match = CHECKED_ITEM_RE.match(line)
        if match is not None:
            checked_items.append(match.group(1))
    return checked_items


def _field_value(body: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\s*(?:-\s*)?(?:\[[xX]\]\s*)?{re.escape(label)}\s*:\s*(.*?)\s*$",
        re.IGNORECASE,
    )
    for line in _iter_visible_lines(body):
        match = pattern.match(line)
        if match is not None:
            return match.group(1).strip()
    return None


def _has_concrete_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return not (normalized.startswith("<") and normalized.endswith(">"))


def _known_provider_lane(body: str) -> str | None:
    provider_lane = _field_value(body, "Provider lane")
    if provider_lane in PROVIDER_LANES:
        return provider_lane
    for lane in PROVIDER_LANES:
        if re.search(rf"(?<!\w){re.escape(lane)}(?!\w)", "\n".join(_iter_visible_lines(body))):
            return lane
    return None


def _has_closing_keyword(body: str, issue: str | None) -> bool:
    visible_body = "\n".join(_iter_visible_lines(body))
    if issue:
        normalized_issue = issue.removeprefix("#").strip()
        if not normalized_issue:
            return False
        return re.search(
            rf"(?im)\bCloses\s+#{re.escape(normalized_issue)}\b",
            visible_body,
        ) is not None
    return re.search(r"(?im)\bCloses\s+#\d+\b", visible_body) is not None


def _normalize_changed_file(path: str) -> str:
    return path.strip().lstrip("./").replace("\\", "/")


def sensitive_surface_reason(path: str) -> str | None:
    normalized = _normalize_changed_file(path)
    if not normalized:
        return None

    for reason, patterns in SENSITIVE_SURFACE_PATTERNS:
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns):
            return reason
    return None


def quality_guardrail_reason(path: str) -> str | None:
    normalized = _normalize_changed_file(path)
    if not normalized:
        return None

    for reason, patterns in QUALITY_GUARDRAIL_PATTERNS:
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns):
            return reason
    return None


def _sensitive_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    sensitive: list[tuple[str, str]] = []
    for path in changed_files:
        reason = sensitive_surface_reason(path)
        if reason is not None:
            sensitive.append((_normalize_changed_file(path), reason))
    return sensitive


def _quality_guardrail_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    guardrail_files: list[tuple[str, str]] = []
    for path in changed_files:
        reason = quality_guardrail_reason(path)
        if reason is not None:
            guardrail_files.append((_normalize_changed_file(path), reason))
    return guardrail_files


def _has_security_gate_evidence(body: str) -> bool:
    return SECURITY_GATE_RE.search(_structured_evidence_text(body)) is not None


def _has_quality_audit_evidence(body: str) -> bool:
    return QUALITY_AUDIT_RE.search(_structured_evidence_text(body)) is not None


def _has_doc_governance_evidence(body: str) -> bool:
    return DOC_GOVERNANCE_RE.search(_structured_evidence_text(body)) is not None


def _has_focused_pytest_evidence(body: str) -> bool:
    return FOCUSED_PYTEST_RE.search(_structured_evidence_text(body)) is not None


def _has_standard_gate_evidence(body: str) -> bool:
    return STANDARD_GATE_RE.search(_structured_evidence_text(body)) is not None


def _docs_guardrail_reason(path: str) -> str | None:
    normalized = _normalize_changed_file(path)
    if not normalized:
        return None
    if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in DOCS_GUARDRAIL_PATTERNS):
        return "docs-guardrail"
    return None


def _lane_for_changed_file(path: str) -> str:
    normalized = _normalize_changed_file(path)
    if quality_guardrail_reason(normalized) is not None:
        return "release-ci-architecture"
    if sensitive_surface_reason(normalized) is not None:
        return "security-runtime"
    if _docs_guardrail_reason(normalized) is not None:
        return "docs-guardrail"
    if normalized.startswith("tests/"):
        return "tests-only"
    if normalized.endswith(".md") or normalized.startswith(("docs/", ".context/")):
        return "tiny-docs"
    return "normal-code"


def _required_verification_lane(changed_files: list[str]) -> str:
    required = "tiny-docs"
    for path in changed_files:
        lane = _lane_for_changed_file(path)
        if VERIFICATION_LANE_RANK[lane] > VERIFICATION_LANE_RANK[required]:
            required = lane
    return required


def _validate_lane_command_evidence(body: str, lane: str) -> list[str]:
    failures: list[str] = []

    if lane == "tiny-docs":
        if not _has_doc_governance_evidence(body):
            failures.append(
                "Verification lane tiny-docs requires `scripts/doc_governance_check.sh` "
                "in Commands run.",
            )
    elif lane == "docs-guardrail":
        if not _has_doc_governance_evidence(body):
            failures.append(
                "Verification lane docs-guardrail requires "
                "`scripts/doc_governance_check.sh` in Commands run.",
            )
        if not _has_focused_pytest_evidence(body):
            failures.append(
                "Verification lane docs-guardrail requires a focused "
                "`uv run pytest tests/... -q` command in Commands run.",
            )
    elif lane == "tests-only":
        if not _has_focused_pytest_evidence(body):
            failures.append(
                "Verification lane tests-only requires a focused "
                "`uv run pytest tests/... -q` command in Commands run.",
            )
    elif lane == "normal-code":
        if not _has_standard_gate_evidence(body):
            failures.append(
                "Verification lane normal-code requires `scripts/feature_gate.sh` "
                "or `scripts/regression.sh` in Commands run.",
            )
    elif lane == "security-runtime":
        if not _has_security_gate_evidence(body):
            failures.append(
                "Verification lane security-runtime requires "
                "`scripts/feature_gate.sh --security` or "
                "`scripts/regression.sh --security` in Commands run.",
            )
    elif lane == "release-ci-architecture":
        if not _has_security_gate_evidence(body):
            failures.append(
                "Verification lane release-ci-architecture requires "
                "`scripts/feature_gate.sh --security` or "
                "`scripts/regression.sh --security` in Commands run.",
            )
        if not _has_quality_audit_evidence(body):
            failures.append(
                "Verification lane release-ci-architecture requires "
                "`scripts/audit_quality.sh` in Commands run.",
            )

    return failures


def _validate_verification_lane(body: str, *, changed_files: list[str]) -> list[str]:
    if not changed_files:
        return []

    value = _field_value(body, VERIFICATION_LANE_LABEL)
    if not _has_concrete_value(value):
        allowed = ", ".join(VERIFICATION_LANES)
        return [f"PR body must include Verification lane: one of {allowed}."]
    assert value is not None

    lane = value.strip()
    if lane not in VERIFICATION_LANE_RANK:
        allowed = ", ".join(VERIFICATION_LANES)
        return [f"Verification lane must be one of: {allowed}."]

    failures: list[str] = []
    required = _required_verification_lane(changed_files)
    if VERIFICATION_LANE_RANK[lane] < VERIFICATION_LANE_RANK[required]:
        failures.append(
            f"Verification lane {lane} is too weak for the changed files; "
            f"use {required} or a stronger lane.",
        )
    failures.extend(_validate_lane_command_evidence(body, lane))
    return failures


def _validate_opencode_evidence(body: str, *, issue: str | None) -> list[str]:
    failures: list[str] = []

    if not _has_closing_keyword(body, issue):
        expected = f"Closes #{issue.removeprefix('#').strip()}" if issue else "Closes #<issue>"
        failures.append(f"OpenCode evidence PR body must include {expected}.")

    autonomy_section = _extract_section(body, AGENT_AUTONOMY_SECTION_TITLE)
    if autonomy_section is None:
        failures.append(f"OpenCode evidence PR body must include {AGENT_AUTONOMY_SECTION_TITLE}.")
    else:
        autonomy_checked = _checked_items(autonomy_section)
        if not autonomy_checked:
            failures.append(
                "OpenCode evidence PR body must check at least one "
                "Agent Autonomy Declaration item.",
            )
        for item in autonomy_checked:
            if ":" in item and not item.split(":", maxsplit=1)[1].strip():
                failures.append(f"Checked agent autonomy declaration needs detail: {item}")

    opencode_section = _extract_section(body, OPENCODE_EVIDENCE_SECTION_TITLE)
    if opencode_section is None:
        failures.append(
            f"OpenCode evidence PR body must include {OPENCODE_EVIDENCE_SECTION_TITLE}."
        )
        opencode_section = ""

    known_lane = _known_provider_lane(opencode_section)
    if known_lane is None and AMBIGUOUS_PROVIDER_RE.search(body):
        failures.append(
            "OpenCode/DeepSeek evidence must use a concrete provider lane, "
            "not bare provider names.",
        )

    for label in OPENCODE_EVIDENCE_LABELS:
        value = _field_value(opencode_section, label)
        if not _has_concrete_value(value):
            failures.append(f"OpenCode evidence must include {label.lower()}.")
            continue
        if label == "Provider lane" and value is not None and value not in PROVIDER_LANES:
            allowed = ", ".join(PROVIDER_LANES)
            failures.append(f"OpenCode evidence provider lane must be one of: {allowed}.")
        if label == "Autonomy tier" and value is not None and value not in AUTONOMY_TIERS:
            allowed = ", ".join(AUTONOMY_TIERS)
            failures.append(f"OpenCode evidence autonomy tier must be one of: {allowed}.")
        if (
            label == "Merge authority"
            and value is not None
            and value not in MERGE_AUTHORITIES
        ):
            allowed = ", ".join(MERGE_AUTHORITIES)
            failures.append(f"OpenCode evidence merge authority must be one of: {allowed}.")

    return failures


def validate_body(
    body: str,
    *,
    require_opencode_evidence: bool = False,
    issue: str | None = None,
    changed_files: list[str] | None = None,
) -> list[str]:
    section = _extract_section(body, SECTION_TITLE)
    if section is None:
        return [f"PR body must include {SECTION_TITLE}."]

    checked = _checked_items(section)
    if not checked:
        return [
            "PR body must check at least one Documentation Impact Declaration item.",
        ]

    failures: list[str] = []
    for item in checked:
        if ":" in item and not item.split(":", maxsplit=1)[1].strip():
            failures.append(f"Checked documentation declaration needs detail: {item}")

    failures.extend(_validate_verification_lane(body, changed_files=changed_files or []))

    if require_opencode_evidence:
        failures.extend(_validate_opencode_evidence(body, issue=issue))

    sensitive_changed = _sensitive_changed_files(changed_files or [])
    if sensitive_changed and not _has_security_gate_evidence(body):
        details = ", ".join(f"{path} ({reason})" for path, reason in sensitive_changed)
        failures.append(
            "Sensitive surface changes require documented security gate evidence: "
            "check `scripts/feature_gate.sh --security` or list "
            "`scripts/regression.sh --security` in Commands run. "
            f"Sensitive files: {details}.",
        )

    quality_guardrail_changed = _quality_guardrail_changed_files(changed_files or [])
    if quality_guardrail_changed and not _has_quality_audit_evidence(body):
        details = ", ".join(
            f"{path} ({reason})" for path, reason in quality_guardrail_changed
        )
        failures.append(
            "Quality/architecture guardrail changes require documented quality audit "
            "evidence: list `scripts/audit_quality.sh` in Commands run. "
            f"Guardrail files: {details}.",
        )

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate PR body documentation-impact declarations and "
            "Verification lane evidence."
        ),
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Validate a plain Markdown PR body file instead of a GitHub event payload.",
    )
    parser.add_argument(
        "--require-opencode-evidence",
        action="store_true",
        help=(
            "Require OpenCode/DeepSeek provider-lane evidence, agent autonomy "
            "evidence, commands run, and a closing issue keyword."
        ),
    )
    parser.add_argument(
        "--issue",
        help=(
            "Issue number that must appear as a Closes #<issue> keyword when "
            "evidence is required."
        ),
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help=(
            "Repo-relative changed file path. Repeat to require security-gate "
            "evidence when sensitive surfaces are touched and quality-audit "
            "evidence when guardrail surfaces are touched. Changed files also "
            "require a proportional Verification lane."
        ),
    )
    parser.add_argument(
        "event_path",
        nargs="?",
        default=os.environ.get("GITHUB_EVENT_PATH"),
        help="Path to the GitHub event JSON payload. Defaults to GITHUB_EVENT_PATH.",
    )
    args = parser.parse_args(argv)

    if args.require_opencode_evidence and not args.issue:
        parser.error("--issue is required with --require-opencode-evidence.")

    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
        failures = validate_body(
            body,
            require_opencode_evidence=args.require_opencode_evidence,
            issue=args.issue,
            changed_files=args.changed_file,
        )
        if failures:
            print("PR documentation impact declaration failed:", file=sys.stderr)
            for failure in failures:
                print(f"  {failure}", file=sys.stderr)
            return 1
        print("PR documentation impact declaration OK")
        return 0

    if not args.event_path:
        print("No GitHub event payload path provided.", file=sys.stderr)
        return 2

    event_path = Path(args.event_path)
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        print("No pull request payload; skipping PR documentation impact check.")
        return 0

    body = pull_request.get("body") or ""
    failures = validate_body(
        body,
        require_opencode_evidence=args.require_opencode_evidence,
        issue=args.issue,
        changed_files=args.changed_file,
    )
    if failures:
        print("PR documentation impact declaration failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("PR documentation impact declaration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
