"""Shared safety, path, and presentation helpers for factory metrics."""

from __future__ import annotations

import html
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .schema import (
    CONTROL_CHARACTER_PATTERN,
    DEFAULT_LEDGER,
    NOTE_FORBIDDEN_PATTERN,
    NOTE_MAX_LENGTH,
    SECRET_REDACTIONS,
)


class FactoryMetricsError(Exception):
    """User-facing metrics CLI error."""


def _redact_text(value: str | None) -> str | None:
    if value is None:
        return None

    redacted = value
    for pattern, replacement in SECRET_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _contains_secret_like(value: str) -> bool:
    return _redact_text(value) != value


def _contains_control_character(value: str) -> bool:
    return CONTROL_CHARACTER_PATTERN.search(value) is not None


def _validate_note(value: str) -> list[str]:
    errors: list[str] = []
    if len(value) > NOTE_MAX_LENGTH:
        errors.append(f"note must be {NOTE_MAX_LENGTH} characters or fewer")
    if NOTE_FORBIDDEN_PATTERN.search(value):
        errors.append("note must not contain raw prompt or transcript material")
    return errors


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _ensure_no_symlink_components(repo_root: Path, path: Path, subject: str) -> None:
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return

    current = repo_root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise FactoryMetricsError(f"{subject} must not use symlink components")


def _repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()
    return Path(completed.stdout.strip()).resolve()


def _safe_factory_metrics_path(repo_root: Path, raw_path: Path, subject: str) -> Path:
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = _lexical_absolute(path)
    factory_root = _lexical_absolute(repo_root / ".entroping" / "factory-metrics")
    try:
        resolved.relative_to(factory_root)
    except ValueError as exc:
        raise FactoryMetricsError(f"{subject} must be under .entroping/factory-metrics/") from exc
    _ensure_no_symlink_components(repo_root, resolved, subject)
    return resolved


def _safe_ledger_path(repo_root: Path, ledger: str | None) -> Path:
    raw_path = Path(ledger).expanduser() if ledger else DEFAULT_LEDGER
    return _safe_factory_metrics_path(repo_root, raw_path, "ledger path")


def _safe_report_path(repo_root: Path, output: str) -> Path:
    return _safe_factory_metrics_path(repo_root, Path(output).expanduser(), "report path")


def _safe_context_scorecard_input_path(repo_root: Path, raw_input: str) -> Path:
    raw_path = Path(raw_input).expanduser()
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = _lexical_absolute(path)
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise FactoryMetricsError("scorecard input must be under repo root") from exc
    _ensure_no_symlink_components(repo_root, resolved, "scorecard input")
    if not resolved.is_file():
        raise FactoryMetricsError("scorecard input must be an existing file")
    return resolved


def _resolve_context_file(repo_root: Path, path: str | None) -> Path | None:
    if not path:
        return None
    context_path = Path(path).expanduser()
    if not context_path.is_absolute():
        context_path = repo_root / context_path
    resolved = context_path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise FactoryMetricsError("context file must be under repo root") from exc
    return resolved


def _markdown_cell(value: object) -> str:
    text = str(value)
    escaped = html.escape(text, quote=False)
    return escaped.replace("\n", " ").replace("|", r"\|").replace("`", r"\`")


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _safe_report_label(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    redacted = _redact_text(value)
    if not redacted.strip():
        return None
    return redacted


def _unknown_safe_report_label(value: object) -> str:
    return _safe_report_label(value) or "unknown"


def _write_report_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return

    for key, value in payload.items():
        print(f"{key}: {value}")
