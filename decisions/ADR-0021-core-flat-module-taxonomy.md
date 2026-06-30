---
title: ADR-0021 Core Flat Module Taxonomy
type: decision
status: accepted
date: 2026-06-29
tags:
  - decision
  - architecture
  - package-taxonomy
  - entroping-core
  - compatibility
---

# ADR-0021: Core Flat Module Taxonomy

## Decision

Entroping should keep existing deterministic runtime behavior unchanged for this
issue and use docs-only planning to stage the next migration wave from
`src/entroping/core` flat modules to explicit package families.

This ADR defines:

- the remaining substantive flat-module surface,
- which compatibility shims must remain flat for import stability,
- the Tier C runtime/safety surfaces that are not candidates for bulk migration
  without a dedicated issue, and
- three narrow follow-up issue proposals.

## Current Evidence

- `find src/entroping/core -maxdepth 1 -type f -name '*.py' | wc -l` -> `102`.
- Top-level core modules with >30 lines (the planned migration surface) -> `55`.
- Compatibility wrappers using `install_core_module_compat` -> `39` shim files remain
  intentionally flat.
- Existing compatibility packages already established in this codebase:
  `core.evidence`, `core.readiness`, `core.plan`, and `core.export`.

## Proposed Staged Packages (Planning-Only)

The grouping below is intentionally narrow and behavior-neutral for this issue.
Each module is listed once to make the migration surface explicit.

- **`core/runtime`**
  - `ci_readiness.py`
  - `coverage_badges.py`
  - `run_delta.py`
  - `run_event_log.py`
  - `run_option_validation.py`
  - `run_safety.py`
  - `run_suite_manifest.py`
  - `run_workflow.py`
  - `rerun_failures.py`
  - `tag_expression.py`
  - `git_changed_hurl.py`
  - `hurl_discovery.py`
  - `hurl_runner.py` (Tier C)
  - `hurl_validator.py`
  - `hurl_variable_preflight.py`
  - `gate_injector.py` (Tier C)

- **`core/reporting`**
  - `agent_manifest.py`
  - `capture_summary_report.py`
  - `evidence_common.py`
  - `evidence_packet_base.py`
  - `dependency_mapper.py`
  - `design_partner_feedback.py`
  - `drift_report.py`
  - `effective_policy_report.py`
  - `failure_bundle.py`
  - `freeze.py`
  - `gate_coverage_report.py`
  - `gate_injection_report.py`
  - `github_annotations.py`
  - `github_actions_starter.py`
  - `report_artifact_manifest.py`
  - `report_fingerprint.py`
  - `report_rendering.py`
  - `report_serialization.py`
  - `report_writer.py`
  - `redaction_review_report.py`
  - `review_summary.py`
  - `runtime_card.py`
  - `sarif_report.py`
  - `session_prompt.py`
  - `story_documents.py`
  - `structured_diagnostics.py`
  - `test_quality_report.py`

- **`core/config`**
  - `config_loader.py`
  - `config_writer.py`
  - `env_loader.py`
  - `openapi_loader.py`
  - `git_openapi.py`
  - `policy_pack_vendor.py`
  - `safe_write.py`

- **`core/traffic`**
  - `traffic_artifact_manifest.py`
  - `traffic_filters.py`
  - `traffic_proxy.py`
  - `traffic_redactor.py`
  - `traffic_store.py`

- **`core/safety-support`**
  - `bounded_read.py`
  - `path_safety.py`

## Compatibility Shims to Remain Flat

These modules must stay as compatibility entrypoints at `entroping.core` until the
next migration wave explicitly retires or re-homes each import path:

- `api_inventory.py`
- `agent_bundle.py`
- `connector_intent.py`
- `devex_readiness.py`
- `evidence_action_plan.py`
- `evidence_bundle.py`
- `evidence_cloud_dashboard.py`
- `evidence_cloud_export.py`
- `evidence_cloud_readiness.py`
- `evidence_cloud_workspace.py`
- `evidence_index.py`
- `evidence_index_report.py`
- `evidence_links.py`
- `evidence_portal.py`
- `external_test_evidence.py`
- `handoff_packet.py`
- `integration_readiness.py`
- `mutation_readiness.py`
- `notification_packet.py`
- `observability_adapter_readiness.py`
- `observability_packet.py`
- `otel_mapping.py`
- `pilot_cohort.py`
- `pilot_metrics.py`
- `pilot_outcome.py`
- `pr_evidence_card.py`
- `qa_brain_eval_plan.py`
- `qa_brain_fine_tune_readiness.py`
- `qa_brain_model_packaging_plan.py`
- `qa_brain_prompt_plan.py`
- `qa_brain_repair_plan.py`
- `qa_brain_retrieval_plan.py`
- `qa_brain_routing_plan.py`
- `qa_brain_seed.py`
- `team_access_control_plan.py`
- `team_evidence_readiness.py`
- `test_pyramid_report.py`
- `work_item_draft.py`
- `work_item_import_bundle.py`
- `_compat.py` (compatibility mechanism)

Flat modules that are intentionally stable API exports but not shim wrappers:

- `__init__.py` (exports `load_qanstitution`)
- `report_errors.py` (shared report exception model used by multiple new/existing
  families)

## Tier C Surfaces (Do Not Move Without Dedicated Issue)

For this issue and adjacent risk-reduction work, the following retain flat status:

1. `hurl_runner.py` (subprocess boundary + process/result semantics).
2. `run_workflow.py` (full run orchestration and lifecycle).
3. `gate_injector.py` (policy-to-Hurl assertion injection contract).
4. Redaction and traffic safety modules: `traffic_store.py`, `traffic_proxy.py`,
   `traffic_filters.py`, `traffic_redactor.py`, `run_safety.py`,
   `safe_write.py`, `path_safety.py`, `bounded_read.py`.

These remain part of a focused Tier C migration plan with an explicit dedicated
issue before any runtime behavior is moved.

## Follow-Up Issue Proposals (2–3 Narrow Slices)

1. **Issue X: Stage `core/reporting` package migration**
   - Move only report rendering/serialization modules plus local packet builders
     into a new `core/reporting/` package.
   - Preserve old import paths through existing shims.
   - Add/refresh architecture-boundary test coverage and changelog note.

2. **Issue Y: Stage `core/config` package migration**
   - Move config and policy-pack loading/writing modules (`config_loader`,
     `config_writer`, `env_loader`, `openapi_loader`, `git_openapi`) into
     `core/config/`.
   - Keep behavior unchanged and keep all old import surfaces temporarily.

3. **Issue Z: Stage `core/run` package migration (proof-point)**
   - Move a minimal deterministic subset (`tag_expression`, `run_option_validation`,
     `run_suite_manifest`, `hurl_discovery`) into `core/run/` first.
   - Defer `hurl_runner.py`, `run_workflow.py`, `gate_injector.py` to dedicated
     follow-up issues due Tier C status.

## Consequences

- No deterministic runtime behavior changes are performed by this ADR alone.
- Runtime import compatibility for legacy `entroping.core.<module>` paths remains
  mandatory for now.
- Subsequent migration issues should be issue-scoped and verify both behavior and
  import compatibility via existing architecture-boundary checks before merge.
