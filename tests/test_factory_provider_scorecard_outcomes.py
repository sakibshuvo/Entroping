"""Classification, threshold, and later-outcome provider-scorecard tests."""
# ruff: noqa: E402, E501

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
    json_object,
    report,
    validate,
    write_scorecard,
)


def _row(tmp_path: Path, *items: dict[str, object]) -> dict[str, object]:
    result = report(tmp_path, write_scorecard(tmp_path, document(*items)))
    assert result.returncode == 0
    payload = json_object(result.stdout)
    rows = payload["scorecards"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    return rows[0]


@pytest.mark.parametrize(
    ("target", "field", "value", "expected"),
    (
        ("review", "decision", "rejected", "rejected"),
        ("verification", "quality", "fail", "rejected"),
        ("verification", "security", "fail", "rejected"),
        ("ci", "status", "failure", "rejected"),
        ("merge", "status", "not_merged", "rejected"),
        ("review", "decision", "needs_review", "inconclusive"),
        ("review", "decision", "inconclusive", "inconclusive"),
        ("verification", "quality", "inconclusive", "inconclusive"),
        ("verification", "security", "inconclusive", "inconclusive"),
        ("ci", "status", "cancelled", "inconclusive"),
        ("ci", "status", "pending", "inconclusive"),
        ("ci", "status", "stale", "inconclusive"),
        ("merge", "status", "inconclusive", "inconclusive"),
    ),
)
def test_terminal_failure_and_inconclusive_states_are_preserved(
    tmp_path: Path, target: str, field: str, value: str, expected: str
) -> None:
    item = case(1)
    receipt = item[target]
    assert isinstance(receipt, dict)
    receipt[field] = value
    if target == "merge" and value != "merged":
        receipt["merge_commit_revision"] = None
    row = _row(tmp_path, item)
    assert row[expected] == 1
    assert row["accepted"] == (1 if expected == "accepted" else 0)


@pytest.mark.parametrize("missing", ("review", "verification", "ci", "merge"))
def test_missing_terminal_receipt_validates_but_reports_inconclusive(
    tmp_path: Path, missing: str
) -> None:
    item = case(1, verification_lane="release-ci-architecture")
    item[missing] = None
    path = write_scorecard(tmp_path, document(item))
    validation = validate(tmp_path, path)
    result = report(tmp_path, path)
    assert validation.returncode == result.returncode == 0
    payload = json_object(result.stdout)
    rows = payload["scorecards"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    assert rows[0]["inconclusive"] == 1
    assert rows[0]["verification_lane"] == "release-ci-architecture"


def test_accepted_rejected_and_inconclusive_cases_share_one_value_free_cohort(
    tmp_path: Path,
) -> None:
    rejected = case(2, decision="rejected")
    inconclusive = case(3)
    inconclusive["ci"] = None
    row = _row(tmp_path, case(1), rejected, inconclusive)
    assert (row["accepted"], row["rejected"], row["inconclusive"]) == (1, 1, 1)


def test_minimum_accepted_sample_boundary_is_inclusive(tmp_path: Path) -> None:
    below = _row(tmp_path, case(1), case(2))
    at = _row(tmp_path, case(4), case(5), case(6))
    assert below["manual_promotion_eligible"] is False
    assert at["manual_promotion_eligible"] is True


def test_acceptance_ratio_boundary_accepts_point_eight_and_rejects_below(
    tmp_path: Path,
) -> None:
    at_cases = [case(index) for index in range(1, 6)]
    at_review = at_cases[-1]["review"]
    assert isinstance(at_review, dict)
    at_review["decision"] = "rejected"
    below_cases = [case(index) for index in range(7, 11)]
    below_review = below_cases[-1]["review"]
    assert isinstance(below_review, dict)
    below_review["decision"] = "rejected"
    at = _row(tmp_path, *at_cases)
    below = _row(tmp_path, *below_cases)
    assert at["accepted_ratio"] == 0.8
    assert at["manual_promotion_eligible"] is True
    assert below["accepted_ratio"] == 0.75
    assert below["manual_promotion_eligible"] is False


@pytest.mark.parametrize(
    ("status", "counter", "eligible"),
    (
        ("passed", None, True),
        ("regressed", "later_regressions", False),
        ("reverted", "later_reverts", False),
        ("inconclusive", "later_inconclusive", False),
    ),
)
def test_later_outcomes_preserve_status_and_gate_confidence(
    tmp_path: Path, status: str, counter: str | None, eligible: bool
) -> None:
    outcome = {
        **identity(1),
        "status": status,
        "observed_at": "2026-08-02T00:00:00Z",
        "merge_commit_revision": "f" * 39 + "1",
        "digest": "2" * 64,
    }
    row = _row(tmp_path, case(1, later_outcomes=[outcome]), case(2), case(3))
    if counter is not None:
        assert row[counter] == 1
    assert row["manual_promotion_eligible"] is eligible


def test_later_outcome_commit_and_chronology_are_bound(tmp_path: Path) -> None:
    wrong_commit = {
        **identity(1),
        "status": "passed",
        "observed_at": "2026-08-02T00:00:00Z",
        "merge_commit_revision": "0" * 40,
        "digest": "2" * 64,
    }
    predates = {
        **identity(2),
        "status": "passed",
        "observed_at": "2026-07-31T00:00:00Z",
        "merge_commit_revision": "f" * 39 + "2",
        "digest": "3" * 64,
    }
    first = validate(
        tmp_path,
        write_scorecard(
            tmp_path, document(case(1, later_outcomes=[wrong_commit])), name="commit.json"
        ),
    )
    second = validate(
        tmp_path,
        write_scorecard(tmp_path, document(case(2, later_outcomes=[predates])), name="time.json"),
    )
    assert first.returncode == second.returncode == 1
    assert "merge commit" in first.stdout
    assert "predate" in second.stdout


def test_as_of_must_be_valid_aware_and_not_predate_observations(tmp_path: Path) -> None:
    path = write_scorecard(tmp_path, document(case(1)))
    invalid = report(tmp_path, path, as_of="not-a-time")
    naive = report(tmp_path, path, as_of="2026-08-03T00:00:00")
    early = report(tmp_path, path, as_of="2026-07-31T00:00:00Z")
    assert invalid.returncode == naive.returncode == early.returncode == 1
