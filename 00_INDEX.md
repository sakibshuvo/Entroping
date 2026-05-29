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

## Canonical Docs

- [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]] - what Entroping is and what v4.1 must do.
- [[docs/technical/TDS|TDS]] - architecture, adapters, schemas, execution, and test strategy.
- [[docs/user/USER_GUIDE|USER_GUIDE]] - how a developer uses Entroping.
- [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]] - locked command surface.
- [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]] - executable governance schema.
- [[docs/product/MVP_PLAN|MVP_PLAN]] - implementation sequence.
- [[docs/technical/CODEX_PROMPT|CODEX_PROMPT]] - implementation-agent guardrails.

## Evolution and Positioning

- [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] - how the product idea evolved.
- [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]] - extracted requirements from source materials.
- [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]] - creator corrections and non-negotiables.
- [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]] - local-first/cloud-second model strategy.
- [[docs/product/MARKETING_NOTE|MARKETING_NOTE]] - positioning and go-to-market language.

## Design Aids

- [[docs/user/USER_FLOWS|USER_FLOWS]] - end-to-end workflows.
- [[docs/user/USE_CASES|USE_CASES]] - concrete scenarios.
- [[docs/architecture/DIAGRAMS|DIAGRAMS]] - Mermaid and PlantUML diagrams.
- [[docs/architecture/ARCHITECTURE|ARCHITECTURE]] - implementation architecture overview.
- [[docs/architecture/DEVELOPMENT|DEVELOPMENT]] - local development and verification commands.
- [[docs/meta/OBSIDIAN_START_HERE|OBSIDIAN_START_HERE]] - first-time Obsidian workflow for this vault.
- [[docs/meta/GLOSSARY|GLOSSARY]] - plain-language explanation of Entroping terms.
- [[docs/meta/CONTEXT_MANAGEMENT|CONTEXT_MANAGEMENT]] - how Codex, Obsidian, `.context`, and Graphify fit together.
- [[docs/meta/AUTONOMOUS_DEVELOPMENT|AUTONOMOUS_DEVELOPMENT]] - Codex-first autonomous workflow and future OpenCode/oMLX plan.
- `AGENTS.md` - project-local Codex implementation rules.
- `.context/plan.md` - current implementation milestone and handoff context.
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

## Working Loop

When the product changes:

1. Update the affected canonical doc.
2. Add or update an ADR if the reason matters later.
3. Update [[docs/evolution/EVOLUTION_TIMELINE|EVOLUTION_TIMELINE]] with a short dated note.
4. Update `.context/changelog.md` for handoff continuity.
5. Update `AGENTS.md` if implementation rules changed.
