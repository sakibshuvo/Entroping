# Entroping Implementation Plan

**Date:** 2026-05-31
**Status:** v0.4 integration and stable-core evidence track

## Objective

Keep the open-source alpha credible by preserving the deterministic governance
loop while tightening the places that can create requirement drift, weak context
handoff, or multi-agent workflow friction:

```text
init -> validate QAnstitution -> discover Hurl tests -> inject gates into temp files -> run Hurl -> emit reports
```

The repo should remain usable as an Obsidian vault, a GitHub issue-driven
project, and a Codex workspace with fast context rehydration.

## Current Baseline

- Product, technical, user, architecture, and evolution docs are organized under `docs/`.
- Root `README.md` and `docs/meta/VAULT_INDEX.md` are the main public and vault entry points.
- Python package and CLI implementation exist under `src/entroping/`.
- CLI command surface is locked to v4.1.
- Pydantic QAnstitution models and typed condition parsing are in place.
- Runtime `ignore_failures` exceptions are deterministic: active entries skip
  only matching Entroping-injected QAnstitution gates in temporary execution
  copies, expired entries block before Hurl execution, and entries targeting
  selected tests fail closed when no injected gate matches.
- Known-failure expiry validation is now shared across policy loading,
  `doctor --ci`, runtime gate injection, and gate-injection reports:
  malformed dates fail QAnstitution loading, and expired exceptions fail CI
  readiness before a policy can be treated as ready.
- Deterministic OpenAPI generation now validates every compiled Hurl file
  before writing, avoids partial generated output on parser failure, and can
  focus regeneration to operations changed from a Git base ref.
- Deterministic OpenAPI generation also emits auth-negative Hurl tests under
  `tests/generated/security/` for operations with supported HTTP bearer/basic
  or API-key header/query/cookie schemes and explicit `401`/`403` responses;
  unsupported schemes are warnings rather than guessed tests.
- HTML run reports escape header fields, summary text, rule IDs,
  known-failure summaries, and captured Hurl output before rendering.
- Common filesystem symlink component traversal is centralized in
  `entroping.core.path_safety`; adapters keep local exception types and
  user-facing messages while sharing the same traversal primitive.
- Public onboarding is launch-first: README points new users to the demo,
  public docs, roadmap, and a short project-context handoff, while MkDocs groups
  deeper references by reader task instead of exposing maintainer memory as a
  flat nav.
- Local AI job orchestration can route affordable worker jobs through OpenCode
  by default or direct DeepSeek API with `--engine deepseek-api`; both paths
  write ignored artifacts for Codex review and never apply patches or affect
  Entroping runtime commands.
- Eye onboarding is honest about real proxy constraints: `watch` users should
  start in local/dev environments, expect per-client mitmproxy CA setup, and
  treat capture authorization and artifact review as their responsibility.
- Eye capture now fails closed unless `watch` has an explicit scope from
  `--target`, `--scope-host`, or `--scope-url-prefix`; out-of-scope and
  malformed flow URLs are ignored before persistence, while in-scope traffic is
  still redacted before storage.
- `freeze --dry-run` now previews selected redacted records, generated Hurl or
  WireMock output paths, golden status, and counts-only redaction categories
  without writing generated artifacts or approval manifests.
- `run --dry-run` now previews selected Hurl files, selector evidence, gate
  injection counts, missing variable names, requested report paths, and
  execution settings without invoking Hurl, writing latest-run state, writing
  run events, writing executed-result reports, or mutating source `.hurl`.
- Eye traffic-state retention keeps local SQLite state bounded with SQL-level
  stale-row deletion while preserving insertion-order reads for retained
  events.
- Constrained agent or downstream sessions can run `scripts/cli_smoke.sh` to
  prove the CLI boots, reports a version, initializes minimal governance, and
  runs `doctor` without requiring Hurl runtime execution.
- Shell-completion onboarding should point to Typer's existing global
  `entroping --install-completion` and `entroping --show-completion` options;
  it must not introduce a custom Entroping completion command.
- Brand terminology is intentional: `qanstitution.yaml` remains the canonical
  policy filename, the QAnstitution/Traffic/Hurl philosophy is preserved, and
  public copy must not imply Entroping is an autonomous agent swarm.
- Prompt-backed Architect generation defaults to Builder and can select Breaker
  with `architect build --agent breaker --prompt ...`; Breaker output is
  generated before review and committed as deterministic Hurl before `run`.
- `architect refactor --preview` uses the same provider, managed-block merge,
  and Hurl validation path as write mode, then prints a redacted unified diff
  and writes only the value-free agent run manifest without mutating target
  Hurl files.
- Auditor reviews are explicit through `architect audit --focus auditor`; they
  validate provider JSON before display, write no files, and never affect
  deterministic `run`.
- Prompt-backed Architect build, refactor, and Auditor review evidence includes
  provider, latency, token counts when available, and estimated cost when local
  QAnstitution rate hints are configured, while manifests remain value-free.
- `entroping report agent-bundle --output md|json` summarizes sanitized
  `.entroping/agent-runs/*.json` evidence for configured Builder, Breaker, and
  Auditor roles, reports missing/invalid/conflicting role evidence as review
  findings, and does not call providers, Hurl, or `entroping run`.
- `entroping report policy-diff --base <path> --current <path> --output md|json`
  compares two existing effective-policy JSON artifacts and emits
  schema-versioned import and gate deltas without loading policy files, fetching
  registries, calling providers, executing Hurl, or failing valid changed diffs.
- Traffic-derived written artifacts from `freeze`, `freeze --mock`, and
  `map --export png` now get value-free approval manifests under
  `reports/approvals/` with generated paths, checksums, deterministic source
  fingerprints, and counts-only redaction summaries.
- `entroping report capture-summary --output md|json` reads existing redacted
  Eye traffic state through the read-only store path and summarizes derived
  sessions, methods, hosts, dependency targets, status families, and redaction
  categories without rendering raw traffic values.
- `entroping report redaction --output md|html` reads existing redacted Eye
  traffic state through the read-only store path and preserves no-mutation
  report generation for review-only workflows.
- Traffic redaction now records low/high confidence for bodies and exchanges.
  Malformed JSON, unknown text payloads, and multipart summaries stay available
  for local review, but `freeze`, `freeze --mock`, and `map --export png` fail
  closed before writing artifacts from low-confidence records.
- `entroping map` and dependency-drift observation loading read existing
  redacted Eye traffic state through the read-only store path instead of
  initializing or migrating local SQLite state during evidence review.
- `entroping doctor` validates configured Builder/Auditor/Breaker persona files
  through the same root-bounded persona loader used at runtime and reports
  `api_key_env` readiness without printing values or calling providers.
- `entroping doctor --output json` emits schema version
  `entroping.doctor.v1` for agent and CI setup health without changing human
  doctor output or exit semantics.
- `entroping doctor --ci` adds strict local CI-readiness evidence for Hurl
  availability, safe `.entroping/` and `reports/` paths, suite manifests,
  required Hurl variables, and provider-free `run --ci` expectations without
  calling CI provider APIs, printing env values, or mutating workflows.
- `entroping doctor` checks `hurl --version` through the bounded local
  subprocess boundary, reports compatible, missing, unsupported, and unparsable
  Hurl version states in human and JSON output, and `doctor --ci` fails when
  Hurl compatibility cannot be proven. Entroping's minimum supported Hurl
  version is 4.3.0; reviewed CI examples pin 8.0.1.
- QAnstitution `gate_groups` now let local authors reuse gate collections while
  expanding to ordinary runtime gates, rejecting missing references/cycles,
  preserving import/final semantics, and exposing source group provenance in
  effective-policy reports.
- `entroping run` preflights unresolved Hurl `{{variable}}` references in
  selected temporary execution copies before invoking Hurl. It accepts resolved
  variables from env files, shell `HURL_VARIABLE_<name>` values, local Hurl
  `[Options] variable` entries, captures, and known Hurl built-ins, while
  reporting only missing names.
- `entroping run` applies `settings.retry` as a bounded per-file Hurl
  subprocess retry budget. The final attempt status remains authoritative, and
  JSON/JUnit/HTML/review-summary artifacts expose retry count, attempt status,
  exit code, duration, and unstable pass-after-retry signals without raw
  per-attempt output.
- `entroping run` records the effective per-test `timeout_ms` in
  JSON/JUnit/HTML/review-summary evidence. Hurl subprocess timeouts use status
  `timeout`, exit code `124`, and timeout-specific report findings so time
  budget failures are distinct from assertion failures.
- `entroping run --changed-from <ref>` selects existing changed `.hurl` files
  from Git diff for fast local or agent feedback; it is not a replacement for
  full-suite release gates.
- `entroping run --tag-expression <expr>` selects Hurl tests with a
  deterministic `and`/`or`/`not` parser over Entroping metadata tags, reports
  selected/skipped counts without executing filtered-out files, and preserves
  repeatable `--tag` OR semantics.
- `entroping run --operation-id <id>` selects existing Hurl tests by exact
  committed OpenAPI `operation_id` metadata, rejects selector conflicts before
  Hurl execution, and writes operation ID evidence into JSON/JUnit/HTML reports.
- `entroping run --rerun-failures` selects failed source `.hurl` files from
  `reports/run-latest.json` or `.entroping/latest-run.json`, reuses the report
  environment unless `--env` overrides it, rejects unsafe or stale paths before
  execution, and remains fast feedback rather than release proof.
- `entroping run --suite <name>` loads committed `suites/<name>.yaml`
  manifests with schema `entroping.suite.v1`, root-bounded path globs, tags,
  env, reports, parallel, and drift settings without changing default `run`
  behavior or calling providers.
