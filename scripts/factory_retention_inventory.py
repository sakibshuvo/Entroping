from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.factory_retention_fs import SnapshotBudget
from scripts.factory_retention_inventory_control import (
    inventory_journals,
    inventory_metrics_archives,
)
from scripts.factory_retention_inventory_jobs import inventory_jobs
from scripts.factory_retention_inventory_logs import inventory_logs
from scripts.factory_retention_inventory_metadata import InventoryEntry
from scripts.factory_retention_inventory_reviews import inventory_reviews
from scripts.factory_retention_models import ArtifactCandidate


@dataclass(frozen=True, slots=True)
class RetentionInventory:
    entries: tuple[InventoryEntry, ...]
    errors: tuple[str, ...]

    @property
    def candidates(self) -> tuple[ArtifactCandidate, ...]:
        return tuple(entry.candidate for entry in self.entries)

    def entry_by_path(self) -> dict[str, InventoryEntry]:
        return {entry.candidate.relative_path: entry for entry in self.entries}


def inventory_factory(repo_root: Path) -> RetentionInventory:
    entries: list[InventoryEntry] = []
    errors: list[str] = []
    review_bundles: dict[str, str] = {}
    snapshot_budget = SnapshotBudget()
    for state in ("completed", "failed"):
        job_entries, job_errors, references = inventory_jobs(
            repo_root,
            state,
            snapshot_budget,
        )
        entries.extend(job_entries)
        errors.extend(job_errors)
        for review_artifact, bundle_id in references:
            existing = review_bundles.get(review_artifact)
            if existing is not None and existing != bundle_id:
                errors.append(f"review artifact has multiple terminal jobs: {review_artifact}")
                review_bundles[review_artifact] = ""
            else:
                review_bundles[review_artifact] = bundle_id
    review_entries, review_errors = inventory_reviews(
        repo_root,
        review_bundles,
        snapshot_budget,
    )
    log_entries, log_errors = inventory_logs(repo_root, snapshot_budget)
    metrics_entries, metrics_errors = inventory_metrics_archives(
        repo_root,
        snapshot_budget,
    )
    journal_entries, journal_errors = inventory_journals(repo_root, snapshot_budget)
    entries.extend(review_entries)
    entries.extend(log_entries)
    entries.extend(metrics_entries)
    entries.extend(journal_entries)
    errors.extend(review_errors)
    errors.extend(log_errors)
    errors.extend(metrics_errors)
    errors.extend(journal_errors)
    return RetentionInventory(
        entries=tuple(sorted(entries, key=lambda item: item.candidate.relative_path)),
        errors=tuple(sorted(set(errors))),
    )
