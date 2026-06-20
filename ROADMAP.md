---
title: Entroping Roadmap
type: roadmap
status: active
tags:
  - roadmap
  - public
  - alpha
  - open-core
---

# Entroping Roadmap

Entroping is an early alpha runtime-governance tool for AI-assisted backend
development. The public roadmap is intentionally narrow: keep the deterministic
Hurl and QAnstitution core strong, preserve the completed onboarding and product
depth evidence, then move carefully into integrations and stable-core proof.

Roadmap milestones such as `v0.4.0-alpha` are release milestones. They do not
replace the locked v4.1 product/spec/CLI contract.

Canonical work tracking lives in:

- GitHub Issues for bugs, feature slices, regressions, and contribution tasks.
- GitHub Milestones for release targets.
- GitHub Project board for visible sequencing.
- Obsidian docs for product history, source evidence, ADRs, and phase-level context.

GitHub Issues remain the backlog. This roadmap explains public direction and
release sequence; it should not become a duplicated task list.

## Roadmap Scope And Docs Inventory Evidence

This file owns public release sequence, near-term scope, and open-core boundary
signals. It should stay readable enough for a first-time visitor to understand
what is current, what is next, and what is intentionally deferred. Detailed
long-range product and monetization reasoning belongs in
[GROWTH_AND_MONETIZATION.md](docs/product/GROWTH_AND_MONETIZATION.md), while
implementation work remains in GitHub Issues.

Docs curation uses `scripts/docs_inventory.py --format json --strict` to check
active/reference/archive tiers, default-agent context budget, duplicate active
titles, and prune candidates. The curation choice is to keep archive and source
material discoverable through [VAULT_INDEX.md](docs/meta/VAULT_INDEX.md) and
`docs/evolution/`, not to delete history or make this roadmap a second backlog.

## Product Direction

Entroping is not a generic test generator or a chat-first QA assistant. The core
product is local-first runtime governance for AI-assisted backend development:
LLMs may generate or repair tests, but Hurl execution and QAnstitution gates
decide pass or fail.

The public core stays useful on its own: local CLI, deterministic Hurl runner,
QAnstitution policy loading, OpenAPI generation, captured-traffic freeze/map,
local reports, and provider-neutral review artifacts. Monetization should wrap
the core through hosted aggregation, organization policy distribution, premium
policy packs, services, and team workflows without weakening the free tool.

## Near-Term Sequence

1. Keep correctness and report safety tight: generated Hurl validation, escaped
   human-readable reports, and regression coverage for every changed runtime
   boundary.
2. Keep the public entry points sharp: README, MkDocs, demo media, and first-hour
   QAnstitution guidance should stay welcoming instead of encyclopedic.
3. Keep policy-pack and organization-governance work local-first until package
   indexes, provenance, and external user feedback prove the distribution path.
