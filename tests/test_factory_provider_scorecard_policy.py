"""Policy and report tests for provider-scorecard evidence."""
# ruff: noqa: E402, E501

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from support.provider_scorecard import (  # pyright: ignore[reportImplicitRelativeImport]
    case,
    cost_digest,
    document,
    identity,
    report,
    validate,
    write_scorecard,
)


def test_report_uses_full_cohort_dimensions(tmp_path: Path) -> None:
    # Given: otherwise identical work reported in different verification lanes.
    first = case(1, verification_lane="security-runtime")
    second = case(2, verification_lane="normal-code")
    path = write_scorecard(tmp_path, document(first, second))

    # When: the authenticated report is projected.
    result = report(tmp_path, path)

    # Then: task, lane, exact model, autonomy tier, and verification lane partition rows.
    assert result.returncode == 0
    rows = json.loads(result.stdout)["scorecards"]
    assert len(rows) == 2
    assert {row["verification_lane"] for row in rows} == {"security-runtime", "normal-code"}
    assert all(row["autonomy_tier"] == "tier_c" for row in rows)


def test_recency_is_per_case_and_later_outcomes_do_not_refresh_old_work(
    tmp_path: Path,
) -> None:
    # Given: an exact-90-day accepted sample, a stale sample with a later pass, and two recent ones.
    boundary = case(1, observed_at="2026-05-05T00:00:00Z")
    stale = case(
        2,
        observed_at="2026-05-04T00:00:00Z",
        later_outcomes=[
            {
                **identity(2),
                "status": "passed",
                "observed_at": "2026-08-02T00:00:00Z",
                "merge_commit_revision": "f" * 39 + "2",
                "digest": "2" * 64,
            }
        ],
    )
    path = write_scorecard(tmp_path, document(boundary, stale, case(3), case(4)))

    # When: evaluation occurs on the 90-day boundary.
    result = report(tmp_path, path, as_of="2026-08-03T00:00:00Z")

    # Then: only the case timestamps count toward the fresh sample/rate policy.
    assert result.returncode == 0
    row = json.loads(result.stdout)["scorecards"][0]
    assert (row["fresh_samples"], row["stale_samples"], row["fresh_accepted"]) == (3, 1, 3)
    assert row["accepted_ratio"] == 1.0
    assert row["manual_promotion_eligible"] is True


def test_recency_rejects_one_second_past_the_ninety_day_boundary(
    tmp_path: Path,
) -> None:
    # Given: three samples just beyond the exact duration cutoff.
    path = write_scorecard(
        tmp_path,
        document(
            case(1, observed_at="2026-05-04T23:59:59Z"),
            case(2, observed_at="2026-05-04T23:59:59Z"),
            case(3, observed_at="2026-05-04T23:59:59Z"),
        ),
    )

    # When: the report is evaluated one second after the 90-day boundary.
    result = report(tmp_path, path, as_of="2026-08-03T00:00:00Z")

    # Then: no nearly-91-day sample can make the cohort eligible.
    row = json.loads(result.stdout)["scorecards"][0]
    assert row["fresh_samples"] == 0
    assert row["manual_promotion_eligible"] is False


def test_later_regression_still_blocks_fresh_cohort_confidence(tmp_path: Path) -> None:
    # Given: fresh accepted evidence with a linked later regression.
    regressed = case(
        1,
        later_outcomes=[
            {
                **identity(1),
                "status": "regressed",
                "observed_at": "2026-08-02T00:00:00Z",
                "merge_commit_revision": "f" * 39 + "1",
                "digest": "2" * 64,
            }
        ],
    )
    path = write_scorecard(tmp_path, document(regressed, case(2), case(3)))

    # When: a report evaluates the cohort.
    result = report(tmp_path, path)

    # Then: later negative evidence remains a confidence and eligibility blocker.
    row = json.loads(result.stdout)["scorecards"][0]
    assert row["later_regressions"] == 1
    assert row["manual_promotion_eligible"] is False
    assert row["confidence"] == "low"


def test_cost_requires_metered_identity_bound_receipt_and_non_metered_forbids_cost(
    tmp_path: Path,
) -> None:
    # Given: a metered receipt replay and a non-metered route carrying a cost.
    replay = case(1)
    replay["cost_receipt_digest"] = "0" * 64
    replay_path = write_scorecard(tmp_path, document(replay), name="replay.json")
    offline = case(2)
    for name in ("identity", "review", "verification", "ci", "merge"):
        value = offline[name]
        assert isinstance(value, dict)
        value.update(
            {
                "provider_lane_id": "local/offline",
                "provider_host": "local runtime",
                "billing_path": "local/offline",
                "model_id": "ollama/qwen-local",
                "cost_provider_id": None,
                "cost_model_id": None,
            }
        )
    identity = offline["identity"]
    assert isinstance(identity, dict)
    offline["cost_receipt_digest"] = cost_digest(identity, 1.5)
    offline_path = write_scorecard(tmp_path, document(offline), name="offline.json")

    # When: each signed document crosses the registry-backed boundary.
    replay_result = validate(tmp_path, replay_path)
    offline_result = validate(tmp_path, offline_path)

    # Then: neither can contribute cost-backed evidence.
    assert replay_result.returncode == offline_result.returncode == 1
    assert "cost" in replay_result.stdout.lower()
    assert "forbids cost" in offline_result.stdout.lower()
