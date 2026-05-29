---
title: ADR-0006 Solo-First MVP
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - mvp
  - solo-first
---

# ADR-0006: Solo-First MVP

## Decision

The MVP should optimize for a solo developer building and debugging locally before packaging, Cloud, or enterprise workflows.

## Context

The creator explicitly pushed against bloated enterprise planning. The product can grow into team governance, but the first useful loop must be local and understandable.

## Consequences

- Use editable source installs and `uv` first.
- Defer Nuitka, Homebrew formula, Docker, PyPI, and Cloud until the governance loop works.
- Prefer a small typed agent router before adding orchestration frameworks.

Links: [[MVP_PLAN]], [[CREATOR_INTENT_AUDIT]], [[TDS]]

