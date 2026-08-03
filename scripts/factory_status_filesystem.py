from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from scripts.factory_cost_policy_io import read_policy_document
from scripts.factory_cost_policy_validation import FactoryCostPolicyError
from scripts.factory_retention_models import RetentionPolicy

from .factory_status_models import QueueStatus, RetentionClassStatus, RetentionStatus, SourceState

type ArtifactClass = Literal[
    "ai_job",
    "ai_review",
    "factory_log",
    "factory_metrics_archive",
    "retention_journal",
]
type Pressure = Literal["unavailable", "normal", "high", "exceeded", "unsafe"]
type Fingerprints = list[tuple[str, int, int, int]]

_QUEUE_STATES = ("queued", "running", "completed", "failed")
_RETENTION_ROOTS: tuple[tuple[ArtifactClass, tuple[str, ...]], ...] = (
    ("ai_job", (".entroping", "ai-jobs", "completed")),
    ("ai_job", (".entroping", "ai-jobs", "failed")),
    ("ai_review", (".entroping", "ai-reviews")),
    ("factory_log", (".entroping", "factory-logs")),
    ("factory_metrics_archive", (".entroping", "factory-metrics", "finished-issues")),
    ("retention_journal", (".entroping", "retention-journal")),
)
_RETENTION_CLASSES: tuple[ArtifactClass, ...] = (
    "ai_job",
    "ai_review",
    "factory_log",
    "factory_metrics_archive",
    "retention_journal",
)
_MAX_ENTRIES = 10_000
_MAX_DEPTH = 64


@dataclass(slots=True)
class _TraversalBudget:
    remaining: int = _MAX_ENTRIES

    def consume(self) -> None:
        if self.remaining <= 0:
            raise FactoryStatusError("entry limit exceeded")
        self.remaining -= 1


class FactoryStatusError(RuntimeError):
    """Signals a sanitized unsafe filesystem condition in the status projection."""


def collect_queue(root: Path, fingerprints: Fingerprints) -> tuple[QueueStatus, tuple[str, ...]]:
    """Count queue metadata paths without parsing their content."""

    queue_root = root / ".entroping" / "ai-jobs"
    if not exists_lstat(queue_root):
        return QueueStatus(
            status="uninitialized", queued=0, running=0, completed=0, failed=0, invalid=0
        ), ("queue-uninitialized",)
    counts = {state: 0 for state in _QUEUE_STATES}
    try:
        _scan_tree(root, queue_root, fingerprints, counts, budget=_TraversalBudget())
    except (FactoryStatusError, OSError):
        return QueueStatus(
            status="unsafe", queued=0, running=0, completed=0, failed=0, invalid=1
        ), ("queue-unsafe",)
    return QueueStatus(
        status="available",
        queued=counts["queued"],
        running=counts["running"],
        completed=counts["completed"],
        failed=counts["failed"],
        invalid=0,
    ), ()


def collect_retention(
    root: Path, fingerprints: Fingerprints
) -> tuple[RetentionStatus, tuple[str, ...]]:
    """Summarize managed retention roots using metadata-only bounded walks."""

    policy_path = root / ".entroping" / "factory-retention-policy.json"
    if not exists_lstat(policy_path):
        policy_path = root / "docs" / "meta" / "factory-retention-policy.example.json"
    try:
        fingerprint_file(root, policy_path, fingerprints)
        policy = RetentionPolicy.model_validate_json(read_policy_document(policy_path), strict=True)
    except FactoryStatusError:
        return _retention_unavailable("unsafe"), ("retention-unsafe",)
    except (FactoryCostPolicyError, ValidationError, OSError, ValueError):
        return _retention_unavailable("unavailable"), ("retention-policy-unavailable",)
    totals: dict[ArtifactClass, list[int]] = {name: [0, 0] for name in _RETENTION_CLASSES}
    budget = _TraversalBudget()
    try:
        for artifact_class, parts in _RETENTION_ROOTS:
            candidate = root.joinpath(*parts)
            if exists_lstat(candidate):
                _scan_tree(
                    root,
                    candidate,
                    fingerprints,
                    None,
                    totals[artifact_class],
                    budget=budget,
                )
    except (FactoryStatusError, OSError):
        return _retention_unavailable("unsafe"), ("retention-unsafe",)
    ceilings = {item.artifact_class: item.byte_ceiling for item in policy.class_policies}
    classes = tuple(
        RetentionClassStatus(
            artifact_class=name,
            count=totals[name][0],
            bytes=totals[name][1],
            byte_ceiling=ceilings.get(name),
            pressure=_pressure(totals[name][1], ceilings.get(name)),
        )
        for name in _RETENTION_CLASSES
    )
    status: SourceState = "uninitialized" if not exists_lstat(root / ".entroping") else "available"
    if status != "available":
        return RetentionStatus(status=status, classes=classes), ("retention-uninitialized",)
    pressured = any(item.pressure in {"high", "exceeded"} for item in classes)
    return RetentionStatus(status=status, classes=classes), (
        ("retention-pressure",) if pressured else ()
    )


