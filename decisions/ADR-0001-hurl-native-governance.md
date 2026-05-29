---
title: ADR-0001 Hurl-Native Governance
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - hurl
  - governance
---

# ADR-0001: Hurl-Native Governance

## Decision

Entroping v4.1 is Hurl-native. Hurl files are the executable test format, and the Rust `hurl` binary is the enforcement boundary.

## Context

Earlier product thinking included broader AI testing and Bruno-like workflows. The stable direction is runtime governance: AI can generate tests, but deterministic Hurl execution decides pass or fail.

## Consequences

- Python orchestrates but does not replace Hurl as the HTTP execution engine.
- QAnstitution gates are injected into execution copies, not source files.
- Bruno and similar clients can still drive traffic through `watch`, but they are not the canonical test format.

Links: [[PRODUCT_SPEC]], [[TDS]], [[REQUIREMENTS_ANALYSIS]]

