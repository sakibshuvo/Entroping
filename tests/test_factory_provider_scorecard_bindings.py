"""Immutable receipt-binding tests for provider scorecards."""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from support.provider_scorecard import (  # pyright: ignore[reportImplicitRelativeImport]
    case,
    document,
    identity,
    validate,
    write_scorecard,
)

IDENTITY_MUTATIONS = (
    ("job_id", "other-job"),
    ("reservation_id", "other-reservation"),
    ("issue_number", 9999),
    ("provider_lane_id", "local/offline"),
    ("provider_host", "other provider host"),
    ("billing_path", "other billing path"),
    ("model_id", "deepseek-v4-flash"),
    ("cost_provider_id", "other-provider"),
    ("cost_model_id", "deepseek/deepseek-v4-flash"),
    ("autonomy_tier", "tier_a"),
    ("base_revision", "d" * 40),
    ("head_revision", "e" * 40),
    ("diff_sha256", "0" * 64),
)


@pytest.mark.parametrize(("field", "bad_value"), IDENTITY_MUTATIONS)
def test_each_immutable_review_identity_mismatch_is_rejected(
    tmp_path: Path, field: str, bad_value: str | int
) -> None:
    # Given: a freshly signed case whose review rebinds one immutable identity field.
    item = case(1)
    receipt = item["review"]
    assert isinstance(receipt, dict)
    receipt[field] = bad_value
    path = write_scorecard(tmp_path, document(item))

    # When: validation parses the independently authenticated mismatch.
    result = validate(tmp_path, path)

    # Then: no identity field can be attached to different work.
    assert result.returncode == 1
    assert "identity" in result.stdout


@pytest.mark.parametrize("receipt_name", ("verification", "ci", "merge"))
def test_each_terminal_receipt_kind_must_match_case_identity(
    tmp_path: Path, receipt_name: str
) -> None:
    item = case(1)
    receipt = item[receipt_name]
    assert isinstance(receipt, dict)
    receipt["job_id"] = "other-job"
    result = validate(tmp_path, write_scorecard(tmp_path, document(item)))
    assert result.returncode == 1
    assert "identity" in result.stdout


def test_later_outcome_receipt_must_match_case_identity(tmp_path: Path) -> None:
    outcome = {
        **identity(1),
        "job_id": "other-job",
        "status": "passed",
        "observed_at": "2026-08-02T00:00:00Z",
        "merge_commit_revision": "f" * 39 + "1",
        "digest": "2" * 64,
    }
    item = case(1, later_outcomes=[outcome])
    result = validate(tmp_path, write_scorecard(tmp_path, document(item)))
    assert result.returncode == 1
    assert "identity" in result.stdout


def test_verification_receipt_lane_must_match_case_lane(tmp_path: Path) -> None:
    item = case(1, verification_lane="security-runtime")
    receipt = item["verification"]
    assert isinstance(receipt, dict)
    receipt["verification_lane"] = "normal-code"
    result = validate(tmp_path, write_scorecard(tmp_path, document(item)))
    assert result.returncode == 1
    assert "lane" in result.stdout
