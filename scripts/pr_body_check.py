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
AMBIGUOUS_PROVIDER_RE = re.compile(r"\b(?:OpenCode|DeepSeek|Kimi)\b", re.IGNORECASE)
SECURITY_GATE_RE = re.compile(
    r"(?im)"
    r"^\s*-\s*\[[xX]\]\s*`?"
    r"scripts/(?:feature_gate\.sh --security|regression\.sh --security)"
    r"`?(?:\s|$)"
    r"|^\s*scripts/(?:feature_gate\.sh --security|regression\.sh --security)\s*$",
)
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
    return re.findall(r"(?im)^-\s*\[[xX]\]\s+(.+)$", section)


def _field_value(body: str, label: str) -> str | None:
    pattern = re.compile(
        rf"(?im)^\s*(?:-\s*)?(?:\[[ xX]\]\s*)?{re.escape(label)}\s*:\s*(.*?)\s*$",
    )
    match = pattern.search(body)
    if match is None:
        return None
    return match.group(1).strip()


def _has_concrete_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return not (normalized.startswith("<") and normalized.endswith(">"))


def _known_provider_lane(body: str) -> str | None:
    for lane in PROVIDER_LANES:
        if re.search(rf"(?<!\w){re.escape(lane)}(?!\w)", body):
            return lane
    return None


def _has_closing_keyword(body: str, issue: str | None) -> bool:
    if issue:
        normalized_issue = issue.removeprefix("#").strip()
        if not normalized_issue:
            return False
        return re.search(rf"(?im)\bCloses\s+#{re.escape(normalized_issue)}\b", body) is not None
    return re.search(r"(?im)\bCloses\s+#\d+\b", body) is not None


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


def _sensitive_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    sensitive: list[tuple[str, str]] = []
    for path in changed_files:
        reason = sensitive_surface_reason(path)
        if reason is not None:
            sensitive.append((_normalize_changed_file(path), reason))
    return sensitive


def _has_security_gate_evidence(body: str) -> bool:
    return SECURITY_GATE_RE.search(body) is not None


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

    known_lane = _known_provider_lane(body)
    if known_lane is None and AMBIGUOUS_PROVIDER_RE.search(body):
        failures.append(
            "OpenCode/DeepSeek evidence must use a concrete provider lane, "
            "not bare provider names.",
        )

    for label in OPENCODE_EVIDENCE_LABELS:
        value = _field_value(body, label)
        if not _has_concrete_value(value):
            failures.append(f"OpenCode evidence must include {label.lower()}.")
            continue
        if label == "Provider lane" and value is not None and value not in PROVIDER_LANES:
            allowed = ", ".join(PROVIDER_LANES)
            failures.append(f"OpenCode evidence provider lane must be one of: {allowed}.")

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

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PR body documentation-impact declarations.",
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
            "evidence when sensitive surfaces are touched."
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
