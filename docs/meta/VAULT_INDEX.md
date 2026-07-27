---
title: Entroping Index
type: index
status: stable
tags:
  - entroping
  - start-here
  - product-evolution
---

# Entroping Index

Use this as the home note for the Entroping vault.

## Start Here Today

Use these first. They are the control panel for current work:

- [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]] - current alpha status, issue queue, and next slice.
- [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]] - required gate for every non-trivial change.
- [[docs/meta/CONTEXT_MANAGEMENT|CONTEXT_MANAGEMENT]] - repo-native context budget baseline, Obsidian/vault role, and optional context-tool boundaries.
- [[docs/meta/DECISION_REGISTRY.yaml|DECISION_REGISTRY]] - durable decision index with pointers back to ADRs, docs, issues, and source evidence.
- `AGENTS.md` - project-local Codex implementation rules.
- `.context/plan.md` - active implementation milestone and handoff context.

## Product Contract

- [[ROADMAP|ROADMAP]] - public roadmap, release sequence, and open-core boundary.
- [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]] - what Entroping is and what v4.1 must do.
- [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC#backend/api-integrity-position]] - API-first positioning, governance, and runtime integrity policy.
- [[docs/user/USER_GUIDE|USER_GUIDE]] - how a developer uses Entroping.
- [[docs/user/DRIFT_BASELINE_WORKFLOW|DRIFT_BASELINE_WORKFLOW]] - reviewed candidate-to-baseline drift workflow.
- [[docs/product/MVP_PLAN|MVP_PLAN]] - implementation sequence.
- [[docs/product/MARKETING_NOTE|MARKETING_NOTE]] - positioning and go-to-market language.
- [[docs/product/OPEN_CORE_BOUNDARIES|OPEN_CORE_BOUNDARIES]] - what stays in the Apache core and what can become commercial.

## Technical Contract

- [[docs/technical/TDS|TDS]] - architecture, adapters, schemas, execution, and test strategy.
- [[docs/technical/FREEZE_MAP_PLAN|FREEZE_MAP_PLAN]] - Eye freeze/map boundaries, tests, and implementation issue set.
- [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]] - locked command surface.
- [[docs/technical/COMMAND_CHEAT_SHEET#evidence-packet-picker-by-surface|COMMAND_CHEAT_SHEET#evidence-packet-picker]] - packet picker table for review surfaces.
- [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]] - executable governance schema.
- [[docs/technical/POLICY_PACK_LAYOUT|POLICY_PACK_LAYOUT]] - reusable QAnstitution policy-pack layout and example.
- [[docs/technical/POLICY_PACK_DISTRIBUTION|POLICY_PACK_DISTRIBUTION]] - local-first policy-pack distribution, provenance, attribution, and open-core boundary.
- [[docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN|STUDIO_MUTATION_WORKFLOW_DESIGN]] - design gate for any future Studio write action.
- [[docs/technical/REPORT_SCHEMAS|REPORT_SCHEMAS]] - versioned JSON report contracts and compatibility policy.
- [[docs/architecture/ARCHITECTURE|ARCHITECTURE]] - implementation architecture overview.
- [[docs/architecture/DEVELOPMENT|DEVELOPMENT]] - local development and verification commands.
- [[docs/architecture/DIAGRAMS|DIAGRAMS]] - Mermaid and PlantUML diagrams.

## Work Management

- [[docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH|GOOD_FIRST_ISSUE_WALKTHROUGH]] - newcomer path from issue labels to validated PR.
- [[docs/meta/ISSUE_TRACKING|ISSUE_TRACKING]] - GitHub issue tracking rules for bugs, features, and regressions.
- [[docs/meta/OBSIDIAN_VS_GITHUB|OBSIDIAN_VS_GITHUB]] - practical guide for where ideas, bugs, roadmap, and context belong.
- [[docs/meta/prompt-library/README|PROMPT_LIBRARY]] - reusable Codex, Spark, Gemini, DeepSeek, OpenCode, multi-agent, review, triage, CI, launch, and status prompts.
- [[docs/meta/AGENT_ROLE_REGISTRY.yaml|AGENT_ROLE_REGISTRY]] - machine-readable portable role registry for agent missions, authority limits, context modes, and metrics tags.
- [[docs/meta/archive/OBSIDIAN_CONTEXT_ENGINE_GUIDE|OBSIDIAN_CONTEXT_ENGINE_GUIDE (archived)]] - historical context-engine strategy retained for traceability.
- [[docs/meta/DECISION_REGISTRY.yaml|DECISION_REGISTRY]] - fast lookup layer for accepted decisions; summaries do not replace linked source material.
- [[docs/meta/ENTROPING_PRODUCT_MAP.canvas|ENTROPING_PRODUCT_MAP]] - visual product/context map for the vault.
- [[docs/meta/ENTROPING_DOCS.base|ENTROPING_DOCS]] - table views over canonical docs, decisions, workflows, and examples.
- [[ROADMAP|ROADMAP]] - public milestones and near-term sequencing.
- [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] - documentation owners, roadmap-change gate, and PR declaration rules.
- [[docs/meta/TEST_STRATEGY|TEST_STRATEGY]] - regression suite and test-pyramid policy.
- [[docs/meta/RELEASE_CHECKLIST|RELEASE_CHECKLIST]] - alpha release bar, required evidence, and known-not-built boundaries.
- [[docs/meta/RELEASE_EVIDENCE|RELEASE_EVIDENCE]] - committed alpha release, main CI, package-index, and stable-core blocker evidence.
- `docs/meta/dependency-license-policy.json` - reviewed direct dependency license policy used by the security gate.
- [[docs/meta/PYPI_RELEASE_RUNBOOK|PYPI_RELEASE_RUNBOOK]] - TestPyPI-first and PyPI Trusted Publishing plan.
- [[docs/meta/PUBLIC_DOCS_SITE_DECISION|PUBLIC_DOCS_SITE_DECISION]] - Astro and Starlight public launch/docs decision, including the superseded MkDocs history.
- [[docs/meta/PUBLIC_REPO_SURFACE|PUBLIC_REPO_SURFACE]] - what belongs in the public clone, maintainer context, and local-only Obsidian state.
- [[docs/meta/INSTALL_SMOKE_MATRIX|INSTALL_SMOKE_MATRIX]] - Linux, macOS, and Windows install-smoke claims and non-claims.
- [[docs/meta/DOWNSTREAM_SMOKE_EVIDENCE|DOWNSTREAM_SMOKE_EVIDENCE]] - local external-project smoke evidence and its stable-core limits.
- [[docs/meta/DOWNSTREAM_FEEDBACK_KIT|DOWNSTREAM_FEEDBACK_KIT]] - sanitized real downstream user feedback template for stable-core evidence.
- [[docs/meta/DISTRIBUTION_RECOMMENDATION|DISTRIBUTION_RECOMMENDATION]] - uv, PyPI, Homebrew tap, and standalone binary sequencing.
- [[docs/meta/archive/AUTONOMOUS_DEVELOPMENT|AUTONOMOUS_DEVELOPMENT (archived)]] - historical Codex-first workflow and future OpenCode/oMLX plan.
- [[docs/meta/AGENT_CONTROL_PLANE|AGENT_CONTROL_PLANE]] - Codex-first multi-agent control plane for Codex, Claude Code, OpenCode, Gemini, NotebookLM, and local Qwen.
- [[docs/meta/FACTORY_OPERATIONS|FACTORY_OPERATIONS]] - Entroping factory scheduler runbook and launchd operations.
- [[docs/meta/prompt-library/README|PROMPT_LIBRARY]] - copy-paste prompt shelf for fresh sessions, issue workers, Spark-safe work, external reviews, bug bashes, launch audits, merge gates, and thread steering.
- [[docs/meta/KNOWLEDGE_BASE_WORKFLOW|KNOWLEDGE_BASE_WORKFLOW]] - Obsidian-first brain, source-promotion rules, and hallucination controls.
- [[docs/product/GROWTH_AND_MONETIZATION|GROWTH_AND_MONETIZATION]] - open-source credibility, hype loop, and open-core monetization path.
- [[docs/assets/launch/README|Launch demo assets]] - two-minute GIF, terminal, report, and dependency-map proof kit.

## Product History

These notes are historical source evidence, not current product truth. Use them
to recover why Entroping changed; use `PRODUCT_SPEC`, `TDS`, `ROADMAP.md`, ADRs,
and current user docs for today's behavior and promises.

- [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] - how the product idea evolved.
- [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]] - extracted requirements from source materials.
- [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]] - creator corrections and non-negotiables.
- [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]] - local-first/cloud-second model strategy.

