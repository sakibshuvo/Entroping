---
title: ADR-0008 Freeze Map Boundaries
type: decision
status: accepted
date: 2026-05-30
tags:
  - decision
  - eye
  - freeze
  - map
---

# ADR-0008: Freeze Map Boundaries

## Decision

`watch`, `freeze`, and `map` remain separate pipeline stages.

- `watch` captures and persists redacted traffic only.
- `freeze` compiles redacted traffic sessions into generated Hurl tests.
- `map` compiles redacted traffic into dependency graph exports.

Filtering, session stitching, traffic-to-Hurl compilation, and graph compilation belong in bridge modules. CLI and core adapters may orchestrate and persist, but they must not own these transformations.

## Context

The Eye subsystem can easily become a dumping ground because it touches proxy capture, redaction, persistence, Hurl generation, mocks, and dependency maps. Keeping the compiler work in bridge modules preserves hexagonal boundaries and makes the transformations testable without mitmproxy, SQLite, Hurl, or LLM providers.

## Consequences

- `core.traffic_proxy` remains capture-only and does not generate Hurl.
- `core.traffic_store` stores redacted state and does not infer sessions or graphs.
- `bridge.traffic_sessions`, `bridge.traffic_to_hurl`, and `bridge.traffic_to_graph` can be tested as pure transformations.
- `freeze` and `map` can share session/filtering behavior without sharing filesystem or proxy code.
- Future AI features may consume only redacted traffic-derived artifacts, never raw captured traffic.

Links: [[docs/technical/FREEZE_MAP_PLAN|FREEZE_MAP_PLAN]], [[docs/technical/TDS|TDS]], [[docs/product/MVP_PLAN|MVP_PLAN]]