- `entroping report failure-bundle` writes a sanitized local handoff directory
  with manifest schema `entroping.failure-bundle.v1`, sanitized run JSON,
  generated bug Markdown, failed-test Hurl metadata, and already-reviewed local
  report artifacts. It refuses missing/latest-passing runs, raw traffic state,
  local env files, source Hurl contents, and unsafe artifact paths.
- `entroping report delta --base <path> --current <path> --output md|json`
  compares two local JSON run reports without executing Hurl, calling
  providers, or uploading results. It emits schema
  `entroping.run-delta-report.v1` with added, resolved, changed, unchanged,
  latency, and policy-gate deltas, and it never renders raw stdout/stderr.
- `entroping report badges` writes local Shields endpoint JSON files from
  existing run, effective-policy, OpenAPI audit, and traceability JSON reports.
  `entroping report traceability --output json` provides the story-traceability
  source report; badge generation fails before writes when source reports are
  missing or malformed and does not call hosted badge services.
- `entroping report traceability --output md|json` now links Hurl `story_id`
  metadata to local `docs/stories/*.md` story documents, reports missing local
  stories, Markdown stories without tests, duplicate story IDs, malformed story
  metadata, and unsafe story paths, and remains local-only with no Jira,
  Notion, Linear, or monday.com calls.
- `entroping report sarif` writes SARIF 2.1.0 from local JUnit, drift, and
  optional traceability findings for code-scanning import. It does not execute
  Hurl, call providers, or upload results.
- `entroping report promote-drift-baseline` validates a reviewed
  `reports/drift-baseline.candidate.json` before atomically writing the active
  `.entroping/drift-baseline.json`; `run` still never auto-approves drift.
- `entroping architect audit --focus logic` emits an
  `entroping.openapi-audit.v1` operation-to-Hurl matrix covering covered,
  uncovered, ambiguous, and stale OpenAPI operation mappings without calling
  providers.
- `entroping architect audit --focus logic --changed-from <ref>` attaches an
  `entroping.openapi-breaking-diff.v1` report for deterministic OpenAPI
  evolution review: removed/added operations, status changes, newly required
  request inputs, and practical JSON response-shape changes, with Hurl metadata
  links when committed tests exist and no generated/deleted test files.
- When redacted Eye traffic state exists, `architect audit --focus logic` also
  attaches an `entroping.traffic-openapi-audit.v1` traffic-vs-OpenAPI route
  section that flags undocumented observed routes and lists documented/spec-only
  route evidence without raw query strings, headers, cookies, bodies, host
  userinfo, or captured values.
- Example coverage includes REST-style checkout/support fixtures plus
  GraphQL-over-HTTP and SOAP-over-HTTP fixtures that use ordinary Hurl
  assertions instead of adding protocol-specific runtime engines.
- Bridge compiler boundaries are implemented for OpenAPI-to-Hurl, policy-to-Hurl,
  traffic-to-Hurl, traffic-to-WireMock, traffic-to-graph, story traceability,
  and managed-block Hurl merges.
- CI runs `scripts/regression.sh --security`, `scripts/audit_quality.sh`, and
  the live Hurl demo smoke.
