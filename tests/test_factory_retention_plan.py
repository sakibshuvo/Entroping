from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_retention_models import (  # noqa: E402
    ArtifactCandidate,
    ArtifactReference,
    RetentionClassPolicy,
    RetentionPlanReport,
    RetentionPolicy,
    RetentionStatePolicy,
)
from scripts.factory_retention_plan import plan_retention  # noqa: E402
from scripts.factory_retention_types import (  # noqa: E402
    CANDIDATE_SCHEMA_VERSION,
    MANAGED_CLASSES,
    POLICY_SCHEMA_VERSION,
)

AS_OF = datetime(2026, 7, 28, tzinfo=UTC)


def _policy(*, age: int = 30, ceiling: int = 250) -> RetentionPolicy:
    return RetentionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        class_policies=tuple(
            RetentionClassPolicy(
                schema_version=POLICY_SCHEMA_VERSION,
                artifact_class=artifact_class,
                byte_ceiling=ceiling,
                state_policies=tuple(
                    RetentionStatePolicy(state=state, max_age_days=age)
                    for state in {
                        "ai_job": ("completed", "failed"),
                        "ai_review": ("accepted", "rejected"),
                        "factory_log": ("rotated",),
                        "factory_metrics_archive": ("archived",),
                        "retention_journal": ("completed", "rolled_back"),
                    }[artifact_class]
                ),
            )
            for artifact_class in MANAGED_CLASSES
        ),
    )


def _candidate(
    artifact_id: str,
    *,
    artifact_class: str = "ai_job",
    state: str = "completed",
    path: str | None = None,
    age_days: int = 31,
    byte_size: int = 100,
    bundle_id: str | None = None,
    **values: object,
) -> ArtifactCandidate:
    suffix = path or f".entroping/ai-jobs/completed/{artifact_id}.json"
    payload: dict[str, object] = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "bundle_id": bundle_id or artifact_id,
        "artifact_class": artifact_class,
        "relative_path": suffix,
        "byte_size": byte_size,
        "created_at": AS_OF - timedelta(days=age_days),
        "state": state,
    }
    payload.update(values)
    return ArtifactCandidate.model_validate(payload)


def _reason(report: RetentionPlanReport, artifact_id: str) -> str:
    return next(item.reason_code for item in report.decisions if item.artifact_id == artifact_id)


def test_age_and_byte_limits_are_independent() -> None:
    old_under_cap = plan_retention(_policy(ceiling=1_000), (_candidate("old"),), AS_OF)
    assert _reason(old_under_cap, "old") == "delete_by_age"

    young = (
        _candidate("first", age_days=1, byte_size=60),
        _candidate("second", age_days=1, byte_size=60),
    )
    young_over_cap = plan_retention(_policy(ceiling=100), young, AS_OF)
    assert _reason(young_over_cap, "first") == "delete_by_byte_cap"
    assert _reason(young_over_cap, "second") == "age_not_reached"


def test_terminal_states_can_have_different_age_limits() -> None:
    base = _policy(age=90, ceiling=1_000)
    job_policy = RetentionClassPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        artifact_class="ai_job",
        byte_ceiling=1_000,
        state_policies=(
            RetentionStatePolicy(state="completed", max_age_days=90),
            RetentionStatePolicy(state="failed", max_age_days=7),
        ),
    )
    policy = RetentionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        class_policies=(job_policy, *base.class_policies[1:]),
    )
    completed = _candidate("completed", state="completed", age_days=8)
    failed = _candidate(
        "failed",
        state="failed",
        age_days=8,
        path=".entroping/ai-jobs/failed/failed.json",
    )
    report = plan_retention(policy, (completed, failed), AS_OF)
    assert _reason(report, "completed") == "age_not_reached"
    assert _reason(report, "failed") == "delete_by_age"


def test_exact_cutoff_and_future_timestamp_are_retained() -> None:
    candidates = (
        _candidate("exact", age_days=30, byte_size=1),
        _candidate("future", age_days=-1, byte_size=1),
    )
    report = plan_retention(_policy(ceiling=1_000), candidates, AS_OF)
    assert {_reason(report, item.artifact_id) for item in candidates} == {"age_not_reached"}


def test_byte_pressure_counts_protected_and_active_bytes() -> None:
    active = _candidate("active", state="running", byte_size=2_000)
    report = plan_retention(_policy(ceiling=1), (active,), AS_OF)
    summary = next(item for item in report.class_summaries if item.artifact_class == "ai_job")
    assert _reason(report, "active") == "protected_active_state"
    assert summary.retained_bytes == 2_000
    assert summary.pressure_bytes == 1_999


