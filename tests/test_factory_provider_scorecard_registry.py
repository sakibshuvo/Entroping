"""Provider-registry and cohort tests for provider scorecards."""
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
    json_object,
    report,
    update_case_identity,
    validate,
    write_scorecard,
)


@pytest.mark.parametrize(
    "updates",
    (
        {"provider_lane_id": "unknown/lane"},
        {"provider_host": "wrong host"},
        {"billing_path": "wrong billing"},
        {"model_id": "unknown-model", "cost_model_id": "deepseek/unknown-model"},
    ),
)
def test_unregistered_provider_tuple_cannot_validate(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    item = case(1)
    update_case_identity(item, **updates)
    result = validate(tmp_path, write_scorecard(tmp_path, document(item)))
    assert result.returncode == 1


def test_metered_cost_may_be_unknown_but_reservation_is_required(tmp_path: Path) -> None:
    unknown = case(1, cost_usd=None)
    missing_reservation = case(2, cost_usd=None)
    update_case_identity(missing_reservation, reservation_id=None)
    valid = validate(tmp_path, write_scorecard(tmp_path, document(unknown), name="unknown.json"))
    invalid = validate(
        tmp_path, write_scorecard(tmp_path, document(missing_reservation), name="reservation.json")
    )
    assert valid.returncode == 0
    assert invalid.returncode == 1
    assert "reservation" in invalid.stdout


def test_nonmetered_evidence_requires_null_reservation_cost_and_cost_identity(
    tmp_path: Path,
) -> None:
    item = case(1, cost_usd=None)
    update_case_identity(
        item,
        provider_lane_id="local/offline",
        provider_host="local runtime",
        billing_path="local/offline",
        model_id="ollama/qwen-local",
        cost_provider_id=None,
        cost_model_id=None,
        reservation_id=None,
    )
    valid = validate(tmp_path, write_scorecard(tmp_path, document(item), name="offline.json"))
    replay = case(2, cost_usd=None)
    update_case_identity(
        replay,
        provider_lane_id="local/offline",
        provider_host="local runtime",
        billing_path="local/offline",
        model_id="ollama/qwen-local",
        cost_provider_id=None,
        cost_model_id=None,
    )
    invalid = validate(
        tmp_path, write_scorecard(tmp_path, document(replay), name="reservation.json")
    )
    assert valid.returncode == 0
    assert invalid.returncode == 1
    assert "null reservation" in invalid.stdout


def test_registry_cost_provider_and_model_identity_must_match(tmp_path: Path) -> None:
    wrong_provider, wrong_model = case(1), case(2)
    update_case_identity(wrong_provider, cost_provider_id="other-provider")
    update_case_identity(wrong_model, cost_model_id="deepseek/deepseek-v4-flash")
    first = validate(
        tmp_path, write_scorecard(tmp_path, document(wrong_provider), name="provider.json")
    )
    second = validate(tmp_path, write_scorecard(tmp_path, document(wrong_model), name="model.json"))
    assert first.returncode == second.returncode == 1
    assert "cost identity" in first.stdout + second.stdout


def test_task_model_autonomy_and_verification_dimensions_form_distinct_cohorts(
    tmp_path: Path,
) -> None:
    task = case(1, task_type="review")
    model = case(2)
    update_case_identity(
        model, model_id="deepseek-v4-flash", cost_model_id="deepseek/deepseek-v4-flash"
    )
    autonomy = case(3)
    update_case_identity(autonomy, autonomy_tier="tier_b")
    verification = case(4, verification_lane="release-ci-architecture")
    result = report(
        tmp_path, write_scorecard(tmp_path, document(task, model, autonomy, verification))
    )
    assert result.returncode == 0
    payload = json_object(result.stdout)
    rows = payload["scorecards"]
    assert isinstance(rows, list) and len(rows) == 4
    assert (
        len(
            {
                (row["task_type"], row["model_id"], row["autonomy_tier"], row["verification_lane"])
                for row in rows
                if isinstance(row, dict)
            }
        )
        == 4
    )


def test_exact_model_rows_expose_model_version_drift(tmp_path: Path) -> None:
    pro, flash = case(1), case(2)
    update_case_identity(
        flash, model_id="deepseek-v4-flash", cost_model_id="deepseek/deepseek-v4-flash"
    )
    result = report(tmp_path, write_scorecard(tmp_path, document(pro, flash)))
    payload = json_object(result.stdout)
    rows = payload["scorecards"]
    assert isinstance(rows, list) and len(rows) == 2
    assert all(isinstance(row, dict) and row["model_drift_detected"] is True for row in rows)
    assert all(isinstance(row, dict) and len(row["distinct_models"]) == 2 for row in rows)
