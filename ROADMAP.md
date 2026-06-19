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

## Expanded Product Lanes

These lanes extend the roadmap without replacing GitHub Issues as the backlog.
Each lane should become issue-backed before implementation, and each paid
surface must preserve the useful local core.

### v0.5 Frictionless Evidence Loop

Goal: make the first serious team workflow feel obvious from editor to PR.

- VS Code extension for `doctor`, `run`, report discovery, latest-run status,
  and problem-matchable findings from existing artifacts.
- Local evidence workbench for reports, applied gates, drift, redaction
  confidence, traffic summaries, and release anchors. It should stay read-only
  until the report-backed workflow is proven.
- One-command onboarding wizard that explains required Hurl, QAnstitution,
  source, report, and CI setup without changing the locked CLI contract.
- PR runtime evidence card that summarizes pass/fail, failed gates, drift,
  redaction confidence, AI-agent provenance, and release-evidence anchors.
- Design-partner pilot kit in
  [USER_GUIDE.md](docs/user/USER_GUIDE.md#design-partner-pilot-kit) with setup
  steps, evidence-bundle acceptance checks, usage metrics, and feedback
  templates for AI-generated backend/API changes.

### v0.6 Cross-Surface Continuity

Goal: make Entroping feel continuous across CLI, desktop, phone, and cloud
surfaces without weakening local-first trust boundaries.

- Shared evidence identifiers and deep links so CLI runs, desktop/workbench
  views, hosted evidence pages, PR cards, and mobile views all point to the
  same sanitized runtime-governance evidence.
- Phone-friendly read-only views for latest run status, failed gates, drift,
  release blockers, design-partner evidence, and next recommended action.
- Desktop-to-cloud and cloud-to-CLI handoff packets that preserve project,
  branch, issue, evidence bundle, report schema, and verification context
  without embedding secrets, raw traffic, source Hurl contents, or env values.
- Resume-anywhere workflow for reviewing evidence, assigning follow-up work,
  opening the right local command, and handing a bounded packet to Codex,
  Claude, or another coding agent.
- Explicit sync policy: repos and vaults remain source-controlled; phone/cloud
  continuity moves curated evidence and handoff metadata, not conflict-prone
  mutable worktrees.

### v0.6 Work Management, Chat, And Enterprise Automation

Goal: put Entroping evidence where teams already coordinate work without making
Entroping a replacement issue tracker or chat platform.

- Issue-tracker evidence links for Jira, Linear, and monday.com: attach
  sanitized PR/runtime-governance evidence, failed-gate summaries, release
  anchors, and follow-up issue links without duplicating the full backlog.
- Chat notifications for Slack and Discord: post value-free run summaries,
  failed-gate alerts, design-partner evidence status, and release-blocker
  digests with links back to local or hosted evidence.
- Enterprise automation connector plan for Workato and similar platforms:
  expose explicit triggers and actions around sanitized evidence bundles,
  release decisions, policy drift, and downstream proof collection.
- Enterprise AI-agent integration surface for Claude, Codex, and other
  agentic coding tools: consume and emit review packets, agent-run provenance,
  and repair proposals while preserving LiteLLM/provider boundaries.
- Start read-only and notification-first; require issue-backed design, access
  control, audit evidence, and user intent before any write-back, ticket
  mutation, or chat-command execution.

### v0.6 Observability And Test-Pyramid Governance

Goal: connect runtime governance to the telemetry and test evidence teams
already trust.

- OpenTelemetry-first evidence adapter for API traces, logs, metrics, and route
  observations, with Datadog and Splunk adapters after the vendor-neutral path
  is proven.
- Observability-to-contract analysis that compares sanitized production-like
  route behavior against OpenAPI, traffic-state, QAnstitution, and Hurl
  evidence.
- External test-evidence ingestion for unit, integration, component, contract,
  and end-to-end suites through standard artifacts such as JUnit, coverage, and
  SARIF.
- Test-pyramid report that classifies existing evidence by layer and highlights
  missing runtime-governance proof without replacing the user's existing test
  runners.
- OpenAPI contract coverage score that separates positive, negative, security,
  drift, story, and operation coverage instead of treating all tests as equal.

### v0.6 API Architecture Breadth

Goal: broaden Entroping's API governance beyond REST while keeping Hurl-backed
HTTP proof as the first-class execution path.

- Promote GraphQL-over-HTTP governance from examples into a documented,
  issue-backed first-class workflow.
- Promote SOAP/XML-over-HTTP governance from examples into a documented,
  issue-backed first-class workflow.
- Add webhook and event-contract governance through signed examples, replayable
  fixtures, and report evidence before promising broad event-bus coverage.
- Plan AsyncAPI and message-driven contract support as a bridge/reporting
  problem first, not as an immediate new runtime.
- Keep native gRPC streaming and WebSocket state-machine testing proof-gated
  until simpler HTTP, event, and contract workflows are loved.

### v0.7 Generated-Test Quality Assurance

Goal: answer "who tests the AI-generated tests?" with deterministic evidence.

- Generated-test quality score for assertion strength, brittle selectors,
  missing negative paths, weak auth coverage, shallow schema checks, and
  overfitted examples.
- Mutation testing for generated API tests, starting with deterministic request,
  response, schema, auth, latency, and status-code mutations.
- Seeded fuzz/property-case generation for API boundaries, always producing
  reviewable tests and reproducible seeds instead of hidden fuzzing.
- QA report for generated Hurl that separates syntax validity, semantic
  assertion strength, coverage value, policy alignment, and flake risk.
- Repair-proposal loop where AI can suggest stronger tests or policies, but
  parser validation, Hurl execution, and QAnstitution gates decide acceptance.

### v0.7 Entroping QA Brain Pro

Goal: build a proprietary QA model around Entroping's runtime-governance data
while preserving LiteLLM as the provider-neutral routing layer.

- Keep LiteLLM as the model access boundary so users can bring OpenAI,
  Anthropic, Gemini, local OSS models, or Entroping's first-party model.
- Build an Entroping QA Brain eval suite for weak-test detection, missing gate
  discovery, unsafe generated Hurl, bogus evidence, redaction mistakes, and API
  drift reasoning.
- Start with sanitized evidence bundles, retrieval, prompts, and evals before
  fine-tuning. Do not train a foundation model from scratch as the first step.
- Offer Entroping QA Brain Pro as an optional hosted, local, or enterprise
  OpenAI-compatible model endpoint routed through LiteLLM.
- Use the model for critique, generation, prioritization, and repair proposals;
  never make it the authority for `entroping run` pass/fail.

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
