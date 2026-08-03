from __future__ import annotations

from pathlib import Path
from typing import Literal

from scripts.factory_cost_policy_validation import FactoryCostPolicyError

from .factory_status_errors import FactoryStatusError
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


def collect_queue(root: Path, fingerprints: Fingerprints) -> tuple[QueueStatus, tuple[str, ...]]:
    """Count queue metadata paths without parsing their content."""

    queue_root = root / ".entroping" / "ai-jobs"
    if not exists_lstat(queue_root):
        return QueueStatus(
            status="uninitialized", queued=0, running=0, completed=0, failed=0, invalid=0
        ), ("queue-uninitialized",)
    try:
        from .factory_status_tree import scan_queue

        counts, invalid = scan_queue(root, fingerprints)
    except (FactoryStatusError, OSError):
        return QueueStatus(
            status="unsafe", queued=0, running=0, completed=0, failed=0, invalid=1
        ), ("queue-unsafe",)
    return QueueStatus(
        status="unavailable" if invalid else "available",
        queued=counts["queued"],
        running=counts["running"],
        completed=counts["completed"],
        failed=counts["failed"],
        invalid=invalid,
    ), (("queue-invalid",) if invalid else ())


def collect_retention(
    root: Path, fingerprints: Fingerprints
) -> tuple[RetentionStatus, tuple[str, ...]]:
    """Summarize managed retention roots using metadata-only bounded walks."""

    policy_path = root / ".entroping" / "factory-retention-policy.json"
    if not exists_lstat(policy_path):
        policy_path = root / "docs" / "meta" / "factory-retention-policy.example.json"
    if not exists_lstat(policy_path):
        return _retention_unavailable("unavailable"), ("retention-policy-unavailable",)
    try:
        from .factory_status_authority import load_retention_policy

        policy = load_retention_policy(root, policy_path, fingerprints)
    except (FactoryCostPolicyError, FactoryStatusError, OSError, ValueError):
        return _retention_unavailable("unsafe"), ("retention-unsafe",)
    totals: dict[ArtifactClass, list[int]] = {name: [0, 0] for name in _RETENTION_CLASSES}
    from .factory_status_tree import TraversalBudget, scan_retention

    budget = TraversalBudget()
    try:
        for artifact_class, parts in _RETENTION_ROOTS:
            candidate = root.joinpath(*parts)
            if exists_lstat(candidate):
                scan_retention(root, parts, fingerprints, totals[artifact_class], budget)
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


def exists_lstat(path: Path) -> bool:
    """Return whether an entry exists without resolving a symlink."""

    try:
        _ = path.lstat()
    except FileNotFoundError:
        return False
    return True


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
