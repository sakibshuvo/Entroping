---
title: ADR-0005 Deterministic Run Boundary
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - execution
  - ci
---

# ADR-0005: Deterministic Run Boundary

## Decision

`entroping run` is deterministic and does not call the LLM.

## Context

AI can generate, refactor, and audit tests through Architect commands. Runtime enforcement must remain explainable from committed Hurl files, environment data, effective QAnstitution, and Hurl output.

## Consequences

- Breaker output must become committed Hurl tests before it can govern CI.
- CI failures are reproducible without model access.
- Reports include exact test paths, rule IDs, and repro commands.

Links: [[PRODUCT_SPEC]], [[TDS]], [[COMMAND_CHEAT_SHEET]]

