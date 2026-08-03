from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_retry_policy import (  # noqa: E402
    RecoverySnapshot,
    RetryPolicy,
    freshness_failure,
    retry_not_before,
)

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _snapshot(source: str, *, expires_in: int = 60) -> RecoverySnapshot:
    return RecoverySnapshot.model_validate(
        {
            "source": source,
            "observed_at": NOW - timedelta(seconds=1),
            "expires_at": NOW + timedelta(seconds=expires_in),
            "digest": "a" * 64,
        },
        strict=True,
    )


def test_retry_deadline_is_deterministic_bounded_and_honors_larger_hint() -> None:
    policy = RetryPolicy(
        base_delay_seconds=10,
        max_delay_seconds=120,
        max_attempts=5,
        max_elapsed_seconds=600,
        jitter_percent=20,
    )

    first = retry_not_before(
        policy,
        job_id="job-1",
        attempt_count=1,
        observed_at=NOW,
        retry_after_seconds=None,
    )
    replay = retry_not_before(
        policy,
        job_id="job-1",
        attempt_count=1,
        observed_at=NOW,
        retry_after_seconds=None,
    )
    hinted = retry_not_before(
        policy,
        job_id="job-1",
        attempt_count=1,
        observed_at=NOW,
        retry_after_seconds=90,
    )
    capped = retry_not_before(
        policy,
        job_id="job-1",
        attempt_count=5,
        observed_at=NOW,
        retry_after_seconds=10_000,
    )

    assert first == replay
    assert NOW + timedelta(seconds=8) <= first <= NOW + timedelta(seconds=12)
    assert hinted == NOW + timedelta(seconds=90)
    assert capped == NOW + timedelta(seconds=120)


@pytest.mark.parametrize("retry_after", [-1, 86_401, True])
def test_retry_policy_rejects_unbounded_or_ambiguous_hints(retry_after: object) -> None:
    with pytest.raises(ValidationError):
        RetryPolicy.model_validate(
            {"retry_after_ceiling_seconds": retry_after},
            strict=True,
        )


def test_freshness_requires_all_paid_authority_sources() -> None:
    fresh = tuple(
        _snapshot(source) for source in ("github", "provider-capability", "price", "quota")
    )

    assert freshness_failure(fresh, worker_class="paid", observed_at=NOW) is None
    assert (
        freshness_failure(fresh[:-1], worker_class="paid", observed_at=NOW)
        == "quota-snapshot-missing"
    )
    assert (
        freshness_failure(
            (*fresh[:-1], _snapshot("quota", expires_in=0)),
            worker_class="paid",
            observed_at=NOW,
        )
        == "quota-snapshot-stale"
    )


def test_freshness_rejects_duplicate_sources_and_future_observations() -> None:
    duplicate = (_snapshot("github"), _snapshot("github"))
    assert (
        freshness_failure(duplicate, worker_class="free-local", observed_at=NOW)
        == "snapshot-source-duplicate"
    )

    future = _snapshot("github").model_copy(update={"observed_at": NOW + timedelta(seconds=1)})
    assert (
        freshness_failure(
            (future, _snapshot("provider-capability")),
            worker_class="free-local",
            observed_at=NOW,
        )
        == "github-snapshot-future"
    )
