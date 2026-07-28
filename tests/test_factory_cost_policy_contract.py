from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"


def _example() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8")),
    )


def _run_policy(tmp_path: Path, policy: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    policy_path = tmp_path / "factory-cost-policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return _run_path(policy_path)


def _run_path(
    policy_path: Path,
    *,
    as_of: str = "2026-07-15T00:00:00Z",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_cost_policy",
            "validate",
            "--policy",
            str(policy_path),
            "--as-of",
            as_of,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_example_exposes_approved_budget_and_failure_controls() -> None:
    policy = _example()

    assert policy["policy_revision"] == 1
    assert policy["currency"] == "USD"
    assert policy["monetary_unit"] == "microcent"
    assert policy["unknown_cost_behavior"] == "deny_paid_dispatch"
    assert policy["unknown_quota_behavior"] == "deny_affected_paid_lane"
    assert policy["cash"] == {
        "calendar_month_timezone": "UTC",
        "calendar_month_cap_microcents": 20_000_000_000,
        "emergency_reserve_microcents": 2_000_000_000,
        "thresholds": {
            "stop_experiments_basis_points": 8_000,
            "subscription_only_basis_points": 9_000,
            "stop_paid_dispatch_basis_points": 10_000,
        },
    }
    assert policy["subscriptions"][0]["renewal"]["timezone"] == "UTC"
    assert policy["automatic_top_up"] == {"mode": "disabled"}
    windows = [quota["window"] for quota in policy["provider_quotas"]]
    assert windows == [
        {"kind": "rolling", "duration_seconds": 18_000},
        {"kind": "rolling", "duration_seconds": 604_800},
        {"kind": "calendar_month", "timezone": "UTC"},
    ]


def test_policy_rejects_automatic_top_up_for_automated_lanes(tmp_path: Path) -> None:
    policy = _example()
    policy["automatic_top_up"] = {
        "mode": "capped",
        "max_calendar_month_microcents": 100_000_000,
    }

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "disabled" in result.stderr


def test_policy_rejects_zero_subscription_charge(tmp_path: Path) -> None:
    policy = _example()
    policy["subscriptions"][0]["charge_microcents"] = 0

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "greater than 0" in result.stderr


def test_policy_rejects_naive_validity_timestamp(tmp_path: Path) -> None:
    policy = _example()
    policy["valid_from"] = "2026-07-01T00:00:00"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "timezone" in result.stderr


def test_subscription_cycle_quota_requires_known_matching_subscription(
    tmp_path: Path,
) -> None:
    policy = _example()
    policy["provider_quotas"][2]["window"] = {
        "kind": "subscription_cycle",
        "subscription_id": "missing-subscription",
    }

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "unknown subscription" in result.stderr


def test_policy_rejects_boolean_money_values(tmp_path: Path) -> None:
    policy = _example()
    policy["cash"]["calendar_month_cap_microcents"] = True

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "valid integer" in result.stderr


def test_policy_rejects_unsupported_currency(tmp_path: Path) -> None:
    policy = _example()
    policy["currency"] = "CAD"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "USD" in result.stderr


def test_policy_rejects_non_utc_cash_boundary(tmp_path: Path) -> None:
    policy = _example()
    policy["cash"]["calendar_month_timezone"] = "America/Toronto"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "UTC" in result.stderr


def test_policy_rejects_reserve_exposed_before_subscription_only_threshold(
    tmp_path: Path,
) -> None:
    policy = _example()
    policy["cash"]["emergency_reserve_microcents"] = 3_000_000_000

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "subscription-only threshold must preserve the reserve" in result.stderr


def test_policy_rejects_reversed_price_window(tmp_path: Path) -> None:
    policy = _example()
    policy["price_snapshots"][0]["observed_at"] = "2026-08-01T00:00:00Z"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "must precede" in result.stderr


def test_policy_rejects_signed_64_bit_overflow(tmp_path: Path) -> None:
    policy = _example()
    policy["policy_revision"] = 2**63

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "signed 64-bit boundary" in result.stderr


def test_policy_reader_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    policy_path = tmp_path / "factory-cost-policy.json"
    policy_path.symlink_to(target)

    result = _run_path(policy_path)

    assert result.returncode == 2
    assert "symlinked path component" in result.stderr


def test_policy_reader_rejects_invalid_utf8(tmp_path: Path) -> None:
    policy_path = tmp_path / "factory-cost-policy.json"
    policy_path.write_bytes(b"\xff\xfe")

    result = _run_path(policy_path)

    assert result.returncode == 2
    assert "valid UTF-8" in result.stderr


def test_policy_rejects_duplicate_quota_references(tmp_path: Path) -> None:
    policy = _example()
    policy["automation_lanes"][0]["quota_ids"].append("example-five-hour-quota")

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "duplicate quota reference" in result.stderr


def test_metered_lane_accepts_canonical_provider_model_identifier(
    tmp_path: Path,
) -> None:
    policy = _example()
    policy["price_snapshots"][0]["provider_id"] = "openai"
    policy["price_snapshots"][0]["model_id"] = "openai/gpt-4.1-mini"
    policy["automation_lanes"][1]["provider_id"] = "openai"
    policy["automation_lanes"][1]["model_id"] = "openai/gpt-4.1-mini"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 0, result.stderr


def test_metered_lane_rejects_price_for_a_different_model(tmp_path: Path) -> None:
    policy = _example()
    policy["price_snapshots"][0]["provider_id"] = "openai"
    policy["price_snapshots"][0]["model_id"] = "openai/gpt-4.1"
    policy["automation_lanes"][1]["provider_id"] = "openai"
    policy["automation_lanes"][1]["model_id"] = "openai/gpt-4.1-mini"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "price model does not match" in result.stderr


def test_metered_lane_rejects_model_with_a_different_provider(tmp_path: Path) -> None:
    policy = _example()
    policy["automation_lanes"][1]["model_id"] = "openai/gpt-4.1-mini"

    result = _run_policy(tmp_path, policy)

    assert result.returncode == 2
    assert "model provider does not match" in result.stderr


def test_invalid_as_of_does_not_echo_attacker_input(tmp_path: Path) -> None:
    policy_path = tmp_path / "factory-cost-policy.json"
    policy_path.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    attacker_input = "sk-example-secret-value"

    result = _run_path(policy_path, as_of=attacker_input)

    assert result.returncode == 2
    assert "must use ISO 8601" in result.stderr
    assert attacker_input not in result.stderr
