---
title: Entroping Evolution Timeline
type: timeline
status: stable
tags:
  - entroping
  - product-evolution
  - timeline
---

# Entroping Evolution Timeline

This note tracks how Entroping changed over time and links each major change to the docs that explain it.

## Phase 1 - Local AI Testing Assistant

The idea started as a local AI-assisted testing tool with a Brain, Eye, Muscle, Face, and Memory. The durable pieces were local-first operation, Hurl execution, traffic capture, and SQLite state.

Links: [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]], [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]]

## Phase 2 - QAnstitution as Executable Law

The governance layer became explicit. Quality rules moved into `qanstitution.yaml`, while agent personas stayed in Markdown.

Links: [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]], [[decisions/ADR-0001-hurl-native-governance]]

## Phase 3 - Hurl-Native Runtime Governance

The product narrowed around deterministic Hurl execution instead of generic AI judgment or Bruno-native workflows.

Links: [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]], [[docs/technical/TDS|TDS]], [[decisions/ADR-0001-hurl-native-governance]]

## Phase 4 - Locked Command Surface

The command namespace was frozen to keep implementation stable and prevent drift from old transcript ideas.

Links: [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]], [[decisions/ADR-0002-locked-command-surface]]

## Phase 5 - Local-First Brain

The AI layer became LiteLLM-routed, local-first through Ollama where practical, and cloud-capable only through explicit configuration.

Links: [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]], [[decisions/ADR-0003-local-first-brain]]

## Phase 6 - Documentation Vault

The Markdown docs became an Obsidian vault so product evolution, decisions, sources, and implementation guidance can remain linked over time.

Links: [[00_INDEX]], [[docs/meta/OBSIDIAN_START_HERE|OBSIDIAN_START_HERE]], [[sources/SOURCE_MAP]]

## Phase 7 - Implementation Scaffold and Security Baseline

The repo became a working Python scaffold with CI, typed QAnstitution models, condition validation, bridge boundaries, a checkout demo fixture, project-local Codex rules, and a first security scan. The next product step is the deterministic governance loop rather than more documentation expansion.

Links: [[docs/product/MVP_PLAN|MVP_PLAN]], [[docs/architecture/DEVELOPMENT|DEVELOPMENT]]

## Phase 8 - Eye Boundary Split

The Eye moved from concept to implementation. `watch` became capture-only, while `freeze` and `map` were deliberately split into filtering/session, traffic-to-Hurl, safe CLI write, and dependency graph compiler slices.

Links: [[docs/technical/FREEZE_MAP_PLAN|FREEZE_MAP_PLAN]], [[decisions/ADR-0008-freeze-map-boundaries]]
