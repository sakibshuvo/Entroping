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

## Current Issue Slice: #1087 Work Item Import Bundle

Add `entroping report work-item-import-bundle --output json|csv` as a local
read-only tracker import packet over the fixed optional work-item draft
artifact. No ticket, chat, PR, API, upload/import, Hurl/test execution,
provider call, traffic parsing, `entroping run` change, source Hurl, or raw
artifact rendering.

## Current Baseline

- Docs live under `docs/`; public entry points are `README.md` and
  `docs/meta/VAULT_INDEX.md`; code lives under `src/entroping/`; the CLI
  command surface is locked to v4.1.
- Report commands stay local-only unless a documented command explicitly says
  otherwise; report help, threshold guards, test-pyramid evidence, and
  performance-smoke evidence are covered in command docs and progress notes.
- Runtime `ignore_failures` exceptions are deterministic: active entries skip
  only matching Entroping-injected QAnstitution gates in temporary execution
  copies, expired entries block before Hurl execution, and entries targeting
  selected tests fail closed when no injected gate matches.
- Known-failure expiry validation is now shared across policy loading,
  `doctor --ci`, runtime gate injection, and gate-injection reports:
  malformed dates fail QAnstitution loading, and expired exceptions fail CI
  readiness before a policy can be treated as ready.
- HTML run reports escape header fields, summary text, rule IDs,
  known-failure summaries, and captured Hurl output before rendering.
- Common filesystem symlink component traversal is centralized in
  `entroping.core.path_safety`; adapters keep local exception types and
  user-facing messages while sharing the same traversal primitive.
- Hurl runner read paths reject symlinked components before resolution for
  selected source `.hurl` files and explicit absolute Hurl binary paths, while
  bare `hurl` continues to trust the parent process `PATH` by design, resolves
  the PATH-selected binary target, and tolerates host-level filesystem aliases.
- AI worker lanes are artifact-only until Codex validates local files, tests,
  and CI; OpenCode/DeepSeek outputs are advisory and tool scopes do not
  transfer automatically into Codex-native surfaces.
- Factory scorecards (`scripts/factory_metrics.py readiness` and
  `context-scorecard`) remain value-free evidence checks before any handoff,
  PR, finish decision, or context-tool promotion claims readiness.
- AI/context artifact hygiene is an executable gate:
  `scripts/ai_artifact_hygiene.py` runs through repo hygiene and docs
  governance so raw worker prompts, provider responses, stdout/stderr captures,
  cookies, raw traffic, token-shaped values, and generated artifact paths stay
  out of tracked docs/context.
- Agent context packs now have a content-free planning surface:
  `scripts/context_pack.sh --manifest` reports selected files, reasons, byte
  counts, estimated tokens, and mode budgets before a worker loads the full
  pack, while `--strict-budget` blocks silent context growth in measured lanes.
- PR evidence now has a sensitive-surface preflight:
  `scripts/pr_body_check.py --changed-file` requires security-gate evidence
  when runner, redaction, provider, proxy, report-evidence, worker, or
  secret-adjacent files change, and CI feeds PR changed files into that check.
- Product runtime direct-provider imports are guarded:
  `tests/test_architecture_boundaries.py` rejects direct SDK imports such as
  DeepSeek/OpenAI/Anthropic/Gemini-style providers under `src/entroping`; worker
  scripts stay maintainer tooling and do not change the LiteLLM product boundary.
- Reusable human-to-agent prompts live under `docs/meta/prompt-library/`;
  durable workflow policy stays in the agent control plane.
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
- Local structured diagnostics now have a separate vendor-neutral
  `entroping.diagnostics.v1` JSONL boundary for headless agents, reports,
  doctor, and future adapter work. Diagnostics are value-free component events:
  safe names, counts, classifications, relative artifact paths, and statuses
  are allowed, while secrets, raw traffic, prompts, provider output, env values,
  and full source Hurl contents are forbidden.
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
- A future official `entroping/action` should live in a dedicated action repo
  after package-index proof, install released Entroping artifacts, verify Hurl,
  run only deterministic local report commands, avoid `.entroping/` uploads by
  default, and keep optional PR comments permission-scoped. The generated
  starter workflow remains the supported downstream CI baseline until that
  action is proven.
- A future Docker CI image should trail package-index proof and publish to GHCR
  only as a CI convenience with pinned Entroping/Hurl/hurlfmt, non-root runtime,
  OCI labels, digest-pinnable tags, rollback and smoke-check rules, and no claim
  that Docker replaces source, `uv tool install`, PyPI, or Homebrew paths.
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

## Historical Milestone Pointers

Older completed-slice detail was compressed on 2026-06-19 to keep
`scripts/context_pack.sh --mode implementation --strict-budget` useful for
agent work. The active plan should carry current constraints, current baseline,
and next validation targets rather than a full implementation ledger.

Lossless sources for compressed history remain in
`docs/meta/PROJECT_PROGRESS.md`, `.context/changelog.md`,
`docs/meta/DECISION_REGISTRY.yaml`, and git history.

Guarded anchors retained for docs-link tests:

- Issue #202 defines organization QAnstitution import controls.
- Issue #204 documents non-GitHub CI provider recipes.

## Current Validation Queue

Keep each marathon issue narrow, tested, merged through GitHub, and cleaned up
before starting the next branch. Near-term validation targets remain package
index proof (#303-#305), downstream feedback (#306), stable-core compatibility
(#308), and non-GitHub CI proof (#309-#310); package issue #268 stays gated on
package-index evidence.

## Explicitly Deferred

- Non-prompt merge generation, Studio mutation workflows, Nuitka packaging,
  hosted/cloud features, and generated context-tool artifacts in Git.

## Working Context Loop

At the start of a new Codex thread, hydrate from `AGENTS.md`, `.context/plan.md`,
`docs/meta/PROJECT_PROGRESS.md`, `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`,
  `docs/meta/DOCS_GOVERNANCE.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and
  issue files found with `rg`. For product history, start with
`docs/meta/VAULT_INDEX.md`. To start issue work, dry-run the launcher first:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
```

## Constraints

- Preserve the locked command namespace.
- Keep `entroping run` deterministic and LLM-free.
- Keep Hurl as the only API execution engine.
- Do not send secrets or raw traffic to LLM providers.
- Keep generated state, reports, local env files, and generated local context output out of Git.
- Treat security and quality checks as release gates.
- Use the feature delivery checklist for TDD, regression, architecture, security, multi-agent, documentation, and commit-readiness gates.
- Use GitHub Issues for individual work items and `docs/meta/PROJECT_PROGRESS.md` for simple Obsidian progress tracking.
