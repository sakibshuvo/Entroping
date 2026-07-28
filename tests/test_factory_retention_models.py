from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_retention_fs import MAX_POLICY_TOTAL_BYTES  # noqa: E402
from scripts.factory_retention_models import (  # noqa: E402
    ArtifactCandidate,
    ArtifactReference,
    ClassRetentionSummary,
    RetentionClassPolicy,
    RetentionDecision,
    RetentionPlanReport,
    RetentionPolicy,
)
from scripts.factory_retention_types import (  # noqa: E402
    CANDIDATE_SCHEMA_VERSION,
    MANAGED_CLASSES,
    PLANNER_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION,
)


def _class_policy(artifact_class: str) -> RetentionClassPolicy:
    states = {
        "ai_job": ("completed", "failed"),
        "ai_review": ("accepted", "rejected"),
        "factory_log": ("rotated",),
        "factory_metrics_archive": ("archived",),
        "retention_journal": ("completed", "rolled_back"),
    }[artifact_class]
    return RetentionClassPolicy.model_validate(
        {
            "schema_version": POLICY_SCHEMA_VERSION,
            "artifact_class": artifact_class,
            "byte_ceiling": 1_000,
            "state_policies": tuple({"state": state, "max_age_days": 30} for state in states),
        }
    )


def _policy() -> RetentionPolicy:
    return RetentionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        class_policies=tuple(_class_policy(item) for item in MANAGED_CLASSES),
    )


def _candidate(**overrides: object) -> ArtifactCandidate:
    values: dict[str, object] = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "artifact_id": "job-1",
        "bundle_id": "job-1",
        "artifact_class": "ai_job",
        "relative_path": ".entroping/ai-jobs/completed/job-1.json",
        "byte_size": 1,
        "created_at": datetime(2026, 7, 1, tzinfo=UTC),
        "state": "completed",
    }
    values.update(overrides)
    return ArtifactCandidate.model_validate(values)


@pytest.mark.parametrize(
    "path",
    (
        ".",
        ".git/config",
        "pyproject.toml",
        "/tmp/job.json",
        ".entroping/ai-jobs/completed/../failed/job.json",
        ".entroping/ai-jobs/completed/a\x00b.json",
        ".entroping/ai-reviews/nested/review",
    ),
)
def test_candidate_rejects_paths_outside_exact_managed_root(path: str) -> None:
    with pytest.raises(ValidationError):
        _ = _candidate(relative_path=path)


def test_candidate_rejects_path_bound_to_wrong_class() -> None:
    with pytest.raises(ValidationError):
        _ = _candidate(
            artifact_class="ai_review",
            relative_path=".entroping/ai-jobs/completed/job-1.json",
        )


def test_candidate_accepts_multi_gigabyte_artifact() -> None:
    candidate = _candidate(byte_size=2_000_000_000)
    assert candidate.byte_size == 2_000_000_000


def test_policy_requires_every_class_once() -> None:
    policy = _policy()
    assert tuple(item.artifact_class for item in policy.class_policies) == MANAGED_CLASSES
    with pytest.raises(ValidationError):
        _ = RetentionPolicy(
            schema_version=POLICY_SCHEMA_VERSION,
            class_policies=policy.class_policies[:-1],
        )
    with pytest.raises(ValidationError):
        _ = RetentionPolicy(
            schema_version=POLICY_SCHEMA_VERSION,
            class_policies=(*policy.class_policies, policy.class_policies[-1]),
        )


def test_policy_reserves_inventory_headroom_above_all_class_ceilings() -> None:
    policy = _policy()
    payload = policy.model_dump(mode="python")
    payload["class_policies"][0]["byte_ceiling"] = MAX_POLICY_TOTAL_BYTES

    with pytest.raises(ValidationError, match="bounded inventory allowance"):
        _ = RetentionPolicy.model_validate(payload)


def test_policy_rejects_unbounded_age_before_datetime_math() -> None:
    with pytest.raises(ValidationError):
        _ = RetentionClassPolicy.model_validate(
            {
                "schema_version": POLICY_SCHEMA_VERSION,
                "artifact_class": "ai_job",
                "byte_ceiling": 1,
                "state_policies": (
                    {
                        "state": "completed",
                        "max_age_days": 9_223_372_036_854_775_807,
                    },
                    {"state": "failed", "max_age_days": 30},
                ),
            }
        )


def test_candidate_rejects_duplicate_references() -> None:
    reference = ArtifactReference(kind="issue", reference_id="42", state="open")
    with pytest.raises(ValidationError):
        _ = _candidate(references=(reference, reference))


def test_structured_custom_errors_do_not_copy_rejected_value_into_context() -> None:
    rejected = "pyproject.toml"
    with pytest.raises(ValidationError) as exc_info:
        _ = _candidate(relative_path=rejected)
    contexts = tuple(error.get("ctx", {}) for error in exc_info.value.errors())
    assert all(rejected not in str(context) for context in contexts)


def test_decision_rejects_delete_with_protected_reason() -> None:
    with pytest.raises(ValidationError):
        _ = RetentionDecision(
            action="delete",
            reason_code="protected_unknown_state",
            artifact_id="job-1",
            bundle_id="job-1",
            artifact_class="ai_job",
            relative_path=".entroping/ai-jobs/completed/job-1.json",
            byte_size=1,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )


def test_report_rejects_forged_totals_and_summaries() -> None:
    decision = RetentionDecision(
        action="retain",
        reason_code="age_not_reached",
        artifact_id="job-1",
        bundle_id="job-1",
        artifact_class="ai_job",
        relative_path=".entroping/ai-jobs/completed/job-1.json",
        byte_size=10,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    summaries = tuple(
        ClassRetentionSummary(
            artifact_class=item,
            state_max_age_days={
                state: 30
                for state in {
                    "ai_job": ("completed", "failed"),
                    "ai_review": ("accepted", "rejected"),
                    "factory_log": ("rotated",),
                    "factory_metrics_archive": ("archived",),
                    "retention_journal": ("completed", "rolled_back"),
                }[item]
            },
            byte_ceiling=1_000,
            candidate_count=1 if item == "ai_job" else 0,
            deleted_count=0,
            retained_count=1 if item == "ai_job" else 0,
            deleted_bytes=0,
            retained_bytes=10 if item == "ai_job" else 0,
            protected_count=0,
            protected_bytes=0,
            pressure_bytes=0,
        )
        for item in MANAGED_CLASSES
    )
    with pytest.raises(ValidationError):
        _ = RetentionPlanReport(
            schema_version=PLANNER_SCHEMA_VERSION,
            as_of=datetime(2026, 7, 28, tzinfo=UTC),
            total_candidate_count=1,
            total_retain_count=1,
            total_delete_count=0,
            total_retain_bytes=0,
            total_delete_bytes=0,
            decisions=(decision,),
            class_summaries=summaries,
        )