@pytest.mark.parametrize(
    ("reservation_id", "settlement_state", "reason"),
    (
        ("r1", None, "protected_missing_settlement"),
        ("r1", "unresolved", "protected_unresolved_settlement"),
        ("r1", "unknown", "protected_unknown_settlement"),
    ),
)
def test_reservation_requires_explicit_settlement(
    reservation_id: str,
    settlement_state: str | None,
    reason: str,
) -> None:
    candidate = _candidate(
        "reserved",
        reservation_id=reservation_id,
        settlement_state=settlement_state,
    )
    report = plan_retention(_policy(), (candidate,), AS_OF)
    assert _reason(report, "reserved") == reason


def test_legacy_unreserved_and_settled_jobs_can_expire() -> None:
    legacy = _candidate("legacy")
    settled = _candidate("settled", reservation_id="r1", settlement_state="settled")
    report = plan_retention(_policy(), (legacy, settled), AS_OF)
    assert {_reason(report, "legacy"), _reason(report, "settled")} == {"delete_by_age"}


@pytest.mark.parametrize("status", ("ready_for_codex", "in_review", "reviewed", "needs_review"))
def test_nonfinal_review_states_are_always_retained(status: str) -> None:
    candidate = _candidate(
        "review",
        artifact_class="ai_review",
        state="ready_for_codex",
        inbox_status=status,
        path=".entroping/ai-reviews/review",
    )
    report = plan_retention(_policy(), (candidate,), AS_OF)
    assert _reason(report, "review") == "protected_review_state"


@pytest.mark.parametrize(
    ("reference_state", "reason"),
    (("open", "protected_open_reference"), ("unknown", "protected_unknown_reference")),
)
def test_accepted_open_or_unknown_reference_protects_entire_bundle(
    reference_state: str,
    reason: str,
) -> None:
    reference = ArtifactReference.model_validate(
        {"kind": "issue", "reference_id": "42", "state": reference_state}
    )
    job = _candidate("job", bundle_id="bundle")
    review = _candidate(
        "review",
        bundle_id="bundle",
        artifact_class="ai_review",
        state="ready_for_codex",
        inbox_status="accepted",
        references=(reference,),
        path=".entroping/ai-reviews/review",
    )
    report = plan_retention(_policy(), (job, review), AS_OF)
    assert _reason(report, "review") == reason
    assert _reason(report, "job") == "protected_bundle"


def test_malformed_and_unknown_states_fail_closed() -> None:
    malformed = _candidate("malformed", metadata_valid=False)
    unknown = _candidate("unknown", state="finished")
    report = plan_retention(_policy(), (malformed, unknown), AS_OF)
    assert _reason(report, "malformed") == "protected_malformed_metadata"
    assert _reason(report, "unknown") == "protected_unknown_state"


def test_multi_gigabyte_aggregates_are_reported_without_validation_failure() -> None:
    candidates = (
        _candidate("a", state="running", byte_size=1_200_000_000),
        _candidate("b", state="running", byte_size=1_200_000_000),
    )
    report = plan_retention(_policy(ceiling=1_000), candidates, AS_OF)
    assert report.total_retain_bytes == 2_400_000_000


def test_deletion_order_is_oldest_then_path_and_output_is_idempotent() -> None:
    candidates = (
        _candidate("z", age_days=1, byte_size=60),
        _candidate("a", age_days=1, byte_size=60),
    )
    first = plan_retention(_policy(ceiling=100), candidates, AS_OF)
    second = plan_retention(_policy(ceiling=100), tuple(reversed(candidates)), AS_OF)
    assert first == second
    assert tuple(item.artifact_id for item in first.decisions if item.action == "delete") == ("a",)


def test_very_early_as_of_fails_cleanly_instead_of_overflowing() -> None:
    with pytest.raises(ValueError, match="datetime range"):
        _ = plan_retention(
            _policy(age=30),
            (_candidate("candidate"),),
            datetime.min.replace(tzinfo=UTC),
        )


def test_duplicate_candidate_identity_is_rejected() -> None:
    candidate = _candidate("same")
    with pytest.raises(ValueError, match="duplicate candidate"):
        _ = plan_retention(_policy(), (candidate, candidate), AS_OF)
