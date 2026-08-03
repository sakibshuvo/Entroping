from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from scripts.factory_cost_policy_io import read_policy_document
from scripts.factory_cost_policy_models import FactoryCostPolicy
from scripts.factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at

from .factory_status_filesystem import FactoryStatusError, exists_lstat, fingerprint_file

type Fingerprints = list[tuple[str, int, int, int]]


def policy_safety_reason(
    root: Path, observed_at: datetime, fingerprints: Fingerprints
) -> str | None:
    """Classify absent optional policy separately from invalid policy authority."""

    path = root / ".entroping" / "factory-cost-policy.json"
    if not exists_lstat(path):
        path = root / "docs" / "meta" / "factory-cost-policy.example.json"
    try:
        fingerprint_file(root, path, fingerprints)
        policy = FactoryCostPolicy.model_validate_json(read_policy_document(path), strict=True)
        validate_policy_at(policy, observed_at)
    except FileNotFoundError:
        return "budget-policy-unavailable"
    except (FactoryCostPolicyError, FactoryStatusError, ValidationError, OSError, ValueError):
        return "budget-policy-unsafe"
    return None


def cash_threshold_reason(
    root: Path,
    observed_at: datetime,
    policy_id: str,
    policy_revision: int,
    cash_cap: int,
    spent: int,
    held: int,
    fingerprints: Fingerprints,
) -> str | None:
    """Return the configured cash-threshold reason without exposing policy values."""

    safety = policy_safety_reason(root, observed_at, fingerprints)
    if safety is not None:
        return safety
    path = root / ".entroping" / "factory-cost-policy.json"
    if not exists_lstat(path):
        path = root / "docs" / "meta" / "factory-cost-policy.example.json"
    try:
        fingerprint_file(root, path, fingerprints)
        policy = FactoryCostPolicy.model_validate_json(read_policy_document(path), strict=True)
        validate_policy_at(policy, observed_at)
    except (FactoryCostPolicyError, FactoryStatusError, ValidationError, OSError, ValueError):
        return "budget-policy-unsafe"
    if (
        policy.policy_id != policy_id
        or policy.policy_revision != policy_revision
        or policy.cash.calendar_month_cap_microcents != cash_cap
        or spent < 0
        or held < 0
    ):
        return "budget-authority-uncertain"
    committed = spent + held
    thresholds = policy.cash.thresholds
    if committed * 10_000 >= cash_cap * thresholds.stop_paid_dispatch_basis_points:
        return "budget-stop-paid-dispatch"
    if committed * 10_000 >= cash_cap * thresholds.subscription_only_basis_points:
        return "budget-subscription-only"
    if committed * 10_000 >= cash_cap * thresholds.stop_experiments_basis_points:
        return "budget-threshold"
    return None
