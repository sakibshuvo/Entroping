---
title: Open Core Boundaries
type: product
status: active
tags:
  - open-core
  - monetization
  - license
  - strategy
---

# Open Core Boundaries

This is the maintainer-facing boundary for monetization work. It keeps the
Apache-2.0 core useful while leaving room for paid policy, hosted, support, and
team surfaces around it.

The rule is simple:

```text
Adoption features stay in the public core. Coordination, aggregation, hosted
operations, and expert services can be commercial.
```

## Public Core Commitments

These features should remain available in Entroping Core under Apache-2.0:

- Local CLI.
- Hurl execution.
- QAnstitution parser and local gates.
- Basic reports.
- OpenAPI generation.
- Traffic capture, freeze, and map MVP.
- Local-first Brain integration.
- Local GitHub Actions PR annotations from committed report artifacts.
- Local documentation, examples, and deterministic validation scripts.

The core must stay strong enough that an individual developer or small team can
adopt Entroping without asking for a hosted account, a sales call, or telemetry.

## Commercial Surfaces

These may become separate paid offerings, services, packages, or repositories:

- Premium policy packs for security, latency, SOC2-style controls, API
  governance, and industry-specific runtime requirements.
- Hosted team dashboard for aggregating reports across repositories and
  services.
- Team audit history, release evidence, drift history, and organization-level
  quality trends.
- Managed QAnstitution registry, policy import governance, approval workflows,
  and private policy distribution.
- Enterprise SSO/RBAC, access control, and compliance export.
- Hosted replay environments, scheduled monitors, and managed dependency
  mock/replay infrastructure.
- Support and implementation services, including onboarding, custom policies,
  custom test generation, migration help, and priority fixes.

Commercial value should come from scale, coordination, trust operations, and
expertise. It should not come from making the local developer loop incomplete.

## Boundary Rules

- Do not weaken the public core to force monetization.
- Do not make `entroping run` depend on a paid service.
- Do not make QAnstitution authoring, local gate injection, or local reports
  paid-only.
- Do not require telemetry, cloud upload, hosted login, or model-provider
  credentials for deterministic local execution.
- Do not move existing Apache-2.0 core features behind a commercial boundary
  without a new ADR and explicit migration plan.
- Do not send captured traffic, reports, code, or policy data to a hosted
  surface without explicit user intent.
- Do keep premium packages and hosted integrations separable from the local CLI
  so downstream users can audit what is installed and what leaves the machine.
- Do keep local PR annotations in the public core; hosted organization reporting
  and cross-repo analytics can be commercial.

## Decision Checklist

Before adding a monetized feature, answer these questions in the issue or ADR:

| Question | Public core answer | Commercial answer |
| --- | --- | --- |
| Does a solo developer need this to trust a local API change? | Keep it core. | Only commercial if there is a core fallback. |
| Does it execute local tests, enforce gates, or produce basic evidence? | Keep it core. | Do not gate it behind a service. |
| Does it aggregate history across teams, repos, or services? | Provide exportable artifacts. | Hosted/team aggregation can be paid. |
| Does it encode generic security or quality law? | Keep starter rules core. | Premium curated packs can add depth. |
| Does it require SSO, RBAC, audit trails, or compliance workflows? | Keep local files compatible. | Enterprise workflow can be paid. |
| Does it require expert labor or custom migration work? | Document the extension point. | Services can be paid. |

If the answer is ambiguous, default to a useful public core and create a
separate issue for the paid surface.

## Current Interpretation

- Local report generation is core.
- Local `entroping report github-annotations` is core because it converts local
  artifacts into review evidence without a hosted service.
- Organization-level policy reporting, team dashboards, and long-term audit
  history can be commercial because they aggregate trusted local artifacts.
- Starter policy examples are core; deep, maintained policy-pack catalogs can be
  commercial if users can inspect and run them locally.
- Reusable policy-pack structure is defined in
  [POLICY_PACK_LAYOUT.md](../technical/POLICY_PACK_LAYOUT.md), with starter
  examples in core and premium curation kept separate from local runtime
  enforcement.
- Core starter packs include `examples/policy-packs/api-baseline/` and
  `examples/policy-packs/owasp-api-top-10/`. They teach and prove local pack
  imports; deeper maintained packs and support can be commercial when they add
  review cadence, organization controls, reports, and expert help without
  weakening local QAnstitution execution.
- Policy-pack distribution, provenance, attribution, and premium-pack
  boundaries are defined in
  [POLICY_PACK_DISTRIBUTION.md](../technical/POLICY_PACK_DISTRIBUTION.md).
- Public docs and examples should describe the core first. Commercial language
  should be explicit, separate, and never imply that the local CLI is crippled.

Related decision: [[decisions/ADR-0009-apache-core-open-core-boundary|ADR-0009]].
