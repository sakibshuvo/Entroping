from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"


def test_factory_cost_policy_validates_integer_cash_and_independent_quota_contract(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "factory-cost-policy.json"
    _ = policy_path.write_text(
        EXAMPLE_POLICY.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_cost_policy",
            "validate",
            "--policy",
            str(policy_path),
            "--as-of",
            "2026-07-15T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "schema_version": "entroping.factory-cost-policy.v1",
        "policy_id": "example-budget-policy",
        "currency": "USD",
        "calendar_month_cap_microcents": 20_000_000_000,
        "emergency_reserve_microcents": 2_000_000_000,
        "subscription_count": 1,
        "price_snapshot_count": 1,
        "provider_quota_count": 3,
        "automation_lane_count": 2,
    }
