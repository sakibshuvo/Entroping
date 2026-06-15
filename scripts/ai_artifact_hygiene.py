#!/usr/bin/env python3
"""Audit tracked files for committed AI artifacts and sensitive context dumps."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from ai_worker_file_safety import secret_like_content_reason
except ImportError as exc:  # pragma: no cover - exercised only by broken installs.
    print(
        "ai_artifact_hygiene: could not import scripts/ai_worker_file_safety.py",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

FORBIDDEN_TRACKED_PREFIXES = {
    ".entroping": "tracked generated artifact path",
    ".mypy_cache": "tracked local cache path",
    ".obsidian": "tracked local machine state path",
    ".pytest_cache": "tracked local cache path",
    ".ruff_cache": "tracked local cache path",
    ".venv": "tracked local virtualenv path",
    ".tmp.driveupload": "tracked local sync staging path",
    "reports": "tracked generated report path",
    "llm-wiki-out": "tracked generated context-tool output path",
    ".understand-anything": "tracked generated context-tool output path",
    "understand-anything-out": "tracked generated context-tool output path",
    "agent-context-out": "tracked generated context-tool output path",
}
FORBIDDEN_TRACKED_NAMES = {
    ".DS_Store": "tracked local machine state path",
}
AI_DUMP_FILENAMES = {
    "prompt.md",
    "request.json",
    "response.json",
    "stdout.txt",
    "stderr.txt",
    "transcript.json",
    "transcript.md",
    "proposal.diff",
}
CONTENT_SCAN_ROOTS = {".context", ".github", "docs"}
CONTENT_SCAN_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".markdown",
    ".txt",
    ".yaml",
    ".yml",
}
FIXTURE_ROOTS = {"tests"}
FIXTURE_MARKERS = {"fixtures", "fixture"}
ALLOW_MARKERS = (
    "ai-artifact-hygiene: allow",
    "ai artifact hygiene: allow",
)
RAW_STREAM_MARKER_RE = re.compile(
    r"(?i)(?:^|\s)(?:prompt|stdout|stderr|provider[\s_-]?transcript|"
    r"model[\s_-]?response)\s*[:=]\s*\S"
)
RAW_BODY_MARKER_RE = re.compile(
    r"(?i)\b(?:request|response)[_-]?body\s*[:=]\s*\S"
)
COOKIE_HEADER_RE = re.compile(
    r"(?i)^\s*(?:set-cookie|cookie)\s*:\s*"
    r"[A-Za-z0-9_.-]+\s*=\s*(?P<value>[^\s;]+)"
)
SAFE_PLACEHOLDER_CREDENTIAL_RE = re.compile(
    r"(?i)(?:^|[^A-Z0-9_-])['\"]?"
    r"(?:[A-Z0-9_-]*API[_-]?KEY|[A-Z0-9_-]*TOKEN|"
    r"[A-Z0-9_-]*SECRET|PASSWORD|PRIVATE[_-]?KEY|PRIVATEKEY)"
    r"['\"]?\s*[:=]\s*['\"]?"
    r"(?:<redacted>|\[redacted]|\{\{[A-Za-z0-9_.-]+\}\}|"
    r"[A-Za-z0-9_.-]*placeholder[A-Za-z0-9_.-]*)"
    r"['\"]?"
)


@dataclass(frozen=True)
class Finding:
    """One AI artifact hygiene finding."""

    path: Path
    line_number: int | None
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit tracked repository paths for generated AI artifacts, prompt or "
            "provider dumps, raw stdout/stderr captures, cookies, raw traffic, "
            "and secret-shaped content."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to audit.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    files = _tracked_files(root)
    findings = _audit_files(root=root, files=files)
    if findings:
        print("AI artifact hygiene failed:", file=sys.stderr)
        for finding in findings:
            relative = _display_path(finding.path, root)
            if finding.line_number is None:
                print(f"  {relative}: {finding.message}", file=sys.stderr)
            else:
                print(
                    f"  {relative}:{finding.line_number}: {finding.message}",
                    file=sys.stderr,
                )
        return 1

    print(f"AI artifact hygiene OK: {len(files)} tracked files checked")
    return 0


def _tracked_files(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        return tuple(
            sorted(root / raw.decode("utf-8") for raw in result.stdout.split(b"\0") if raw)
        )

    if not root.exists():
        return ()
    return tuple(
        sorted(path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts)
    )


def _audit_files(*, root: Path, files: tuple[Path, ...]) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in files:
        findings.extend(_audit_path(root=root, path=path))
        findings.extend(_audit_content(root=root, path=path))
    return tuple(findings)


def _audit_path(*, root: Path, path: Path) -> list[Finding]:
    relative = _relative_path(path, root)
    parts = relative.parts
    if not parts:
        return []

    findings: list[Finding] = []
    prefix_reason = FORBIDDEN_TRACKED_PREFIXES.get(parts[0])
    if prefix_reason is not None:
        findings.append(Finding(path=path, line_number=None, message=prefix_reason))
    for part in parts:
        name_reason = FORBIDDEN_TRACKED_NAMES.get(part)
        if name_reason is not None:
            findings.append(Finding(path=path, line_number=None, message=name_reason))

    if relative.name.lower() in AI_DUMP_FILENAMES and not _is_fixture_path(relative):
        findings.append(
            Finding(
                path=path,
                line_number=None,
                message="tracked AI prompt/response/stdout/stderr artifact filename",
            )
        )

    return findings


def _audit_content(*, root: Path, path: Path) -> list[Finding]:
    relative = _relative_path(path, root)
    if not _should_scan_content(relative):
        return []

    try:
        data = path.read_bytes()
    except OSError:
        return []
    if b"\0" in data:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[Finding] = []
    if _looks_like_provider_response_dump(text):
        findings.append(
            Finding(
                path=path,
                line_number=None,
                message="provider response dump",
            )
        )

    for line_number, line in enumerate(text.splitlines(), start=1):
        if _line_is_allowed(line):
            continue
        if RAW_STREAM_MARKER_RE.search(line):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="raw prompt/stdout/stderr marker",
                )
            )
        if RAW_BODY_MARKER_RE.search(line):
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message="raw request/response body marker",
                )
            )
        if _is_cookie_header_leak(line):
            findings.append(
                Finding(path=path, line_number=line_number, message="cookie header")
            )
        secret_reason = _secret_like_content_reason(line)
        if secret_reason is not None:
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    message=f"secret-like content ({secret_reason})",
                )
            )

    return findings


def _looks_like_provider_response_dump(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return bool(
            (
                re.search(r'"choices"\s*:', text)
                and re.search(r'"prompt_tokens"\s*:', text)
            )
            or (
                re.search(r'"candidates"\s*:', text)
                and re.search(r'"(?:usageMetadata|promptTokenCount)"\s*:', text)
            )
            or (
                re.search(r'"model"\s*:', text)
                and re.search(r'"usage"\s*:', text)
                and re.search(r'"(?:content|output|message)"\s*:', text)
            )
        )
    return _json_has_provider_response_shape(payload)


def _json_has_provider_response_shape(value: Any) -> bool:
    if isinstance(value, dict):
        if "choices" in value and ("usage" in value or "model" in value):
            return True
        if "candidates" in value and (
            "usageMetadata" in value
            or "usage_metadata" in value
            or "modelVersion" in value
        ):
            return True
        if "model" in value and "usage" in value and (
            "content" in value or "output" in value or "message" in value
        ):
            return True
        return any(_json_has_provider_response_shape(item) for item in value.values())
    if isinstance(value, list):
        return any(_json_has_provider_response_shape(item) for item in value)
    return False


def _should_scan_content(relative: Path) -> bool:
    if _is_fixture_path(relative):
        return False
    if relative.suffix.lower() not in CONTENT_SCAN_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        return True
    return bool(relative.parts and relative.parts[0] in CONTENT_SCAN_ROOTS)


def _is_fixture_path(relative: Path) -> bool:
    parts = tuple(part.lower() for part in relative.parts)
    if parts and parts[0] in FIXTURE_ROOTS:
        return True
    return any(part in FIXTURE_MARKERS for part in parts)


def _line_is_allowed(line: str) -> bool:
    lowered = line.lower()
    if not any(marker in lowered for marker in ALLOW_MARKERS):
        return False
    stripped = lowered.strip()
    if not stripped.startswith(("#", "//", "<!--")):
        return False
    has_blocked_shape = (
        RAW_STREAM_MARKER_RE.search(line)
        or RAW_BODY_MARKER_RE.search(line)
        or COOKIE_HEADER_RE.search(line)
        or _secret_like_content_reason(line) is not None
    )
    return not has_blocked_shape


def _is_cookie_header_leak(line: str) -> bool:
    match = COOKIE_HEADER_RE.search(line)
    if match is None:
        return False
    value = match.group("value").strip().strip("'\"")
    return not _is_placeholder_value(value)


def _is_placeholder_value(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in {"<redacted>", "[redacted]"}
        or "{{" in lowered
        or "${" in lowered
        or "placeholder" in lowered
        or "example" in lowered
        or lowered.startswith("<") and lowered.endswith(">")
    )


def _secret_like_content_reason(line: str) -> str | None:
    sanitized = SAFE_PLACEHOLDER_CREDENTIAL_RE.sub(" ", line)
    return secret_like_content_reason(sanitized)


def _relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
