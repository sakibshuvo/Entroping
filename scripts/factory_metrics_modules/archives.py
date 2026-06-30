"""Finished-issue ledger archive loading for factory metrics reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .common import _lexical_absolute, _safe_report_label
from .events import _load_events
from .schema import FINISHED_ISSUE_DIR_RE, FINISHED_ISSUES_DIR


def _finished_issues_root(repo_root: Path) -> Path:
    return _lexical_absolute(repo_root / FINISHED_ISSUES_DIR)


def _finished_issue_ledger_label(repo_root: Path, ledger: Path) -> str:
    factory_root = _lexical_absolute(repo_root / ".entroping" / "factory-metrics")
    try:
        return ledger.relative_to(factory_root).as_posix()
    except ValueError:
        return ledger.as_posix()


def _finished_issue_from_ledger_path(repo_root: Path, ledger: Path) -> str | None:
    archive_root = _finished_issues_root(repo_root)
    try:
        relative = _lexical_absolute(ledger).relative_to(archive_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    match = FINISHED_ISSUE_DIR_RE.fullmatch(relative.parts[0])
    if match is None:
        return None
    return match.group("issue")


def _events_with_default_issue(
    events: list[dict[str, Any]], default_issue: str | None
) -> list[dict[str, Any]]:
    if default_issue is None:
        return events

    attributed: list[dict[str, Any]] = []
    for event in events:
        if _safe_report_label(event.get("issue")) is not None:
            attributed.append(event)
            continue
        attributed_event = dict(event)
        attributed_event["issue"] = default_issue
        attributed.append(attributed_event)
    return attributed


def _iter_finished_issue_ledgers(repo_root: Path) -> list[Path]:
    archive_root = _finished_issues_root(repo_root)
    if not archive_root.exists() or archive_root.is_symlink() or not archive_root.is_dir():
        return []

    ledgers: list[Path] = []
    for current_root, dirnames, filenames in os.walk(archive_root, followlinks=False):
        current = Path(current_root)
        dirnames[:] = sorted(
            dirname for dirname in dirnames if not (current / dirname).is_symlink()
        )
        for filename in sorted(filenames):
            candidate = current / filename
            if candidate.suffix == ".jsonl" and not candidate.is_symlink() and candidate.is_file():
                ledgers.append(candidate)

    return sorted(
        ledgers,
        key=lambda ledger: ledger.relative_to(archive_root).as_posix(),
    )


def _load_report_events(
    repo_root: Path, ledger: Path, *, include_finished_issues: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    events, errors = _load_events(ledger)
    events = _events_with_default_issue(events, _finished_issue_from_ledger_path(repo_root, ledger))
    if not include_finished_issues:
        return events, errors

    active_ledger = _lexical_absolute(ledger)
    for archived_ledger in _iter_finished_issue_ledgers(repo_root):
        if archived_ledger == active_ledger:
            continue
        label = _finished_issue_ledger_label(repo_root, archived_ledger)
        archived_events, archived_errors = _load_events(
            archived_ledger,
            error_prefix=f"{label}: ",
        )
        events.extend(
            _events_with_default_issue(
                archived_events,
                _finished_issue_from_ledger_path(repo_root, archived_ledger),
            )
        )
        errors.extend(archived_errors)

    return events, errors
