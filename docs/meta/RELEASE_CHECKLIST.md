---
title: Alpha Release Checklist
type: runbook
status: active
tags:
  - release
  - alpha
  - quality
  - security
---

# Alpha Release Checklist

This checklist defines the release bar for `v0.1.0-alpha`. It is intentionally stricter than the daily feature gate because the public alpha should prove the deterministic governance loop, not only compile.

## Release Claim

`v0.1.0-alpha` may claim:

- Local-first Hurl-native API governance.
- QAnstitution policy loading, validation, matching, and gate injection.
- Deterministic Hurl execution through subprocess boundaries.
- JSON, JUnit, HTML, and bug-report handoff artifacts.
- OpenAPI-to-Hurl generation for the checkout demo and common request shapes.
- Prompt-backed Architect build/refactor foundations with parser-backed Hurl validation.
- Capture-only traffic observation, Hurl freeze generation, WireMock mock export, and Mermaid/DOT/Markdown dependency maps from redacted traffic.
- Optional Graphviz-backed PNG dependency map export from redacted traffic.
- CI proof through the live checkout demo smoke.

## Required Evidence

Run the release gate from a clean checkout:

```bash
scripts/release_check.sh --require-live-demo
```

This gate includes:

- `scripts/repo_hygiene.sh`
- `scripts/regression.sh --security`
- `scripts/live_demo_smoke.sh`

If the local machine does not have Hurl installed, the non-release diagnostic form is:

```bash
scripts/release_check.sh
```

That still runs hygiene and `scripts/regression.sh --security`, but skips the live demo unless Hurl is available.

## CI Evidence

Before tagging, the latest `main` commit must have passing GitHub Actions jobs:

- `checks`
- `live-demo-smoke`

The `live-demo-smoke` job installs a pinned Hurl binary, generates Hurl from the checkout OpenAPI fixture, runs the deterministic Enforcer path, and uploads run reports.

## Manual Review

Before tagging:

- Review `git status --short` and confirm the worktree is clean.
- Review `git log -1 --oneline` and confirm the intended release commit.
- Review `README.md` for accurate current status.
- Review `docs/meta/PROJECT_PROGRESS.md` for phase-level status.
- Confirm no secrets, local env files, `.entroping/`, generated reports, Graphify output, or Obsidian UI state are tracked.
- Confirm `watch` is described as capture-only, `freeze` is described as Hurl/mock generation from redacted traffic, `map` is described as Mermaid/DOT/Markdown/PNG export with optional Graphviz, and `studio` is clearly presented as not built yet.

## Not Built Yet

Do not imply these are complete in release notes:

- Studio/TUI.
- hosted cloud workflows.
- enterprise policy approval workflows.

## Tagging Steps

Only after required evidence passes:

```bash
git tag -a v0.1.0-alpha -m "Entroping v0.1.0-alpha"
git push origin v0.1.0-alpha
```

Then create a GitHub release with:

- A short alpha positioning statement.
- The exact verification commands and CI run link.
- The implemented command list.
- The "Not Built Yet" section above.
- A pointer to the next milestone: Eye capture.
