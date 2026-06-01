---
title: ADR-0012 Brand Integrity And QAnstitution Name
type: decision
status: accepted
date: 2026-06-01
tags:
  - decision
  - brand
  - qanstitution
  - terminology
  - compatibility
---

# ADR-0012: Brand Integrity And QAnstitution Name

## Decision

qanstitution.yaml remains the canonical policy filename for Entroping.
QAnstitution is not a placeholder name, and the product philosophy remains:

**The QAnstitution is Law. Traffic is Truth. Hurl is the Enforcer.**

Do not add `entroping.yaml` or `entroping-policy.yaml` as aliases unless a
future compatibility ADR accepts a migration plan, backward-compatibility
policy, CLI/help behavior, schema mapping, documentation impact, and deprecation
window.

The near-term fix for terminology friction is explanation, not renaming. Public
docs should introduce the plain meaning first when needed:

```text
Define runtime policy in qanstitution.yaml.
Entroping calls that executable policy the QAnstitution.
```

## Rationale

The unusual vocabulary is part of Entroping's positioning. The project should
not become a generic test-generator wrapper by sanding down the words that make
its governance model memorable.

The implementation already treats `qanstitution.yaml` as a public contract:

- `entroping init` creates it.
- `entroping doctor`, `entroping run`, and Architect commands load it.
- editor schema mappings target `qanstitution.yaml` and `**/qanstitution.yaml`.
- examples, policy packs, and CI docs reference it.

Adding aliases now would create configuration ambiguity without solving a
verified implementation problem. It would also expand compatibility, migration,
schema, docs, and support surface before stable-core evidence exists.

## Public Positioning Boundary

Entroping is a runtime governance and compliance-evidence layer for
AI-assisted backend and API changes. It is not an autonomous agent swarm, not a
general prompt orchestrator, and not an LLM approval engine.

The branded subsystem names stay:

- Architect: AI-assisted generation, refactor, and audit commands.
- Builder, Auditor, Breaker: Architect roles configured in QAnstitution.
- Eye: traffic observation through `watch`, `freeze`, and `map`.
- Enforcer: deterministic `entroping run`, Hurl, QAnstitution gates, and reports.

These names are allowed in public docs when they are tied to concrete commands
or artifacts. Avoid copy that implies Entroping independently operates a swarm
of agents, merges generated code, or approves behavior through model judgment.

## Compatibility Rules

- `qanstitution.yaml` is the only supported root policy filename.
- `entroping.yaml` and `entroping-policy.yaml` are not aliases.
- CLI behavior remains unchanged by this decision.
- Any future alias requires a separate issue and ADR before implementation.
- If a future alias is accepted, `qanstitution.yaml` must remain supported for
  a documented compatibility window.

## Documentation Rules

Public docs should preserve the philosophy and explain it clearly. They should
not hide QAnstitution behind generic "policy file" wording after the first
mention, and they should not replace the core slogan with a bland substitute.

Technical docs may use internal names such as Brain, Eye, Architect, Enforcer,
Builder, Auditor, and Breaker as long as the implementation boundary is clear.
First-run docs should connect those names to commands, files, or reports before
using them as standalone metaphors.

## Consequences

This decision prioritizes brand coherence over generic onboarding language.
Some first-time users may need one extra sentence to understand QAnstitution,
but the project keeps a sharper identity and avoids premature compatibility
surface.

The accepted mitigation is glossary and reference clarity, not rename churn.
