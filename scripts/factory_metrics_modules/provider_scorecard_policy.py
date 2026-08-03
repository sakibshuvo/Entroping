"""Pure classification and cohort policy for provider scorecards."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from .provider_scorecard_primitives import (
    AutonomyTier,
    Identifier,
    TaskType,
    VerificationLane,
)
from .provider_scorecard_report_schema import ProviderScorecardRow
from .provider_scorecard_schema import ProviderScorecardCase

Classification = Literal["accepted", "rejected", "inconclusive"]
Confidence = Literal["insufficient", "low", "medium", "high"]
ScorecardKey = tuple[TaskType, Identifier, Identifier, AutonomyTier, VerificationLane]
MINIMUM_ACCEPTED_SAMPLES = 3
RECENCY_WINDOW_DAYS = 90


def scorecard_entry(
    key: ScorecardKey,
    cases: tuple[ProviderScorecardCase, ...],
    distinct_models: tuple[str, ...],
    as_of: datetime,
) -> ProviderScorecardRow:
    """Project one policy cohort without exposing evidence values."""

    task_type, provider_lane_id, model_id, autonomy_tier, verification_lane = key
    classifications = tuple(classify_case(case) for case in cases)
    fresh = tuple(case for case in cases if is_fresh(case, as_of))
    fresh_classifications = tuple(classify_case(case) for case in fresh)
    accepted, rejected, inconclusive = (
        classifications.count("accepted"),
        classifications.count("rejected"),
        classifications.count("inconclusive"),
    )
    fresh_accepted, fresh_rejected, fresh_inconclusive = (
        fresh_classifications.count("accepted"),
        fresh_classifications.count("rejected"),
        fresh_classifications.count("inconclusive"),
    )
    latest = max(case.observed_at for case in cases)
    regressions = sum(
        outcome.status == "regressed" for case in cases for outcome in case.later_outcomes
    )
    reverts = sum(outcome.status == "reverted" for case in cases for outcome in case.later_outcomes)
    later_inconclusive = sum(
        outcome.status == "inconclusive" for case in cases for outcome in case.later_outcomes
    )
    quality_failures = sum(
        case.verification is not None and case.verification.quality == "fail" for case in cases
    )
    security_failures = sum(
        case.verification is not None and case.verification.security == "fail" for case in cases
    )
    known_costs = tuple(case.cost_usd for case in cases if case.cost_usd is not None)
    complete = all(
        case.verification is not None
        and case.verification.quality != "inconclusive"
        and case.verification.security != "inconclusive"
        for case in cases
    )
    ratio = fresh_accepted / len(fresh) if fresh else 0.0
    eligible = (
        fresh_accepted >= MINIMUM_ACCEPTED_SAMPLES
        and bool(fresh)
        and regressions == reverts == later_inconclusive == 0
        and quality_failures == security_failures == 0
        and complete
        and fresh_inconclusive == 0
        and ratio >= 0.80
    )
    return ProviderScorecardRow(
        task_type=task_type,
        provider_lane_id=provider_lane_id,
        model_id=model_id,
        autonomy_tier=autonomy_tier,
        verification_lane=verification_lane,
        sample_size=len(cases),
        fresh_samples=len(fresh),
        stale_samples=len(cases) - len(fresh),
        fresh_accepted=fresh_accepted,
        fresh_rejected=fresh_rejected,
        fresh_inconclusive=fresh_inconclusive,
        accepted=accepted,
        rejected=rejected,
        inconclusive=inconclusive,
        latest_case_observed_at=timestamp(latest),
        age_days=max(0, (as_of.astimezone(UTC) - latest.astimezone(UTC)).days),
        stale=not fresh,
        distinct_models=distinct_models,
        model_drift_detected=len(distinct_models) > 1,
        later_regressions=regressions,
        later_reverts=reverts,
        later_inconclusive=later_inconclusive,
        quality_failures=quality_failures,
        security_failures=security_failures,
        known_cost_samples=len(known_costs),
        unknown_cost_samples=len(cases) - len(known_costs),
        average_cost_usd=sum(known_costs) / len(known_costs) if known_costs else None,
        accepted_ratio=ratio,
        complete_quality_security_receipts=complete,
        manual_promotion_eligible=eligible,
        manual_promotion_required=True,
        automatic_promotion_allowed=False,
        tier_c_automatic_promotion_allowed=False,
        confidence=confidence(
            fresh_accepted, eligible, not fresh, not complete or inconclusive > 0
        ),
    )


def classify_case(case: ProviderScorecardCase) -> Classification:
    """Classify terminal evidence without treating missing evidence as success."""

    review, verification, ci, merge = case.review, case.verification, case.ci, case.merge
    negative = (
        (review is not None and review.decision == "rejected")
        or (
            verification is not None
            and (verification.quality == "fail" or verification.security == "fail")
        )
        or (ci is not None and ci.status == "failure")
        or (merge is not None and merge.status == "not_merged")
    )
    if negative:
        return "rejected"
    accepted = (
        review is not None
        and review.decision == "accepted"
        and verification is not None
        and verification.quality == verification.security == "pass"
        and ci is not None
        and ci.status == "success"
        and merge is not None
        and merge.status == "merged"
    )
    return "accepted" if accepted else "inconclusive"


def is_fresh(case: ProviderScorecardCase, as_of: datetime) -> bool:
    """Return whether case observation is inside the inclusive 90-day window."""

    elapsed = as_of.astimezone(UTC) - case.observed_at.astimezone(UTC)
    return timedelta(0) <= elapsed <= timedelta(days=RECENCY_WINDOW_DAYS)


def latest_observation(case: ProviderScorecardCase) -> datetime:
    """Return the latest linked observation for chronology checks."""

    return max(
        (case.observed_at, *(outcome.observed_at for outcome in case.later_outcomes))
    ).astimezone(UTC)


def timestamp(value: datetime) -> str:
    """Render a normalized deterministic UTC timestamp."""

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def confidence(accepted: int, eligible: bool, stale: bool, incomplete: bool) -> Confidence:
    """Return the conservative cohort confidence label."""

    if accepted < MINIMUM_ACCEPTED_SAMPLES:
        return "insufficient"
    if not eligible or stale or incomplete:
        return "low"
    return "high" if accepted >= 5 else "medium"
