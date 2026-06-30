"""Context scorecard schema constants."""

from __future__ import annotations

CONTEXT_SCORECARD_REQUIRED_METRICS = (
    "grounded_file_hit_rate",
    "nonexistent_reference_count",
    "forbidden_scope_incidents",
    "retrieval_precision",
    "retrieval_recall",
    "stale_claim_count",
    "context_recovery_time_seconds",
    "review_correction_count",
    "human_steering_count",
    "accepted_output_ratio",
    "context_bytes",
    "estimated_tokens",
)

CONTEXT_SCORECARD_HIGHER_IS_BETTER = {
    "grounded_file_hit_rate",
    "retrieval_precision",
    "retrieval_recall",
    "accepted_output_ratio",
}

CONTEXT_SCORECARD_RATE_METRICS = {
    "grounded_file_hit_rate",
    "retrieval_precision",
    "retrieval_recall",
    "accepted_output_ratio",
}

CONTEXT_SCORECARD_INTEGER_METRICS = {
    "nonexistent_reference_count",
    "forbidden_scope_incidents",
    "stale_claim_count",
    "review_correction_count",
    "human_steering_count",
    "context_bytes",
    "estimated_tokens",
}

CONTEXT_SCORECARD_RECOMMENDATIONS = {
    "active",
    "optional_manual",
    "probation",
    "discard",
}

CONTEXT_SCORECARD_PROOF_STATUSES = {
    "measured",
    "not_measured",
    "baseline_component",
    "insufficient",
}

CONTEXT_SCORECARD_SETUP_STATUSES = {
    "available",
    "blocked",
    "failed",
    "installed",
    "missing",
    "not_applicable",
}

CONTEXT_SCORECARD_ALLOWED_SOURCE_TYPES = {
    "repo_source",
    "test",
    "github_issue",
    "github_pr",
    "ci_check",
    "decision_registry",
    "adr",
    "curated_markdown",
    "generated_graph",
    "generated_wiki",
    "generated_understand_anything",
    "factory_metrics",
}

CONTEXT_SCORECARD_FORBIDDEN_SOURCE_TYPES = {
    "obsidian_workspace_state",
    "obsidian_plugin_cache",
    "provider_transcript",
    "raw_prompt",
    "raw_traffic",
    "product_runtime_evidence",
}

CONTEXT_SCORECARD_REQUIRED_BASELINE_COMPONENTS = {
    "rg",
    "scripts/context_pack.sh",
    "docs/meta/DECISION_REGISTRY.yaml",
}

CONTEXT_SCORECARD_ALLOWED_KEYS = {
    "schema_version",
    "scorecard_id",
    "recorded_at",
    "baseline",
    "tool_evaluations",
}

CONTEXT_SCORECARD_BASELINE_KEYS = {"name", "components"}

CONTEXT_SCORECARD_EVALUATION_KEYS = {
    "tool",
    "tool_layer",
    "proof_status",
    "status_before",
    "recommended_status",
    "setup",
    "evidence_sources",
    "trials",
}

CONTEXT_SCORECARD_EVIDENCE_KEYS = {"source_type", "reference", "summary"}

CONTEXT_SCORECARD_SETUP_KEYS = {
    "status",
    "duration_seconds",
    "command",
    "failure_reason",
}

CONTEXT_SCORECARD_TRIAL_KEYS = {
    "issue",
    "packet_type",
    "workflow",
    "baseline_workflow",
    "metrics",
    "baseline_metrics",
    "evidence_summary",
}
