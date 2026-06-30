"""Factory readiness schema constants."""

from __future__ import annotations

READINESS_GATES = (
    "quality",
    "security",
    "context_preservation",
    "token_cost_efficiency",
)

READINESS_MISSING_MESSAGES = {
    "quality": (
        "quality evidence requires a successful test, quality check, or gate-run "
        "event for the issue"
    ),
    "security": (
        "security evidence requires a successful security gate/review event or "
        "explicit security:not-applicable marker"
    ),
    "context_preservation": (
        "context preservation evidence requires a successful context_pack event "
        "with bounded context bytes, estimated tokens, and file counts"
    ),
    "token_cost_efficiency": (
        "token/cost evidence requires provider/model plus token or cost metrics, "
        "cost metrics, or an explicit provider:not-applicable/no-provider marker"
    ),
}

QUALITY_MARKERS = (
    "pytest",
    "test",
    "tests",
    "ruff",
    "coverage",
    "quality",
    "feature_gate",
    "feature-gate",
    "feature gate",
    "scripts/check.sh",
    "scripts/feature_gate.sh",
    "doc_governance_check",
)

SECURITY_MARKERS = (
    "security",
    "security:not-applicable",
    "vulnerab",
    "license policy",
    "no known vulnerabilities",
    "scripts/regression.sh --security",
    "scripts/feature_gate.sh --security",
)

NO_PROVIDER_MARKERS = (
    "provider:not-applicable",
    "no-provider",
    "no provider",
    "llm-free",
    "llm free",
)
