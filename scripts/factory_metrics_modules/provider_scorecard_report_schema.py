"""Strict frozen value-free provider-scorecard report models."""

from __future__ import annotations

from typing import Literal

from .provider_scorecard_primitives import (
    AutonomyTier,
    CostUsd,
    Identifier,
    StrictScorecardModel,
    TaskType,
    VerificationLane,
)


class ProviderScorecardPolicy(StrictScorecardModel):
    """Frozen policy constants included in every deterministic report."""

    minimum_accepted_samples: Literal[3]
    recency_window_days: Literal[90]
    manual_promotion_required: Literal[True]
    automatic_promotion_allowed: Literal[False]
    tier_c_automatic_promotion_allowed: Literal[False]


class ProviderScorecardRow(StrictScorecardModel):
    """A value-free, one-cohort provider-scorecard projection."""

    task_type: TaskType
    provider_lane_id: Identifier
    model_id: Identifier
    autonomy_tier: AutonomyTier
    verification_lane: VerificationLane
    sample_size: int
    fresh_samples: int
    stale_samples: int
    fresh_accepted: int
    fresh_rejected: int
    fresh_inconclusive: int
    accepted: int
    rejected: int
    inconclusive: int
    latest_case_observed_at: str
    age_days: int
    stale: bool
    distinct_models: tuple[Identifier, ...]
    model_drift_detected: bool
    later_regressions: int
    later_reverts: int
    later_inconclusive: int
    quality_failures: int
    security_failures: int
    known_cost_samples: int
    unknown_cost_samples: int
    average_cost_usd: CostUsd | None
    accepted_ratio: float
    complete_quality_security_receipts: bool
    manual_promotion_eligible: bool
    manual_promotion_required: Literal[True]
    automatic_promotion_allowed: Literal[False]
    tier_c_automatic_promotion_allowed: Literal[False]
    confidence: Literal["insufficient", "low", "medium", "high"]


class ProviderScorecardReport(StrictScorecardModel):
    """Strict frozen report envelope for provider-scorecard output."""

    schema_version: Literal["entroping.provider-scorecard-report.v1"]
    as_of: str
    policy: ProviderScorecardPolicy
    scorecards: tuple[ProviderScorecardRow, ...]
