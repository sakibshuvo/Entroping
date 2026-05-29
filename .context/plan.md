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
- `docs/meta/ISSUE_TRACKING.md`, `docs/meta/TEST_STRATEGY.md`, `docs/meta/PROJECT_PROGRESS.md`, and `scripts/regression.sh` define issue tracking, regression coverage, and simple phase-level progress tracking.
- `scripts/start_issue.sh` creates issue-scoped worktrees and deterministic session prompts for multi-session Codex/OpenCode work.
- Issues #1, #2, #3, #4, and #5 are integrated locally: `entroping init --minimal`, `entroping doctor`, QAnstitution local loading/import validation, Hurl discovery, Entroping metadata parsing, tag-filter validation, gate matching, gate assertion compilation, temporary Hurl execution-copy injection, deterministic Hurl subprocess execution, JSON/JUnit reports, latest-run state, and bug Markdown generation.

## Next Milestone: Deterministic Core

Implement only the deterministic path before adding AI, proxy capture, or Studio:

1. Make `entroping init` create a minimal `qanstitution.yaml` and safe project skeleton. **Done in issue #1.**
2. Make `entroping doctor` validate local config, Hurl availability, and optional tools without network calls. **Done in issue #1.**
3. Add QAnstitution file loading and local import handling. **Done in issue #1.**
4. Implement Hurl test discovery and metadata parsing. **Done in issue #2.**
5. Implement QAnstitution gate matching and gate-to-Hurl assertion compilation. **Done in issue #3.**
6. Implement Hurl subprocess execution with timeout, bounded output, cleanup, and redaction. **Done in issue #4.**
7. Emit JSON and JUnit reports. **Done in issue #5.**
8. Wire the checkout demo into README quickstart.

## Completed Slice: Issue #3 Gate Matching And Injection

Outcome: QAnstitution gates match discovered Hurl test metadata and compile into Hurl assertions in temporary execution copies without mutating source `.hurl` files.

Source-of-truth files:

- GitHub issue #3, `Phase 2B: QAnstitution gate matching and temporary Hurl injection`.
- `docs/product/MVP_PLAN.md`, Phase 2 Hurl Runner and Gate Injection.
- `docs/technical/TDS.md`, gate injection and Hurl execution design.
- `docs/technical/QANSTITUTION_REFERENCE.md`, gate syntax and metadata examples.
- `docs/meta/TEST_STRATEGY.md`, regression and security expectations.

Planned boundaries:

- Gate matching should operate on typed QAnstitution conditions and discovered Hurl metadata.
- Gate-to-Hurl compilation should live behind a policy compiler boundary and be tested with fixtures.
- Injection must write temporary execution copies and prove source `.hurl` fixtures are unchanged.

Implemented boundaries:

- `models.hurl` parses shallow request method, URL, and path metadata without executing requests.
- `bridge.policy_to_hurl` matches typed QAnstitution conditions and compiles rule ID, assertion, and enforcement metadata.
- `core.gate_injector` writes deterministic temporary execution copies with `# entroping-gate:` annotations while leaving source `.hurl` files unchanged.

## Completed Slice: Issue #4 Hurl Subprocess Runner

Outcome: execute injected Hurl copies through the external Hurl binary with timeouts, bounded output, cleanup, redaction, and deterministic non-zero failure handling.

Implemented boundaries:

- `core.hurl_runner` invokes Hurl through subprocess argument arrays with `shell=False`.
- Runner results are typed, timeout-aware, redacted, and bounded before printing.
- `entroping run` loads QAnstitution, discovers Hurl files, creates temporary injected execution copies, runs Hurl, cleans run state, and exits deterministically.

## Completed Slice: Issue #5 JSON And JUnit Reports

Outcome: emit machine-consumable JSON and JUnit summaries from deterministic run results so CI and humans can inspect failures without rerunning Hurl.

Implemented boundaries:

- `core.report_writer` writes redacted JSON and JUnit XML from typed run results.
- `entroping run --report json --report junit` writes artifacts under `reports/` and always writes `.entroping/latest-run.json`.
- `entroping report bug` writes a Markdown handoff from the latest failing run or returns an actionable no-run/no-failure message.

## Active Slice: Issue #6 Alpha Demo Quickstart

Outcome: make the checkout demo and README quickstart prove the deterministic alpha loop for a first-time user.

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
9. `docs/meta/PROJECT_PROGRESS.md`
10. `docs/meta/ISSUE_TRACKING.md`
11. `docs/meta/TEST_STRATEGY.md`

For product history, open Obsidian and start with `00_INDEX.md`.

To start an implementation or review session from an issue, dry-run the launcher first:

```bash
scripts/start_issue.sh 6 docs/alpha-demo-quickstart --dry-run
```

## Constraints

- Preserve the locked command namespace.
- Keep `entroping run` deterministic and LLM-free.
- Keep Hurl as the only API execution engine.
- Do not send secrets or raw traffic to LLM providers.
- Keep generated state, reports, local env files, and Graphify output out of Git.
- Treat security and quality checks as release gates.
- Use the feature delivery checklist for TDD, regression, architecture, security, multi-agent, documentation, and commit-readiness gates.
- Use GitHub Issues for individual work items and `docs/meta/PROJECT_PROGRESS.md` for simple Obsidian progress tracking.
