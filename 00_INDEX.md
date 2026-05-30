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

- [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]] - what Entroping is and what v4.1 must do.
- [[docs/user/USER_GUIDE|USER_GUIDE]] - how a developer uses Entroping.
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

- [[docs/meta/ISSUE_TRACKING|ISSUE_TRACKING]] - GitHub issue tracking rules for bugs, features, and regressions.
- [[docs/meta/TEST_STRATEGY|TEST_STRATEGY]] - regression suite and test-pyramid policy.
- [[docs/meta/RELEASE_CHECKLIST|RELEASE_CHECKLIST]] - alpha release bar, required evidence, and known-not-built boundaries.
- [[docs/meta/AUTONOMOUS_DEVELOPMENT|AUTONOMOUS_DEVELOPMENT]] - Codex-first autonomous workflow and future OpenCode/oMLX plan.
- [[docs/meta/AGENT_CONTROL_PLANE|AGENT_CONTROL_PLANE]] - Codex-first multi-agent control plane for Codex, Claude Code, OpenCode, Gemini, NotebookLM, and local Qwen.
- [[docs/meta/KNOWLEDGE_BASE_WORKFLOW|KNOWLEDGE_BASE_WORKFLOW]] - Obsidian-first brain, source-promotion rules, and hallucination controls.
- [[docs/product/GROWTH_AND_MONETIZATION|GROWTH_AND_MONETIZATION]] - open-source credibility, hype loop, and open-core monetization path.

## Product History

- [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] - how the product idea evolved.
- [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]] - extracted requirements from source materials.
- [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]] - creator corrections and non-negotiables.
- [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]] - local-first/cloud-second model strategy.

## Reference Library

- [[docs/user/USER_FLOWS|USER_FLOWS]] - end-to-end workflows.
- [[docs/user/USE_CASES|USE_CASES]] - concrete scenarios.
- [[docs/meta/OBSIDIAN_START_HERE|OBSIDIAN_START_HERE]] - first-time Obsidian workflow for this vault.
- [[docs/meta/GLOSSARY|GLOSSARY]] - plain-language explanation of Entroping terms.
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

## Working Loop

When the product changes:

1. Update the affected canonical doc.
2. Add or update an ADR if the reason matters later.
3. Update [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]] for phase-level progress.
4. Update [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] with a short dated note when the product story changes.
5. Update `.context/changelog.md` for handoff continuity.
6. Update `AGENTS.md` if implementation rules changed.
