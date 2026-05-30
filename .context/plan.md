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
- Issues #1 through #6, #11, #13, #15, #17, #19, #23, #25, #29, #31, #33, #35, #37, and #39 are integrated: `entroping init --minimal`, `entroping doctor`, QAnstitution local loading/import validation, Hurl discovery, Entroping metadata parsing, tag-filter validation, gate matching, gate assertion compilation, temporary Hurl execution-copy injection, deterministic Hurl subprocess execution, JSON/JUnit/HTML reports, latest-run state, bug Markdown generation, the local checkout quickstart, env-file Hurl variables, CI live Hurl smoke, deterministic OpenAPI-to-Hurl generation, OpenAPI parameter/example support, deterministic Architect audit coverage, non-secret agent routing config, Brain prompt/provider foundations, staged Architect output writes, user-facing `architect build --prompt`, parser-backed prompt Hurl validation, and safe persona-template creation from `config set`.

## Next Milestone: Deterministic Core

Implement only the deterministic path before adding AI, proxy capture, or Studio:

1. Make `entroping init` create a minimal `qanstitution.yaml` and safe project skeleton. **Done in issue #1.**
2. Make `entroping doctor` validate local config, Hurl availability, and optional tools without network calls. **Done in issue #1.**
3. Add QAnstitution file loading and local import handling. **Done in issue #1.**
4. Implement Hurl test discovery and metadata parsing. **Done in issue #2.**
5. Implement QAnstitution gate matching and gate-to-Hurl assertion compilation. **Done in issue #3.**
6. Implement Hurl subprocess execution with timeout, bounded output, cleanup, and redaction. **Done in issue #4.**
7. Emit JSON and JUnit reports. **Done in issue #5.**
8. Wire the checkout demo into README quickstart. **Done in issue #6.**

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

## Completed Slice: Issue #6 Alpha Demo Quickstart

Outcome: make the checkout demo and README quickstart prove the deterministic alpha loop for a first-time user.

Implemented boundaries:

- `examples/checkout-api/demo_server.py` provides a tiny local API for the smoke Hurl file.
- The fixture Hurl file uses a literal localhost URL so the alpha quickstart does not depend on env-file loading.
- README and fixture docs show the deterministic run plus JSON/JUnit reports.

## Completed Slice: Issue #11 OpenAPI Architect Build

Outcome: make `entroping architect build --new` compile a local OpenAPI source configured at `sources.spec` into deterministic reviewable Hurl files under `tests/generated/`, without calling an LLM or collapsing bridge/compiler boundaries.

Implemented boundaries:

- `bridge.openapi_to_hurl` compiles supported OpenAPI operations into Hurl content without filesystem writes, Hurl execution, or adapter imports.
- `core.openapi_loader` loads local YAML/JSON OpenAPI documents and rejects remote URLs, unsupported schemes, symlinks, non-files, and non-mapping documents.
- `cli.architect build --new` loads QAnstitution, resolves `sources.spec`, writes generated files under `tests/generated/`, and refuses unsupported prompt/merge paths clearly.

## Completed Slice: Issue #13 Environment File Loading

Outcome: make `entroping run --env <name>` load gitignored `envs/<name>.env` files and pass variables to Hurl through subprocess argument arrays so generated OpenAPI tests using `{{base_url}}` are runnable.

Implemented boundaries:

- `core.env_loader` parses simple local dotenv files, rejects path traversal, symlinks, invalid lines, duplicate keys, and invalid variable names.
- Process environment overrides only matching file keys; unrelated process variables are not imported.
- `core.hurl_runner` passes variables to Hurl and redacts variable values from captured output; issue #15 hardens the transport away from secret-bearing argv.
- `cli.run` loads env variables only when `--env` is supplied and keeps missing env files actionable.

## Completed Slice: Issue #15 Hurl Variable Argv Hardening

Outcome: keep environment values out of Hurl process arguments by writing merged variables to a short-lived Hurl variables file and invoking Hurl with `--variables-file <path>`.

Implemented boundaries:

- `core.hurl_runner` writes sorted `KEY=value` lines to a temporary variables file only when variables are present.
- Hurl subprocess command arrays contain the variables-file path, not loaded variable values.
- The temporary variables file is removed after normal, failing, and timeout runs.
- Redaction still includes loaded variable values before outputs reach reports.

## Completed Slice: Issue #17 HTML Run Reports

Outcome: make `entroping run --report html` write a dependency-free human-readable report under `reports/run-latest.html` while preserving existing JSON and JUnit report behavior.

Implemented boundaries:

- `core.report_writer` renders escaped HTML from the existing typed `RunReport` model.
- `cli.run` accepts repeatable `--report html` alongside `json` and `junit`.
- HTML reports include project, environment, summary counts, test status, duration, rule IDs, and escaped Hurl output.

## Completed Slice: Issue #19 Live Hurl Demo Smoke In CI

Outcome: prove the user-facing demo path in GitHub Actions with the real Hurl binary:
start the checkout demo server, generate Hurl tests from OpenAPI, load `--env local`,
run smoke tests, and emit HTML/JSON/JUnit artifacts.

Planned boundaries:

- Keep live Hurl smoke separate from fast unit/regression checks.
- Do not commit generated Hurl tests, env files, reports, or runtime state.
- Keep logs actionable while preserving env-value redaction.

