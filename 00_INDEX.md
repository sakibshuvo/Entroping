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
- [[docs/meta/CONTEXT_MANAGEMENT|CONTEXT_MANAGEMENT]] - how Codex, Obsidian, `.context`, and Graphify fit together.
- `AGENTS.md` - project-local Codex implementation rules.
- `.context/plan.md` - active implementation milestone and handoff context.

## Product Contract

- [[ROADMAP|ROADMAP]] - public roadmap, release sequence, and open-core boundary.
- [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]] - what Entroping is and what v4.1 must do.
- [[docs/user/USER_GUIDE|USER_GUIDE]] - how a developer uses Entroping.
- [[docs/user/DRIFT_BASELINE_WORKFLOW|DRIFT_BASELINE_WORKFLOW]] - reviewed candidate-to-baseline drift workflow.
- [[docs/product/MVP_PLAN|MVP_PLAN]] - implementation sequence.
- [[docs/product/MARKETING_NOTE|MARKETING_NOTE]] - positioning and go-to-market language.

## Technical Contract

- [[docs/technical/TDS|TDS]] - architecture, adapters, schemas, execution, and test strategy.
- [[docs/technical/FREEZE_MAP_PLAN|FREEZE_MAP_PLAN]] - Eye freeze/map boundaries, tests, and implementation issue set.
- [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]] - locked command surface.
- [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]] - executable governance schema.
- [[docs/architecture/ARCHITECTURE|ARCHITECTURE]] - implementation architecture overview.
- [[docs/architecture/DEVELOPMENT|DEVELOPMENT]] - local development and verification commands.
- [[docs/architecture/DIAGRAMS|DIAGRAMS]] - Mermaid and PlantUML diagrams.

## Work Management

- [[docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH|GOOD_FIRST_ISSUE_WALKTHROUGH]] - newcomer path from issue labels to validated PR.
- [[docs/meta/ISSUE_TRACKING|ISSUE_TRACKING]] - GitHub issue tracking rules for bugs, features, and regressions.
- [[docs/meta/OBSIDIAN_VS_GITHUB|OBSIDIAN_VS_GITHUB]] - practical guide for where ideas, bugs, roadmap, and context belong.
- [[docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE|OBSIDIAN_CONTEXT_ENGINE_GUIDE]] - how to use Obsidian as an agent-friendly context preservation engine.
- [[ROADMAP|ROADMAP]] - public milestones and near-term sequencing.
- [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] - documentation owners, roadmap-change gate, and PR declaration rules.
- [[docs/meta/TEST_STRATEGY|TEST_STRATEGY]] - regression suite and test-pyramid policy.
- [[docs/meta/RELEASE_CHECKLIST|RELEASE_CHECKLIST]] - alpha release bar, required evidence, and known-not-built boundaries.
- [[docs/meta/PYPI_RELEASE_RUNBOOK|PYPI_RELEASE_RUNBOOK]] - TestPyPI-first and PyPI Trusted Publishing plan.
- [[docs/meta/PUBLIC_DOCS_SITE_DECISION|PUBLIC_DOCS_SITE_DECISION]] - MkDocs Material public docs site decision and scaffold.
- [[docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT|ZERO_CONFIG_DEMO_ENTRYPOINT]] - why `scripts/demo.sh` is the v0.2 checkout demo entrypoint.
- [[docs/meta/DISTRIBUTION_RECOMMENDATION|DISTRIBUTION_RECOMMENDATION]] - uv, PyPI, Homebrew tap, and standalone binary sequencing.
- [[docs/meta/AUTONOMOUS_DEVELOPMENT|AUTONOMOUS_DEVELOPMENT]] - Codex-first autonomous workflow and future OpenCode/oMLX plan.
- [[docs/meta/AGENT_CONTROL_PLANE|AGENT_CONTROL_PLANE]] - Codex-first multi-agent control plane for Codex, Claude Code, OpenCode, Gemini, NotebookLM, and local Qwen.
- [[docs/meta/KNOWLEDGE_BASE_WORKFLOW|KNOWLEDGE_BASE_WORKFLOW]] - Obsidian-first brain, source-promotion rules, and hallucination controls.
- [[docs/product/GROWTH_AND_MONETIZATION|GROWTH_AND_MONETIZATION]] - open-source credibility, hype loop, and open-core monetization path.
- [[docs/assets/launch/README|Launch demo assets]] - two-minute terminal, report, and dependency-map proof kit.

## Product History

- [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] - how the product idea evolved.
- [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]] - extracted requirements from source materials.
- [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]] - creator corrections and non-negotiables.
- [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]] - local-first/cloud-second model strategy.

## Reference Library

- [[docs/user/USER_FLOWS|USER_FLOWS]] - end-to-end workflows.
- [[docs/user/USE_CASES|USE_CASES]] - concrete scenarios.
- [[docs/user/QANSTITUTION_FIRST_HOUR|QANSTITUTION_FIRST_HOUR]] - first-hour status, latency, and request-ID header policy guide.
- [[docs/user/DRIFT_BASELINE_WORKFLOW|DRIFT_BASELINE_WORKFLOW]] - safe drift baseline creation and update workflow.
- [[docs/user/AI_PROVIDER_SETUP|AI_PROVIDER_SETUP]] - LiteLLM, local Qwen/oMLX, cloud model, and no-provider CI setup.
- [[docs/user/GITHUB_ACTIONS_STARTER|GITHUB_ACTIONS_STARTER]] - copyable downstream GitHub Actions CI gate.
- [[docs/meta/OBSIDIAN_START_HERE|OBSIDIAN_START_HERE]] - first-time Obsidian workflow for this vault.
- [[docs/meta/GLOSSARY|GLOSSARY]] - plain-language explanation of Entroping terms.
- [[docs/technical/THREAT_MODEL|THREAT_MODEL]] - stable-core security boundaries, residual risks, and remediation issue map.
- [[docs/technical/CLI_COMPATIBILITY_AUDIT|CLI_COMPATIBILITY_AUDIT]] - locked alpha command, exit-code, and report-artifact compatibility audit.
- [[docs/technical/CODEX_PROMPT|CODEX_PROMPT]] - historical implementation-agent prompt; `AGENTS.md` is current.
- [[examples/checkout-api/README|Checkout API demo fixture]] - minimal example for first-time users.
- [[sources/SOURCE_MAP]] - where the source materials live.

## Decision Trail

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

## Working Loop

When the product changes:

1. Update the affected canonical doc.
2. Add or update an ADR if the reason matters later.
3. Update [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]] for phase-level progress.
4. Update [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] with a short dated note when the product story changes.
5. Update `.context/changelog.md` for handoff continuity.
6. Update `AGENTS.md` if implementation rules changed.