def unsafe_retention() -> RetentionStatus:
    """Return the complete sanitized retention section for a root-level failure."""

    return _retention_unavailable("unsafe")


def fingerprint_file(
    root: Path,
    path: Path,
    fingerprints: Fingerprints,
    *,
    strict_state_file: bool = False,
) -> None:
    """Capture non-content file identity after rejecting unsafe metadata."""

    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise FactoryStatusError("unsafe file")
    if strict_state_file and (
        metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise FactoryStatusError("unsafe file")
    fingerprints.append(
        (path.relative_to(root).as_posix(), metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
    )


def exists_lstat(path: Path) -> bool:
    """Return whether an entry exists without resolving a symlink."""

    try:
        _ = path.lstat()
    except FileNotFoundError:
        return False
    return True


def _scan_tree(
    root: Path,
    path: Path,
    fingerprints: Fingerprints,
    queue_counts: dict[str, int] | None = None,
    totals: list[int] | None = None,
    depth: int = 0,
    budget: _TraversalBudget | None = None,
) -> None:
    if depth > _MAX_DEPTH:
        raise FactoryStatusError("path depth exceeded")
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise FactoryStatusError("unsafe directory")
    active_budget = budget or _TraversalBudget()
    with os.scandir(path) as entries:
        for entry in entries:
            active_budget.consume()
            child = Path(entry.path)
            child_metadata = child.lstat()
            relative = child.relative_to(root).as_posix()
            if stat.S_ISREG(child_metadata.st_mode):
                if child_metadata.st_nlink != 1:
                    raise FactoryStatusError("unsafe file")
                fingerprints.append(
                    (
                        relative,
                        child_metadata.st_ino,
                        child_metadata.st_size,
                        child_metadata.st_mtime_ns,
                    )
                )
                if totals is not None:
                    totals[0] += 1
                    totals[1] += child_metadata.st_size
                if (
                    queue_counts is not None
                    and child.suffix == ".json"
                    and child.parent.name in queue_counts
                ):
                    queue_counts[child.parent.name] += 1
                continue
            if stat.S_ISDIR(child_metadata.st_mode):
                _scan_tree(
                    root, child, fingerprints, queue_counts, totals, depth + 1, active_budget
                )
                continue
            raise FactoryStatusError("special file")


def _pressure(size: int, ceiling: int | None) -> Pressure:
    if ceiling is None:
        return "unavailable"
    if size > ceiling:
        return "exceeded"
    if size * 100 >= ceiling * 90:
        return "high"
    return "normal"


def _retention_unavailable(status: Literal["unsafe", "unavailable"]) -> RetentionStatus:
    pressure: Pressure = "unsafe" if status == "unsafe" else "unavailable"
    return RetentionStatus(
        status=status,
        classes=tuple(
            RetentionClassStatus(
                artifact_class=name, count=0, bytes=0, byte_ceiling=None, pressure=pressure
            )
            for name in _RETENTION_CLASSES
        ),
    )
