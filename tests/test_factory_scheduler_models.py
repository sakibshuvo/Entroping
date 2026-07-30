from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import json
from pathlib import Path

import pytest
from factory_scheduler_test_support import (
    NOW,
    dead,
    owner,
    request,
    scheduler,
)

from scripts.factory_scheduler_models import AssignmentRequest, LeaseOwner, SchedulerLimits


def test_worktree_identity_rejects_paths_and_unverified_labels() -> None:
    payload = request().model_dump(mode="json")
    for value in ("issue-1569", "../Entroping-issue-1569", "/tmp/worktree"):
        payload["worktree_id"] = value
        with pytest.raises(ValueError):
            AssignmentRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", "ghp_abcdefghijklmnopqrstuvwxyz"),
        ("job_id", "sk-proj-not-a-scheduler-job-id"),
    ],
)
def test_assignment_identifiers_reject_secret_shaped_values(
    field: str,
    value: str,
) -> None:
    payload = request().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValueError, match="secret-like"):
        AssignmentRequest.model_validate(payload, strict=True)


def test_lease_owner_identifiers_reject_secret_shaped_values() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        LeaseOwner(
            owner_id="ghp_abcdefghijklmnopqrstuvwxyz",
            pid=123,
            process_start_token=f"proc_{1:064x}",
        )


def test_process_start_token_is_a_dedicated_hash_type() -> None:
    valid_hash_with_luhn_substring = "a" * 45 + "4111111111111111" + "b" * 3

    parsed = LeaseOwner(
        owner_id="scheduler-owner",
        pid=123,
        process_start_token=f"proc_{valid_hash_with_luhn_substring}",
    )

    assert parsed.process_start_token == f"proc_{valid_hash_with_luhn_substring}"
    with pytest.raises(ValueError):
        LeaseOwner(
            owner_id="scheduler-owner",
            pid=123,
            process_start_token="process-start-token",
        )


def test_receipt_schema_is_value_free_and_bounded(tmp_path: Path) -> None:
    receipt = scheduler(tmp_path).tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )
    payload = json.loads(receipt.model_dump_json())

    assert set(payload) == {
        "schema_version",
        "decision_id",
        "decision",
        "reason",
        "authoritative",
        "paid_work_authorized",
        "request_id",
        "job_id",
        "issue_number",
        "worktree_id",
        "assignment_id",
        "lease_owner_id",
        "lease_epoch",
        "observed_at",
        "active_paid",
        "active_free_reviews",
        "active_writers_in_scope",
    }
    assert len(receipt.model_dump_json()) < 2_048
    assert "instruction" not in receipt.model_dump_json().lower()


def test_limits_reject_values_above_the_initial_safety_ceiling() -> None:
    for field in ("max_paid", "max_free_local_reviews", "max_writers_per_scope"):
        payload = SchedulerLimits().model_dump()
        payload[field] = 2
        with pytest.raises(ValueError):
            SchedulerLimits.model_validate(payload, strict=True)