## Archived Decision Notes

These completed one-off notes are retained for traceability, not active
instructions.

- [[docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT|ZERO_CONFIG_DEMO_ENTRYPOINT]] - active demo-entrypoint decision approving `entroping demo --project <path>` for package-installed Aha implementation while preserving `scripts/demo.sh`.
- [[docs/meta/archive/AUTONOMOUS_DEVELOPMENT|AUTONOMOUS_DEVELOPMENT]] - archived historical autonomous-dev operating plan.
- [[docs/meta/archive/OBSIDIAN_CONTEXT_ENGINE_GUIDE|OBSIDIAN_CONTEXT_ENGINE_GUIDE]] - archived Obsidian context-engine strategy.

## Reference Library

- [[docs/user/USER_FLOWS|USER_FLOWS]] - end-to-end workflows.
- [[docs/user/USE_CASES|USE_CASES]] - concrete scenarios.
- [[docs/user/QANSTITUTION_FIRST_HOUR|QANSTITUTION_FIRST_HOUR]] - first-hour status, latency, and request-ID header policy guide.
- [[docs/user/DRIFT_BASELINE_WORKFLOW|DRIFT_BASELINE_WORKFLOW]] - safe drift baseline creation and update workflow.
- [[docs/user/AI_PROVIDER_SETUP|AI_PROVIDER_SETUP]] - LiteLLM, local Qwen/oMLX, cloud model, and no-provider CI setup.
- [[docs/user/USER_GUIDE#evidence-packet-picker|USER_GUIDE - evidence packet picker]] - packet chooser map for launch/stable/experimental surfaces.
- [[docs/user/GITHUB_ACTIONS_STARTER|GITHUB_ACTIONS_STARTER]] - copyable downstream GitHub Actions CI gate.
- [[docs/user/CI_PROVIDER_RECIPES|CI_PROVIDER_RECIPES]] - GitLab CI, Buildkite, CircleCI, and generic shell guidance.
- [[docs/meta/OBSIDIAN_START_HERE|OBSIDIAN_START_HERE]] - first-time Obsidian workflow for this vault.
- [[docs/meta/GLOSSARY|GLOSSARY]] - plain-language explanation of Entroping terms.
- [[docs/technical/THREAT_MODEL|THREAT_MODEL]] - stable-core security boundaries, residual risks, and remediation issue map.
- [[docs/technical/THREAT_MODEL|THREAT_MODEL#local-first-traffic-and-evidence-export-faq]] - local state paths, redaction boundaries, upload behavior, and evidence sharing guidance.
- [[docs/technical/CLI_COMPATIBILITY_AUDIT|CLI_COMPATIBILITY_AUDIT]] - locked alpha command, exit-code, and report-artifact compatibility audit.
- [[docs/technical/PYTHON_COMPATIBILITY|PYTHON_COMPATIBILITY]] - CI-proven Python runtime support policy.
- [[docs/technical/REPORT_SCHEMAS|REPORT_SCHEMAS]] - run, diagnostics, drift, effective-policy, and traceability schema versions.
- [[docs/technical/CODEX_PROMPT|CODEX_PROMPT]] - historical implementation-agent prompt; `AGENTS.md` is current.
- [[examples/checkout-api/README|Checkout API demo fixture]] - minimal example for first-time users.
- [[examples/support-api/README|Support API demo fixture]] - second fixture with ticket filters, request headers, and mutation audit gates.
- [[examples/graphql-api/README|GraphQL API demo fixture]] - Hurl-over-HTTP GraphQL example with top-level `errors` governance.
- [[examples/soap-api/README|SOAP API demo fixture]] - Hurl-over-HTTP SOAP example with XML envelope assertions.
- [[examples/ai-regression-demo/README|AI regression demo fixture]] - failure proof for missing `X-Request-Id` governance.
- [[examples/policy-packs/api-baseline/README|API baseline policy pack]] - minimal reusable QAnstitution pack shape.
- [[examples/policy-packs/owasp-api-top-10/README|OWASP API Top 10 starter pack]] - honest starter gates inspired by recognizable API security concerns.
- [[sources/SOURCE_MAP]] - where the source materials live.

## Decision Trail

- [[docs/meta/DECISION_REGISTRY.yaml|DECISION_REGISTRY]] - lossless decision-memory catalog across ADRs, docs, issues, and source evidence.
- [[decisions/ADR-0001-hurl-native-governance]]
- [[decisions/ADR-0002-locked-command-surface]]
- [[decisions/ADR-0003-local-first-brain]]
- [[decisions/ADR-0004-hurl-metadata-comments]]
- [[decisions/ADR-0005-deterministic-run-boundary]]
- [[decisions/ADR-0006-solo-first-mvp]]
- [[decisions/ADR-0007-external-business-truth]]
- [[decisions/ADR-0008-freeze-map-boundaries]]
- [[decisions/ADR-0009-apache-core-open-core-boundary]]
- [[decisions/ADR-0010-studio-cli-report-first-boundary]]
- [[decisions/ADR-0011-organization-qanstitution-import-controls|ADR-0011]]
- [[decisions/ADR-0012-brand-integrity-and-qanstitution-name|ADR-0012]]
- [[decisions/ADR-0016-ide-authoring-support-for-qanstitution|ADR-0016]]
- [[decisions/ADR-0017-official-github-action-boundary|ADR-0017]]
- [[decisions/ADR-0018-docker-ci-image-boundary|ADR-0018]]
- [[decisions/ADR-0021-core-flat-module-taxonomy|ADR-0021]]

## Working Loop

When the product changes:

1. Update the affected canonical doc.
2. Add or update an ADR if the reason matters later.
3. Update [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]] for phase-level progress.
4. Update [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] with a short dated note when the product story changes.
5. Update `.context/changelog.md` for handoff continuity.
6. Update `AGENTS.md` if implementation rules changed.
