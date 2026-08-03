from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import BudgetPeriodConfig, FactoryBudgetLedger  # noqa: E402


def status_policy(
    now: datetime,
    *,
    enabled: bool = True,
    quota_backed: bool = False,
    thresholds: tuple[int, int, int] = (8000, 9000, 10000),
) -> dict[str, object]:
    """Build one validated policy fixture for every status test surface."""

    stop_experiments, subscription_only, stop_paid_dispatch = thresholds
    return {
        "schema_version": "entroping.factory-cost-policy.v1",
        "policy_id": "status-policy",
        "policy_revision": 1,
        "currency": "USD",
        "monetary_unit": "microcent",
        "valid_from": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "unknown_cost_behavior": "deny_paid_dispatch",
        "unknown_quota_behavior": "deny_affected_paid_lane",
        "cash": {
            "calendar_month_timezone": "UTC",
            "calendar_month_cap_microcents": 10_000,
            "emergency_reserve_microcents": 1_000,
            "thresholds": {
                "stop_experiments_basis_points": stop_experiments,
                "subscription_only_basis_points": subscription_only,
                "stop_paid_dispatch_basis_points": stop_paid_dispatch,
            },
        },
        "subscriptions": [],
        "price_snapshots": []
        if quota_backed
        else [
            {
                "id": "deepseek-price",
                "provider_id": "deepseek",
                "model_id": "deepseek/deepseek-v4-pro",
                "unit": "input_token",
                "quantity": 1,
                "price_microcents": 1,
                "observed_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        "provider_quotas": [
            {
                "id": "deepseek-five-hour",
                "provider_id": "deepseek",
                "unit": "requests",
                "limit": 100,
                "window": {"kind": "rolling", "duration_seconds": 18_000},
            }
        ]
        if quota_backed
        else [],
        "automatic_top_up": {"mode": "disabled"},
        "automation_lanes": [
            {
                "id": "deepseek-included" if quota_backed else "deepseek-metered",
                "provider_id": "deepseek",
                "billing_mode": "included_quota" if quota_backed else "metered",
                "enabled": enabled,
                **(
                    {"quota_ids": ["deepseek-five-hour"]}
                    if quota_backed
                    else {
                        "model_id": "deepseek/deepseek-v4-pro",
                        "price_snapshot_ids": ["deepseek-price"],
                        "quota_ids": [],
                    }
                ),
            }
        ],
    }


def write_status_policy(
    root: Path,
    now: datetime,
    *,
    enabled: bool = True,
    quota_backed: bool = False,
    thresholds: tuple[int, int, int] = (8000, 9000, 10000),
) -> None:
    """Persist the shared trusted policy and provider registry fixture."""

    policy_dir = root / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    (policy_dir / "factory-cost-policy.example.json").write_text(
        json.dumps(
            status_policy(
                now,
                enabled=enabled,
                quota_backed=quota_backed,
                thresholds=thresholds,
            )
        ),
        encoding="utf-8",
    )
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )


def initialize_status_period(root: Path, now: datetime) -> FactoryBudgetLedger:
    """Create one ledger period matching the shared policy fixture."""

    ledger = FactoryBudgetLedger.open_project(root)
    _ = ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(now.year, now.month, 1),
            cash_cap_microcents=10_000,
            emergency_reserve_microcents=1_000,
            currency="USD",
            policy_id="status-policy",
            policy_revision=1,
            reserve_idempotency_key="status-period",
        )
    )
    return ledger
