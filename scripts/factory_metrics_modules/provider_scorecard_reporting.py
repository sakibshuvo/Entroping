"""Classification and value-free projections for provider scorecards."""
# ruff: noqa: E501

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import cast

from scripts.provider_capability_registry import load_provider_registry, resolve_provider_evidence
from scripts.provider_capability_types import (
    ProviderCapabilityRegistry,
    ProviderEvidence,
    ProviderRegistryError,
)

from .common import contains_secret_like
from .errors import FactoryMetricsError
from .provider_scorecard_policy import (
    MINIMUM_ACCEPTED_SAMPLES,
    RECENCY_WINDOW_DAYS,
    ScorecardKey,
)
from .provider_scorecard_policy import (
    latest_observation as _case_latest_observation,
)
from .provider_scorecard_policy import (
    scorecard_entry as _scorecard_entry,
)
from .provider_scorecard_policy import (
    timestamp as _timestamp,
)
from .provider_scorecard_report_schema import (
    ProviderScorecardPolicy,
    ProviderScorecardReport,
)
from .provider_scorecard_schema import (
    PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION,
    ProviderScorecardCase,
    ProviderScorecardEvidence,
)


def validate_provider_scorecard(evidence: ProviderScorecardEvidence) -> None:
    """Verify each canonical provider tuple without interpreting legacy labels."""

    try:
        registry = load_provider_registry()
    except ProviderRegistryError:
        raise FactoryMetricsError("provider scorecard registry is unavailable") from None
    for case in evidence.cases:
        identity = case.identity
        try:
            resolve_provider_evidence(
                registry,
                ProviderEvidence(
                    lane_id=identity.provider_lane_id,
                    provider_host=identity.provider_host,
                    billing_path=identity.billing_path,
                    model_id=identity.model_id,
                    autonomy_tier=identity.autonomy_tier,
                ),
            )
            _validate_registry_cost_identity(registry, case)
        except ProviderRegistryError as exc:
            raise FactoryMetricsError(
                f"provider scorecard registry tuple is invalid ({exc.detail})"
            ) from None


def _validate_registry_cost_identity(
    registry: ProviderCapabilityRegistry, case: ProviderScorecardCase
) -> None:
    """Require the cost-policy identity derived by the canonical registry route."""

    lane = next(item for item in registry.lanes if item.id == case.identity.provider_lane_id)
    model = next((item for item in lane.models if item.id == case.identity.model_id), None)
    billing_kind = (
        model.billing_kind if model is not None and model.billing_kind else lane.billing_kind
    )
    if billing_kind == "metered":
        if case.identity.reservation_id is None:
            raise FactoryMetricsError(
                "provider scorecard metered evidence requires reservation identity"
            )
        if case.cost_usd is not None and case.cost_receipt_digest is None:
            raise FactoryMetricsError(
                "provider scorecard metered cost requires a bound cost receipt"
            )
        expected_provider = lane.cost_provider_id
        expected_model = model.cost_model_id if model is not None else None
        if (
            case.identity.cost_provider_id != expected_provider
            or case.identity.cost_model_id != expected_model
        ):
            raise FactoryMetricsError("provider scorecard cost identity does not match registry")
        return
    if case.cost_usd is not None:
        raise FactoryMetricsError("provider scorecard non-metered evidence forbids cost_usd")
    if case.identity.reservation_id is not None:
        raise FactoryMetricsError(
            "provider scorecard non-metered evidence requires null reservation"
        )
    if case.identity.cost_provider_id is not None or case.identity.cost_model_id is not None:
        raise FactoryMetricsError("provider scorecard non-metered cost identity must be null")


def provider_scorecard_report(
    evidence: ProviderScorecardEvidence, *, as_of: datetime
) -> ProviderScorecardReport:
    """Build a deterministic, value-free policy report from validated evidence."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise FactoryMetricsError("--as-of must include a timezone")
    latest_observation = max(
        (_case_latest_observation(case) for case in evidence.cases), default=None
    )
    if latest_observation is not None and as_of.astimezone(UTC) < latest_observation:
        raise FactoryMetricsError("--as-of must not predate provider scorecard observations")
    groups: defaultdict[ScorecardKey, list[ProviderScorecardCase]] = defaultdict(list)
    models_by_cohort: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for case in evidence.cases:
        key: ScorecardKey = (
            case.task_type,
            case.identity.provider_lane_id,
            case.identity.model_id,
            case.identity.autonomy_tier,
            case.verification_lane,
        )
        groups[key].append(case)
        models_by_cohort[(key[0], key[1], key[3], key[4])].add(case.identity.model_id)
    scorecards = tuple(
        _scorecard_entry(
            key,
            tuple(sorted(cases, key=lambda item: (item.observed_at, item.identity.job_id))),
            tuple(sorted(models_by_cohort[(key[0], key[1], key[3], key[4])])),
            as_of,
        )
        for key, cases in sorted(groups.items())
    )
    report = ProviderScorecardReport(
        schema_version=PROVIDER_SCORECARD_REPORT_SCHEMA_VERSION,
        as_of=_timestamp(as_of),
        policy=ProviderScorecardPolicy(
            minimum_accepted_samples=MINIMUM_ACCEPTED_SAMPLES,
            recency_window_days=RECENCY_WINDOW_DAYS,
            manual_promotion_required=True,
            automatic_promotion_allowed=False,
            tier_c_automatic_promotion_allowed=False,
        ),
        scorecards=scorecards,
    )
    _reject_secret_like_report(cast(dict[str, object], report.model_dump(mode="json")))
    return report


def _reject_secret_like_report(report: dict[str, object]) -> None:
    content = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if contains_secret_like(content):
        raise FactoryMetricsError("provider scorecard report contains secret-like content")
