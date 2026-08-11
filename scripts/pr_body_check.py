#!/usr/bin/env python3
"""Validate pull request body declarations."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import stat
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.factory_control_plane_policy import (  # noqa: E402
    autonomy_tier_from_labels,
    normalize_repo_path,
    protected_surface_reason,
)

SECTION_TITLE = "## Documentation Impact Declaration"
AGENT_AUTONOMY_SECTION_TITLE = "## Agent Autonomy Declaration"
OPENCODE_EVIDENCE_SECTION_TITLE = "## OpenCode Provider Lane Evidence"
VERIFICATION_LANE_LABEL = "Verification lane"
ISSUE_METADATA_MAX_BYTES = 1024 * 1024

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
AUTONOMY_TIERS = (
    "Tier A autonomous lane",
    "Tier B assisted lane",
    "Tier C restricted lane",
)
AUTONOMY_TIER_IDS: dict[str, Literal["tier_a", "tier_b", "tier_c"]] = {
    "Tier A autonomous lane": "tier_a",
    "Tier B assisted lane": "tier_b",
    "Tier C restricted lane": "tier_c",
}
MERGE_AUTHORITIES = (
    "Tier A autonomous after gates and green CI",
    "Codex/human required",
    "no merge authority",
)
MERGE_AUTHORITIES_BY_AUTONOMY_TIER = {
    "Tier A autonomous lane": frozenset(MERGE_AUTHORITIES),
    "Tier B assisted lane": frozenset({"Codex/human required", "no merge authority"}),
    "Tier C restricted lane": frozenset({"Codex/human required", "no merge authority"}),
}
AMBIGUOUS_PROVIDER_RE = re.compile(r"\b(?:OpenCode|DeepSeek|Kimi)\b", re.IGNORECASE)
DEPENDENCY_AUTOMATION_AUTHORS = frozenset({"dependabot[bot]", "app/dependabot"})
DEPENDENCY_AUTOMATION_TITLE_RE = re.compile(
    r"^(?:build|chore)\(deps(?:[-/\w]+)?\):\s+",
    re.IGNORECASE,
)
DEPENDENCY_AUTOMATION_FILE_PATTERNS = (
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "pyproject.toml",
    "uv.lock",
    "requirements*.txt",
    "requirements*.in",
    "constraints*.txt",
    "constraints*.in",
    "package.json",
    "package-lock.json",
    "docs/meta/dependency-license-policy.json",
)
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
FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
BLOCKQUOTE_RE = re.compile(r"^ {0,3}>[ \t]?(?P<content>.*)$")
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-+*]|\d{1,9}[.)])[ \t]+")
CLOSING_ISSUE_RE = re.compile(r"(?im)\bCloses\s+#(\d+)\b")
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
        "provider-control-plane",
        (
            "docs/meta/provider-capability-registry*",
            "scripts/provider_capability_*.py",
            "scripts/update_provider_capability_schema.py",
            "scripts/ai_job_quarantine.py",
            "scripts/ai_job_quarantine_modules/*",
            "scripts/opencode_readiness.py",
            "docs/meta/AGENT_CONTROL_PLANE.md",
            "docs/meta/AGENT_ROLE_REGISTRY.yaml",
            "docs/meta/DECISION_REGISTRY.yaml",
            "docs/meta/FACTORY_OPERATIONS.md",
            "docs/meta/prompt-library/model-comparison-trial.md",
            "docs/meta/prompt-library/model-output-acceptance-gate.md",
            "docs/meta/prompt-library/multi-agent-marathon.md",
            "docs/meta/prompt-library/opencode-codex-review-request.md",
            "docs/meta/prompt-library/opencode-desktop-handoff.md",
            "docs/meta/prompt-library/opencode-desktop-one-shot.md",
            "docs/technical/TDS.md",
            ".github/pull_request_template.md",
            "decisions/ADR-0024-provider-capability-registry.md",
            "tests/test_provider_capability_registry*.py",
            "tests/test_ai_job_quarantine.py",
            "tests/test_ai_jobs_provider_registry.py",
            "tests/test_ci_workflow.py",
            "tests/test_doc_governance_script.py",
            "tests/test_pr_body_provider_registry.py",
            "tests/test_opencode_readiness.py",
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
    "tests/test_agent_workflow_*.py",
)


@dataclass(frozen=True)
class _MarkdownLine:
    kind: Literal[
        "visible",
        "fence-open",
        "fenced",
        "fence-close",
        "quote",
        "indented",
    ]
    raw: str
    visible: str = ""


def _is_not_run_marker(line: str) -> bool:
    normalized = line.strip().lower()
    if not normalized:
        return False
    normalized = re.sub(r"^#+\s*", "", normalized)
    normalized = re.sub(r"^-\s*(?:\[[ xX]\]\s*)?", "", normalized)
    normalized = re.sub(r"\s*(?:\(|-|:).*$", "", normalized).strip()
    return normalized in (
        "commands not run",
        "commands not executed",
        "commands skipped",
        "not run",
        "not executed",
        "skipped",
        "skipped commands",
    )


def _is_backslash_escaped(markdown: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and markdown[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _mask_inline_code(markdown: str) -> str:
    runs_by_length: dict[int, list[int]] = {}
    cursor = 0
    while cursor < len(markdown):
        if markdown[cursor] != "`" or _is_backslash_escaped(markdown, cursor):
            cursor += 1
            continue
        end = cursor
        while end < len(markdown) and markdown[end] == "`":
            end += 1
        runs_by_length.setdefault(end - cursor, []).append(cursor)
        cursor = end

    masked = list(markdown)
    cursor = 0
    while cursor < len(markdown):
        if markdown[cursor] != "`" or _is_backslash_escaped(markdown, cursor):
            cursor += 1
            continue
        end = cursor
        while end < len(markdown) and markdown[end] == "`":
            end += 1
        run_length = end - cursor
        positions = runs_by_length[run_length]
        closing_index = bisect_right(positions, cursor)
        if closing_index >= len(positions):
            cursor = end
            continue
        closing_start = positions[closing_index]
        closing_end = closing_start + run_length
        for index in range(cursor, closing_end):
            if masked[index] != "\n":
                masked[index] = " "
        cursor = closing_end
    return "".join(masked)


def _strip_html_comments(markdown: str) -> str:
    visible = list(markdown)
    cursor = 0
    while True:
        start = markdown.find("<!--", cursor)
        if start == -1:
            break
        terminator = markdown.find("-->", start + 4)
        end = len(markdown) if terminator == -1 else terminator + 3
        for index in range(start, end):
            if visible[index] != "\n":
                visible[index] = " "
        cursor = end
    return "".join(visible)


def _fence_opening(raw_line: str) -> tuple[str, int] | None:
    match = FENCE_OPEN_RE.match(raw_line)
    if match is None:
        return None
    fence = match.group("fence")
    if fence[0] == "`" and "`" in match.group("rest"):
        return None
    return fence[0], len(fence)


def _is_fence_closing(raw_line: str, *, character: str, length: int) -> bool:
    stripped = raw_line.lstrip(" ")
    if len(raw_line) - len(stripped) > 3 or not stripped.startswith(character):
        return False
    run_end = 0
    while run_end < len(stripped) and stripped[run_end] == character:
        run_end += 1
    return run_end >= length and not stripped[run_end:].strip()


def _markdown_lines(markdown: str) -> list[_MarkdownLine]:
    raw_lines = markdown.splitlines()
    kinds: list[_MarkdownLine] = []
    fence_character: str | None = None
    fence_length = 0
    lazy_quote = False

    for raw_line in raw_lines:
        if fence_character is not None:
            if _is_fence_closing(
                raw_line,
                character=fence_character,
                length=fence_length,
            ):
                kinds.append(_MarkdownLine("fence-close", raw_line))
                fence_character = None
                fence_length = 0
            else:
                kinds.append(_MarkdownLine("fenced", raw_line))
            continue

        if not raw_line.strip():
            kinds.append(_MarkdownLine("visible", raw_line))
            lazy_quote = False
            continue

        quote_match = BLOCKQUOTE_RE.match(raw_line)
        if quote_match is not None:
            kinds.append(_MarkdownLine("quote", raw_line))
            lazy_quote = bool(quote_match.group("content").strip())
            continue

        if lazy_quote:
            interrupts_lazy_quote = (
                ATX_HEADING_RE.match(raw_line) is not None
                or LIST_ITEM_RE.match(raw_line) is not None
                or _fence_opening(raw_line) is not None
            )
            if not interrupts_lazy_quote:
                kinds.append(_MarkdownLine("quote", raw_line))
                continue
            lazy_quote = False

        opening = _fence_opening(raw_line)
        if opening is not None:
            fence_character, fence_length = opening
            kinds.append(_MarkdownLine("fence-open", raw_line))
            continue

        leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
        if raw_line.startswith("\t") or leading_spaces >= 4:
            kinds.append(_MarkdownLine("indented", raw_line))
            continue

        kinds.append(_MarkdownLine("visible", raw_line))

    top_level = "\n".join(
        line.raw if line.kind == "visible" else "" for line in kinds
    )
    rendered = _strip_html_comments(_mask_inline_code(top_level)).split("\n")
    return [
        _MarkdownLine(line.kind, line.raw, rendered[index])
        for index, line in enumerate(kinds)
    ]


def _iter_visible_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    skip_not_run_section = False

    for line in _markdown_lines(markdown):
        if line.kind != "visible":
            continue
        raw_line = line.visible
        stripped = raw_line.strip()

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
    capture_fence = False
    commands_run_active = False
    skip_not_run_section = False

    for line in _markdown_lines(body):
        if line.kind == "fence-open":
            capture_fence = commands_run_active
            continue
        if line.kind == "fenced":
            stripped = line.raw.strip()
            if capture_fence and stripped:
                lines.append(stripped)
            continue
        if line.kind == "fence-close":
            capture_fence = False
            commands_run_active = False
            continue
        if line.kind != "visible":
            continue

        raw_line = line.visible
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


def _extract_sections(body: str, title: str) -> tuple[str, ...]:
    sections: list[str] = []
    current: list[str] | None = None

    for line in _markdown_lines(body):
        stripped = line.visible.strip() if line.kind == "visible" else ""
        is_heading = line.kind == "visible" and stripped.startswith("## ")
        if is_heading:
            if current is not None:
                sections.append("\n".join(current))
            current = [] if stripped == title else None
            continue

        if current is not None:
            current.append(line.raw)

    if current is not None:
        sections.append("\n".join(current))
    return tuple(sections)


def _extract_section(body: str, title: str) -> str | None:
    sections = _extract_sections(body, title)
    return sections[0] if sections else None


def _checked_items(section: str) -> list[str]:
    checked_items: list[str] = []
    for line in _iter_visible_lines(section):
        match = CHECKED_ITEM_RE.match(line)
        if match is not None:
            checked_items.append(match.group(1))
    return checked_items


def _field_value(body: str, label: str) -> str | None:
    values = _field_values(body, label)
    return values[0] if values else None


def _field_values(body: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"^\s*(?:-\s*)?(?:\[[xX]\]\s*)?{re.escape(label)}\s*:\s*(.*?)\s*$",
        re.IGNORECASE,
    )
    values: list[str] = []
    for line in _iter_visible_lines(body):
        match = pattern.match(line)
        if match is not None:
            values.append(match.group(1).strip())
    return values


def _has_concrete_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return not (normalized.startswith("<") and normalized.endswith(">"))


def _known_provider_lane(body: str, provider_lanes: tuple[str, ...]) -> str | None:
    provider_lane = _field_value(body, "Provider lane")
    if provider_lane in provider_lanes:
        return provider_lane
    for lane in provider_lanes:
        if re.search(rf"(?<!\w){re.escape(lane)}(?!\w)", "\n".join(_iter_visible_lines(body))):
            return lane
    return None


def _has_closing_keyword(body: str, issue: str | None) -> bool:
    visible_body = "\n".join(_iter_visible_lines(body))
    if issue:
        normalized_issue = issue.removeprefix("#").strip()
        if not normalized_issue:
            return False
        return (
            re.search(
                rf"(?im)\bCloses\s+#{re.escape(normalized_issue)}\b",
                visible_body,
            )
            is not None
        )
    return re.search(r"(?im)\bCloses\s+#\d+\b", visible_body) is not None


def _closing_issue_numbers(body: str) -> tuple[str, ...]:
    visible_body = "\n".join(_iter_visible_lines(body))
    return tuple(dict.fromkeys(CLOSING_ISSUE_RE.findall(visible_body)))


def _declares_provider_evidence(body: str) -> bool:
    for autonomy_section in _extract_sections(body, AGENT_AUTONOMY_SECTION_TITLE):
        for item in _checked_items(autonomy_section):
            label, separator, value = item.partition(":")
            if (
                separator
                and label.strip().casefold() == "merge authority"
                and value.strip().removesuffix(".")
                == "Tier A autonomous after gates and green CI"
            ):
                return True
    return any(
        _has_concrete_value(_field_value(provider_section, label))
        for provider_section in _extract_sections(body, OPENCODE_EVIDENCE_SECTION_TITLE)
        for label in OPENCODE_EVIDENCE_LABELS
    )


def _read_issue_metadata(path: Path) -> dict[str, object]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"could not safely open trusted issue metadata: {exc}") from None
    try:
        metadata_stat = os.fstat(descriptor)
        if not stat.S_ISREG(metadata_stat.st_mode):
            raise ValueError("trusted issue metadata must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(ISSUE_METADATA_MAX_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > ISSUE_METADATA_MAX_BYTES:
        raise ValueError(
            f"trusted issue metadata exceeds {ISSUE_METADATA_MAX_BYTES} bytes"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("trusted issue metadata must be valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("trusted issue metadata must be a JSON object")
    return payload


def _trusted_issue_autonomy_tier(path: Path, *, issue: str) -> str:
    payload = _read_issue_metadata(path)
    normalized_issue = issue.removeprefix("#").strip()
    number = payload.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
        raise ValueError("trusted issue metadata must include an integer issue number")
    if str(number) != normalized_issue:
        raise ValueError(
            f"trusted issue metadata number #{number} does not match #{normalized_issue}"
        )
    state = payload.get("state")
    if not isinstance(state, str) or state.casefold() != "open":
        raise ValueError(f"trusted issue #{number} must still be open")
    if payload.get("pull_request") is not None:
        raise ValueError(f"trusted issue #{number} must not be a pull request")
    return autonomy_tier_from_labels(payload.get("labels"))


def _normalize_changed_file(path: str) -> str:
    return normalize_repo_path(path) or path.strip().replace("\\", "/")


def _dependency_automation_login(pull_request: dict[str, object]) -> str | None:
    candidate = pull_request.get("user")
    if not isinstance(candidate, dict):
        return None
    login = candidate.get("login")
    if isinstance(login, str) and login:
        return login
    return None


def _is_dependency_automation_file(path: str) -> bool:
    normalized = _normalize_changed_file(path)
    if not normalized:
        return False
    return any(
        fnmatch.fnmatchcase(normalized, pattern) for pattern in DEPENDENCY_AUTOMATION_FILE_PATTERNS
    )


def _is_scoped_dependency_automation_pr(
    pull_request: dict[str, object],
    *,
    changed_files: list[str],
) -> bool:
    login = _dependency_automation_login(pull_request)
    if login not in DEPENDENCY_AUTOMATION_AUTHORS:
        return False
    title = pull_request.get("title")
    if not isinstance(title, str) or DEPENDENCY_AUTOMATION_TITLE_RE.search(title) is None:
        return False
    normalized_files = [
        _normalize_changed_file(path) for path in changed_files if _normalize_changed_file(path)
    ]
    if not normalized_files:
        return False
    return all(_is_dependency_automation_file(path) for path in normalized_files)


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


def _protected_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    protected: list[tuple[str, str]] = []
    for path in changed_files:
        reason = protected_surface_reason(path, repo_root=_REPO_ROOT)
        if reason is not None:
            protected.append((_normalize_changed_file(path), reason))
    return protected


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


def _validate_opencode_evidence(
    body: str,
    *,
    issue: str | None,
    trusted_issue_autonomy_tier: str | None,
    changed_files: list[str],
) -> list[str]:
    try:
        from scripts.provider_capability_registry import (
            load_provider_registry,
            provider_lane_ids,
            resolve_provider_evidence,
        )
        from scripts.provider_capability_types import (
            ProviderEvidence,
            ProviderRegistryError,
        )
    except (ImportError, SyntaxError):
        return [
            "Provider capability registry dependencies are unavailable; run "
            "`uv run python scripts/pr_body_check.py ...`."
        ]

    failures: list[str] = []
    try:
        registry = load_provider_registry()
    except ProviderRegistryError as exc:
        return [f"Provider capability registry is invalid: {exc}."]
    provider_lanes = provider_lane_ids(registry)

    if not _has_closing_keyword(body, issue):
        expected = f"Closes #{issue.removeprefix('#').strip()}" if issue else "Closes #<issue>"
        failures.append(f"OpenCode evidence PR body must include {expected}.")

    declared_autonomy_tier: str | None = None
    declared_merge_authority: str | None = None
    autonomy_sections = _extract_sections(body, AGENT_AUTONOMY_SECTION_TITLE)
    autonomy_section = autonomy_sections[0] if autonomy_sections else None
    if autonomy_section is None:
        failures.append(f"OpenCode evidence PR body must include {AGENT_AUTONOMY_SECTION_TITLE}.")
    elif len(autonomy_sections) != 1:
        failures.append(
            "OpenCode evidence PR body must include exactly one "
            f"{AGENT_AUTONOMY_SECTION_TITLE} section."
        )
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
        declared_tiers = [
            item.partition(":")[0].strip()
            for item in autonomy_checked
            if item.partition(":")[0].strip() in AUTONOMY_TIERS
        ]
        if len(declared_tiers) != 1:
            failures.append(
                "Agent Autonomy Declaration must check exactly one recognized autonomy tier."
            )
        else:
            declared_autonomy_tier = declared_tiers[0]

        declared_authorities = [
            item.partition(":")[2].strip().removesuffix(".")
            for item in autonomy_checked
            if item.partition(":")[0].strip().casefold() == "merge authority"
        ]
        if len(declared_authorities) != 1 or declared_authorities[0] not in MERGE_AUTHORITIES:
            failures.append(
                "Agent Autonomy Declaration must check exactly one recognized merge authority."
            )
        else:
            declared_merge_authority = declared_authorities[0]

    opencode_sections = _extract_sections(body, OPENCODE_EVIDENCE_SECTION_TITLE)
    opencode_section = opencode_sections[0] if opencode_sections else None
    if opencode_section is None:
        failures.append(
            f"OpenCode evidence PR body must include {OPENCODE_EVIDENCE_SECTION_TITLE}."
        )
        opencode_section = ""
    elif len(opencode_sections) != 1:
        failures.append(
            "OpenCode evidence PR body must include exactly one "
            f"{OPENCODE_EVIDENCE_SECTION_TITLE} section."
        )

    known_lane = _known_provider_lane(opencode_section, provider_lanes)
    if known_lane is None and AMBIGUOUS_PROVIDER_RE.search(body):
        failures.append(
            "OpenCode/DeepSeek evidence must use a concrete provider lane, "
            "not bare provider names.",
        )

    for label in OPENCODE_EVIDENCE_LABELS:
        values = _field_values(opencode_section, label)
        if len(values) != 1:
            failures.append(
                f"OpenCode evidence must include exactly one {label.lower()}."
            )
        value = values[0] if len(values) == 1 else None
        if not _has_concrete_value(value):
            if not values:
                failures.append(f"OpenCode evidence must include {label.lower()}.")
            continue
        if label == "Provider lane" and value is not None and value not in provider_lanes:
            allowed = ", ".join(provider_lanes)
            failures.append(f"OpenCode evidence provider lane must be one of: {allowed}.")
        if label == "Autonomy tier" and value is not None and value not in AUTONOMY_TIERS:
            allowed = ", ".join(AUTONOMY_TIERS)
            failures.append(f"OpenCode evidence autonomy tier must be one of: {allowed}.")
        if label == "Merge authority" and value is not None and value not in MERGE_AUTHORITIES:
            allowed = ", ".join(MERGE_AUTHORITIES)
            failures.append(f"OpenCode evidence merge authority must be one of: {allowed}.")

    provider_lane = _field_value(opencode_section, "Provider lane")
    provider_host = _field_value(opencode_section, "Provider host")
    billing_path = _field_value(opencode_section, "Billing path")
    model_id = _field_value(opencode_section, "Model id")
    autonomy_tier = _field_value(opencode_section, "Autonomy tier")
    merge_authority = _field_value(opencode_section, "Merge authority")
    if autonomy_tier in AUTONOMY_TIERS and merge_authority in MERGE_AUTHORITIES:
        if merge_authority not in MERGE_AUTHORITIES_BY_AUTONOMY_TIER[autonomy_tier]:
            failures.append(
                f"OpenCode evidence autonomy tier {autonomy_tier} cannot use merge authority "
                f"{merge_authority}."
            )
        if declared_autonomy_tier is not None and autonomy_tier != declared_autonomy_tier:
            failures.append(
                "OpenCode evidence autonomy tier does not match the checked "
                "Agent Autonomy Declaration."
            )
        if (
            declared_merge_authority is not None
            and merge_authority != declared_merge_authority
        ):
            failures.append(
                "OpenCode evidence merge authority does not match the checked "
                "Agent Autonomy Declaration."
            )
        if (
            trusted_issue_autonomy_tier is not None
            and autonomy_tier != trusted_issue_autonomy_tier
        ):
            failures.append(
                f"OpenCode evidence autonomy tier {autonomy_tier} does not match "
                f"trusted issue autonomy tier {trusted_issue_autonomy_tier}."
            )
        if merge_authority == "Tier A autonomous after gates and green CI":
            if trusted_issue_autonomy_tier != "Tier A autonomous lane":
                failures.append(
                    "Tier A autonomous merge authority requires trusted open-issue "
                    "metadata that declares Tier A autonomy."
                )
            tier_a_blocked_files = {
                path
                for path, _reason in (
                    _protected_changed_files(changed_files)
                    + _sensitive_changed_files(changed_files)
                    + _quality_guardrail_changed_files(changed_files)
                )
            }
            if tier_a_blocked_files:
                failures.append(
                    "Tier A autonomous merge authority is forbidden for sensitive or "
                    "release/quality guardrail changes: "
                    + ", ".join(sorted(tier_a_blocked_files))
                    + "."
                )
    if (
        provider_lane in provider_lanes
        and provider_host is not None
        and _has_concrete_value(provider_host)
        and billing_path is not None
        and _has_concrete_value(billing_path)
        and model_id is not None
        and _has_concrete_value(model_id)
        and autonomy_tier in AUTONOMY_TIER_IDS
    ):
        try:
            resolve_provider_evidence(
                registry,
                ProviderEvidence(
                    lane_id=provider_lane,
                    provider_host=provider_host,
                    billing_path=billing_path,
                    model_id=model_id,
                    autonomy_tier=AUTONOMY_TIER_IDS[autonomy_tier],
                ),
            )
        except ProviderRegistryError as exc:
            failures.append(f"OpenCode evidence {exc.detail}.")

    return failures


def validate_body(
    body: str,
    *,
    require_opencode_evidence: bool = False,
    issue: str | None = None,
    changed_files: list[str] | None = None,
    trusted_issue_autonomy_tier: str | None = None,
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

    if require_opencode_evidence or _declares_provider_evidence(body):
        failures.extend(
            _validate_opencode_evidence(
                body,
                issue=issue,
                trusted_issue_autonomy_tier=trusted_issue_autonomy_tier,
                changed_files=changed_files or [],
            )
        )

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
        details = ", ".join(f"{path} ({reason})" for path, reason in quality_guardrail_changed)
        failures.append(
            "Quality/architecture guardrail changes require documented quality audit "
            "evidence: list `scripts/audit_quality.sh` in Commands run. "
            f"Guardrail files: {details}.",
        )

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate PR body documentation-impact declarations and Verification lane evidence."
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
            "Issue number that must appear as a Closes #<issue> keyword when evidence is required."
        ),
    )
    parser.add_argument(
        "--issue-metadata-file",
        type=Path,
        help=(
            "Trusted GitHub issue JSON containing number, state, labels, and "
            "pull_request fields for autonomy binding."
        ),
    )
    parser.add_argument(
        "--print-provider-evidence-issue",
        action="store_true",
        help=(
            "Print the single closing issue when the PR declares provider or "
            "autonomous-merge evidence; used by CI before fetching trusted metadata."
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
    if args.issue_metadata_file is not None and not args.issue:
        parser.error("--issue is required with --issue-metadata-file.")

    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
        pull_request: dict[str, object] | None = None
    else:
        if not args.event_path:
            print("No GitHub event payload path provided.", file=sys.stderr)
            return 2
        event_path = Path(args.event_path)
        payload = json.loads(event_path.read_text(encoding="utf-8"))
        raw_pull_request = payload.get("pull_request")
        if not isinstance(raw_pull_request, dict):
            if args.print_provider_evidence_issue:
                return 0
            print("No pull request payload; skipping PR documentation impact check.")
            return 0
        pull_request = raw_pull_request
        raw_body = pull_request.get("body")
        body = raw_body if isinstance(raw_body, str) else ""

    if args.print_provider_evidence_issue:
        if not _declares_provider_evidence(body):
            return 0
        closing_issues = _closing_issue_numbers(body)
        if len(closing_issues) != 1:
            print(
                "Provider/autonomous evidence must close exactly one GitHub issue.",
                file=sys.stderr,
            )
            return 1
        print(closing_issues[0])
        return 0

    if (
        pull_request is not None
        and not args.require_opencode_evidence
        and _is_scoped_dependency_automation_pr(
            pull_request,
            changed_files=args.changed_file,
        )
    ):
        print("PR documentation impact declaration OK (dependency automation lane)")
        return 0

    trusted_issue_autonomy_tier: str | None = None
    if args.issue_metadata_file is not None:
        try:
            trusted_issue_autonomy_tier = _trusted_issue_autonomy_tier(
                args.issue_metadata_file,
                issue=args.issue,
            )
        except ValueError as exc:
            print("PR documentation impact declaration failed:", file=sys.stderr)
            print(f"  {exc}", file=sys.stderr)
            return 1

    failures = validate_body(
        body,
        require_opencode_evidence=args.require_opencode_evidence,
        issue=args.issue,
        changed_files=args.changed_file,
        trusted_issue_autonomy_tier=trusted_issue_autonomy_tier,
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
