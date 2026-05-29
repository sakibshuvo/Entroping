# Entroping Implementation Plan

**Date:** 2026-05-29  
**Status:** Active implementation scaffold and launch-prep track

## Objective

Turn the current Entroping knowledge base into a credible open-source alpha by building the smallest deterministic governance loop first:

```text
init -> validate QAnstitution -> discover Hurl tests -> inject gates into temp files -> run Hurl -> emit reports
```

The repo should remain usable as an Obsidian vault and as a Codex workspace with fast context rehydration.

## Current Baseline

- Product, technical, user, architecture, and evolution docs are organized under `docs/`.
- Root `README.md` and `00_INDEX.md` are the main public and vault entry points.
- Python package scaffold exists under `src/entroping/`.
- CLI command surface is locked to v4.1.
- Pydantic QAnstitution models and typed condition parsing are in place.
- Bridge compiler boundary modules exist but are mostly placeholders.
- CI runs `scripts/check.sh`.
- Security scan completed on 2026-05-29 and found one low-severity optional proxy dependency issue; the proxy dependency floor was raised to `mitmproxy>=12.2.3`, vulnerable transitives were refreshed, and the all-extras audit is now clean.
- Project-local `AGENTS.md` now captures repository-specific implementation rules.
- `docs/meta/AUTONOMOUS_DEVELOPMENT.md` defines the Codex-first loop, Spec Kit pilot path, and future OpenCode/oMLX worker plan.
- `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, `.github/pull_request_template.md`, and `scripts/feature_gate.sh` define the executable delivery gates for feature work.

## Next Milestone: Deterministic Core

Implement only the deterministic path before adding AI, proxy capture, or Studio:

1. Make `entroping init` create a minimal `qanstitution.yaml` and safe project skeleton.
2. Make `entroping doctor` validate local config, Hurl availability, and optional tools without network calls.
3. Add QAnstitution file loading and local import handling.
4. Implement Hurl test discovery and metadata parsing.
5. Implement QAnstitution gate matching and gate-to-Hurl assertion compilation.
6. Implement Hurl subprocess execution with timeout, bounded output, cleanup, and redaction.
7. Emit JSON and JUnit reports.
8. Wire the checkout demo into README quickstart.

## Explicitly Deferred

- LiteLLM Architect implementation.
- OpenAPI-to-Hurl generation.
- mitmproxy `watch`, `freeze`, and `map`.
- Studio TUI.
- Nuitka packaging.
- Hosted/cloud features.
- Graphify-generated artifacts in Git.

## Working Context Loop

At the start of a new Codex thread, read:

1. `AGENTS.md`
2. `README.md`
3. `00_INDEX.md`
4. `.context/plan.md`
5. `docs/product/MVP_PLAN.md`
6. `docs/technical/TDS.md`
7. `docs/meta/AUTONOMOUS_DEVELOPMENT.md`
8. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`

For product history, open Obsidian and start with `00_INDEX.md`.

## Constraints

- Preserve the locked command namespace.
- Keep `entroping run` deterministic and LLM-free.
- Keep Hurl as the only API execution engine.
- Do not send secrets or raw traffic to LLM providers.
- Keep generated state, reports, local env files, and Graphify output out of Git.
- Treat security and quality checks as release gates.
- Use the feature delivery checklist for TDD, regression, architecture, security, multi-agent, documentation, and commit-readiness gates.