- Security scan completed on 2026-05-29 and found one low-severity optional proxy dependency issue; the proxy dependency floor was raised to `mitmproxy>=12.2.3`, vulnerable transitives were refreshed, and the all-extras audit is now clean.
- Project-local `AGENTS.md` now captures repository-specific implementation rules.
- `docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md` defines the Codex-first loop, Spec Kit pilot path, and future OpenCode/oMLX worker plan.
- `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, `.github/pull_request_template.md`, and `scripts/feature_gate.sh` define the executable delivery gates for feature work.
- `docs/meta/ISSUE_TRACKING.md`, `docs/meta/TEST_STRATEGY.md`, `docs/meta/PROJECT_PROGRESS.md`, `scripts/regression.sh`, and `scripts/audit_quality.sh` define issue tracking, regression coverage, quality audit coverage, and simple phase-level progress tracking.
- `scripts/performance_smoke.py` produces local release-owner evidence for large Hurl suites, parallel runner behavior, report size, and SQLModel traffic-store retention.
- CI includes an `install-smoke` matrix for Linux, macOS, and Windows setup claims. Linux uses a pinned Hurl archive, macOS uses Homebrew Hurl, and Windows is explicitly doctor-only until Hurl-backed execution is reviewed.
- `scripts/community_profile_audit.sh` and `.github/workflows/scorecard.yml` provide public trust-signal hygiene without adding a pull-request gate.
- Apache-2.0 licensing and package metadata are in place for the public core; `docs/product/OPEN_CORE_BOUNDARIES.md` now defines what stays core versus what can become commercial.
- `docs/technical/POLICY_PACK_LAYOUT.md`, `examples/policy-packs/api-baseline/`,
  and `examples/policy-packs/owasp-api-top-10/` define reusable QAnstitution
  policy packs as local importable files plus provenance metadata, without
  adding registry or runtime manifest dependency.
- `entroping config vendor-policy-pack` vendors reviewed local policy-pack
  directories under `policy-packs/`, validates manifest and QAnstitution
  entrypoint evidence, preserves final-gate behavior, and appends local imports
  without remote registry coupling.
- `entroping config test-policy-pack` validates reviewed local policy-pack
  directories before vendoring or publishing, emits text or JSON pass/fail
  evidence, and writes nothing to the consumer project.
- `entroping run` writes `.entroping/latest-run-events.jsonl`, a sanitized
  `entroping.run-events.v1` JSONL progress log for CI wrappers and coding
  agents, covering run start, selected tests, redacted results, artifact
  writes, no-match/error events, and completion status.
- `entroping run --fail-fast` stops scheduling new Hurl files after the first
  failing result. Sequential runs stop immediately; parallel runs let already
  scheduled workers finish and report selected, executed, not-scheduled, and
  fail-fast summary evidence.
- `entroping report gate-injection --target <path> --output md|json` explains
  selected-file QAnstitution gate injection without running Hurl, writing
  temporary execution copies, or mutating source `.hurl` files.
- `entroping report gate-coverage --output md|json` maps effective
  QAnstitution gates to committed Hurl files, tags, operation IDs, request
  methods, and redacted paths without executing Hurl, injecting assertions, or
  calling providers.
- `entroping report artifact-manifest` writes local checksum evidence for
  standard report artifacts without embedding artifact contents or claiming
  signing/attestation.
- `entroping init --github-actions` installs the packaged, reviewed starter
  workflow at `.github/workflows/entroping.yml`, refuses existing workflows,
  rejects symlinked path components, and keeps the packaged template aligned
  with `examples/github-actions/entroping-ci.yml` without adding secrets,
  provider credentials, hosted-service coupling, or package-index claims.
- `scripts/start_issue.sh` creates issue-scoped worktrees and deterministic session prompts for multi-session Codex/OpenCode work; `scripts/finish_issue.sh` verifies merged PRs and safely removes completed local worktrees.
- Eye capture now has security-first traffic models, pre-persistence redaction, bounded SQLModel-backed SQLite state, and capture-only `watch` wiring through a lazy-loaded mitmproxy adapter.
- Issues #1 through #85, plus validation fixes #95 and #97, are integrated.
  The shipped alpha covers init/doctor, QAnstitution loading/import validation,
  Hurl discovery and metadata, gate injection, deterministic Hurl subprocess
  execution, JSON/JUnit/HTML/drift reports, bug templates, OpenAPI generation
  and audit, env-file variables, live Hurl CI smoke, Brain/LiteLLM prompt
  generation and refactor paths, managed-block merges, architecture boundary
  tests, capture-only `watch`, `freeze`, WireMock mocks, dependency maps,
  package artifact checks, bounded parallel run, and a read-only Studio status
  shell.

## Completed Milestone: Deterministic Core

The deterministic path is available and should remain the regression anchor:

1. Make `entroping init` create a minimal `qanstitution.yaml` and safe project skeleton. **Done in issue #1.**
2. Make `entroping doctor` validate local config, Hurl availability, and optional tools without network calls. **Done in issue #1.**
3. Add QAnstitution file loading and local import handling. **Done in issue #1.**
4. Implement Hurl test discovery and metadata parsing. **Done in issue #2.**
5. Implement QAnstitution gate matching and gate-to-Hurl assertion compilation. **Done in issue #3.**
6. Implement Hurl subprocess execution with timeout, bounded output, cleanup, and redaction. **Done in issue #4.**
7. Emit JSON and JUnit reports. **Done in issue #5.**
8. Wire the checkout demo into README quickstart. **Done in issue #6.**

## Current Milestone: Validation And Hardening

1. Keep public alpha license and package metadata explicit. **Done in issue #58.**
2. Keep capture-only `watch` separate from `freeze` and `map`. **Done in issue #60.**
3. Design traffic-to-Hurl and dependency export before implementation. **Done in issue #59.**
4. Publish `v0.1.0-alpha` only after local and CI release evidence. **Done from commit `abd08c0`.**
5. Keep post-alpha additions small, issue-backed, release-gated, and reflected in
   this context file.
6. Use the validation queue to remove drift, workflow friction, and maintenance
   hotspots before adding larger product surface.

Issue #59 outcome leaves behind `docs/technical/FREEZE_MAP_PLAN.md`, ADR-0008,
and focused implementation issues #66, #67, #68, and #69 for
filtering/sessioning, traffic-to-Hurl freeze generation, safe `freeze` CLI
writes, and dependency map exports. Issues #66 through #69 are implemented;
issue #75 adds WireMock-compatible `freeze --mock` output, and issue #80 adds
optional Graphviz-backed PNG dependency map rendering.
Issues #82 through #85 added package install polish, bounded parallel Hurl
execution, deterministic drift reporting, and the read-only Studio shell.
Issues #95 and #97 removed the remaining generic Architect build placeholder
path and ignored validation coverage artifacts. Issue #93 added the heavier
local quality audit gate for coverage, complexity, maintainability, and
dead-code discovery checks. Issue #94 added the symmetric finish workflow for
post-merge worktree, local branch, label, and project-board cleanup.
Issue #91 implemented the bridge-level story traceability report for Hurl
metadata without adding business-system API clients. Issue #106 exposed that
local report through `entroping report traceability --output md` while keeping
external sync out of scope.
Issue #109 added community-profile auditing and a scheduled/manual OpenSSF
Scorecard workflow without making Scorecard a required pull-request check.
Issue #110 extended drift reports with optional value-free response fingerprints
for status code, selected stable headers, and JSON body shape paths.
Issue #176 extended drift reports with conservative material latency regression
warnings from reviewed `duration_ms` baselines, without adding flags or storing
response values.
Issue #108 added a launch asset kit under `docs/assets/launch/`, linked it from
the README and Obsidian index, and documented the concrete publish order in the
growth plan while keeping raw generated reports and recording sources out of
Git.
Issue #166 removed maintainer-local temp paths from launch rebuild commands and
added a regression guard so public launch docs stay copy/paste portable.
Issue #168 made `scripts/context_pack.sh --mode source` source-archive paths
configurable through `ENTROPING_SOURCE_ROOT`, with a sibling `../entroping-specs`
default instead of a maintainer-local script constant.
Issue #170 replaced maintainer-local repo/source paths in agent and Obsidian
workflow docs with `<repo-root>`, `<source-archive>`, and `ENTROPING_SOURCE_ROOT`
guidance so external agents and contributors can reuse the same flow.
Issue #172 refreshed the public README status language so it describes the repo
as the active alpha implementation without overclaiming production stability.
Issue #174 rewrote the README as a public open-source front door: sourced hype
and runtime-governance positioning first, two-minute live demo proof next, and
deep Obsidian/spec inventory later.
Issue #179 improved Architect validation UX for invalid provider JSON and
parser-rejected Hurl while preserving no-write behavior and raw output redaction.
Issue #199 extended that UX with safe retry guidance: schema/parser failures now
tell users to return only the Architect JSON object, while parser-rejected Hurl
tells users to return syntactically valid Hurl in the selected file only. Both
paths still avoid echoing raw provider output or parser streams.
Issue #90 moved deterministic run orchestration behind `core.run_workflow`,
leaving the CLI adapter responsible for option normalization, output, and exit
mapping.
Issue #184 added a good-first-issue walkthrough. Issue #189 added a downstream
GitHub Actions starter workflow. Issue #195 documents LiteLLM, local Qwen
through Ollama/oMLX, optional `api_base` and `api_key_env` agent metadata, and
the no-provider CI boundary.
Issue #186 adds the TestPyPI-first package-index release runbook, including
Trusted Publishing feasibility, token-free GitHub environments, PEP 440 alpha
versioning, PyPI publish policy, and yank/new-version rollback guidance.
Issue #188 chooses MkDocs Material for the public docs site, adds a minimal
`mkdocs.yml` plus `docs/index.md` scaffold, and keeps the canonical Markdown
tree as the source instead of duplicating docs.
Issue #228 activates that path: CI now runs `mkdocs build --strict` on pull
requests and pushes to `main`, while a separate Pages workflow publishes the
curated `docs/` site from `main`.
Issue #202 defines organization QAnstitution import controls in ADR-0011:
central policy imports remain part of the same effective local policy, must
preserve provenance and `final: true` behavior, and should add effective-policy
evidence before remote registries or approval workflows become runtime features.
Issue #204 documents non-GitHub CI provider recipes without committing untested
native templates: GitLab CI, Buildkite, and CircleCI should start from the same
pinned-Hurl, tagged-Entroping, `doctor`, and `run --ci` shell sequence until a
real provider runner proves a copyable template.
Issue #183 recommends the distribution sequence: keep `uv tool install` first,
activate PyPI/TestPyPI next, prototype Homebrew after the PyPI alpha, and defer
standalone binaries/signing until there is demand.
Issue #225 adds the concrete standalone-binary decision: defer Nuitka and
PyInstaller automation until PyPI alpha, Homebrew tap demand, release-owner
signing/notarization runbooks, and platform support evidence justify the cost.
Issue #223 activates the protected manual package-index workflow: build
distributions without OIDC privileges, then publish to TestPyPI or PyPI through
reviewer-gated GitHub environments and PyPI Trusted Publishing.
Issue #224 adds the Homebrew tap prototype as a formula template and runbook:
the tap should install from a proven PyPI sdist, depend on Hurl, keep optional
extras out of the default formula, and pass local `brew audit`, source install,
`brew test`, `entroping doctor`, and checkout demo smoke before any public tap
claim.
Issue #230 chooses `scripts/demo.sh` as the friendly v0.2 checkout demo
entrypoint while preserving `scripts/live_demo_smoke.sh` as the CI/release
primitive and deferring product-level demo commands until packaging can carry
fixtures cleanly.
Issue #232 simplifies first-hour QAnstitution onboarding by aligning
`init --minimal`, the checkout demo fixture, and the new
`docs/user/QANSTITUTION_FIRST_HOUR.md` guide around three schema-validated
starter gates: status, latency, and request-ID header.
Issue #194 adds a second realistic support-ticket fixture so example coverage
is not overfit to checkout: filtered list reads, required request headers,
POST/PATCH mutations, OpenAPI examples, Hurl smoke tests, QAnstitution method
and path gates, and real-run report guidance.
Issue #205 turns the locked v4.1 CLI surface into an explicit compatibility
audit before stable-core claims. The audit ties README, TDS, command cheat
sheet, ADR-0002, Typer help, deprecated aliases, exit-code policy, and report
artifact paths to regression tests so future command drift is caught by CI.
Issue #207 refreshes the security threat model as a tracked technical document
instead of leaving it only in `/tmp` scan artifacts. The model now covers the
implemented Hurl subprocess, Brain/LiteLLM, Eye/traffic redaction, SQLModel
SQLite state, report, filesystem, dependency, Studio, CI, and residual-risk
issue boundaries that matter before stable-core claims.
Issue #198 closes one of those residual Eye risks by adding a counts-only
redaction review report. `entroping report redaction --output md|html` reads
redacted `.entroping/state.db` records, reports header/query/body redaction
categories and body-summary counts, and writes safe local artifacts under
`reports/` without rendering raw captured values.
Issue #227 closes the optional-runtime CI gap by adding a dedicated
`optional-extras-smoke` workflow lane. The lane installs all optional extras and
boots the LiteLLM, mitmproxy, and Textual adapter boundaries without provider
credentials or live capture, while keeping the default regression path
lightweight.
Issue #231 settles the next Studio boundary before v0.3 expansion. ADR-0010
keeps the roadmap CLI/report-first, allows only optional read-only
report-backed Studio drilldowns over sanitized artifacts or redacted summaries,
and keeps mutation workflows design-only until a separate accepted decision.
Issue #196 adds that accepted design gate without changing runtime behavior:
future Studio write actions must use preview, two-step confirmation, redaction,
rollback, and existing CLI/core use cases before any mutation code lands.
Issue #192 adds read-only applied-gate drilldowns over existing deterministic
artifacts: Studio links latest-run report rule IDs to loaded QAnstitution gate
definitions without running Hurl, calling providers, or editing tests/config.
Issue #190 adds a read-only Studio traffic session browser over redacted
SQLModel-backed state: Studio uses a read-only query path plus existing traffic
session and dependency-graph compilers to show inferred target/dependency route
summaries and safe redaction categories without starting `watch`, rendering raw
traffic values, or mutating runtime state.
Issue #229 defines the alpha Python compatibility policy: Entroping supports
Python 3.12 and 3.13, keeps 3.12 as the syntax and mypy floor, proves both
versions in CI for security regression and optional-extras smoke, and does not
claim Python 3.14 until a future compatibility issue adds evidence.
Issues #279 through #285 close the integration/stable-proof wave: effective
QAnstitution policy reports, public-claims audit, direct dependency license
policy, downstream integration-example guardrails, AI-regression failure proof,
stable-core evidence checks, and backlog-health checks are now implemented as
scripts, tests, docs, and report artifacts rather than prompt-only workflow
rules.
Issues #287 through #291 add the next launch-proof layer: policy-pack smoke
evidence, alpha launch-readiness aggregation, a demo proof matrix for checkout,
AI-regression, policy-pack, launch-readiness, and backlog-health rehearsals, and
README-facing developer use cases plus curated animated previews.
Issue #293 adds a committed release-evidence ledger and validator so repeated
alpha release, last reviewed `main` CI, package-index, and stable-core blocker
evidence is visible without relying on chat memory or live GitHub API calls.
Issue #295 clarifies that committed CI evidence is reviewed evidence as of the
ledger update, not an automatically current assertion about the latest `main`
HEAD.
Issue #297 adds a downstream smoke evidence harness that creates an external
temporary project and runs Entroping through the public CLI, proving the local
core can operate outside its own repository while keeping real downstream user
feedback as an unsatisfied stable-core blocker.
Issue #299 expands the release-evidence ledger so Pages CI and local downstream
smoke evidence are validated alongside main CI and release entries, without
turning maintainer-controlled smoke proof into real downstream user feedback.
Issue #301 aligns release-evidence blockers with stable-core readiness so both
gates report the same unresolved stable-core requirements.
Issue #307 records a repeated alpha release-candidate rehearsal in the
release-evidence ledger, including reviewed CI/Pages run IDs and a passing
`scripts/release_check.sh --require-live-demo` gate, without treating it as
package-index proof, a stable-core compatibility decision, or real downstream
user feedback.
Issue #313 adds a local wheel install smoke that installs the built artifact
into a temporary venv and runs only installed public CLI commands without
depending on TestPyPI, PyPI, or registry credentials.
Issue #314 runs the downstream smoke harness from the release gate when Hurl is
available, keeping local external-project proof fresh without treating it as
real downstream user feedback.
Issue #315 adds an optional release-evidence freshness check that compares the
committed CI and Pages run IDs/commits with latest successful `main` runs
through `gh`, or fixture JSON in tests, while keeping normal strict validation
offline and read-only.
Issue #319 exposes the stable-core blocker issue map directly from
`scripts/stable_core_readiness.py --format json` and Markdown output so future
agents can jump from each unresolved blocker to the tracked GitHub issues that
advance it.
Issue #316 adds `entroping report review-summary`, a provider-neutral Markdown
artifact rendered from local run JSON, JUnit, drift, and optional traceability
evidence without calling CI provider APIs or model providers.
Issue #398 adds `entroping report sarif`, a SARIF 2.1.0 artifact rendered from
local JUnit, drift, and optional traceability evidence without changing
`run --report`, executing Hurl, calling providers, or uploading results.
Issue #399 adds `entroping report promote-drift-baseline`, an explicit reviewed
promotion command that validates the drift-baseline candidate schema and writes
the active local baseline atomically without changing `run` auto-approval rules.
Issue #400 extends deterministic `architect audit --focus logic` output with a
versioned OpenAPI operation-to-Hurl coverage matrix, including ambiguous
multi-test mappings and stale committed `operation_id` references.
Issue #401 adds `entroping config vendor-policy-pack`, a local-only vendoring
workflow that copies reviewed policy packs into a project, validates manifest
and QAnstitution evidence, and appends a local import without registry fetches.
Issue #402 adds `entroping run --suite <name>`, a committed suite-manifest path
that resolves env, tags, paths, reports, parallel, and drift settings through
the existing deterministic run workflow.
Issue #317 extends policy-pack smoke evidence with local provenance manifest
validation for source, license, supported Entroping version, evidence command,
gate files, gate IDs, and final flags without fetching registries.
Issue #318 adds a downstream feedback evidence kit so real external-user
feedback can be collected safely without secrets, private URLs, raw traffic, or
proprietary payloads, while keeping local downstream smoke separate from real
user evidence.
Issue #312 defines the policy-pack distribution path so versioning, imports,
verification, attribution, open-core/premium boundaries, minimum smoke evidence,
and follow-up implementation work are explicit before registries or hosted
catalogs.

Issue #96 is complete. PR #105 merged the post-alpha security review hardening on
2026-05-30 after fixing 14 validated candidates across Brain redaction, Hurl
subprocess isolation, filesystem symlink boundaries, traffic redaction/body
limits, OpenAPI compilation/audit safety, policy gate semantics, Markdown
escaping, generated Hurl writes, and live-demo workdir safety.

## Completed Slice: Issue #316 Artifact-Backed Review Summary

Outcome: downstream CI systems now have a provider-neutral Entroping review
artifact without adding GitHub, GitLab, Buildkite, CircleCI, Jira, Linear, or
model-provider API calls to the deterministic run path.

Implemented boundaries:

- `entroping report review-summary` writes `reports/review-summary.md`.
- The summary reads existing local JSON run reports, JUnit XML, drift JSON, and
  optional local traceability metadata.
- Missing artifacts are listed as missing so the command can still run in
  `if: always()` style CI steps; malformed artifacts fail with clear errors.
- Findings are redacted and Markdown-escaped before rendering.
- The GitHub Actions starter now runs `--report json --report junit --report html`,
  emits annotations, writes the review summary, and uploads `reports/`.

## Completed Slice: Issue #398 SARIF Report Output

Outcome: downstream code-scanning systems can consume Entroping security,
policy, drift, and traceability findings through SARIF without replacing JUnit,
GitHub annotations, or review summaries.

Implemented boundaries:

- `entroping report sarif` writes `reports/entroping.sarif` by default and
  accepts `--output`, `--junit`, `--drift`, and `--traceability`.
- SARIF results reuse the existing local GitHub annotation collector for JUnit,
  drift, and optional traceability evidence.
- Rule IDs are stable, severities map to SARIF `error`, `warning`, and `note`,
  and locations are best-effort path/line references.
- Finding titles, messages, and locations are redacted before serialization;
  absolute project-root paths are relativized.
- The command writes only local artifacts. CI-specific code-scanning upload
  remains an explicit downstream workflow step.

## Completed Slice: Issue #399 Reviewed Drift Baseline Promotion

Outcome: accepted drift-baseline candidates now have a deterministic promotion
command instead of manual copy instructions.

Implemented boundaries:

- `entroping report promote-drift-baseline` reads
  `reports/drift-baseline.candidate.json` by default and writes
  `.entroping/drift-baseline.json` by default.
- Promotion requires the `entroping.drift-baseline.v1` schema marker and
  rejects malformed, stale, future-version, non-object, and non-list-test
  candidates before writing.
- Candidate and output paths must stay under the project root and reject
  symlink component traversal.
- Active baseline writes remain atomic through the shared safe artifact writer.
- `entroping run` still never promotes or overwrites the active drift baseline;
  it only writes reviewable candidate evidence after passing Hurl suites.

## Completed Slice: Issue #400 OpenAPI Operation Coverage Matrix

Outcome: deterministic Architect logic audits now show which committed Hurl
files cover each OpenAPI operation instead of reporting only missing coverage.

Implemented boundaries:

- `architect audit --focus logic --output json` emits
  `schema_version: entroping.openapi-audit.v1`.
- JSON output includes an `operation_matrix` with covered, uncovered, and
  ambiguous operation rows plus project-relative Hurl test paths.
- Markdown output includes the same compact matrix for PR review.
- Stale committed `operation_id` metadata is listed as review evidence without
  changing the existing uncovered-operation pass/fail boundary.
- The deterministic audit remains a pure bridge comparison over OpenAPI
  metadata and discovered Hurl tests; it does not invoke Hurl or model
  providers.

## Completed Slice: Issue #401 Local Policy-Pack Vendoring

Outcome: reviewed local policy packs can now be copied into a consumer project
and imported without hand-editing YAML or adding remote registry behavior.

Implemented boundaries:

- `entroping config vendor-policy-pack --pack <path> [--name <dir>]` copies a
  local pack under `policy-packs/` and appends the resulting local import to
  `qanstitution.yaml`.
- The command validates pack manifests, gate IDs, gate prefixes, final-gate
  declarations, QAnstitution entrypoints, duplicate manifest gates, and final
  override behavior before writing.
- Source and destination paths stay project-bounded and symlink-safe.
- The workflow remains local-only: no remote fetch, registry authentication,
  runtime manifest dependency, paid-service dependency, or automatic update
  check was added.

## Completed Slice: Issue #402 Named Suite Manifests

Outcome: teams can commit reviewable run-suite manifests instead of relying
only on repeated ad hoc `--env`, `--tag`, and `--report` command strings.

Implemented boundaries:

- `entroping run --suite <name>` loads `suites/<name>.yaml` with schema
  `entroping.suite.v1`.
- Suite manifests can define `env`, `tags`, root-bounded `paths` globs,
  `reports`, `parallel`, and `drift_check`.
- Suite execution feeds the existing deterministic Hurl/QAnstitution run
  workflow; it does not call LLM providers and does not alter default `run`.
- `--suite` rejects ad hoc selector conflicts such as `--env`, `--tag`,
  `--report`, `--parallel`, `--drift-check`, and `--changed-from`; `--ci`
  remains the strict exit-code wrapper.

## Completed Slice: Issue #317 Policy-Pack Provenance Manifest Validation

Outcome: the example API-baseline policy-pack manifest now acts as local,
test-backed provenance evidence instead of unverified catalog copy.

Implemented boundaries:

- `entroping-policy-pack.yaml` declares source, license, supported Entroping
  range, evidence command, gate files, gate IDs, and final flags.
- `scripts/policy_pack_smoke.py --strict` validates those manifest claims
  against local files and loaded QAnstitution gates.
- Validation remains local-only: no registry fetch, pack install command,
  package signing, or runtime manifest dependency was added.

## Completed Slice: Issue #318 Downstream Feedback Evidence Kit

Outcome: maintainers now have a sanitized intake path for real external-user
feedback, which is different from maintainer-controlled downstream smoke.

Implemented boundaries:

- `docs/meta/DOWNSTREAM_FEEDBACK_KIT.md` asks for install path, OS, Python,
  Hurl, command used, success or failure, friction, and sanitized logs.
- The kit explicitly rejects secrets, private URLs, raw traffic, proprietary API
  payloads, customer data, unredacted request/response bodies, and internal
  hostnames.
- Release evidence, downstream smoke evidence, contributor guidance, vault
  index, public docs index, and MkDocs navigation link to the kit.
- `scripts/stable_core_readiness.py` keeps the real feedback blocker open but
  marks #318 as done in the blocker issue map.

## Completed Slice: Issue #312 Policy-Pack Distribution And Provenance Path

Outcome: reusable policy packs now have a local-first distribution decision
before any registry, hosted catalog, or premium pack implementation exists.

Implemented boundaries:

- `docs/technical/POLICY_PACK_DISTRIBUTION.md` defines versioning, distribution
  modes, local import verification, provenance, attribution, open-core versus
  premium boundaries, and minimum smoke evidence.
- Distributed packs must become local, inspectable QAnstitution imports before
  deterministic runtime.
- The decision explicitly keeps no registry fetch, no telemetry, no
  paid-service dependency, and no runtime manifest dependency out of
  `entroping run`.
- Follow-up implementation work remains issue-backed.

## Completed Slice: Issue #319 Stable-Core Blocker Issue Map

Outcome: stable-core blockers now point to tracked GitHub issues instead of
depending on chat memory or ad hoc roadmap interpretation.

Implemented boundaries:

- `scripts/stable_core_readiness.py --format json` includes
  `blocker_issue_map`, keyed by the exact blocker names in the readiness report.
- Markdown readiness output includes a `Blocker Issue Map` section with issue
  numbers, titles, URLs, and current dependency status.
- Tests assert that blocker names cannot drift away from the map, and that the
  stable-core blockers still resolve to the intended issue clusters.
- The readiness result remains blocked until package-index proof,
  stable-core compatibility decision, and real downstream user feedback are
  actually available.

## Completed Slice: Issue #307 Repeated Alpha Release Evidence

Outcome: release evidence now includes a second reviewed alpha release cycle
without pretending a new public GitHub release or package-index publish
happened.

Implemented boundaries:

- `docs/meta/release-evidence.json` records `v0.1.2-alpha-rc.1` as a local
  release-candidate rehearsal tied to the latest reviewed CI and Pages runs.
- `scripts/release_evidence.py --strict` validates release-candidate evidence,
  including the exact release gate, pass result, CI/Pages run IDs, release
  notes, and alpha/stable-core boundary language.
- `scripts/stable_core_readiness.py` and `scripts/launch_readiness.py` no
  longer report repeated release evidence as an unresolved blocker.
- Stable-core remains false until package-index proof, stable-core
  compatibility decision, and real downstream user feedback exist.

## Completed Slice: Issue #315 Release Evidence Freshness Check

Outcome: maintainers can ask whether the release-evidence ledger's reviewed CI
and Pages runs are stale without making normal release validation
network-dependent.

Implemented boundaries:

- `scripts/release_evidence.py --check-freshness --strict` compares recorded
  `latest_main_ci` and `latest_pages_ci` run IDs/commits against latest
  successful `main` runs when `gh` is available and authenticated.
- Fixture input keeps freshness checks deterministic in tests and offline review.
- Missing or unauthenticated `gh` reports `freshness.status=unavailable` without
  failing the default offline strict validation path.
- The command never mutates `docs/meta/release-evidence.json`; maintainers must
  refresh the ledger deliberately after reviewing new evidence.

Completed security-review context: repository-wide scan artifacts were written
under `/tmp/codex-security-scans/Entroping/eb08827323c6_20260530T160200Z`, all
14 deduplicated candidates have validation/verification ledgers, and no
unresolved finding remained in the merged branch.

Implemented boundaries:

- Prompt and provider-error redaction now catch cookie, API-key, password, Basic
  auth, token, and key-value secret shapes while allowing templated Hurl auth
  placeholders.
- Hurl execution uses a minimal subprocess environment instead of inheriting the
  parent shell environment.
- Env loading, report writing, drift reads/writes, traffic state, and generated
  Hurl writes reject symlinked path components before resolving or writing.
- Traffic redaction strips URL userinfo, handles JSON subtypes structurally, and
  caps textual body extraction before decode/redaction work.
- OpenAPI compilation rejects secret-like fallback variables and Hurl template
  delimiters in JSON object keys.
- OpenAPI audit coverage requires matching method/path evidence, not only
  spoofable `operation_id` metadata.
- Policy gates reject no-op comments and Hurl section headers.
- Markdown renderers for audit and traceability escape HTML metacharacters.
- The live demo smoke script refuses non-empty custom workdirs instead of
  deleting their contents.

Latest local evidence:

- `PYTHONPATH=src uv run pytest tests/test_openapi_loader.py tests/test_release_docs.py -q`: 15 passed.
- `PYTHONPATH=src uv run pytest tests/test_openapi_loader.py --cov=entroping.core.openapi_loader --cov-report=term-missing -q`: 10 passed; `core.openapi_loader` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_validator.py --cov=entroping.core.hurl_validator --cov-report=term-missing -q`: 5 passed; `core.hurl_validator` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_merge.py tests/test_architect_output_parser.py --cov=entroping.bridge.merge --cov=entroping.brain.output_parser --cov-report=term-missing -q`: 23 passed; `bridge.merge` and `brain.output_parser` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_to_graph.py --cov=entroping.bridge.traffic_to_graph --cov-report=term-missing -q`: 6 passed; `bridge.traffic_to_graph` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_report_writer.py --cov=entroping.core.report_writer --cov-report=term-missing -q`: 12 passed; `core.report_writer` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_redactor.py --cov=entroping.core.traffic_redactor --cov-report=term-missing -q`: 10 passed; `core.traffic_redactor` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_prompt_builder.py --cov=entroping.brain.prompt_builder --cov-report=term-missing -q`: 16 passed; `brain.prompt_builder` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_story_traceability.py --cov=entroping.bridge.story_traceability --cov-report=term-missing -q`: 6 passed; `bridge.story_traceability` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_store.py --cov=entroping.core.traffic_store --cov-report=term-missing -q`: 10 passed; `core.traffic_store` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_safety.py --cov=entroping.brain.safety --cov-report=term-missing -q`: 9 passed; `brain.safety` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_persona_loader.py tests/test_litellm_client.py --cov=entroping.brain.persona_loader --cov=entroping.brain.litellm_client --cov-report=term-missing --cov-fail-under=100 -q`: 24 passed; Brain provider/persona boundary modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_metadata.py --cov=entroping.models.hurl --cov-report=term-missing -q`: 11 passed; `models.hurl` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_discovery.py --cov=entroping.core.hurl_discovery --cov-report=term-missing -q`: 11 passed; `core.hurl_discovery` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_policy_to_hurl.py --cov=entroping.bridge.policy_to_hurl --cov-report=term-missing -q`: 17 passed; `bridge.policy_to_hurl` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_gate_injector.py --cov=entroping.core.gate_injector --cov-report=term-missing -q`: 12 passed; `core.gate_injector` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_runner.py --cov=entroping.core.hurl_runner --cov-report=term-missing -q`: 20 passed; `core.hurl_runner` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_sessions.py tests/test_traffic_to_hurl.py tests/test_traffic_to_wiremock.py --cov=entroping.bridge.traffic_sessions --cov=entroping.bridge.traffic_to_hurl --cov=entroping.bridge.traffic_to_wiremock --cov-report=term-missing -q`: 38 passed; targeted traffic compiler modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_config_loader.py tests/test_config_writer.py tests/test_env_loader.py --cov=entroping.core.config_loader --cov=entroping.core.config_writer --cov=entroping.core.env_loader --cov-report=term-missing -q`: 58 passed; targeted config/env modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_openapi_to_hurl.py tests/test_architect_audit.py --cov=entroping.bridge.openapi_to_hurl --cov=entroping.bridge.openapi_audit --cov-report=term-missing -q`: 39 passed; `bridge.openapi_to_hurl` and `bridge.openapi_audit` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_safe_write.py --cov=entroping.core.safe_write --cov-report=term-missing -q`: 12 passed; `core.safe_write` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_dependency_mapper.py tests/test_drift_report.py tests/test_traffic_models.py tests/test_studio_status.py --cov=entroping.core.dependency_mapper --cov=entroping.core.drift_report --cov=entroping.models.traffic --cov=entroping.studio.status --cov-report=term-missing --cov-fail-under=100 -q`: 49 passed; targeted support modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_proxy.py tests/test_freeze.py --cov=entroping.core.traffic_proxy --cov=entroping.core.freeze --cov-report=term-missing --cov-fail-under=100 -q`: 42 passed; Eye proxy/freeze modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_architect_prompt_build.py tests/test_architect_refactor.py tests/test_architect_writer.py --cov=entroping.brain.architect_build --cov=entroping.brain.architect_refactor --cov=entroping.brain.architect_writer --cov-report=term-missing --cov-fail-under=100 -q`: 57 passed; Architect workflow modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_cli.py --cov=entroping.cli.main --cov-report=term-missing --cov-fail-under=100 -q`: 85 passed; CLI adapter at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_ci_workflow.py tests/test_release_docs.py tests/test_agent_workflow_docs.py -q`: 15 passed.
- `scripts/regression.sh --security`: 682 passed; Bandit and default/all-extras dependency audits passed.
- `scripts/audit_quality.sh`: 682 passed with the default 100 percent coverage gate, 100.00 percent total coverage, and passing Radon/Vulture gates.

## Completed Slice: Issue #90 Run Workflow Extraction

Outcome: `entroping run` no longer owns discovery, env loading, gate injection,
Hurl execution, report writes, drift comparison, and exit-code policy directly
inside the Typer adapter.

Implemented boundaries:

- `core.run_workflow.execute_run_workflow` owns the deterministic governance
  loop and returns a typed `RunWorkflowResult`.
- The CLI still normalizes `--tag` and `--report`, prints user-facing messages,
  and maps no-match behavior to CI/non-CI exit codes.
- JSON, JUnit, HTML, drift, latest-run state, parallel workers, environment
  variables, temporary execution cleanup, and drift exit-code behavior are
  preserved.
- Focused core tests cover report writing, no-match handling, temporary cleanup,
  and drift exit-code policy.
- `entroping run` CLI complexity dropped from Radon E(34) to C(14).

## Completed Slice: Issue #91 Story Traceability Bridge

Outcome: the dedicated `story_traceability.py` bridge is no longer a placeholder
and the docs now match the shipped local behavior.

Implemented boundaries:

- Discovered Hurl metadata compiles into story/test records with story IDs,
  owners, external doc URLs, tags, and linked test paths.
- Missing `story_id` metadata is reported deterministically.
- One external `doc_url` mapped to multiple story IDs is reported as a
  traceability conflict, while repeated tests for the same story remain valid.
- Markdown rendering escapes table cells for safe local review.
- No Jira, Notion, Linear, monday.com, or other business-system clients are
  introduced in the bridge layer.

## Completed Slice: Issue #106 Traceability Report CLI

Outcome: the story traceability bridge is available through the reporting CLI
without expanding into external business-system integrations.

Implemented boundaries:

- `entroping report traceability --output md` renders the local Markdown
  story/test traceability report from discovered Hurl metadata.
- Empty suites return a successful report with no story-linked tests.
- Missing `story_id` metadata and conflicting external `doc_url` links return a
  failing exit code for CI or reviewer use.
- Unsupported output formats are rejected; Markdown is the only public format.
- Focused CLI coverage remains at 100 percent for `entroping.cli.main`.

## Completed Slice: Issue #94 Finish-Issue Workflow

Outcome: completed issue sessions can be cleaned up deterministically after PR
merge instead of relying on manual branch/worktree judgement.

Implemented boundaries:

- `scripts/finish_issue.sh <issue-number>` verifies the GitHub issue is closed,
  identifies its closing PR, confirms the PR is merged, and checks reported CI
  statuses before local deletion.
- The script refuses dirty, unregistered, branch-mismatched, or current
  worktree removal.
- Squash-merged local branches are deleted only after the closing PR and checks
  are verified.
- GitHub issue labels and Project status are updated on a best-effort basis,
  with warnings when permissions are unavailable.
- Temporary-repo tests cover dry-run output, unsafe dirty worktree rejection,
  and successful clean worktree plus squash-merged branch cleanup.

## Completed Slice: Issue #93 Quality Audit Gate

Outcome: marathon validation and release hardening now have a repeatable local
quality audit separate from the faster regression suite.

Implemented boundaries:

- `scripts/audit_quality.sh` runs the full suite with `pytest-cov` and a default
  100 percent coverage threshold.
- Radon cyclomatic complexity and maintainability-index checks are enforced with
  documented environment thresholds.
- Vulture dead-code discovery runs with a curated confidence threshold.
- Coverage and static-analysis JSON outputs are written only under ignored
  `reports/`, and transient `.coverage` state is removed on exit.
- The script has help, dry-run, and unknown-option smoke tests.

## Completed Slice: Issue #148 CI Security And Quality Enforcement

Outcome: GitHub Actions no longer treats the security and quality gates as
local-only marathon proof.

Implemented boundaries:

- The primary CI checks job runs `scripts/regression.sh --security`, so Bandit
  and default/all-extras dependency audits are part of pull-request and `main`
  push verification.
- The workflow runs `scripts/audit_quality.sh` in a separate `quality-audit`
  job after the fast security regression job.
- The quality-audit job uploads ignored `reports/` artifacts for review when
  available.
- README and `docs/meta/TEST_STRATEGY.md` now distinguish CI-enforced gates from
  local release-owner package/live-demo release checks.

## Completed Slice: Issue #150 Live-Demo Hurl Checksum Pinning

Outcome: the CI live-demo job no longer trusts a `.sha256` sidecar downloaded
from the same upstream release at runtime.

Implemented boundaries:

- `.github/workflows/ci.yml` pins `HURL_VERSION` and the reviewed
  `HURL_SHA256` value for the Linux archive used by `live-demo-smoke`.
- The workflow keeps bounded archive download retries but verifies the archive
  against the in-repo checksum before extracting it.
- The release checklist documents the Hurl bump process: update version,
  compute `sha256sum` locally, update `HURL_SHA256`, and let CI prove the demo
  path.

## Completed Slice: Issue #149 Atomic Artifact Writes

Outcome: core artifact writers now share one durable, symlink-safe write path
instead of maintaining separate direct-write and temp-file implementations.

Implemented boundaries:

- `core.safe_write` writes text and binary artifacts through destination-local
  temporary files, flushes and fsyncs them, rejects symlinked targets and parent
  components, and atomically replaces final targets.
- Existing targets are preserved when temporary writes or replacements fail.
- Freeze-generated Hurl, WireMock mappings, PNG dependency maps, drift reports,
  JSON/JUnit/HTML run reports, and bug reports all route through the shared
  helper while preserving their module-specific public error types.
- `core.safe_write` and `core.report_writer` have 100 percent focused module
  coverage for the touched behavior.

## Completed Slice: Issue #146 Deterministic Support-Module Coverage

Outcome: the remaining deterministic support modules from the issue #112
coverage queue now have focused 100 percent coverage without provider calls,
live network, or UI sessions.

Implemented boundaries:

- `core.dependency_mapper` coverage includes missing state, unsupported export
  values, all printable export modes, traffic-store error wrapping, internal PNG
  misuse protection, Graphviz `OSError`, empty renderer output, and existing PNG
  safety behavior.
- `core.drift_report` coverage includes malformed baseline JSON shapes, invalid
  baseline records, optional metadata defaults, non-file baseline paths, and
  existing symlink/report-write behavior.
- `models.traffic` coverage includes content-type, method, URL, header, tab
  allowance, and timezone-aware timestamp validation.
- `studio.status` coverage includes missing optional Textual dependency,
  missing QAnstitution, QAnstitution load errors, latest-run load errors,
  no-report rendering, and existing latest-run state rendering.

## Completed Slice: Issue #145 Eye Proxy And Freeze Coverage

Outcome: Eye capture and freeze edge cases now have focused 100 percent coverage
without live proxy sessions, external network traffic, or real mitmproxy
processes.

Implemented boundaries:

- `core.traffic_proxy` coverage includes WatchConfig bounds, missing and
  malformed mitmproxy runtime imports, flow-shape errors, target-scope matching,
  body/header variants, bounded text extraction, timestamp fallbacks, and fake
  `run_watch` addon registration.
- `core.freeze` coverage includes missing/empty state, successful Hurl and
  WireMock artifact generation, name/service validation, Hurl validation error
  wrapping, invalid WireMock JSON, path traversal/POSIX/suffix validation,
  non-file targets, resolved symlink escapes, and existing symlink/atomic-write
  protections.

## Completed Slice: Issue #144 Architect Workflow Coverage

Outcome: Architect prompt-build, refactor, and staged writer edge cases now have
focused 100 percent coverage without provider calls or live Hurl execution.

Implemented boundaries:

- `brain.architect_build` coverage includes merge-mode Architect-owned targets,
  manual managed-block merges, invalid and unknown managed blocks, tag metadata
  replacement/insertion, unsafe merge targets, size/encoding/read errors, and
  resolved symlink escapes.
- `brain.architect_refactor` coverage includes empty/unsafe target globs,
  resolved symlink escapes, directory targets, invalid managed blocks,
  stat/read/encoding/empty target errors, and selected-target enforcement
  before writes.
- `brain.architect_writer` coverage includes unsafe refactor paths, resolved
  escapes, symlink and non-file preflight failures, blank-header helpers,
  newline preservation, atomic replacement failures, and temporary-write
  failures.

## Completed Slice: Issue #157 Brain Provider And Persona Boundary Coverage

Outcome: the remaining Brain provider/persona boundaries now have focused 100
percent coverage without invoking LiteLLM providers or external networks.

Implemented boundaries:

- `brain.persona_loader` coverage includes URL/absolute/non-Markdown/missing
  persona sources, symlinked persona paths, stat/read failures, size limits,
  UTF-8 errors, empty content, control characters, and secret-like content.
- `brain.litellm_client` coverage includes optional dependency absence,
  installed modules without `completion`, provider boundary re-raise behavior,
  redacted provider exceptions, malformed choices/content responses, object
  attribute response shapes, usage type fallbacks, model defaulting, and lazy
  completion loading.

## Completed Slice: Issue #159 CLI Adapter Coverage

Outcome: the Typer CLI adapter now has focused 100 percent coverage without
changing the locked v4.1 command surface.

Implemented boundaries:

- Doctor/config coverage includes missing Hurl, missing/invalid QAnstitution,
  no-source/no-agent display, source field display, description display, and
  agent `max_tokens` display.
- Architect/watch/run/report coverage includes unsupported strategies, missing
  audit spec, keyboard-interrupted capture, no-match CI exit policy, failed
  stdout printing, report-bug no-failure handling, and report writer errors.
- Helper coverage includes audit focus normalization, remote/absolute spec
  reference handling, generated Hurl path rejection, symlinked generated output
  rejection, non-OpenAPI overwrite rejection, and outside-CWD path display.

## Completed Slice: Issue #112 100 Percent Coverage Release Gate

Outcome: 100 percent meaningful coverage is now the default quality-audit gate,
not only the target tracked by issue slices.

Implemented boundaries:

- `scripts/audit_quality.sh` defaults `ENTROPING_COVERAGE_FAIL_UNDER` to `100`
  and documents the default in help output.
- `docs/meta/TEST_STRATEGY.md` states that `scripts/audit_quality.sh` enforces
  the 100 percent default, and any lower threshold must be an explicit tracked
  override.
- The latest full local quality audit passed with 682 tests, 100.00 percent
  total coverage, and passing Radon plus Vulture gates.

## Completed Slice: Issue #85 Read-Only Studio Status Shell

Outcome: `entroping studio --env <name>` no longer uses the generic placeholder
for the supported local read-only path.

Implemented boundaries:

- The command requires the optional Studio/Textual extra and returns actionable
  `uv sync --extra studio` guidance when it is missing.
- The first status shell reads only local state: QAnstitution project, latest
  run summary, existing report artifacts, and traffic-state availability.
- No tests, config, `.entroping` state, or report files are mutated by Studio.
- Full interactive TUI navigation, failure drilldown, and traffic-session views
  remain later Studio work.

## Completed Slice: Issue #84 Deterministic Drift Report MVP

Outcome: `entroping run --drift-check` and `--report drift` compare the current
sanitized run report against a local baseline without invoking AI providers.

Implemented boundaries:

- The MVP baseline path is `.entroping/drift-baseline.json`; active baselines
  are promoted manually from reviewed candidate artifacts.
- Drift comparison is deterministic and limited to current structured run-report
  fields: test path, Hurl status, exit code, injected QAnstitution rule IDs,
  and optional value-free response fingerprints.
- Missing baselines produce an actionable CLI message and a machine-readable
  `missing_baseline` finding when `--report drift` is requested.
- `--drift-check` affects the final exit code only after Hurl execution
  completes, so Hurl failures are not hidden by baseline problems.

## Completed Slice: Issue #197 Reviewed Drift Baseline Workflow

Outcome: `entroping run --report drift` now writes
`reports/drift-baseline.candidate.json` after passing Hurl suites so users can
review and deliberately promote drift baselines without treating current
behavior as automatically approved.

Implemented boundaries:

- The active `.entroping/drift-baseline.json` file is never written by the run
  workflow.
- Candidate baselines exclude stdout, stderr, execution paths, volatile
  headers, cookies, authorization data, raw response bodies, and raw values.
- Candidate writes use the same symlink-safe artifact writer as reports.
- The user guide and command references describe candidate review, diff, and
  promotion before baseline updates.

## Completed Slice: Issue #203 Versioned Report Schemas

Outcome: machine-readable report payloads now carry explicit v1 schema versions
so downstream dashboards, PR annotations, and hosted surfaces can depend on
stable contracts instead of incidental JSON shape.

Implemented boundaries:

- `reports/run-latest.json` and `.entroping/latest-run.json` include
  `schema_version: entroping.run-report.v1`.
- `reports/drift.json` includes `schema_version:
  entroping.drift-report.v1`.
- The story traceability bridge exposes `entroping.traceability-report.v1` as a
  JSON-serializable data contract without expanding the locked CLI output
  surface.
- `docs/technical/REPORT_SCHEMAS.md` and checked-in JSON Schema files define
  compatibility rules for additive and breaking report changes.
- `tests/test_report_schema_contracts.py` freezes representative v1 payloads so
  report shape changes require intentional schema updates.

## Completed Slice: Issue #200 GitHub PR Annotations

Outcome: downstream GitHub Actions workflows can surface Entroping failures and
governance findings directly on pull requests without calling GitHub APIs or
replacing report artifacts.

Implemented boundaries:

- `entroping report github-annotations` reads local JUnit and drift report
  artifacts and prints GitHub Actions workflow-command annotations to stdout.
- `--traceability` compiles local Hurl metadata and annotates missing story IDs
  or duplicate external doc links when teams opt into traceability checks.
- Annotation rendering escapes GitHub workflow-command properties and messages
  and applies Hurl output redaction before emitting text.
- The downstream GitHub Actions starter runs the annotation step with
  `if: always()` so failed Entroping runs still produce inline PR feedback.

## Completed Slice: Issue #209 Open-Core Boundary Audit

Outcome: monetization work now has a maintainer-facing boundary document that
keeps the Apache-2.0 local CLI useful while reserving hosted, team, policy-pack,
audit-history, and services layers for paid offerings.

Implemented boundaries:

- Local CLI, Hurl execution, QAnstitution parsing, local gates, basic reports,
  OpenAPI generation, traffic capture/freeze/map MVP, local-first Brain, and
  local PR annotations stay in the public core.
- Premium policy packs, hosted dashboards, organization policy reporting, team
  audit history, enterprise SSO/RBAC, scheduled monitors, and support services
  can be commercial.
- Local runtime governance must not require paid services, telemetry, hosted
  login, or model credentials.
- Roadmap and growth docs now separate local PR annotations from commercial
  cross-repo/team reporting.

## Completed Slice: Issue #201 Reusable Policy Pack Layout

Outcome: reusable QAnstitution policy packs now have a documented directory
shape, import contract, versioning policy, conflict/final-gate rules, and
open-core boundary before any community or premium packs exist.

Implemented boundaries:

- Policy packs are ordinary local QAnstitution imports plus
  `entroping-policy-pack.yaml` metadata; the current runtime does not read the
  manifest.
- The example `examples/policy-packs/api-baseline/` pack is loadable by the
  existing local import loader and contains no agents, source pointers, secrets,
  traffic, reports, or provider configuration.
- Pack imports remain root-bounded, HTTP(S) pack imports remain future work, and
  no registry, `pack` command, automatic updates, telemetry, or paid-service
  dependency was added.
- Starter pack examples stay in the Apache-2.0 public core; deeper curated
  policy-pack catalogs can be commercial only if they still produce local,
  auditable QAnstitution files before enforcement.

## Completed Slice: Issue #196 Studio Mutation Workflow Design

Outcome: future Studio write actions now have an accepted design gate before
any Textual mutation code can land.

Implemented boundaries:

- v0.3 Studio remains read-only; no rerun, config-edit, Hurl-edit, baseline
  promotion, freeze/map write, provider-backed edit, scheduler, cloud, or
  telemetry behavior was added.
- Future mutation workflows must call existing CLI/core use cases instead of
  Textual widgets writing files directly.
- Every future write needs a sanitized preview, reviewable diff or structured
  change summary, two-step confirmation, result evidence, and rollback path.
- Future Studio previews must not render raw secrets, raw captured traffic,
  raw provider output, or unredacted Hurl output.

## Completed Slice: Issue #192 Read-Only Studio Applied-Gate Drilldowns

Outcome: Studio can now explain which QAnstitution gates applied to which tests
using committed deterministic artifacts, without becoming an execution or edit
surface.

Implemented boundaries:

- `collect_studio_status` loads latest-run report rule IDs and QAnstitution
  gate definitions into a read-only applied-gate status model.
- The Studio view model exposes a Gates tab with rule ID, test path,
  enforcement, test status, condition, and assertion rows.
- Missing gate definitions are shown as `unknown` instead of failing the whole
  Studio view, so old reports remain inspectable.
- Studio still does not run Hurl, call LLM providers, edit tests, edit config,
  or mutate reports/runtime state.

## Completed Slice: Issue #190 Read-Only Studio Traffic Session Browser

Outcome: Studio can inspect captured traffic state before `freeze` or `map`
without becoming a live-capture or mutation surface.

Implemented boundaries:

- Studio reads `.entroping/state.db` through a read-only SQLModel query path
  that does not create missing state or initialize tables for UI browsing.
- Traffic rows are compiled from already-redacted exchanges through the existing
  traffic session and dependency-graph compiler boundaries.
- The Traffic tab shows route summaries, inferred target/dependency grouping,
  average latency, failures, and safe redaction categories/counts.
- Studio does not start `watch`, control capture, run Hurl, write config, edit
  tests, mutate reports, or render raw URLs with query values, headers, bodies,
  cookies, tokens, or secrets.

## Completed Slice: Issue #229 Python Compatibility Policy

Outcome: Entroping's alpha runtime support promise is explicit, package-level,
and CI-proven.

Implemented boundaries:

- `pyproject.toml` now claims Python `>=3.12,<3.14` and advertises Python 3.12
  plus 3.13 classifiers only.
- The main CI security regression job runs on Python 3.12 and 3.13.
- The optional-extras smoke job runs on Python 3.12 and 3.13 so LiteLLM,
  mitmproxy, and Textual dependency surfaces are included in compatibility
  proof.
- Ruff and mypy remain anchored to Python 3.12 because it is the lowest
  supported runtime and syntax floor.
- Docs and release checklist explicitly avoid Python 3.14 claims until a future
  compatibility issue adds CI evidence.

## Completed Slice: Issue #208 Performance Smoke Evidence

Outcome: stable-core scalability claims now have a bounded local smoke script
that produces reviewable JSON evidence instead of relying on intuition.

Implemented boundaries:

- `uv run python scripts/performance_smoke.py` generates a synthetic Hurl suite,
  injects gates, runs execution copies through a fake Hurl binary with bounded
  parallel workers, and writes JSON/JUnit/HTML reports.
- The same script records a larger set of already-redacted traffic exchanges in
  the SQLModel-backed SQLite store and verifies retention behavior.
- Evidence is written to ignored `reports/performance-smoke.json` with
  `entroping.performance-smoke.v1`, per-check durations, thresholds, sizes, and
  pass/fail status.
- `scripts/release_check.sh` runs the performance smoke by default and supports
  `--skip-performance` for local diagnostics.

## Completed Slice: Issue #206 Cross-Platform Install Smoke Matrix

Outcome: public setup claims now have a CI-backed operating-system matrix and
explicit non-claims instead of relying on generic "cross-platform" wording.

Implemented boundaries:

- The `install-smoke` CI job runs after `checks` on Ubuntu, macOS, and Windows.
- Linux installs a reviewed pinned Hurl archive and verifies `HURL_SHA256`
  before running `uv tool install . --force`, `entroping --version`,
  `entroping init --minimal`, and `entroping doctor`.
- macOS uses Homebrew Hurl with the same uv tool install and CLI smoke path.
- Windows proves uv tool install, console-script startup, minimal init, and
  doctor guidance only. Windows Hurl-backed `entroping run` is not claimed for
  alpha.
- Optional adapters stay in the separate `optional-extras-smoke` lane, so base
  install claims do not imply mitmproxy, Textual, Graphviz, or provider setup.

## Completed Slice: Issue #110 Structured Response Drift

Outcome: drift reports can compare optional response fingerprints without
storing brittle or sensitive response values.

Implemented boundaries:

- Run reports can include response status code, selected stable headers, and
  JSON body shape paths when Hurl output provides parseable response detail.
- Drift comparison ignores response details when the baseline has none, keeping
  older baselines compatible.
- Volatile headers and full response body values are not drift truth.
- Missing current response fingerprints are reported when the baseline expected
  one.

## Completed Slice: Issue #176 Latency Regression Drift

Outcome: drift reports can warn when a current Hurl test becomes materially
slower than a reviewed run baseline.

Implemented boundaries:

- Baselines copied from `.entroping/latest-run.json` now preserve optional
  `duration_ms` values per test.
- Latency findings require both a minimum 100 ms increase and a minimum 25
  percent increase from a positive baseline duration, keeping tiny local timing
  noise out of drift reports.
- Findings are warnings and include only duration/increase numbers, never
  response bodies, captured traffic, cookies, tokens, or raw provider data.

## Completed Slice: Issue #179 Architect Validation UX

Outcome: prompt-backed Architect failures are easier to act on without making
provider output or parser streams visible.

Implemented boundaries:

- Invalid provider JSON now reports that Architect output validation failed
  before write and names the expected `summary` / `warnings` / `edits[]` shape.
- Parser-rejected Hurl now reports that Hurl validation failed before write.
- Both paths still print the redacted root error, preserve all-or-nothing writes,
  and keep raw model output plus parser stdout/stderr out of the CLI.

## Completed Slice: Issue #83 Bounded Parallel Hurl Execution

Outcome: `entroping run --parallel` executes multiple Hurl files concurrently
without changing deterministic reporting semantics.

Implemented boundaries:

- Serial execution remains the default for `entroping run`.
- `--parallel` uses `settings.parallel_workers` from `qanstitution.yaml`, with
  a positive bounded worker count and no LLM involvement.
- Each file still goes through the existing subprocess boundary, timeout,
  output-bound, redaction, and variables-file cleanup behavior.
- Suite results are restored to input order before JSON, JUnit, HTML, latest-run,
  and CLI failure output are built.

## Completed Slice: Issue #82 Distribution Install Polish

Outcome: make the source-distributed alpha easier to evaluate without PyPI,
TestPyPI, Homebrew, or hosted-service credentials.

Implemented boundaries:

- `scripts/package_check.sh` removes `dist/`, builds wheel/sdist artifacts with
  `uv build`, and verifies release-critical metadata before any publishing
  claim.
- The release gate now runs package verification before regression/security
  checks and live demo proof.
- README, user guide, TDS, and release checklist document GitHub branch/tag
  install paths, local editable installs, and the fact that package-index
  publishing is not automated yet.

## Completed Slice: Issue #313 Local Wheel Install Smoke

Outcome: release checks can prove the locally built wheel installs and exposes
the public console script without waiting on TestPyPI/PyPI proof.

Implemented boundaries:

- `scripts/local_wheel_install_smoke.py` builds or reuses `dist/`, creates a
  temporary venv and temporary project outside the repository, installs the
  wheel with `uv pip install --offline`, and runs `entroping --version`,
  `entroping init --minimal`, and `entroping doctor` from the installed CLI.
- The smoke emits `entroping.local-wheel-install-smoke.v1` JSON or Markdown
  evidence and can copy JSON evidence to an artifact directory.
- Unit coverage proves dry-run, fake-installer success, and missing-wheel
  failure without performing a real wheel install.
- `scripts/release_check.sh` runs the smoke after `scripts/package_check.sh`
  with `--skip-build`, leaving package-index proof as an unresolved
  stable-core blocker until Trusted Publishing runs.

## Completed Slice: Issue #315 Release Evidence Freshness Check

Outcome: maintainers can ask whether committed release evidence is behind the
latest successful `main` CI and Pages runs without turning normal offline
validation into a network-dependent gate.

Implemented boundaries:

- `scripts/release_evidence.py --check-freshness` compares recorded
  `latest_main_ci` and `latest_pages_ci` `run_id` and `commit` values with
  latest successful `main` runs.
- `--freshness-input <json>` allows deterministic fixture-backed checks for
  tests and offline review.
- Missing or unauthenticated `gh` is reported as `freshness.status=unavailable`
  instead of failing normal ledger validation.
- Stale evidence reports the exact ledger fields to refresh and exits non-zero
  only when combined with `--strict`.
- The check never mutates `docs/meta/release-evidence.json`; release owners
  still refresh the ledger deliberately.

## Completed Slice: Issue #314 Downstream Smoke Release Gate

Outcome: release checks now refresh local external-project proof instead of
only validating that the downstream smoke harness exists.

Implemented boundaries:

- `scripts/release_check.sh` runs `uv run python scripts/downstream_smoke.py`
  when Hurl is available and shows the step in dry-run output.
- `--skip-downstream-smoke` skips only the downstream smoke for local
  diagnostics; `--skip-live-demo` remains scoped to the checkout live demo.
- Missing Hurl is reported by the release gate before attempting downstream or
  live Hurl smokes when `--require-live-demo` is used.
- `scripts/downstream_smoke.py` now reports Entroping-run failures on stderr
  with the failing exit code while keeping machine-readable failure details in
  JSON/Markdown output.
- The smoke remains maintainer-controlled local evidence and does not satisfy
  the stable-core real-user-feedback blocker.

## Completed Slice: Issue #80 PNG Dependency Map Rendering

Outcome: `entroping map --export png` writes `reports/dependency-map.png` when
local Graphviz `dot` is available, while preserving actionable missing-renderer
errors when it is not.

Implemented boundaries:

- DOT text still comes from the pure `bridge.traffic_to_graph` compiler.
- PNG rendering lives in `core.dependency_mapper` as a subprocess adapter using
  argument arrays, binary stdin/stdout, a timeout, bounded errors, and atomic
  ignored report writes.
- Renderer failures do not echo raw DOT content, captured traffic, or secrets.
- CLI output prints only the generated artifact path.

## Completed Slice: Issue #58 License And Package Metadata

Outcome: make the public alpha legally explicit and package-index friendly.

Implemented boundaries:

- `LICENSE` contains the Apache License 2.0 text.
- `pyproject.toml` declares the SPDX license expression `Apache-2.0`, ships the root license file, and uses alpha-level classifiers without overclaiming maturity.
- `README.md` states the open-core boundary: Entroping Core is Apache-2.0, while future hosted, model, enterprise, policy-pack, and support offerings may use separate commercial terms.
- `docs/meta/PROJECT_PROGRESS.md` no longer treats license/package metadata as the remaining alpha blocker.

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

## Completed Slice: Issue #414 Capture Filters

Outcome: let users narrow noisy Eye captures before generating Hurl tests,
WireMock mappings, or dependency maps.

- Added a shared `core.traffic_filters` module for already-redacted
  `TrafficExchange` records.
- Added exact host filters, normalized method filters, and path prefix/glob
  filters for `freeze`, `freeze --mock`, and `map`.
- Kept exclude filters authoritative over include filters.
- Failed empty filtered sessions before writing generated artifacts.
- Rejected unsafe filter values and avoided query, header, cookie, or body
  values in filter errors and generated artifacts.

## Completed Slice: Issue #427 Agent Run Manifests

Outcome: make prompt-backed Architect runs leave local value-free audit evidence
without making deterministic `run` depend on AI or manifests.

- Added `core.agent_manifest` with schema version
  `entroping.agent-run-manifest.v1`.
- Wrote manifests under `.entroping/agent-runs/` for Builder prompt-build,
  Breaker prompt-build, prompt merge-build, Architect refactor, and Auditor
  review paths.
- Recorded role, model, persona path/digest, prompt intent/package hashes,
  output paths, tags, validation status, latency, and token counts.
- Kept raw prompts, provider outputs, provider keys, env values, persona
  content, Hurl contents, raw traffic, and model approval out of the manifest.

## Current Validation Queue

Use these issues as the next marathon targets. Keep each one narrow, tested, and
merged through GitHub before starting the next branch:

- Next local targets are #441 explicit timeout evidence per test, #442
  security-scheme coverage generation, and #443 undocumented live-traffic route
  audit evidence.
- Packaging issue #268 is intentionally gated on package-index alpha evidence:
  publish TestPyPI/PyPI through the protected workflow first, then promote the
  Homebrew tap from prototype to supported install path.
- After local gates pass, dogfood the public install/demo flow with the
  maintainer before changing release status language.

## Explicitly Deferred

- Complete non-prompt `architect build --strategy merge` if product demand justifies it.
- Studio mutation workflows beyond read-only report-backed inspection.
- Nuitka packaging.
- Hosted/cloud features.
- Graphify-generated artifacts in Git.

## Working Context Loop

At the start of a new Codex thread, read:

1. `AGENTS.md`
2. `README.md`
3. `docs/meta/VAULT_INDEX.md`
4. `.context/plan.md`
5. `docs/product/MVP_PLAN.md`
6. `docs/technical/TDS.md`
7. `docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md`
8. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
9. `docs/meta/PROJECT_PROGRESS.md`
10. `docs/meta/ISSUE_TRACKING.md`
11. `docs/meta/TEST_STRATEGY.md`
12. `docs/meta/DOCS_GOVERNANCE.md`
13. `docs/meta/AGENT_CONTROL_PLANE.md`

For product history, open Obsidian and start with `docs/meta/VAULT_INDEX.md`.

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
