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
Hurl and QAnstitution core strong, make onboarding frictionless, then add depth
around traffic evidence, Studio, integrations, and open-core surfaces.

Canonical work tracking lives in:

- GitHub Issues for bugs, feature slices, regressions, and contribution tasks.
- GitHub Milestones for release targets.
- GitHub Project board for visible sequencing.
- Obsidian docs for product history, source evidence, ADRs, and phase-level context.

## Now: v0.1.1-alpha Public Cleanup

Goal: make the current alpha credible to a first-time open-source visitor.

- Keep the README demo-first and clear about alpha boundaries.
- Publish a public roadmap, visible milestones, and issue-backed backlog.
- Sync the current release tag with the implemented `main` branch.
- Keep install, live demo, release, community-profile, Scorecard, security, and
  quality gates reproducible.
- Add dependency-update visibility for GitHub Actions and Python dependencies.

Exit proof:

- `scripts/release_check.sh --require-live-demo`
- Passing required GitHub Actions checks on `main`
- A current alpha GitHub release with explicit "not built yet" boundaries

## Next: v0.2.0-alpha Adoption And Onboarding

Goal: make the first hour with Entroping smooth enough for real users.

- Fresh clone smoke test from the public README.
- Contributor-friendly good-first-issue path.
- Better demo media: terminal recording, HTML report screenshot, and dependency map.
- Public docs site decision and first pass.
- Packaging plan for PyPI, Homebrew, or standalone binaries.
- GitHub Actions template for running Entroping in downstream repos.
- Provider setup guide for LiteLLM, local Qwen/oMLX, and no-provider CI.

## Next: v0.3.0-alpha CLI/report-first product depth

Goal: deepen the alpha without weakening deterministic execution.

- Studio stays optional, read-only, and report-backed. It may add drilldowns
  only over already-sanitized reports, applied gate metadata, or redacted
  traffic summaries.
- CLI and reports remain the primary workflow for drift baselines, redaction
  review, Architect remediation feedback, and richer examples.
- No Studio mutation implementation is planned for v0.3; mutation work remains
  a design gate only.
- Baseline workflows for drift, latency, response-shape, and dependency-route evidence.
- Redaction review UX for captured traffic.
- Better Architect feedback when provider output is invalid or incomplete.
- More realistic example apps beyond the checkout fixture.

## Later: v0.4.0-alpha Integrations

Goal: connect Entroping to the places teams already review backend behavior.

- GitHub PR annotations from JUnit, HTML, drift, and traceability reports.
- Reusable policy-pack structure for security, latency, compliance, and API governance.
- Organization QAnstitution import governance design.
- Stable report artifact schemas for downstream dashboards.
- CI examples for GitHub Actions first, then other providers as demand appears.

## Future: v1.0 Stable Core

Goal: make the local deterministic core safe to depend on.

- Command compatibility audit and documented stability policy.
- Cross-platform install and smoke matrix.
- Security threat-model refresh and dependency-policy review.
- Performance smoke for large test suites and traffic stores.
- Clear extension boundaries for open-core offerings.

## Open-Core Path

The Apache-2.0 public core should stay genuinely useful:

- local CLI
- Hurl execution
- QAnstitution parser and gates
- OpenAPI generation
- traffic capture, freeze, map
- local reports
- local-first Brain integration

Commercial surfaces should sit around the core:

- hosted team dashboard
- organization policy registry
- premium policy packs
- PR annotations and team reporting
- audit history and scheduled monitors
- paid onboarding, support, and custom policy/test generation

Do not make the free tool weak to force monetization. Adoption comes first.

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
