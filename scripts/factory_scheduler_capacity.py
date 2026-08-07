"""Pure scheduler capacity policy helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.factory_scheduler_models import AssignmentRequest, SchedulerLimits
from scripts.factory_scheduler_validation import aware_utc


def capacity_reason(
    request: AssignmentRequest,
    *,
    counts: tuple[int, int, int],
    limits: SchedulerLimits,
) -> str | None:
    paid, free_reviews, writers = counts
    if request.worker_class == "paid" and paid >= limits.max_paid:
        return "paid-capacity"
    if (
        request.worker_class == "free-local"
        and request.access_mode == "read-only"
        and free_reviews >= limits.max_free_local_reviews
    ):
        return "free-review-capacity"
    if request.access_mode == "write" and writers >= limits.max_writers_per_scope:
        return "writer-scope-capacity"
    return None


def observed_at(as_of: datetime | None) -> datetime:
    return aware_utc(datetime.now(UTC) if as_of is None else as_of)
