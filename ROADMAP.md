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

Canonical work tracking lives in:

- GitHub Issues for bugs, feature slices, regressions, and contribution tasks.
- GitHub Milestones for release targets.
- GitHub Project board for visible sequencing.
- Obsidian docs for product history, source evidence, ADRs, and phase-level context.

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
- Stable-core claims still require repeated release evidence, package-index
  proof, compatibility discipline, and real-user feedback. Do not call the
  project stable just because alpha gates are green.

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

Commercial surfaces should sit around the core:

- hosted team dashboard
- organization policy registry
- premium policy packs
- cross-repo team reporting
- audit history and scheduled monitors
- paid onboarding, support, and custom policy/test generation

The detailed maintainer boundary lives in
[OPEN_CORE_BOUNDARIES.md](docs/product/OPEN_CORE_BOUNDARIES.md). Do not make the
free tool weak to force monetization. Adoption comes first.

## Explicitly Not Near-Term

These are intentionally outside the immediate alpha roadmap:

- Bruno import/compiler
- native gRPC streaming
- WebSocket state machine testing
- hosted cloud product
- enterprise policy approval workflows
- broad visual dashboard
- arbitrary-expression condition DSL

They can return later only after the local deterministic loop is loved.
