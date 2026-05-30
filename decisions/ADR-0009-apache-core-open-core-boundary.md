---
title: ADR-0009 Apache Core Open Core Boundary
type: decision
status: accepted
date: 2026-05-30
tags:
  - decision
  - license
  - open-core
  - release
---

# ADR-0009: Apache Core Open Core Boundary

## Decision

Entroping Core is licensed under Apache-2.0.

The public core includes the local CLI, deterministic Hurl runner, QAnstitution
policy loading and enforcement, local reports, OpenAPI/Hurl bridge compilers,
traffic-derived freeze/map/mock features, and local/BYOK Brain integrations.

Future hosted services, proprietary model weights, premium policy packs,
enterprise dashboards, team governance workflows, support, SLAs, and managed
cloud features may be distributed separately under commercial terms.

## Context

The project needs fast developer adoption, credible open-source positioning,
and a monetization path. A restrictive "free except commercial/SaaS" license
would weaken open-source credibility and add adoption friction. A permissive
core license makes the local tool easy to try, package, fork, integrate, and
trust, while monetization can happen through hosted intelligence, enterprise
workflow, support, and managed governance.

Apache-2.0 is preferred over MIT for this project because it remains permissive
while adding an explicit patent grant and patent termination language that is
useful for enterprise-oriented developer tooling.

## Consequences

- Public alpha packaging can use SPDX metadata: `Apache-2.0`.
- The README can clearly invite commercial and private use of the core without
  implying that hosted or enterprise products are included.
- Paid surfaces should live in separate services, packages, repos, or clearly
  separated modules with their own terms.
- The Entroping name, logo, hosted model, datasets, and service identity remain
  separate product assets; the Apache-2.0 code license does not grant trademark
  rights.
- Any future change to AGPL, BSL, FSL, dual licensing, or a contributor CLA
  requires a new explicit decision.

Links: [[README]], [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]], [[docs/product/MARKETING_NOTE|MARKETING_NOTE]]