Implemented boundaries:

- `scripts/live_demo_smoke.sh` copies the checkout fixture into a temporary workspace,
  starts the demo server, generates OpenAPI Hurl tests, writes a local env file, runs
  smoke tests with HTML/JSON/JUnit reports, and optionally copies report artifacts.
- CI pins Hurl `8.0.1`, verifies the upstream release checksum, runs the live smoke
  after the fast regression job, and uploads generated reports as workflow artifacts.
- Local tests exercise the smoke script with a fake Hurl binary so contributors do not
  need Hurl installed for the normal regression suite.

## Completed Slice: Issue #23 OpenAPI Parameters And Schema Examples

Outcome: make `architect build --new` generate useful Hurl for common OpenAPI
operations with path, query, header, and cookie parameters plus source-grounded
request examples/defaults.

Planned boundaries:

- Keep the OpenAPI compiler pure: no filesystem writes, Hurl execution, adapter imports,
  or LLM calls.
- Use safe Hurl variables for parameter fallbacks and literal values only when OpenAPI
  provides examples, defaults, constants, or enums.
- Reject unsafe parameter names, locations, control characters, and unsupported
  parameter value shapes before emitting Hurl.
- Exercise the behavior through unit tests, CLI adapter tests, and the checkout demo
  fixture used by the live CI smoke.

Implemented boundaries:

- `bridge.openapi_to_hurl` supports common path/query/header/cookie parameter rendering
  and schema example/default/const/enum request bodies.
- OpenAPI literal rendering rejects Hurl template delimiters, non-finite numbers, unsafe
  parameter names, and fallback variable collisions before emitting `.hurl`.
- The checkout demo now includes a parameterized lookup endpoint covered by the live CI
  Hurl smoke.

## Completed Slice: Issue #25 Deterministic Architect Audit Coverage

Outcome: make `architect audit` report OpenAPI operations that do not have committed
Hurl coverage, without calling an LLM or executing Hurl.

Implemented boundaries:

- Keep audit comparison in a pure bridge module.
- Use discovered executable Hurl tests with metadata comments, especially `source=openapi`
  and `operation_id`, as the coverage signal.
- Support Markdown and raw JSON output while preserving machine-readable JSON.
- Exit successfully when all operations are covered and non-zero when gaps are found.

## Completed Slice: Issue #29 Non-Secret Agent Config Commands

Outcome: make `config list` and `config set` real deterministic commands for
Builder/Auditor/Breaker model routing, without storing credentials or calling model
providers.

Implemented boundaries:

- Keep updates in a core filesystem adapter that validates the effective QAnstitution
  before mutation and validates the updated temp file before replacing the original.
- Reject empty, control-character, and secret-looking model identifiers through the
  domain schema.
- Preserve existing agent persona source, temperature, and max token settings when only
  changing the model.
- Create missing roles with `agents/<role>.md`, `temperature: 0.0`, and the requested
  model.
- Use exclusive random same-directory temporary files so predictable symlink paths
  cannot receive config content.
- Keep CLI output human-readable and non-secret.

## Completed Slice: Issue #31 Architect Brain Foundation

Outcome: add deterministic Brain foundations for future LLM-backed Architect commands
without calling providers from `entroping run` or tests.

- Added a lazy LiteLLM boundary without wiring it into `entroping run`.
- Loaded Builder/Auditor/Breaker persona files through validated non-secret config.
- Defined structured output models for generated Hurl edits before making provider calls.
- Added prompt package assembly that rejects secret-shaped content and unsafe context paths.
- Keep all model invocation outside deterministic CI/run paths.

## Completed Slice: Issue #35 Architect Prompt Build

Outcome: wire `architect build --prompt` to the Brain foundation while keeping
`entroping run` deterministic and LLM-free.

- Loaded the configured Builder persona and model routing from the effective
  QAnstitution.
- Built a redaction-checked prompt package with scoped intent and requested tags.
- Invoked LiteLLM only through the Brain adapter boundary.
- Parsed raw provider JSON into `ArchitectEditSet` before filesystem writes.
- Reused the staged Architect writer so generated Hurl files are marked
  `# entroping: source=architect` and non-Architect files are not overwritten.
- Redacted untrusted provider summaries, warnings, and errors before CLI output.

## Completed Slice: Issue #37 Prompt Hurl Validation

Outcome: validate prompt-generated Hurl through `hurlfmt --out json` before
Architect writes generated files.

- Added a `core.hurl_validator` subprocess adapter with argument arrays,
  timeouts, temporary file cleanup, and no raw provider-content echo on failure.
- Validated every prompt-generated edit after structured parsing and tag injection
  but before staged filesystem writes.
- Kept validation all-or-nothing: one invalid edit prevents every generated file
  from being written.
- Hardened Architect edit paths against control characters.

## Next Slice: Architect Minimal Hardening

Planned direction:

- Decide whether the next Architect slice should be merge strategy, refactor,
  prompt-generation UX hardening, or the Eye capture spike.
- Keep provider failures explicit and keep deterministic `run` isolated from model access.

## Explicitly Deferred

- Complete LiteLLM Architect refactor workflow.
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
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
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
