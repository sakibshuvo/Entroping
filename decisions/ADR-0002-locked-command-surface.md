---
title: ADR-0002 Locked Command Surface
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - cli
  - command-surface
---

# ADR-0002: Locked Command Surface

## Decision

The v4.1 command surface is intentionally small and compatibility-reviewed in
`docs/technical/CLI_COMPATIBILITY_AUDIT.md`:

`init`, `doctor`, `config list`, `config set`, `architect build`,
`architect refactor`, `architect audit`, `watch`, `freeze`, `map`, `studio`,
`run`, `report bug`, and `report traceability`.

## Context

The source conversation included older names such as `gen`, `fix`, `ui`, `scan`, `verify`, `explain`, `chaos`, `auth`, and `report --type`. The creator repeatedly corrected command drift.

## Consequences

- Deprecated names can only become aliases after an explicit compatibility decision.
- `run --report` emits run artifacts.
- `report bug` generates bug handoff Markdown.
- New flags such as `--dry-run` or `--verbose` require a spec update before implementation.

Links: [[docs/technical/CLI_COMPATIBILITY_AUDIT|CLI_COMPATIBILITY_AUDIT]], [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]], [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]], [[docs/evolution/CREATOR_INTENT_AUDIT|CREATOR_INTENT_AUDIT]]