4. Keep multi-agent development issue-scoped and evidence-backed through
   `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, context packs, and CI.
5. Keep launch-hardening work ahead of broad v0.6/v0.7 expansion when external
   review points to verified adoption, runtime-confidence, or evidence-quality
   gaps.

## Launch Hardening Queue

External review triage added a small consolidation queue before Entroping expands
into broader integrations and QA-brain surfaces:

- [#957](https://github.com/sakibshuvo/Entroping/issues/957) keeps the report
  command surface launch-ready without breaking the locked v4.1 CLI contract.
- [#958](https://github.com/sakibshuvo/Entroping/issues/958) deepens real Hurl
  subprocess integration coverage for high-risk failure boundaries.
- [#959](https://github.com/sakibshuvo/Entroping/issues/959) defines the local
  structured diagnostics boundary before vendor observability adapters.
- [#960](https://github.com/sakibshuvo/Entroping/issues/960) adds bounded
  performance-smoke regression evidence for stable-core confidence.
- [#961](https://github.com/sakibshuvo/Entroping/issues/961) uses the existing
  docs governance and inventory tooling to keep `ROADMAP.md`
  release-sequence-focused while moving long-range product and monetization lane
  reasoning to `docs/product/GROWTH_AND_MONETIZATION.md`.

Package-index distribution remains tracked by the existing stable-core issues
for TestPyPI, PyPI, Homebrew, compatibility, and downstream feedback.

## Completed: v0.1.1-alpha Public Cleanup

Goal: make the current alpha credible to a first-time open-source visitor.

- README is demo-first and clear about alpha boundaries.
- Public roadmap, visible milestones, GitHub Project, and issue-backed workflow
  are in place.
- `v0.1.1-alpha` was published from verified `main` evidence.
- Install, live demo, release, community-profile, Scorecard, security, and
  quality gates are reproducible.
- Dependency-update visibility exists for GitHub Actions and Python dependencies.

Proof:

- `scripts/release_check.sh --require-live-demo`
- Passing required GitHub Actions checks on `main`
- `v0.1.1-alpha` GitHub prerelease with explicit "not built yet" boundaries

## Completed: v0.2.0-alpha Adoption And Onboarding

Goal: make the first hour with Entroping smooth enough for real users.

- Fresh clone smoke test from the public README.
- Contributor-friendly good-first-issue path.
- Better demo media: terminal output, HTML report preview, and dependency map.
- Public docs site decision and strict MkDocs deployment.
- Packaging plan for PyPI/TestPyPI, Homebrew, and deferred standalone binaries.
- GitHub Actions template for running Entroping in downstream repos.
- Provider setup guide for LiteLLM, local Qwen/oMLX, and no-provider CI.
- First-hour QAnstitution guide and zero-config checkout demo entrypoint.

## Completed: v0.3.0-alpha CLI/report-first Product Depth

Goal: deepen the alpha without weakening deterministic execution.

- Studio stays optional, read-only, and report-backed. It may add drilldowns
  only over already-sanitized reports, applied gate metadata, or redacted
  traffic summaries.
- CLI and reports remain the primary workflow for drift baselines, redaction
  review, Architect remediation feedback, and richer examples.
- No Studio mutation implementation is planned for v0.3; mutation work remains
  governed by [STUDIO_MUTATION_WORKFLOW_DESIGN.md](docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md).
- Baseline workflows for drift, latency, response-shape, and dependency-route evidence.
- Redaction review UX for captured traffic.
- Better Architect feedback when provider output is invalid or incomplete.
- More realistic example apps beyond the checkout fixture.
- `doctor` validates existing traffic-state compatibility without creating
  runtime state.

## Current: v0.4.0-alpha Integrations

Goal: connect Entroping to the places teams already review backend behavior.

- Keep the local GitHub Actions annotation command as the proven integration.
- Add review integrations beyond local annotations only through issue-backed,
  artifact-backed slices.
- Reusable policy-pack structure for security, latency, compliance, and API
  governance is documented in [POLICY_PACK_LAYOUT.md](docs/technical/POLICY_PACK_LAYOUT.md);
  follow-up work can add registries or package distribution later.
- Organization QAnstitution import governance design is recorded in ADR-0011;
  runtime provenance/effective-policy evidence should come before remote
  registries.
- Report artifact schemas are versioned for run, drift, and traceability
  reports; downstream dashboard schemas should remain explicit and compatible.
- CI examples should stay GitHub Actions first, with other providers promoted
  only after real runner proof.

## Proposed Next: v0.5 Design Partner Evidence Cloud

Goal: prove that teams will pay for organization-level runtime governance
evidence while preserving the local-first Apache-2.0 core.

This is a scoped design-partner experiment, not a broad hosted product. The
local CLI, Hurl execution, QAnstitution policy loading, local reports, and
provider-free `entroping run` path remain core. The paid surface is aggregation
and team visibility over sanitized evidence that teams already chose to
produce.

- Define an upload-ready sanitized team evidence bundle from existing Entroping
  reports and artifact manifests.
- Prototype a dashboard for PR/runtime-governance status across repositories:
  pass/fail, failed gates, drift summaries, redaction confidence, and release
  evidence anchors.
- Support design partner pilots focused on AI-generated backend/API changes and
  measure whether engineering leads will pay for cross-repo runtime governance
  visibility.
- Keep uploads explicit and value-free: no raw traffic, secrets, prompts,
  provider outputs, source Hurl contents, environment values, or full report
  artifact contents.
- Treat premium policy packs and managed organization policy registries as later
  commercial surfaces after design partners prove that evidence aggregation is
  valuable.

## Directional Product Lanes

These lanes extend the release sequence without replacing GitHub Issues as the
backlog. They are directional themes, not implementation tickets. Before any
lane becomes build work, create or reuse issue-backed slices and keep the useful
local core intact. Detailed product and monetization reasoning lives in
[GROWTH_AND_MONETIZATION.md](docs/product/GROWTH_AND_MONETIZATION.md#long-range-product-and-commercial-lanes).

| Lane | Public promise | Promotion rule |
| --- | --- | --- |
| v0.5 Frictionless Evidence Loop | Make serious team adoption obvious from editor to PR through editor/workbench/onboarding/report-card surfaces over existing artifacts, including the [Design-partner pilot kit](docs/user/USER_GUIDE.md#design-partner-pilot-kit). | Start read-only and prove report-backed value before mutation or broad dashboard work. |
| v0.6 Cross-Surface Continuity | Let CLI, desktop/workbench, hosted evidence pages, PR cards, and mobile views point to the same sanitized evidence. | Move curated evidence and handoff metadata only; do not sync raw repos, vaults, traffic, secrets, source Hurl, env values, or mutable worktrees. |
| v0.6 Work Management, Chat, And Enterprise Automation | Put Entroping evidence into Jira, Linear, monday.com, Slack, Discord, Workato, Claude, Codex, and similar team surfaces. | Begin with read-only links and notifications; require access control, audit evidence, and user intent before write-back or chat commands. |
| v0.6 Observability And Test-Pyramid Governance | Connect runtime governance to OpenTelemetry, Datadog, Splunk, and existing test evidence without replacing teams' test runners. | Prove the vendor-neutral OpenTelemetry and standard-artifact path before vendor-specific adapters or scoring claims. |
| v0.6 API Architecture Breadth | Broaden beyond REST through HTTP-first GraphQL, SOAP/XML, webhook, event-contract, AsyncAPI, gRPC, and WebSocket lanes. | Promote examples into issue-backed workflows in order of simplest proof; keep Hurl-backed HTTP evidence first-class. |
| v0.7 Generated-Test Quality Assurance | Answer "who tests the AI-generated tests?" through deterministic quality, mutation, fuzz, and repair-proposal evidence. | Produce reviewable Hurl/tests with reproducible seeds; Hurl/QAnstitution remains pass/fail authority. |
| v0.7 Entroping QA Brain Pro | Build a proprietary QA model around sanitized Entroping runtime-governance evidence while preserving LiteLLM routing. | Start with evidence bundles, retrieval, prompts, and evals before fine-tuning; do not train a foundation model from scratch first. |

## External Stable-Core Blockers

Stable-core completion requires proof outside the local repo:

- package-index proof from TestPyPI/PyPI publish and install smoke.
- a documented compatibility policy that constrains future CLI/report changes.
- real downstream user feedback from at least one external project.
- provider-specific CI templates only after real GitLab/Buildkite/CircleCI
  runner evidence.

These blockers are tracked in GitHub Issues and the release-evidence ledger.
Repeated alpha release-candidate evidence is tracked separately in the
release-evidence ledger; it is not currently an unresolved stable-core blocker.
Do not call the project stable just because alpha gates are green.

## Future: v1.0 Stable Core

Goal: make the local deterministic core safe to depend on.

- Command compatibility audit and documented stability policy exist.
- Cross-platform install and smoke matrix exists for Linux, macOS, and
  Windows doctor-only claims.
- Security threat-model refresh, dependency-policy review, and security gates
  exist.
- Performance smoke exists for large test suites and traffic stores.
- A downstream smoke harness exists for local external-project proof, but this
  is not a substitute for feedback from a real project outside this repository.
- Clear extension boundaries for open-core offerings exist.
- Stable-core claims still require package-index proof, a stable-core
  compatibility decision, and real downstream user feedback. Repeated alpha
  release-candidate evidence is tracked separately in the release-evidence
  ledger.

## Open-Core Path

The Apache-2.0 public core should stay genuinely useful:

- local CLI
- Hurl execution
- QAnstitution parser and gates
- OpenAPI generation
- traffic capture, freeze, map
- local reports
- local-first Brain integration
- local GitHub Actions PR annotations
- editor and local workbench surfaces over already-sanitized local artifacts
- external test-evidence classification from standard report artifacts
- cross-surface evidence identifiers and local handoff packets

Commercial surfaces should sit around the core:

- hosted team dashboard
- organization policy registry
- premium policy packs
- cross-repo team reporting
- audit history and scheduled monitors
- paid onboarding, support, and custom policy/test generation
- Datadog, Splunk, and other managed observability integrations
- Jira, Linear, monday.com, Slack, Discord, Workato, and enterprise workflow
  connectors
- Claude, Codex, and enterprise AI-agent evidence integrations
- hosted cross-surface continuity for phone, desktop, cloud, and CLI workflows
- Entroping QA Brain Pro hosted, local, or enterprise model packaging
- proprietary model fine-tuning, model-evaluation, and policy-pack services

The detailed maintainer boundary lives in
[OPEN_CORE_BOUNDARIES.md](docs/product/OPEN_CORE_BOUNDARIES.md). Do not make the
free tool weak to force monetization. Adoption comes first.

## Explicitly Not Near-Term

These are intentionally outside the immediate alpha roadmap:

- Bruno import/compiler
- native gRPC streaming before HTTP/event-contract proof is strong
- WebSocket state-machine testing before simpler API-style lanes are proven
- broad hosted cloud product beyond the scoped v0.5 design-partner evidence
  prototype
- enterprise policy approval workflows
- broad visual dashboard
- arbitrary-expression condition DSL
- training a proprietary foundation model from scratch before evidence bundles,
  evals, and fine-tuned adapter economics are proven
- two-way issue-tracker synchronization, ticket mutation, chat commands, or
  enterprise automation writes before read-only evidence links, audit controls,
  and explicit user intent are proven
- raw repo, vault, worktree, traffic, or secret synchronization across phone,
  desktop, cloud, and CLI before a conflict model and data-boundary audit exist

They can return later only after the local deterministic loop is loved.
