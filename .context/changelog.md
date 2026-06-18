# Entroping Changelog

## 2026-06-18

- Fixed issue #874's failure-bundle metadata redaction boundary:
  `hurl-metadata.json` now preserves discovered metadata keys while redacting
  secret-like metadata values before local bug-handoff bundles are written.
- Fixed issue #838's policy-pack manifest provenance boundary:
  `manifest.source` now validates as local provenance evidence, preserving `.`
  while rejecting remote, absolute, traversal, control-character, and empty
  values through vendor and self-test paths.
- Fixed issue #839's QAnstitution policy compilation boundary:
  unknown future condition objects now fail closed with `GateCompilationError`
  through public matching and compilation paths instead of silently dropping
  matching gates.
- Fixed issue #841's OpenAPI security-alternative handling:
  auth-negative generation now treats an empty OpenAPI security requirement as
  a public alternative and skips missing/invalid-auth Hurl files for those
  operations while preserving security-only negative generation.
- Fixed issue #843's traffic-to-Hurl header name boundary:
  freeze-generated Hurl now validates header names during compilation,
  rejecting control characters, invalid field-name tokens, and Hurl template
  delimiters even when traffic model validation was bypassed.
- Fixed issue #842's traffic-to-Hurl request method boundary:
  freeze-generated Hurl now validates and normalizes request methods during
  compilation, rejecting control characters, whitespace, and Hurl template
  delimiters even when traffic model validation was bypassed.
- Fixed issue #844's traffic URL fragment redaction gap:
  redacted Eye traffic now strips URL fragments before persistence so
  fragment-borne OAuth or token-like values cannot survive in traffic state,
  reports, or generated artifacts.
- Fixed issue #876's traffic URL path redaction gap:
  redacted Eye traffic now replaces secret-like URL path segments with an
  encoded redaction marker while preserving ordinary route shape and existing
  userinfo, query, and fragment protections.
- Fixed issue #877's redacted traffic validation gap:
  traffic persistence, session building, and direct Hurl, WireMock, and graph
  compilers now fail closed when records marked redacted still contain obvious
  secret-like content, reporting only value-free unsafe locations.
- Fixed issue #855's root QAnstitution symlink boundary:
  root policy loading now rejects symlinked selected policy paths before
  resolution and applies stricter raw-path symlink checks to absolute imports
  that resolve back inside the policy root.
- Fixed issue #856's absolute QAnstitution import boundary:
  policy imports now fail closed unless they are local relative references,
  including POSIX absolute, Windows absolute, UNC, and tilde-expanded paths.
- Fixed issue #857's imported gate merge boundary:
  duplicate non-final gate IDs across imported QAnstitution files now fail
  closed with both source paths instead of silently depending on import order.
- Fixed issue #858's QAnstitution gate ID validation gap:
  gate IDs now reject blank and control-character values during policy loading,
  normalize surrounding whitespace, and keep compiler-side defense for bypassed models.
- Fixed issue #836's GitHub annotation artifact error handling:
  unreadable JUnit XML or drift JSON report paths now raise controlled
  `GitHubAnnotationError` messages instead of leaking raw filesystem
  exceptions, while missing report artifacts still produce no annotations.
- Added issue #775's architecture-gate OpenCode readiness check:
  `scripts/opencode_readiness.py` now requires
  `scripts/architecture_integrity.sh` and verifies its value-free help surface
  before independent OpenCode implementation sessions, without running Hurl,
  calling providers, touching the network, or reading secrets.
- Fixed issue #798's OpenCode PR evidence spoofing gap:
  `scripts/pr_body_check.py` now validates gate evidence from structured
  `Commands run` blocks or checked items instead of arbitrary PR prose,
  ignores examples, blockquotes, unchecked items, and not-run sections, and
  enforces canonical OpenCode provider lane, autonomy tier, and merge
  authority values across the prompt-library worker guidance.
- Fixed issue #829's concurrent latest event-log evidence gap:
  `entroping run` now acquires an exclusive latest event-log writer lock per
  project root and fails concurrent runs before Hurl execution, preventing two
  runs from interleaving or losing `.entroping/latest-run-events.jsonl`
  evidence.
- Fixed issue #830's primary OpenAPI spec path boundary:
  `architect build --new` and `architect audit` now load local
  `sources.spec` through a project-root-bounded OpenAPI loader that rejects
  parent/root escapes and symlinked path components before reading, while
  preserving the separate dependency-spec contract.

## 2026-06-17

- Fixed issue #808's low-severity security review sweep:
  run-delta failure signatures now include policy rule IDs, Hurl tag metadata
  rejects control characters, append writes recheck symlink targets immediately
  before opening, tag expressions fail closed on excessive nesting, and failed
  temp-file writes remove partial Hurl variable, safe-write, and policy-pack
  vendoring artifacts.
- Added issue #821's secure agent CLI toolchain profile:
  `scripts/agent_toolchain.py` now reports local CLI availability with schema
  `entroping.agent-toolchain.v1`, classifying tools as `safe_default`,
  `guarded_local_only`, or `manual_explicit` through PATH lookup only. The
  OpenCode readiness preflight consumes that report without executing
  scanners, reading provider config, inspecting local secret stores, or making
  network calls, and the agent docs now forbid automatic use of high-risk tools
  such as `act`, `trufflehog`, `semgrep`, `trivy`, `syft`, and `grype`.

## 2026-06-16

- Added issue #787's architecture/quality guardrail PR preflight:
  `scripts/pr_body_check.py --changed-file` now requires
  `scripts/audit_quality.sh` evidence when architecture-integrity,
  delivery-gate, or quality-audit guardrail files change.
- Fixed issue #785's context-management graph-tool framing:
  `docs/meta/CONTEXT_MANAGEMENT.md` now opens with repo-native context
  rehydration and keeps graph/wiki/compression tooling behind measured
  promotion evidence instead of presenting future graph tooling as a normal
  agent path.
- Added issue #783's model-output acceptance gate prompt:
  `docs/meta/prompt-library/model-output-acceptance-gate.md` now gives Codex,
  OpenCode, DeepSeek, Kimi/Qwen, and local-model reviewers a reusable intake
  gate for accepting grounded output, escalating Tier B/Tier C work, converting
  out-of-scope value into GitHub issues, and rejecting stale/opinion/unsafe
  output without treating cheap-model volume as source truth.
- Added issue #781's engineering-health review prompt:
  `docs/meta/prompt-library/engineering-health-review.md` now gives agents a
  reusable review-only audit for architectural drift, anti-patterns, code
  smells, documentation health, quality, testability, debugging ergonomics,
  security, maintainability, and regression risk.
- Added issue #772's architecture-integrity gate:
  `scripts/architecture_integrity.sh` now runs the focused AST architecture
  boundary tests as a named provider-free, no-Hurl, source-only gate, and
  `scripts/feature_gate.sh` runs it before the broad Python check suite.
- Added issue #770's context-pack manifest next-action guidance:
  `scripts/context_pack.sh --manifest` now emits value-free
  `recommended_next_action` instructions so agents choose targeted file reads
  when a pack is in budget and reduce scope instead of loading the full pack
  when the pack exceeds budget.

## 2026-06-15

- Added issue #768's OpenCode-to-Codex review request prompt:
  `docs/meta/prompt-library/opencode-codex-review-request.md` now gives
  OpenCode, OpenCode Go, DeepSeek, and local worker sessions a read-only Codex
  CLI review wrapper for local diffs and PRs, preserving provider-lane,
  autonomy-tier, source-of-truth, no-edit, and PR-evidence boundaries.
- Added issue #766's OpenCode independent-session readiness kit:
  `scripts/opencode_readiness.py` now checks the active repo path,
  branch/worktree state, OpenCode binary/version, required workflow files,
  prompt-library guardrails, command help surfaces, ignored local
  OpenCode/Codex/artifact paths, and tracked local-state leaks without reading
  provider keys, MCP credentials, local config values, prompts, transcripts, or
  `.entroping/` artifacts. The OpenCode handoff prompt now runs the preflight
  before independent implementation and PR verification.
- Fixed issue #750's AI job running-state recovery gap:
  `scripts/ai_jobs.py run-next` now fails malformed running jobs with missing
  or unparsable timestamps, drains all stale or invalid running jobs before
  claiming queued work, and reports how many running jobs were failed before
  continuing.
- Fixed issue #748's Hurl runner symlink-component gap:
  selected source `.hurl` paths and explicit absolute Hurl binary paths now
  reject symlinked path components before resolution, preserving the reviewed
  deterministic subprocess boundary while keeping bare `hurl` PATH discovery
  behavior, resolved PATH-selected binary symlinks, and host-level filesystem
  aliases intact.
- Added issue #746's four-gate factory readiness scorecard:
  `scripts/factory_metrics.py readiness --issue <issue>` now emits
  schema-versioned JSON or Markdown and returns nonzero unless issue metrics
  evidence covers quality, security, context preservation, and token/cost
  efficiency without printing notes, prompts, transcripts, raw traffic, or
  secrets.
- Added issue #738's docs-prune candidate report:
  `scripts/docs_inventory.py` now emits non-destructive prune/archive
  candidates for archive/source material, stale reference docs, duplicate
  titles, and default-agent context risk while keeping deletion/manual archive
  decisions outside the tool.
- Added issue #737's Tier A cheap-worker defaults:
  `scripts/ai_jobs.py submit --autonomy-tier tier-a` now defaults OpenCode
  jobs to `flash-free`, direct DeepSeek API jobs to `flash`, records provider
  lane/host/billing/merge-authority metadata, and injects a
  context-pack-manifest-first worker instruction.
- Added issue #736's quality trend summary:
  `scripts/audit_quality.sh` now writes `reports/quality-trend.json` through
  `scripts/quality_trend_summary.py`, capturing deterministic coverage,
  complexity, maintainability, dead-code, and test-taxonomy metrics plus
  optional numeric deltas from `ENTROPING_QUALITY_TREND_PREVIOUS`.
- Added issue #735's AI artifact hygiene scanner:
  `scripts/ai_artifact_hygiene.py` now audits tracked paths for generated
  worker/context artifacts, prompt or provider dumps, raw stdout/stderr
  captures, cookies, raw traffic, and secret-shaped docs/context content;
  `scripts/repo_hygiene.sh` and `scripts/doc_governance_check.sh` run it.
- Added issue #734's direct-provider runtime import guard hardening:
  the executable architecture guard now rejects direct DeepSeek-style provider
  SDK imports in `src/entroping` while preserving maintainer-only worker scripts
  outside product runtime.
- Added issue #733's sensitive-surface PR preflight:
  `scripts/pr_body_check.py --changed-file` now classifies runner, redaction,
  provider, proxy, report-evidence, worker, and secret-adjacent paths and
  requires checked or command-listed security-gate evidence when those surfaces
  change; CI passes PR changed files into the checker.
- Added issue #732's context-pack manifest and budget guard:
  `scripts/context_pack.sh --manifest` now emits a content-free JSON inventory
  with selected files, selection reasons, byte counts, estimated tokens, and
  mode budget status, while `--strict-budget` fails context packs that exceed
  their explicit byte budget.
- Added issue #730's documentation diet guard: `scripts/docs_inventory.py`
  now inventories tracked Markdown by active/reference/archive tier, owner,
  audience, canonical/default-agent status, and stale-risk hints; documentation
  governance runs it in strict mode, and implementation context packs no longer
  load README/vault navigation by default.
- Added issue #728's retired context-tool surface cleanup: active docs,
  prompts, hygiene/public-claim scripts, Hurl discovery ignores, and scorecard
  fixtures no longer name the discarded graph/compression tools or their
  generated output directories. Historical context notes now use generic
  retired-tool wording so fresh agents stay on the repo-native baseline.
- Added issue #726's repo-native context budget baseline: the canonical
  context-management docs, agent control plane, issue-worker prompt, and
  `scripts/context_pack.sh --help` now state that agents should start from
  `rg`, `scripts/context_pack.sh`, the decision registry, GitHub issues, source
  files, focused tests, CI, and factory metrics before loading any generated
  context, and token-saving claims require measured local evidence.

## 2026-06-14

- Fixed issue #722's finished-ledger attribution bug: factory metrics reports now
  use the archived `finished-issues/issue-<number>/...` path as a default issue
  only when an event omits the issue field, preserving explicit issue values.
- Added issue #708's OpenCode-only week monitoring prompt:
  `docs/meta/prompt-library/opencode-week-monitoring.md` now gives cheap
  OpenCode/DeepSeek workers a read-only monitor for open PRs, CI rollups, ready
  issues, merged PRs needing `finish_issue.sh`, factory metrics status,
  blockers, and safe next actions without mutating repo or GitHub state.
- Added issue #702's Codex-outage OpenCode/DeepSeek work queue to the agent
  control plane: `docs/meta/AGENT_CONTROL_PLANE.md` now records the one-week
  low-Codex-capacity queue index, child issue order, provider lanes, autonomy
  tiers, merge authority, acceptance rules, and forbidden runtime/security
  scopes for OpenCode Desktop/OpenCode Go and paid DeepSeek API workers.
- Added issue #704's Codex-outage daily operations prompt:
  `docs/meta/prompt-library/codex-outage-daily-operations.md` now gives
  OpenCode/DeepSeek workers a daily low-Codex-capacity loop for pulling main,
  inspecting PRs/issues, choosing only ready scoped issues, using provider
  lanes, running focused tests/gates and CI, finishing issue cleanup, enforcing
  emergency stop conditions, and returning after-sleep status.
- Added issue #703's model-comparison trial prompt:
  `docs/meta/prompt-library/model-comparison-trial.md` now makes Codex,
  OpenCode native DeepSeek, direct DeepSeek API, OpenCode Go Kimi/Qwen, and
  local/offline model comparisons record provider lane, model id,
  cost/token/context evidence, files changed/read, tests/gates, CI status,
  accepted/rejected/stale findings, and reviewer overrides before drawing
  conclusions.
- Added issue #705's OpenCode Desktop tooling setup checklist:
  `docs/meta/prompt-library/opencode-desktop-handoff.md` now distinguishes
  Codex-native tools from OpenCode-exposed equivalents and covers read-only MCP,
  hooks, branch hygiene, dirty worktree checks, secret/local-state hygiene,
  PR-body evidence, CI, provider lanes, and metrics hooks.
- Added issue #709's architecture-boundary brief prompt:
  `docs/meta/prompt-library/architecture-boundary-brief.md` now gives
  OpenCode/DeepSeek worker packets explicit ownership, allowed files,
  forbidden files, architecture invariants, tests, provider/runtime
  constraints, and stop conditions before edits begin.
- Added issue #706's OpenCode provider-lane PR-body preflight:
  `scripts/pr_body_check.py --require-opencode-evidence --issue <issue>` now
  preserves the existing documentation-impact validation by default while
  optionally requiring concrete provider lane, provider host, billing path,
  model id, autonomy tier, merge authority, commands run, and `Closes #<issue>`
  evidence for OpenCode/DeepSeek-produced PRs.
- Added issue #707's model-comparison view to factory metrics reports:
  `scripts/factory_metrics.py report` now emits additive `model_comparison`
  rows grouped by issue, role, provider lane, and model id, with known and
  unknown metric counts so missing token, cost, or duration evidence remains
  explicit for Codex/OpenCode/DeepSeek/Spark/local model comparisons.
- Ran issue #712's full context-tool trial across curated Markdown/Obsidian,
  retired generated context tools, the LLM wiki pattern, Understand Anything,
  and the repo-native agent context probe. The scorecard now records setup
  status, setup duration, setup command, and setup failure reason;
  generated-output hygiene covers ignored local generated outputs and
  `.understand-anything/`; and `scripts/agent_context_probe.py` preserves
  source-heading paths for retired symbol-context outputs. The measured
  decision is active curated Markdown plus active agent context probe,
  optional-manual retired graph-context/LLM-wiki patterns, and probationary
  retired compression/Understand Anything until real local evidence proves
  savings or live graph value.
- Added issue #710's context-tool proof/discard scorecard:
  `scripts/factory_metrics.py context-scorecard validate/report` now validates
  local value-free scorecards with schema
  `entroping.context-tool-scorecard.v1` and renders reports with schema
  `entroping.context-tool-scorecard-report.v1`, comparing optional graph,
  wiki, comprehension, symbol-context, and compression tools against the
  repo-native `rg`/context-pack/decision-registry/curated-Markdown baseline
  without storing raw prompts, provider transcripts, secrets, raw traffic, or
  product runtime evidence.
- Added issue #700's OpenCode Desktop handoff prompt:
  `docs/meta/prompt-library/opencode-desktop-handoff.md` now gives OpenCode
  Desktop/OpenCode Go workers implementation and PR-verification launch prompts
  that require provider lane, billing path, model id, role, autonomy tier,
  allowed files, forbidden files, optional graph-context boundaries, metrics
  evidence, and merge authority before work starts.
- Documented issue #698's provider-lane taxonomy:
  `docs/meta/AGENT_CONTROL_PLANE.md` now distinguishes `deepseek-api/direct`,
  `opencode/native-deepseek`, `opencode-go/kimi-k2.7-code`,
  `opencode-go/qwen3.7-max`, `opencode-go/other`, and `local/offline`, with
  OpenCode Go positioned as the Kimi/Qwen/model-variety lane.
- Fixed issue #696's direct DeepSeek response-payload artifact gap:
  `scripts/deepseek_worker.py` now checks serialized provider response payloads
  with the shared secret-like detector before execution artifacts are written,
  marks unsafe response-payload runs failed, skips raw response/proposal
  artifacts, and records only value-free failure evidence.
- Fixed issue #694's direct DeepSeek output artifact gap:
  `scripts/deepseek_worker.py` now checks generated stdout/stderr with the
  shared secret-like detector before writing execution artifacts, marks the
  worker run failed when unsafe generated output appears, writes only
  value-free withheld-output markers, and skips raw response/proposal artifacts
  that could contain the same generated value.
- Added issue #692's OpenCode-hosted DeepSeek tool-lane boundary:
  `scripts/opencode_worker.py` now injects a versioned OpenCode Host Capability
  Context into review and patch prompts, records the context version in worker
  metadata, and states that DeepSeek V4 Pro may use only OpenCode-configured
  agents, plugins, MCP servers, hooks, shell/tools, and GitHub integrations
  that are present and permissioned by OpenCode. Codex-native plugins, skills,
  Codex Security, Browser, Computer Use, thread tools, and Codex-specific MCP
  state remain unavailable unless OpenCode exposes equivalents, and the harness
  still forbids permission bypasses, raw traffic, product-runtime provider
  calls, and autonomous Tier B/Tier C merge authority. OpenCode stdout/stderr
  that matches the shared secret-like detector is now withheld before artifact
  persistence and marks the worker run failed.
- Added issue #690's direct DeepSeek capability context manifest:
  `scripts/deepseek_worker.py` now injects a versioned Factory Capability
  Context into review and patch prompts so paid direct API workers know they
  have no live MCP/tool/skill execution, can cite the valid repo harnesses, and
  must keep Codex or humans responsible for applying patches, tests, PRs, and
  Tier B/Tier C decisions.
- Added issue #688's finished-issue factory metrics report aggregation:
  `scripts/factory_metrics.py report --include-finished-issues` now loads
  archived `.jsonl` ledgers from the ignored
  `.entroping/factory-metrics/finished-issues/` tree, keeps default reports
  unchanged, labels malformed archived events by archive-relative path, and
  skips symlinked archive files or directories.
- Fixed issue #686's issue-worktree metrics retention gap so
  `scripts/finish_issue.sh` preserves `.jsonl` factory metrics ledgers from
  the issue worktree into the main checkout's ignored
  `.entroping/factory-metrics/finished-issues/issue-<number>/` archive before
  deleting the worktree, while dry-run reports the plan without writing.
- Fixed issue #684's graph-assisted context probe gap so
  `scripts/agent_context_probe.py` reads every list-valued field in retired graph tooling or
  retired symbol-context tooling JSON artifacts instead of only the first, preserving edge evidence
  such as source/test relationships for agent retrieval.
- Fixed issue #682's AI worker queue selected-file symlink gap so
  `scripts/ai_jobs.py submit` rejects symlinked input files and files reached
  through symlinked directories before path resolution, preserving the
  OpenCode/DeepSeek preflight boundary before any worker job can be queued.

## 2026-06-13

- Fixed issue #673's AI worker selected-file safety gap so the shared
  OpenCode/DeepSeek preflight rejects quoted JSON credential assignments such
  as `api_key`, `access_token`, and `client_secret` before subprocess or model
  calls, while preserving non-secret documentation and placeholder examples.
- Fixed issue #672's Architect provider routing boundary so `api_base` must
  target a local loopback OpenAI-compatible endpoint at QAnstitution load time
  and again before LiteLLM key lookup/provider invocation; tampered prompt
  packages also revalidate `api_key_env` before reading environment variables,
  and provider setup docs/schema metadata now state the loopback-only rule.
- Fixed issue #671's traffic-to-Hurl body injection gap so captured request
  bodies that contain Hurl request lines, response lines, sections, or comments
  are emitted as inert `base64,...;` Hurl body data before freeze writes
  generated tests; bridge and freeze regressions prove injected body text no
  longer creates extra parsed exchanges or Entroping metadata.

## 2026-06-12

- Added issue #669's Markdown freshness guardrail:
  `scripts/docs_freshness_check.py` now audits current tracked Markdown for
  corrupt encodings, NUL bytes, merge markers, broken local Markdown links,
  unmarked stale active-repo paths, deprecated command literals outside
  deprecation context, unsupported readiness/security claims, and placeholder
  markers; `scripts/doc_governance_check.sh` runs it before the existing
  public-claims and source-preservation gates so agents use current Markdown as
  context truth and reserve deleted historical paths for explicit archaeology.
- Added issue #667's factory metrics report export:
  `scripts/factory_metrics.py report` now renders schema-versioned JSON or
  Markdown per-issue cost/yield summaries from ignored local metrics ledgers,
  grouping unassigned exploratory events separately and preserving the
  no-prompts/no-transcripts/no-stdout/no-stderr/no-raw-traffic boundary for
  future software-factory extraction.
- Added issue #656's queued-worker factory metrics pass-through:
  `scripts/ai_jobs.py run-next --record-factory-metrics` now forwards
  `--factory-role` and `--factory-metrics-ledger` to the selected OpenCode or
  direct DeepSeek worker harness, keeping metrics schema ownership in
  `scripts/factory_metrics.py`, leaving default queue behavior unchanged, and
  preserving the no-prompts/no-transcripts/no-stdout/no-stderr ledger boundary.
- Added issue #654's opt-in factory metrics hooks for maintainer workflows:
  `scripts/context_pack.sh --record-factory-metrics` records context-pack
  byte/token estimates and selected file counts without persisting the pack
  body, while `scripts/opencode_worker.py` and `scripts/deepseek_worker.py`
  can record worker status, duration, selected-file byte counts,
  provider/model metadata, and sanitized DeepSeek usage totals through
  `scripts/factory_metrics.py` without storing prompts, stdout/stderr,
  provider transcripts, secrets, raw traffic, product runtime evidence, or
  involving `entroping run`.
- Added issue #652's portable factory role and metrics ledger: the
  machine-readable `docs/meta/AGENT_ROLE_REGISTRY.yaml` defines Product Manager,
  Architect, Dev Agent, QA Agent, Code Review Agent, Security Agent, Monitoring
  Agent, and Integrator missions plus authority limits, while
  `scripts/factory_metrics.py` appends, validates, and summarizes ignored local
  workflow metrics under `.entroping/factory-metrics/` without storing raw
  prompts, provider transcripts, secrets, raw traffic, product runtime evidence,
  or involving `entroping run`.
- Added issue #650's optional graph-assisted agent context probe:
  `scripts/agent_context_probe.py` reads existing local retired graph-context tools
  outputs, emits advisory text/JSON manifests with candidate file/test
  evidence, redacts obvious secret-like values, writes only under ignored
  `agent-context-out/`, and `scripts/context_pack.sh --with-local-graphs`
  exposes it to Codex/OpenCode/DeepSeek without making graph tools required or
  authoritative.
- Documented issue #648's autonomous OpenCode shipping lanes: Tier A
  docs/tests/guard/script work can be implemented, PR'd, merged, and cleaned up
  by OpenCode/DeepSeek after issue-scoped worktrees, deterministic gates, PR
  autonomy declaration, green CI, and `finish_issue.sh`; Tier B/Tier C work
  remains human/Codex-reviewed for runtime, security, architecture, release,
  provider-boundary, and secrets-sensitive surfaces.
- Added issue #646's protected-block report evidence guard so JUnit and HTML
  reports expose selected, executed, not-scheduled, and fail-fast summary counts
  when protected safety preflight blocks a mixed selected run before Hurl.
- Added issue #640's context-tool output hygiene boundary: generated retired graph tooling,
  LLM wiki, Understand Anything, retired symbol-context tooling, and retired compression tooling artifacts now have
  explicit ignored local output paths, repo hygiene rejects tracked generated
  context output, and docs preserve the promotion-only rule.
- Added issue #639's AI worker queue review summary: completed queue
  collection now reports value-free counts by engine, profile, mode,
  worker status, and model; direct DeepSeek token usage is copied into
  completed job records and `collect --json` only after numeric sanitization,
  without raw stdout, prompts, provider responses, or secrets.
- Fixed issue #642's DeepSeek/OpenCode prompt-library drift so local AI worker
  examples use the supported `scripts/ai_jobs.py status` command instead of a
  stale `list` subcommand, with a docs guard preventing future unsupported
  queue command examples.
- Documented issue #638's context-factory rollout order: Obsidian discipline
  comes before generated wiki or graph layers, Understand Anything stays a
  human comprehension aid, symbol-context tooling remains scoped to `src/` and
  `tests/`, compression tooling waits until retrieval is stable, and
  cheap/Chinese/local model workers stay behind Codex-owned validation.
- Codified issue #636's context-engineering software-factory boundary:
  source files, tests, GitHub evidence, ADRs, the decision registry, and
  QAnstitution/Hurl evidence remain authoritative while Obsidian/LLM wiki,
  optional context tooling, Understand Anything, and bounded workers stay
  memory, comprehension, context, economic, or review aids.
- Completed issue #602's graph context retrieval pilot against the active repo:
  graph-context tooling stayed local and wrote only ignored local output; `rg`
  plus context packs and the decision registry remained the best initial
  discovery path, and symbol-known impact queries proved useful only as
  optional maintainer impact analysis.
- Added issue #601's local tamper-evident report audit chain:
  `entroping report artifact-manifest` now appends value-free
  `.entroping/report-audit-chain.jsonl` events with previous-hash linkage,
  artifact checksums, command metadata, schema versions, verification status,
  and broken-chain diagnostics while keeping artifact contents, env values,
  raw traffic, provider prompts, and provider outputs out of the evidence.
- Added issue #598's local auth-chain evidence boundary: Hurl metadata can
  declare value-free `auth_flow`, `auth_requires`, and `auth_produces` names,
  dry-run plans and JSON/JUnit/HTML run reports expose only those names, env
  values still pass to Hurl through the existing variables-file path, and CSRF
  token key/value redaction now shares the common secret-safety helper.

## 2026-06-11

- Added issue #599's self-healing Hurl maintenance boundary: Architect
  proposals stay preview/diff/manifest-backed, `entroping run` remains
  provider-free, agent-run manifests now carry value-free `source_evidence`,
  and agent-bundle reports can scope preview evidence by selected Hurl target
  without storing raw prompts, provider output, or Hurl contents.
- Fixed issue #630's AI worker queue state-write race so queued, running,
  completed, and failed job JSON artifacts are written through same-directory
  atomic replacement instead of direct truncation; concurrent `run-next`
  processes no longer misclassify valid running jobs as corrupt while another
  process rewrites their state.
- Added a curated prompt library under `docs/meta/prompt-library/` for fresh
  Codex handoffs, issue workers, Spark-safe sessions, multi-agent marathons,
  thread steering, Gemini reviews, and DeepSeek/OpenCode reviews, with the
  vault index and agent control plane pointing to the reusable prompt shelf.
  The library defaults to the maintainer's active Entroping and source-archive
  paths so local sessions can paste prompts without placeholder replacement.
  It now also includes reusable PR merge-gate, bug-bash, backlog-triage,
  roadmap/progress, launch-readiness, stable-core, context-reconciliation, CI
  debug, security-review, and after-sleep status prompts. Each local-path prompt
  now tells Codex Cloud to use the task-provided repository root when the
  maintainer macOS path is unavailable.
- Added issue #600's bounded OpenAPI negative-path corpus so
  `architect build --new` now emits committed Hurl under
  `tests/generated/negative/` for malformed JSON, schema violations, boundary
  values, SQLi-like strings, and IDOR-style path variants when operations
  declare explicit `400` or `422` validation responses; generated files carry
  category, severity, and safety metadata, run reports expose that
  classification without arbitrary metadata dumps, and mutating negatives are
  marked `destructive` for protected-run blocking.
- Added issue #596's production safe-mode preflight so protected environments
  default to `prod`, `production`, and `protected`, suite manifests can declare
  `protected` plus safety intent, mutating Hurl methods block before subprocess
  execution unless marked `read-only`, `idempotent`, or `teardown-backed`, and
  JSON/JUnit/HTML/dry-run evidence explains blocked tests without leaking
  environment values.
- Fixed issue #627's protected-block report accounting so mixed safe/unsafe
  protected selections preserve selected, executed, and not-scheduled evidence
  when the preflight stops before Hurl execution.
- Accepted issue #595's Docker CI image boundary: GHCR image work is deferred
  until package-index proof, must include pinned Entroping/Hurl/hurlfmt,
  non-root runtime, OCI labels, digest-pinnable tags, rollback and smoke-check
  rules, and cannot replace `uv tool install`, PyPI, source checkout, or later
  Homebrew paths.
- Accepted issue #594's official GitHub Action boundary: the generated starter
  workflow remains the supported downstream CI path, while a future
  `entroping/action` belongs in a dedicated action repo after package-index
  proof, with Hurl verification, local report artifacts, read-only defaults,
  opt-in permission-scoped PR comments, and no LLM calls during `run`. The
  generated starter now also matches the documented `reports/doctor-health.json`
  diagnostic artifact.
- Clarified issue #586's launch surface boundary: WireMock mappings and
  dependency maps remain supported, tested, optional advanced surfaces, while
  REST/OpenAPI + QAnstitution + Hurl + CI reports stay the primary launch story.
- Defined issue #588's QAnstitution schema-version policy: `version: "4.1"`
  or omitted legacy markers are accepted, old/future markers fail closed with
  migration guidance, the authoring JSON Schema exposes the supported marker,
  and migration helpers must stay explicit instead of running from `run`,
  `doctor`, or config loading.
- Added issue #571's install-reference sync check so public pinned GitHub
  install docs are validated against `docs/meta/release-evidence.json` during
  release checks, with an intentional `--write` path for release-tag bumps.
- Compressed issue #591's README front door from 517 lines to under 220 lines
  while preserving launch copy, demo assets, install/basic-use guidance, alpha
  status, license, and deep links to existing docs.
- Added issue #590's deterministic test taxonomy report so
  `scripts/audit_quality.sh` now writes `reports/test-taxonomy.json` with
  behavior, docs-compliance, script-integrity, integration, smoke, regression,
  and security evidence categories before coverage/Radon/Vulture gates.
- Clarified issue #592's versioning split across README, Product Spec, TDS, and
  Roadmap: v4.1 is the product/spec/CLI contract generation, while package
  releases stay on alpha Git tags and PEP 440 metadata from `pyproject.toml`.
- Added issue #593's installed CLI plus real-Hurl E2E proof so the suite now
  covers `entroping init` through `entroping run --ci --report json --report
  junit` against a localhost API, with JSON/JUnit assertions, injected
  QAnstitution rule evidence, and source `.hurl` immutability.
- Fixed issue #570's generated GitHub Actions bootstrap workflow so new
  downstream starters default to `ENTROPING_INSTALL_SPEC` pointing at the
  latest GitHub source branch, while teams can still pin a reviewed tag by
  changing that one env value.
- Fixed issue #611's Hurl binary trust policy so bare binary names
  intentionally follow parent `PATH`, explicit absolute Hurl paths are
  normalized and can bypass hostile earlier `PATH` entries, relative binary
  paths fail closed, missing default Hurl no longer claims version-check
  evidence, and the minimized child subprocess `PATH` remains tested.
- Fixed issue #609's AI worker queue supervisor races so concurrent
  `run-next` calls atomically claim distinct queued jobs, failed workers do not
  leave `running/` entries behind, corrupt queued artifacts are quarantined to
  `failed/` without blocking valid work, and stale `running/` jobs fail closed
  after their timeout grace window.
- Added issue #610's Hurl runner chaos regression matrix covering empty output,
  signal-like exit codes, binary/non-UTF-8 streams, truncation boundaries,
  redaction plus truncation, partial stdout/stderr on subprocess errors,
  variable-file cleanup after `OSError`, and unstable retry evidence without
  changing runtime behavior.
- Tuned issue #605's direct DeepSeek worker default so short review jobs use
  `--thinking disabled` by default, with high-effort thinking kept as an
  explicit opt-in for deliberate deep-review runs.
- Added issue #589's direct DeepSeek bounded-context policy so
  `scripts/deepseek_worker.py` now sends selected repo file contents only after
  size, binary, path, UTF-8, and secret-like-content checks pass before any
  artifact write or provider call.
- Fixed issue #572's public changelog ordering so dated release sections stay
  reverse-chronological, with a release-doc regression test to prevent stale
  release history from drifting again.
- Fixed issue #583's traffic-capture startup warning so `entroping watch`
  explicitly reminds users to review redaction coverage before freezing,
  mapping, mocking, or sharing traffic-derived artifacts.
- Added issue #581's direct DeepSeek API worker engine so queued AI jobs can
  run through OpenCode by default or `--engine deepseek-api` for paid
  DeepSeek Flash/Pro runs, with env-only API key handling, local ignored
  artifacts, usage metadata, and no automatic patch application.
- Added issue #579's queued AI worker supervisor so affordable OpenCode and
  DeepSeek jobs can be submitted under `.entroping/ai-jobs/`, run through the
  bounded worker harness, and collected later for Codex validation without
  auto-applying patches or mutating source files.
- Fixed issues #573 and #577's Hurl selection safety gaps so changed-file runs
  reject unsafe Git base refs before invoking `git diff`, and explicit empty
  Hurl discovery roots stay empty instead of falling back to default tests.
- Added issue #575's bounded OpenCode worker harness for DeepSeek review and
  patch proposals, with prompt templates, local `.entroping/ai-reviews/`
  artifacts, timeout classification, patch-diff capture, and a user-local
  Codex skill for repeatable invocation.
- Removed issue #562's duplicate `docs/meta/AUTONOMOUS_DEVELOPMENT.md`
  wrapper and pointed issue prompts plus implementation context packs at the
  canonical archived runbook path.
- Added issue #559's root `CHANGELOG.md` as the concise public release history,
  with `.context/changelog.md` kept as the detailed maintainer/agent handoff
  log.
- Extracted issue #561's `entroping run` option validation into
  `entroping.core.run_option_validation`, keeping Typer responsible only for
  user-facing `BadParameter` formatting while preserving existing CLI behavior.
- Added issue #565's `entroping report policy-diff --fail-on-change` CI mode
  so effective-policy drift can fail a build explicitly while default
  review/report behavior still exits successfully for valid changed diffs.
- Added issue #558's report help tiering so `entroping report --help` now
  shows first-hour CI/review commands before advanced local evidence commands
  without renaming or removing any report subcommands.
- Added issue #560's scheduled/manual performance-smoke workflow so
  `scripts/performance_smoke.py` now produces recurring CI evidence without
  adding timing-sensitive work to every pull request.
- Added issue #556's source-preservation coverage for external `--source-root`
  links so the decision registry now has direct pass/fail tests for preserved
  Gemini/NotebookLM-style source material outside the implementation repo.
- Added issue #554's direct optional-extras smoke script coverage so local
  tests now verify suppressed provider-library output, success output, safe
  exception reporting, and non-callable AI/proxy boundary failures.
- Fixed issue #552's Git-backed changed-file and OpenAPI baseline subprocess
  boundaries so slow `git diff` or `git show` calls time out after 30 seconds
  and surface typed Entroping errors instead of hanging beta workflows.
- Refreshed issue #550's project progress dashboard after the #517-#523 and
  #548 cleanup queue closed, keeping the next queue focused on external
  stable-core blockers unless a real local defect or ready product gap appears.
- Added issue #548's public MkDocs Roadmap navigation link to the canonical
  root `ROADMAP.md`, keeping roadmap detail out of duplicated docs content
  while making launch/status discovery available from the docs site.

## 2026-06-10

- Raised issue #544's default GitHub Project GraphQL preflight threshold from
  5 to 50 remaining calls after finish-session cleanup still hit Project
  field/item read warnings below that range; the environment override remains
  available for local tuning.
- Added issue #542's remote branch preflight so `scripts/start_issue.sh`
  refuses to create an issue worktree when the requested branch name already
  exists on `origin`, preventing multi-session pushes from colliding with stale
  or unrelated remote branches.
- Added issue #540's bytecode-free local gate setting so `scripts/check.sh`,
  `scripts/feature_gate.sh`, and `scripts/regression.sh` run with
  `PYTHONDONTWRITEBYTECODE=1`, reducing ignored `__pycache__` noise during
  repeated agent verification loops without changing product runtime behavior.
- Added issue #538's GitHub Project GraphQL quota preflight so
  `scripts/start_issue.sh` and `scripts/finish_issue.sh` skip only
  Project-board updates when quota is exhausted or below the configured local
  threshold, while keeping issue labels, worktree creation, verified cleanup,
  and clear warnings intact.
- Refreshed issue #515's release-evidence ledger pointers after the
  freshness-validator fix, preserving alpha and stable-core non-claims.
- Fixed issue #513's release-evidence freshness loop so a post-merge
  self-refresh commit remains current only when Git proves the newer successful
  `main` runs changed only the ledger, pinned evidence test, and changelog.
- Refreshed issue #511's release-evidence ledger pointers to the latest green
  `main` CI and Pages runs after the stable-core blocker wording updates,
  without changing alpha release or stable-core readiness claims.
- Aligned issue #509's roadmap and maintainer-context stable-core blocker
  wording with the canonical blocker names from the release-evidence ledger.
- Aligned issue #507's launch-readiness stable-core blocker wording with the
  canonical stable-core readiness blocker names so alpha launch output can be
  compared directly to stable-core evidence.
- Aligned issue #505's roadmap stable-core blocker list with the readiness
  gates so repeated alpha release-candidate evidence stays tracked separately
  instead of appearing as an unresolved blocker.
- Fixed issue #503's stable-core readiness Markdown output so blocker issue
  links now show their tracked status, making closed helper work visibly
  distinct from still-blocked stable-core evidence.
- Updated the GitHub Actions `astral-sh/setup-uv` pin from `v8.1.0` to
  `v8.2.0` across CI, Pages, publish workflows, downstream starter templates,
  release runbook examples, and workflow guard tests.
- Refreshed issue #501's daily project dashboard so
  `docs/meta/PROJECT_PROGRESS.md` no longer points agents at the closed #491
  queue, shows #499's traffic approval manifest redaction-confidence evidence,
  and keeps the local queue honest when only external blockers remain.
- Added issue #499's approval-manifest redaction confidence field so
  `reports/approvals/*.json` now records `low_confidence_records` alongside
  other counts-only redaction evidence and the published schema requires the
  field. The same PR repaired strict-doc archive links and kept CI's Hurl
  formatter checks aligned with the Windows doctor-only install-smoke claim.
- Fixed issue #495's redaction-confidence boundary so captured traffic now
  records low/high redaction confidence, malformed JSON and unknown textual
  payloads remain locally usable but low-confidence, redaction reports expose
  only safe counts, and `freeze`, `freeze --mock`, and `map --export png` fail
  closed before writing artifacts from low-confidence records.

## 2026-06-09

- Fixed issue #491's known-failure preflight gap so malformed
  `ignore_failures[].expires` values fail QAnstitution loading,
  `entroping doctor --ci` reports expired exceptions as readiness errors, and
  runtime/report gate-injection paths share one expiry validator.
- Fixed issue #489's dependency traffic-state readers so `entroping map` and
  run dependency-drift observations now use the read-only SQLite path, preserve
  existing missing/empty-state behavior, and have regression coverage proving
  these evidence workflows do not open the write-capable traffic store.
- Fixed issue #487's redaction review state access so
  `entroping report redaction --output md|html` now reads existing traffic
  state through the read-only SQLite path, preserves missing/empty-state
  behavior, and has regression coverage proving report generation does not
  mutate the traffic state database.
- Added issue #415's safe capture summary report so
  `entroping report capture-summary --output md|json` summarizes redacted local
  traffic state by derived session, method, host, dependency target, status
  family, and redaction category without rendering raw traffic values.
- Added issue #416's effective-policy evidence diff so
  `entroping report policy-diff --base <path> --current <path> --output md|json`
  compares existing effective-policy JSON artifacts, emits schema-versioned
  import and gate deltas, and avoids policy reloads, provider calls, Hurl
  execution, and failure-on-valid-change behavior.
- Added issue #417's run dry-run execution plan so `entroping run --dry-run`
  resolves selected tests, tag or changed-file selectors, effective and
  injected QAnstitution gates, environment name, missing variable names, worker
  settings, and requested report paths without invoking Hurl, writing
  latest-run state, writing execution events, writing executed-result reports,
  or mutating source `.hurl`. `--report json` writes the separate
  schema-versioned `reports/run-plan.json` artifact.
- Added issue #418's Hurl version compatibility checks so `entroping doctor`
  runs `hurl --version` through the bounded subprocess boundary, reports
  compatible, missing, unsupported, and unparsable states in human and JSON
  output, keeps normal warning exit compatibility, and makes `doctor --ci`
  fail when Hurl compatibility cannot be proven.
- Added issue #467's local multi-agent review bundle so
  `entroping report agent-bundle --output md|json` summarizes configured
  Builder, Breaker, and Auditor evidence from sanitized
  `.entroping/agent-runs/*.json` manifests, supports role and scope filters,
  writes schema-versioned `reports/agent-bundle.md` or
  `reports/agent-bundle.json`, and reports missing config/evidence, invalid
  provider-output validation, missing Hurl validation, unsafe manifests, and
  multi-role output-path conflicts without calling providers, Hurl, or
  `entroping run`.

## 2026-06-05

- Added issue #419's Architect refactor preview mode so
  `entroping architect refactor --preview` validates proposed Hurl edits
  through the existing provider, parser, and managed-block merge boundaries,
  prints a redacted unified diff, and leaves target Hurl files unchanged while
  preserving value-free agent run evidence.
- Added issue #420's latest-failure rerun workflow so
  `entroping run --rerun-failures` selects failed source `.hurl` files from
  `reports/run-latest.json` or `.entroping/latest-run.json`, reuses the prior
  report environment unless `--env` overrides it, validates paths before Hurl
  execution, and stays a fast-feedback shortcut rather than release proof.
- Added issue #421's policy gate coverage matrix so
  `entroping report gate-coverage --output md|json` maps effective
  QAnstitution gates to committed Hurl test files, tags, operation IDs, request
  methods, and redacted paths, lists unmatched gates, and avoids Hurl
  execution, temporary assertion injection, provider calls, full URLs, query
  strings, headers, bodies, variables, and captured traffic values.
- Added issue #422's opt-in GitHub Actions starter install so
  `entroping init --github-actions` writes the reviewed starter workflow to
  `.github/workflows/entroping.yml`, refuses existing workflows, ships the
  starter as package data, and verifies the packaged template in package
  artifacts without adding secrets, provider credentials, hosted-service
  coupling, or PyPI/TestPyPI readiness claims.
- Added issue #423's report artifact manifest so
  `entroping report artifact-manifest` writes
  `reports/artifact-manifest.json` with project-relative paths, schema
  versions when available, sizes, SHA-256 checksums, and missing-artifact
  evidence for standard local reports without embedding report contents or
  claiming signing/attestation.
- Added issue #428's gate-injection explanation report so
  `entroping report gate-injection --target <path> --output md|json` resolves
  effective QAnstitution gates for selected local Hurl files without running
  Hurl or mutating source `.hurl` files.
- Added issue #429's deterministic fail-fast execution mode so
  `entroping run --fail-fast` stops scheduling after the first failing Hurl
  result, preserves source `.hurl` immutability, and records selected,
  executed, not-scheduled, and fail-fast summary evidence in latest-run state
  and requested reports.
- Added issue #430's sanitized run execution event log so every
  `entroping run` writes `.entroping/latest-run-events.jsonl` with
  `entroping.run-events.v1` start, selected-test, redacted-result, artifact,
  no-match/error, and completion events for CI wrappers and coding agents.
- Added issue #431's local policy-pack self-test command so
  `entroping config test-policy-pack --pack <path> [--output text|json]`
  validates safe local boundaries, manifest/entrypoint/gate/final-gate
  consistency, consumer examples, and local-only behavior before vendoring or
  publishing without copying files, editing `qanstitution.yaml`, contacting a
  registry, or requiring provider keys.
- Added issue #432's `freeze --dry-run` preview so Hurl and WireMock freeze
  flows can show selected redacted records, proposed output paths, golden
  status, and counts-only redaction categories without writing tests, mocks,
  approval manifests, or source artifacts.
- Added issue #433's explicit `watch` capture scope allowlist so traffic
  persistence now requires `--target`, `--scope-host`, or
  `--scope-url-prefix`. The proxy adapter normalizes case and default ports,
  ignores out-of-scope or malformed flow URLs before building traffic models,
  preserves pre-persistence redaction for in-scope records, and reports only
  count summaries for recorded, out-of-scope, and malformed flows.

## 2026-06-04

- Added issue #468's lossless decision registry so
  `docs/meta/DECISION_REGISTRY.yaml` indexes durable product, architecture,
  workflow, and monetization decisions with links back to ADRs, docs, issues,
  and source evidence. `scripts/source_preservation_check.py` now validates the
  registry, local source-history anchors, and registry links through
  `scripts/doc_governance_check.sh`, while `scripts/context_pack.sh` includes
  the registry in generated agent context.
- Added issue #434's story traceability gap summary so
  `entroping report traceability --output md|json` links Hurl `story_id`
  metadata to local `docs/stories/*.md` story documents, reports missing
  local stories, stories without tests, duplicate story IDs, malformed story
  metadata, and unsafe story paths, and keeps the workflow local-only with no
  business-system API calls.
- Added issue #435's OpenAPI operation selector so `entroping run
  --operation-id <id>` executes existing Hurl files with exact committed
  `operation_id` metadata, rejects selector conflicts before execution, and
  preserves operation ID evidence in JSON, JUnit, and HTML run reports.
- Added issue #436's known-failure runtime guardrail so selected-test
  `ignore_failures` entries now fail before Hurl execution when their rule ID
  does not match any injected QAnstitution gate, while filtered-out test
  exceptions stay outside the current subset.
- Added issue #437's deterministic OpenAPI breaking-change diff audit so
  `architect audit --focus logic --changed-from <ref> --output md|json`
  compares the configured local OpenAPI spec with the same file at a Git base
  ref, reports removed/added operations, status-code changes, newly required
  request inputs, and practical JSON response-shape changes, and links findings
  to committed OpenAPI Hurl metadata without generating or deleting tests.
- Added issue #449's captured-artifact approval manifests so `freeze`,
  `freeze --mock`, and `map --export png` write
  `reports/approvals/*.json` with schema
  `entroping.traffic-artifact-approval.v1`, generated paths, checksums,
  deterministic source fingerprints, and counts-only redaction summaries
  without raw traffic values or approval decisions.
- Added issue #448's provider budget evidence so prompt-backed Architect build,
  refactor, and Auditor review paths expose provider, latency, token counts
  when available, and estimated cost when local QAnstitution rate hints are
  configured. Agent run manifests stay value-free and do not store prompts,
  secrets, raw provider responses, or approval decisions.
- Added issue #447's reusable QAnstitution gate groups so local policy authors
  can define `gate_groups`, reference them from top-level `gates`, expand nested
  groups deterministically, reject missing references and cycles before
  execution, preserve import/final semantics, and show source group provenance
  in effective-policy reports without adding registry behavior or a second
  runtime policy format.
- Added issue #446's CI-readiness doctor mode so `entroping doctor --ci`
  validates Hurl availability, safe `.entroping/` and `reports/` artifact
  paths, committed suite manifests, required Hurl variables, and provider-free
  `run --ci` expectations without CI provider API calls, workflow mutation, or
  env-value disclosure. JSON output extends `entroping.doctor.v1` with optional
  `ci_readiness` evidence.
- Added issue #445's local coverage badge report so `entroping report badges`
  writes Shields endpoint JSON for policy-gate, OpenAPI operation, and
  story-traceability coverage from existing local reports. `report traceability`
  now supports `--output json` so badge generation can stay report-backed
  without calling shields.io or any hosted service.
- Added issue #444's run-to-run regression delta report so
  `entroping report delta --base <path> --current <path> --output md|json`
  compares existing JSON run reports, emits deterministic added/resolved/
  changed/unchanged failure, latency, and policy-gate deltas with schema
  `entroping.run-delta-report.v1`, exits nonzero for added or changed failures,
  and never renders raw stdout/stderr.
- Added issue #443's traffic-vs-OpenAPI route audit so
  `architect audit --focus logic --output md|json` opportunistically compares
  redacted Eye traffic route summaries against OpenAPI templates, flags
  undocumented observed routes, lists documented and spec-only routes, and keeps
  raw query strings, headers, cookies, bodies, host userinfo, credentials, and
  captured values out of audit output.
- Added issue #442's OpenAPI security-scheme coverage generation so
  `architect build --new` writes deterministic missing/invalid auth Hurl tests
  under `tests/generated/security/` for supported HTTP bearer/basic and API-key
  header/query/cookie schemes when operations declare explicit `401` or `403`
  responses, while unsupported schemes are reported as warnings instead of
  guessed.
- Added issue #441's timeout evidence so JSON, JUnit, HTML, and
  review-summary artifacts show effective per-test `timeout_ms`, while Hurl
  subprocess timeouts use status `timeout`, exit code `124`, and
  timeout-specific report findings distinct from assertion failures.
- Added issue #440's deterministic tag-expression run selection so
  `entroping run --tag-expression "smoke and not slow"` selects Hurl tests with
  a safe `and`/`or`/`not` parser over Entroping metadata tags, reports
  selected/skipped counts without file contents, rejects invalid expressions
  before Hurl execution, and preserves repeatable `--tag` OR semantics.
- Added issue #427's sanitized agent run manifests so prompt-backed Architect
  build, Breaker build, merge-build, refactor, and Auditor review paths write
  `.entroping/agent-runs/*.json` with value-free role/model/persona/prompt-hash,
  output-path, tag, validation, latency, and token evidence without raw prompts,
  provider output, persona content, secrets, Hurl contents, or traffic.
- Added issue #414's include/exclude capture filters so `freeze`,
  `freeze --mock`, and `map` narrow already-redacted traffic by host, method,
  and request path before generating Hurl, WireMock, or dependency-map
  artifacts, with exclude precedence, empty-filter errors before writes, and no
  query/header/body values in filter output.
- Added issue #405's bounded retry and flake evidence so
  `settings.retry` drives deterministic per-file Hurl subprocess retries,
  final attempt status remains authoritative, and JSON/JUnit/HTML/review-summary
  artifacts expose retry count, attempt status, exit code, duration, and
  unstable pass-after-retry signals without raw per-attempt output.
- Added issue #404's changed OpenAPI operation generation so
  `entroping architect build --new --changed-from <ref>` compares the configured
  local OpenAPI spec with the same file at a Git base ref, classifies added,
  modified, renamed, removed, and unchanged operations, regenerates only current
  added/modified/renamed operation IDs, and reports removed operations for
  manual review without deleting tests.
- Added issue #403's sanitized failure-bundle workflow so
  `entroping report failure-bundle` writes `reports/failure-bundle/manifest.json`
  with `entroping.failure-bundle.v1`, sanitized latest-run JSON, generated bug
  Markdown, failed-test Hurl metadata, optional reviewed report artifacts,
  artifact sizes/hashes, and guardrails against missing/passing runs, raw local
  state, env files, symlinked artifacts, and source Hurl contents.

## 2026-06-03

- Added issue #402's named suite manifests so `entroping run --suite <name>`
  loads committed `suites/<name>.yaml` files with schema
  `entroping.suite.v1`, root-bounded path globs, tags, env, reports, parallel,
  and drift settings while preserving the existing deterministic run workflow.
- Added issue #401's local policy-pack vendoring workflow so
  `entroping config vendor-policy-pack` copies reviewed local packs under
  `policy-packs/`, validates manifest and QAnstitution evidence, preserves
  final-gate behavior, and appends a local import without remote registry
  coupling.
- Added issue #400's OpenAPI operation-to-Hurl coverage matrix so
  `architect audit --focus logic --output md|json` now reports covered,
  uncovered, ambiguous, and stale operation mappings with
  `entroping.openapi-audit.v1` JSON output and project-relative Hurl paths.
- Added issue #399's reviewed drift-baseline promotion command so
  `entroping report promote-drift-baseline` validates
  `entroping.drift-baseline.v1` candidates, rejects unsafe paths and
  stale/future schemas, and atomically writes `.entroping/drift-baseline.json`
  only after human review.
- Added issue #398's SARIF report output so `entroping report sarif` writes
  `reports/entroping.sarif` from local JUnit, drift, and optional traceability
  findings with stable rule IDs, SARIF severities, best-effort locations,
  redacted text, and no provider calls or upload side effects.
- Added issue #397's changed-test run mode so
  `entroping run --changed-from <ref>` selects existing changed `.hurl` files
  from Git diff for fast local or agent feedback while preserving full-suite
  `run` as the default release gate.
- Added issue #395's machine-readable doctor output so
  `entroping doctor --output json` emits schema version
  `entroping.doctor.v1` with tool, traffic-state, QAnstitution, and
  agent-readiness health while preserving human doctor exit semantics.
- Added issue #394's doctor agent-readiness validation so configured
  Builder/Auditor/Breaker persona files are checked through the runtime persona
  loader, unsafe persona setup fails locally, and configured `api_key_env`
  names are reported without printing secret values or calling providers.
- Added issue #396's Hurl variable preflight so `entroping run` scans
  selected temporary execution copies before invoking Hurl, fails early with
  missing variable names only, accepts `envs/<name>.env`, shell
  `HURL_VARIABLE_<name>`, Hurl `[Options] variable`, captures, and safe Hurl
  built-ins, and keeps variable values out of CLI errors.
- Added issue #393's Auditor-backed Architect audit route so
  `architect audit --focus auditor` loads the configured Auditor persona/model,
  sends deterministic coverage and path-only Hurl inventory context, validates
  review JSON before display, and renders Markdown or JSON without writing files.
- Added issue #392's Breaker-backed Architect prompt build route so
  `architect build --agent breaker --prompt ...` loads the configured Breaker
  persona/model, adds Breaker-specific generation instructions, tags generated
  Hurl with `breaker`, and keeps Auditor out of prompt-build file generation.
- Added issue #385's transitive dependency security refresh so `uv.lock` moves
  optional `litellm`'s `aiohttp` dependency from vulnerable `3.13.5` to
  `3.14.0`, restoring the all-extras dependency audit gate without adding a
  direct runtime dependency.
- Added issue #381's README OWASP policy-pack wedge so the public launch story
  highlights the local starter pack as runtime security governance while
  preserving explicit non-endorsement, non-compliance, and non-certification
  boundaries.
- Added issue #382's README backstage-context cleanup so first-time users see
  the product, demo, install, and CI path before maintainer vault, release, and
  agent-handoff material.
- Added issue #383's README schema-autocomplete note so new users can find the
  checked-in QAnstitution JSON Schema while `entroping doctor` stays the
  authoritative runtime validation path.
- Added issue #384's launch-copy cleanup so the public first story stays
  focused on REST/OpenAPI, QAnstitution, Hurl, and CI reports while advanced
  surfaces remain documented as optional or deeper examples.
- Added issue #372's post-alpha CLI UX decision queue so env-file paths,
  generated output roots, deprecated command guidance, and QAnstitution policy
  migration rules are documented before any command-surface change.

## 2026-06-02

- Added issue #371's vault/context cleanup so completed one-off demo context is
  marked archival, evolution docs are labeled historical evidence rather than
  current product truth, and Obsidian/GitHub/source-promotion guides have
  explicit ownership boundaries.
- Added issue #370's report writer module split so the public
  `entroping.core.report_writer` facade remains stable while response
  fingerprinting, JSON serialization, JUnit/HTML/bug rendering, and report
  errors move into focused core modules.
- Added issue #368's CLI adapter test split so the former 3,374-line
  `tests/test_cli.py` is now organized by command area, with shared CLI test
  helpers and the existing 113 assertions preserved.
- Added issue #369's shell script quality gate so tracked `.sh` files are
  checked with `bash -n`, ShellCheck runs when available with an explicit skip
  message otherwise, and `scripts/feature_gate.sh` executes the shell gate
  before Python lint/type/test checks.
- Added issue #367's Python integration proof for `entroping run`, using a
  fake `hurl` executable on `PATH` to exercise CLI wiring, discovery, gate
  injection, variables-file passing, subprocess execution, source immutability,
  and JSON/JUnit report writing without network access.
- Added issue #366's PEP 561 package marker so `src/entroping/py.typed` ships
  with the wheel and sdist, while `scripts/package_check.sh` and its tests now
  fail if package artifacts omit `entroping/py.typed`.
- Added issue #365's captured-traffic redaction hardening so multipart request
  and response bodies are replaced with redacted media-type summaries before
  persistence, broad token prefix patterns avoid short documentation
  placeholders, and harmless Bearer prose is preserved while common credential
  coverage remains tested.
- Added issue #364's hardened XML report parsing so JUnit inputs consumed by
  GitHub annotations and review summaries use `defusedxml`, reject DTD/entity
  constructs as unsafe XML, keep valid JUnit behavior intact, and include
  `defusedxml` in the reviewed direct dependency license policy.

## 2026-06-01

- Added issue #347's shell-completion onboarding note for Typer's existing
  `--install-completion` and `--show-completion` global options without
  expanding Entroping's locked command namespace.
- Added issue #346's no-Hurl CLI smoke script so constrained agent or
  downstream sessions can prove CLI boot, version, minimal init, and doctor
  behavior without installing or executing Hurl.
- Added issue #345's traffic-store retention optimization so pruning now uses
  a SQL-level delete for stale event IDs while preserving newest-event
  retention semantics and insertion-order reads.
- Added issue #344's shared path-safety helper so common symlink component
  traversal lives in `entroping.core.path_safety`, config imports reject
  symlinked local imports, and existing adapters keep their domain-specific
  error messages.
- Added issue #351's OWASP API Security Top 10-inspired starter policy pack
  under `examples/policy-packs/owasp-api-top-10/`, with local QAnstitution
  imports, provenance metadata, smoke evidence, honest non-compliance claims,
  and open-core boundary notes for deeper maintained packs and support.
- Added issue #350's practical `watch` limits guidance so the user guide now
  warns about per-client mitmproxy CA setup, corporate VPN/proxy conflicts,
  certificate pinning, proxy bypass, session headers, and capture authorization
  before users try real traffic interception.
- Added issue #349's brand-integrity audit: ADR-0012 keeps
  `qanstitution.yaml` canonical, preserves "The QAnstitution is Law. Traffic
  is Truth. Hurl is the Enforcer.", rejects unplanned `entroping.yaml` aliases,
  and tightens public positioning away from autonomous-agent-swarm claims.
- Added issue #348's public-docs launch-path cleanup so README uses a concise
  `Project Context` handoff instead of a deep-docs inventory, MkDocs navigation
  is grouped by reader task, and documentation governance blocks casual
  first-level public-nav expansion.
- Added issue #343's HTML run-summary escaping so the local HTML report now
  escapes the summary header consistently with project, environment, generated
  timestamp, rule IDs, known-failure summaries, and captured output.
- Added issue #342's OpenAPI-generated Hurl validation so
  `architect build --new` validates every compiled Hurl file through the
  parser-backed Hurl validator before writing and leaves no partial generated
  files behind when validation fails.
- Added issue #352's progress and agent-control cleanup so
  `docs/meta/PROJECT_PROGRESS.md` is a short daily dashboard again,
  `ROADMAP.md` separates product direction from backlog tracking,
  `docs/meta/DOCS_GOVERNANCE.md` blocks new strategy-doc sprawl, and
  `docs/meta/AGENT_CONTROL_PLANE.md` defines the Codex-first software-factory
  model for OpenCode/free-model/local-Qwen workers.
- Added issue #340's public-docs discoverability cleanup so the README links
  the MkDocs site before deep context, the MkDocs landing page explains how it
  relates to GitHub Issues, ROADMAP, Obsidian, and docs governance, and the
  documentation control plane names each canonical surface.
- Added issue #337's GraphQL and SOAP Hurl-over-HTTP fixtures with local demo
  servers, QAnstitution gates, env examples, protocol-specific Hurl assertions,
  and README/Vault discoverability without adding new protocol engines.
- Added issue #336's runtime known-failure semantics so active
  `ignore_failures` entries skip only matching Entroping-injected QAnstitution
  gates by exact test path and rule ID, expired exceptions block before Hurl
  execution, and JSON/JUnit/HTML run reports expose the applied exception
  evidence.
- Added issue #329's reusable policy-pack verification artifact so
  `scripts/policy_pack_smoke.py --pack <local-pack> --format json --strict`
  validates arbitrary local pack directories, emits attachable
  `policy-pack-verification` evidence, and checks attribution, entrypoint
  imports, final gates, and consumer examples without registry or runtime
  manifest behavior.
- Added issue #307's repeated alpha release evidence so the committed ledger
  records `v0.1.2-alpha-rc.1` local release-candidate rehearsal proof with
  reviewed CI/Pages run IDs and a passing `scripts/release_check.sh
  --require-live-demo` gate, while stable-core remains blocked by package-index
  proof, stable-core compatibility decision, and real downstream user feedback.
- Added issue #312's policy-pack distribution decision so packs have a
  local-first path for versioning, distribution, import verification,
  provenance, attribution, open-core/premium boundaries, minimum smoke evidence,
  and follow-up implementation issues before registries or hosted catalogs.
- Added issue #318's downstream feedback evidence kit so real external-user
  feedback can be collected with install path, OS, Python, Hurl, command,
  success/failure, friction, and sanitized logs while excluding secrets,
  private URLs, raw traffic, and proprietary payloads.
- Added issue #317's policy-pack provenance validation so the example
  API-baseline manifest declares local source, license, supported Entroping
  range, evidence command, gate files, gate IDs, and final flags, and
  `scripts/policy_pack_smoke.py --strict` verifies those claims against loaded
  QAnstitution gates without adding registry behavior.
- Added issue #316's artifact-backed review summary:
  `entroping report review-summary` writes provider-neutral Markdown from local
  JSON, JUnit, drift, and optional traceability evidence, and the downstream
  GitHub Actions starter now generates JSON before uploading `reports/`.
- Added issue #319's stable-core blocker issue map so
  `scripts/stable_core_readiness.py --format json` and Markdown output link
  each unresolved stable-core blocker to the GitHub issues that can satisfy it,
  without changing `stable_core_ready=false`.
- Added issue #315's optional release-evidence freshness check so maintainers
  can compare committed CI/Pages run IDs and commits with latest successful
  `main` runs through `gh`, or fixture input in tests, without mutating the
  ledger or making normal release validation network-dependent.
- Added issue #314's downstream smoke release-gate wiring so
  `scripts/release_check.sh` runs `scripts/downstream_smoke.py` when Hurl is
  available, supports `--skip-downstream-smoke` for diagnostics, and reports
  missing-Hurl versus Entroping-run failures distinctly.
- Added issue #313's local wheel install smoke so release checks can install
  the built wheel into a temporary venv, run only installed public CLI commands
  from a temporary project, and emit machine-readable evidence without
  PyPI/TestPyPI or network registry access.
- Aligned issue #301's release-evidence blocker list with stable-core
  readiness so package-index proof, real downstream user feedback, and the
  stable-core compatibility decision remain consistent across both gates.
- Expanded issue #299's release-evidence validator so Pages CI and local
  downstream smoke evidence are strict ledger fields, while the ledger still
  states that stable-core remains blocked by package-index proof,
  compatibility decision, and real downstream user feedback.
- Added issue #297's downstream smoke evidence harness so maintainers can prove
  Entroping runs through the public CLI from an external temporary project while
  keeping real downstream user feedback as a separate stable-core blocker.
- Clarified issue #295's release-evidence wording so committed CI evidence is
  treated as last reviewed release evidence, not a self-updating current-HEAD
  assertion.
- Added issue #293's release-evidence ledger so alpha releases, last reviewed
  `main` CI, package-index status, and stable-core blockers are committed and
  validated by `scripts/release_evidence.py --strict`,
  `scripts/stable_core_readiness.py`, and the release gate.
- Added issue #291's README launch-polish slice: concrete "Use Entroping
  When" scenarios now appear before the demo, and reviewed animated GIF
  previews show the checkout happy path plus AI-regression failure proof.
- Added issue #279's effective policy evidence command:
  `entroping report policy --output md|json` writes resolved QAnstitution
  gate provenance, including imports and local overrides.
- Added issue #280's public claims audit so documentation governance blocks
  unsupported production-readiness and security-guarantee language before it
  reaches public Markdown.
- Added issue #281's direct dependency license policy gate with reviewed
  runtime, optional, and dev dependency entries plus security-gate wiring.
- Added issue #282's downstream integration guardrails so only the proven
  GitHub Actions template is committed and other CI providers require real
  runner evidence before native examples land.
- Added issue #283's AI-regression failure proof fixture and script, showing
  Entroping blocking a body-correct API that drops `X-Request-Id`.
- Added issue #284's stable-core readiness evidence check and release-gate
  wiring so v1/stable claims stay tied to explicit evidence and blockers.
- Added issue #285's backlog health guard for checking GitHub issue labels and
  milestones before or after marathons.
- Added issue #287's policy-pack smoke evidence so the example API-baseline
  pack is validated through local QAnstitution imports before policy-pack
  claims.
- Added issue #288's alpha launch-readiness aggregator and wired it into the
  release check so public demo, release, policy-pack, backlog, and stability
  boundary evidence cannot silently drift.
- Added issue #289's demo proof matrix so maintainers can rehearse the checkout
  happy path, AI-regression failure proof, policy-pack smoke, launch readiness,
  and backlog health from one wrapper.
- Implemented issue #275's doctor traffic-state health check so
  `entroping doctor` reports missing, readable, and incompatible
  `.entroping/state.db` state through the read-only SQLModel traffic-store
  boundary without creating runtime state.
- Reconciled issue #277's public roadmap drift so completed v0.2 adoption and
  v0.3 CLI/report-first depth are no longer presented as future work, and
  v0.4 integration plus v1.0 stable-core evidence are the clear next frontier.

## 2026-05-31

- Implemented issue #260's CLI adapter split so `cli.main` is now a small
  entrypoint and project, config, architect, execution, and report commands live
  in focused modules with architecture regression coverage.
- Implemented issue #262's traffic-store schema policy with
  `schema_version=1`, future-version fail-closed behavior, and TDS migration
  guidance for `.entroping/state.db`.
- Implemented issue #263's typed dependency-drift run failures with
  `DependencyDriftObservationError` under `RunWorkflowError`.
- Implemented issue #264's Studio typing cleanup by removing `no_type_check`
  from the lazy Textual app boundary while keeping optional imports lazy.
- Implemented issue #265's live-demo guidance cleanup so the smoke script
  distinguishes the HTTP readiness probe from Hurl-backed API assertions and
  gives direct Hurl install guidance.
- Added `docs/meta/OBSIDIAN_VS_GITHUB.md` as the internal maintainer guide
  for choosing between Obsidian, GitHub Issues, GitHub Project, roadmap, ADRs,
  source archives, and context files.
- Added executable documentation governance through `docs/meta/DOCS_GOVERNANCE.md`,
  `scripts/doc_governance_check.sh`, CI PR-body validation, PR template
  documentation-impact declarations, and feature-gate wiring so roadmap and
  docs ownership rules are enforced for both humans and agents.
- Added a public `ROADMAP.md`, linked it from the README and Obsidian index,
  and reframed the progress dashboard around visible public backlog, project
  board, and `v0.1.1-alpha` release sync.
- Made the GitHub Project public as `Entroping Public Roadmap`, enabled
  Discussions, closed completed empty milestones, and seeded 26 open issues
  across five public roadmap milestones.
- Added Dependabot visibility for GitHub Actions and Python dependencies so
  dependency drift becomes issue/PR-backed instead of ad hoc.
- Implemented issue #174's README front-door rewrite so the public overview now leads with the sourced AI-regression problem, two-minute live demo proof, launch assets, and concise alpha boundaries before deep Obsidian/spec inventory.
- Added README guardrail tests that keep the public page demo-first and prevent the old "Available now" knowledge-dump structure from drifting back above the alpha/status sections.
- Implemented issue #176's latency drift slice so drift baselines preserve optional `duration_ms` values and reports warn on material per-test latency regressions without adding CLI flags or response-value snapshots.
- Implemented issue #179's Architect validation UX slice so invalid provider JSON and parser-rejected Hurl print actionable no-write guidance without echoing raw provider or parser streams.
- Ran issue #185's public clean-checkout onboarding smoke from a fresh GitHub clone on macOS 26.5 arm64, proving `uv sync --dev`, Hurl availability, `scripts/live_demo_smoke.sh`, and `scripts/release_check.sh --require-live-demo`.
- Implemented issue #191's public launch preview upgrade with curated terminal, HTML report, and dependency-map PNGs generated from live checkout fixture output and redacted traffic state.
- Added issue #184's good-first-issue walkthrough so new contributors can move from labeled issue selection through `scripts/start_issue.sh`, local validation gates, and PR documentation expectations without reading the whole vault first.
- Added issue #189's downstream GitHub Actions starter workflow with pinned Hurl installation, tagged Entroping install, JUnit/HTML report upload, user docs, and guard tests.
- Added issue #195's Brain provider setup path with optional `api_base` and `api_key_env` agent metadata, LiteLLM/local Qwen/oMLX setup docs, no-provider CI guidance, and docs/code guard tests.
- Added issue #186's package-index release runbook for TestPyPI-first Trusted Publishing, PEP 440 alpha naming, token-free GitHub Actions environments, PyPI publish policy, and yank/new-version rollback.
- Added issue #188's public docs site decision and minimal MkDocs Material scaffold with `mkdocs.yml`, `docs/index.md`, and guard tests, while keeping canonical docs in the existing Markdown tree.
- Added issue #183's distribution recommendation: keep `uv tool install` first, activate PyPI/TestPyPI next, prototype Homebrew after PyPI alpha, defer standalone binaries, and track follow-up implementation issues #223 through #225.
- Added issue #230's zero-config checkout demo entrypoint: `scripts/demo.sh` now provides friendly preflight guidance and delegates to the existing live smoke release gate without expanding the locked CLI surface.
- Added issue #232's first-hour QAnstitution UX: the starter policy, checkout demo policy, and new user guide now share schema-validated status, latency, and request-ID header gates without adding condition syntax.
- Added issue #205's CLI compatibility audit: locked command signatures, deprecated alias policy, exit-code semantics, report artifacts, and Typer/help/documentation guard tests now anchor stable-core command claims.
- Added issue #207's tracked threat model refresh: `docs/technical/THREAT_MODEL.md` now records current stable-core security boundaries, implemented controls, prior validated findings, and residual-risk issue mapping.
- Added issue #198's redaction review report: `entroping report redaction --output md|html` writes counts-only captured-traffic redaction reviews without raw header, query, or body values.
- Added issue #227's optional-extras runtime smoke lane: CI installs all extras and runs `scripts/optional_extras_smoke.py` against LiteLLM, mitmproxy, and Textual boundaries without credentials or live capture.
- Added ADR-0010 for issue #231: v0.3 stays CLI/report-first, Studio remains optional/read-only/report-backed, and mutation workflows remain design-only.
- Added issue #199's Architect remediation guidance: invalid provider JSON and parser-rejected Hurl now print safe retry constraints while preserving no-write behavior and raw-output redaction.
- Added issue #209's open-core boundary audit with a maintainer-facing `OPEN_CORE_BOUNDARIES.md`, entrypoint links, and guard tests that keep the Apache-2.0 local CLI strong while separating paid policy-pack, hosted, audit-history, and service surfaces.
- Added issue #208's bounded performance smoke evidence script for large Hurl suites, parallel runner behavior, report size, and SQLModel traffic-store retention, and wired it into the local release check.
- Added issue #206's cross-platform install smoke matrix with Linux pinned-Hurl, macOS Homebrew-Hurl, Windows doctor-only install proof, and docs that keep platform claims aligned with CI.
- Added issue #201's reusable policy-pack layout, including a runtime-neutral `POLICY_PACK_LAYOUT.md` design note and a loadable `examples/policy-packs/api-baseline/` pack shape.
- Added issue #196's Studio mutation workflow design note, keeping v0.3 Studio read-only while documenting future preview, two-step confirmation, no-raw-secret, rollback, and test gates.
- Added issue #192's read-only Studio applied-gate drilldowns by linking latest-run rule IDs to QAnstitution gate definitions without running Hurl or mutating tests/config.
- Added issue #190's read-only Studio traffic session browser, using read-only SQLModel-backed state access plus existing traffic session and graph compilers to show target/dependency route summaries and safe redaction category counts without starting capture or rendering raw traffic values.
- Added issue #229's Python compatibility policy: package metadata now claims Python 3.12 and 3.13 only, CI runs security regression and optional-extras smoke on both versions, and release docs no longer imply unproven Python 3.14 support.
- Added issue #228's strict public docs automation: pull requests run `mkdocs build --strict`, `main` publishes through GitHub Pages, and public-site docs now describe the active deployment instead of the old deferred scaffold.
- Added issue #259's centralized secret-safety boundary so Brain prompt packaging, Hurl runner output, traffic redaction, and traffic-to-Hurl compilation share one redaction model before provider or report boundaries.
- Added issue #261's `hurlfmt` doctor check so the Hurl executor and Architect parser dependency are reported separately.
- Added issue #267's QAnstitution authoring schema: `docs/technical/qanstitution.schema.json`, VS Code/YAML-language-server mapping, schema drift tests, and docs that keep runtime validation authoritative.
- Added issue #266's public repo surface hygiene by moving the Obsidian vault index to `docs/meta/VAULT_INDEX.md`, removing tracked `.obsidian/` machine state, and documenting why `.context/` remains tracked as maintainer/agent handoff material.
- Added ADR-0011 for issue #202: organization QAnstitution imports must preserve provenance, final-gate behavior, local-first validation, and effective-policy evidence before remote/registry features are implemented.
- Added issue #204's non-GitHub CI provider recipes with GitLab CI, Buildkite, CircleCI, and generic shell guidance while deferring untested native templates from `examples/`.
- Added issue #225's standalone binary distribution decision: defer Nuitka/PyInstaller automation until PyPI alpha, Homebrew tap demand, platform signing/notarization runbooks, and support evidence justify it.
- Added issue #223's manual PyPI/TestPyPI Trusted Publishing workflow with unprivileged artifact build, protected `testpypi`/`pypi` environments, and token-free OIDC publish jobs.
- Added issue #224's Homebrew tap prototype with a PyPI-sdist formula template, required Hurl dependency, local audit/install/test smoke commands, and guardrails that keep optional extras out of the default formula.
- Added issue #194's support-ticket API fixture with a local demo server, OpenAPI spec, Hurl smoke test, QAnstitution gates, README runbook, and real-run report path distinct from checkout.

## 2026-05-30

- Promoted the 2026-05-29 NotebookLM Markdown export as the final current source snapshot for reconciliation, while keeping older Gemini and dated NotebookLM files archival.
- Migrated the Eye traffic state adapter from raw `sqlite3` calls to SQLModel-backed SQLite, preserving the local `.entroping/state.db` runtime state boundary and redaction-first persistence behavior.
- Added a deterministic `scripts/context_pack.sh` agent context launcher, cross-agent control-plane docs, Obsidian/NotebookLM/Gemini knowledge workflow, open-source growth and monetization strategy, and community health files.
- Implemented issue #107's session-prompt context-pack wiring so write sessions point to `scripts/context_pack.sh --mode implementation`, review sessions point to `--mode review`, and `core.session_prompt` has meaningful 100% module coverage.
- Started issue #112's 100% meaningful coverage hardening by adding OpenAPI loader error-path tests, raising `core.openapi_loader` to 100% module coverage without weakening loader behavior.
- Continued issue #112 by covering Hurl validator subprocess startup failures and raising `core.hurl_validator` to 100% module coverage.
- Covered root-level Architect output validation errors, removed an unreachable managed-block marker branch, and raised `brain.output_parser` plus `bridge.merge` to 100% module coverage.
- Covered traffic dependency graph path-normalization edge cases and raised `bridge.traffic_to_graph` to 100% module coverage.
- Covered report writer mismatch, out-of-root path display, no-failure bug guidance, and bug-report write paths, raising `core.report_writer` to 100% module coverage.
- Created focused follow-up coverage issues #119 through #122 and implemented #119's security-focused traffic redactor tests, raising `core.traffic_redactor` to 100% module coverage.
- Implemented #120's Architect prompt builder coverage slice, covering missing-source-context rendering and malformed context paths while raising `brain.prompt_builder` to 100% module coverage.
- Implemented #121's story traceability coverage slice, covering empty-story Markdown and findings-table rendering while raising `bridge.story_traceability` to 100% module coverage.
- Implemented #122's SQLModel traffic store coverage slice, covering retention/list validation and missing inserted-id handling while raising `core.traffic_store` to 100% module coverage.
- Created focused follow-up coverage issues #127 through #130 and implemented #127's Brain safety tests, raising `brain.safety` to 100% module coverage.
- Implemented #128's Hurl metadata model coverage slice, covering malformed metadata keys, duplicate/empty metadata, direct tags access, and path extraction edge cases while raising `models.hurl` to 100% module coverage.
- Implemented #129's Hurl discovery adapter coverage slice, covering direct file roots, duplicate roots, missing/non-Hurl roots, invalid UTF-8, symlink skips, deterministic ordering, and tag-filter normalization while raising `core.hurl_discovery` to 100% module coverage.
- Implemented #130's policy-to-Hurl compiler coverage slice, covering invalid rule/assertion rejection, public gate matching, unsupported fields, and future-condition fallback while raising `bridge.policy_to_hurl` to 100% module coverage.
- Created focused follow-up coverage issues #135 through #138 and implemented #135's gate injector coverage slice, covering source read failures, execution-root validation, no-response handling, no-op matching, missing sources, and response-header insertion while raising `core.gate_injector` to 100% module coverage.
- Implemented #136's Hurl runner coverage slice, covering option validation, binary discovery, subprocess `OSError` mapping, path rejection, worker-count validation, missing worker results, and variable validation while raising `core.hurl_runner` to 100% module coverage.
- Implemented #137's traffic compiler coverage slice, covering session validation, unknown/binary body handling, unsafe Hurl line values, response-less records, unstable golden assertions, WireMock safe stems, redacted headers, and textual/unknown body payloads while raising `bridge.traffic_sessions`, `bridge.traffic_to_hurl`, and `bridge.traffic_to_wiremock` to 100% module coverage.
- Implemented #138's config/env coverage slice, covering QAnstitution load failures, import cycles, writer validation/rollback/race branches, persona path safety, env file decoding/read errors, and duplicate variables while raising `core.config_loader`, `core.config_writer`, and `core.env_loader` to 100% module coverage.
- Implemented #143's OpenAPI compiler/audit coverage slice, covering duplicate generated paths, malformed OpenAPI shapes, parameter fallback rendering, schema examples/defaults, response selection, audit spoofing gaps, and fallback operation IDs while raising `bridge.openapi_to_hurl` and `bridge.openapi_audit` to 100% module coverage.
- Implemented #148's CI gate hardening so GitHub Actions runs `scripts/regression.sh --security`, runs `scripts/audit_quality.sh` as a separate quality-audit job, uploads quality reports, and documents CI-enforced versus local release-owner gates.
- Implemented #150's live-demo Hurl supply-chain hardening by pinning the Linux archive SHA-256 in GitHub Actions and documenting the reviewed checksum bump process.
- Implemented #149's durable artifact-write hardening with a shared `core.safe_write` helper, fsynced temp-file writes, symlink rejection, atomic replacement, no-partial-replacement tests, and adoption by freeze outputs, dependency-map PNGs, drift reports, JSON/JUnit/HTML run reports, and bug reports.
- Implemented #146's deterministic support-module coverage slice, raising `core.dependency_mapper`, `core.drift_report`, `models.traffic`, and `studio.status` to 100% focused coverage with meaningful edge/error tests.
- Implemented #145's Eye proxy/freeze coverage slice, raising `core.traffic_proxy` and `core.freeze` to 100% focused coverage without live mitmproxy sessions or network traffic.
- Implemented #144's Architect workflow coverage slice, raising `brain.architect_build`, `brain.architect_refactor`, and `brain.architect_writer` to 100% focused coverage across merge safety, selected-target enforcement, path validation, and atomic-write failure handling.
- Implemented #157's Brain provider/persona boundary coverage slice, raising `brain.persona_loader` and `brain.litellm_client` to 100% focused coverage without provider or network calls.
- Implemented #159's CLI adapter coverage slice, raising `entroping.cli.main` to 100% focused coverage across doctor/config/architect/watch/run/report helper and error branches.
- Implemented #112's coverage release gate by changing `scripts/audit_quality.sh` to default to `ENTROPING_COVERAGE_FAIL_UNDER=100` and documenting 100% meaningful coverage as the enforced audit default.
- Implemented #106's traceability report CLI so `entroping report traceability --output md` renders local story/test metadata and returns failing exit codes for missing story IDs or conflicting doc links.
- Implemented #109's public trust hardening with a local community-profile audit script, README OpenSSF Scorecard badge, and scheduled/manual Scorecard workflow that avoids PR gating.
- Implemented #110's structured response drift MVP with value-free response fingerprints for status code, selected stable headers, and JSON body shape paths.
- Implemented #108's launch demo asset kit with README links, real checkout smoke terminal frames, a text/SVG HTML report preview, a dependency-map example from redacted traffic, and a concrete growth-plan publish order.
- Fixed #166's launch-doc portability gap by replacing maintainer-local temp paths with an `ENTROPING_DEMO_TMP_BASE` override and adding a guardrail test.
- Implemented #168's configurable source archive path for `scripts/context_pack.sh --mode source`, replacing the hardcoded maintainer-local path with `ENTROPING_SOURCE_ROOT` plus a sibling-folder default.
- Fixed #170's agent workflow docs so Obsidian, retired graph tooling, and prompt examples use portable `<repo-root>` and `<source-archive>` placeholders instead of maintainer-local paths.
- Refreshed #172's README current-status wording so the public overview says active alpha implementation instead of initial scaffold.
- Ran issue #96's formal post-alpha security review and fixed 14 validated candidates across Brain prompt redaction, Hurl subprocess env isolation, symlinked path components, traffic redaction/body limits, OpenAPI generation/audit safety, policy gate compilation, Markdown escaping, Architect generated-file writes, and live demo workdir handling.
- Wrote the consolidated Codex Security scan artifacts under `/tmp/codex-security-scans/Entroping/eb08827323c6_20260530T160200Z`, including discovery, coverage, reconciliation, validation, attack-path, Markdown, and HTML reports.
- Refactored issue #90's `entroping run` orchestration into `core.run_workflow`, preserving reports, drift behavior, exit codes, and LLM-free execution while lowering CLI adapter complexity.
- Implemented issue #91's bridge-level story traceability compiler with missing-story and conflicting-doc-link findings, Markdown rendering, tests, and docs that avoid implying external API sync.
- Hardened local validation scripts to use the repo `src/` path explicitly so audit and regression gates do not depend on editable-install `.pth` state.
- Implemented issue #94's finish-issue workflow with merged-PR and CI verification, clean worktree safety checks, squash-merged branch cleanup, project Done updates, docs, and script tests.
- Implemented issue #93's repeatable local quality audit gate with coverage, Radon complexity/maintainability, Vulture dead-code discovery, ignored report artifacts, and script smoke tests.
- Refreshed issue #92's post-alpha context handoff so `.context/plan.md` and `PROJECT_PROGRESS.md` describe the implemented compiler/runtime surface and current validation queue instead of stale placeholder-era status.
- Fixed issue #95's remaining `architect build` placeholder path so invoking the command without `--new` or `--prompt` now returns actionable supported-mode guidance.
- Fixed issue #97's coverage-artifact hygiene gap by ignoring `.coverage`, `coverage.xml`, and `htmlcov/`, with a regression test proving Git ignores validation coverage output.
- Implemented issue #85's read-only Studio status shell with optional Textual dependency guidance, local latest-run/report/traffic-state inspection, and no-mutation coverage.
- Implemented issue #84's deterministic drift report MVP with `.entroping/drift-baseline.json`, `run --drift-check`, `--report drift`, missing-baseline artifacts, and result/rule-ID comparison.
- Implemented issue #83's bounded parallel Hurl execution so `entroping run --parallel` uses QAnstitution worker limits while preserving per-file safety behavior and deterministic report ordering.
- Implemented issue #82's distribution and install polish with a deterministic package artifact check, source/tag install guidance, and release documentation that keeps package publishing credentials out of the repo.
- Implemented issue #80's optional PNG dependency map export through local Graphviz `dot`, with subprocess-bounded rendering, atomic `reports/dependency-map.png` writes, missing-renderer errors, and secret-safe renderer failure handling.
- Implemented issue #58's license and package metadata blocker with Apache-2.0 core licensing, SPDX package metadata, alpha-safe classifiers, README license status, and ADR-0009 for the open-core boundary.
- Updated the progress dashboard and active implementation context so the remaining public-alpha action is release-gate evidence and tagging, not license selection.

## 2026-05-29

- Replaced the initial thin v4.1 notes with a comprehensive product specification.
- Expanded the technical design around hexagonal architecture, QAnstitution validation, Hurl execution, mitmproxy observation, LiteLLM routing, and reports.
- Added a detailed user guide for new APIs, legacy rescue, existing Hurl adoption, CI, smoke tests, and Studio.
- Added requirements analysis comparing the Gemini evolution, older specs, the slide deck, and the latest v4.1 direction.
- Added QAnstitution reference, command cheat sheet, user flows, use cases, diagrams, and MVP plan.
- Captured the final command namespace and marked older command ideas as deprecated, aliases, or future work.
- Re-ran a multi-pass audit over the old docs and Gemini transcript to recover creator intent around solo-first development, local-first model UX, source-grounded AI, traffic filtering/session stitching, state retention, external business systems, and command-surface conflicts.
- Added `CREATOR_INTENT_AUDIT.md` and `BRAIN_PROVIDER_STRATEGY.md`.
- Completed an additional hard-review pass against Hurl behavior and command contracts.
- Replaced invalid Hurl metadata examples with `# entroping:` comments and removed the invented Hurl validation command in favor of parser-backed validation through `hurlfmt --out json <file>` or an equivalent parser.
- Clarified that `--report` is repeatable for multiple run artifacts and that `report bug` is the only primary reporting subcommand.
- Tightened the MVP agent-routing choice to a small typed in-process router, leaving LangGraph-style orchestration as a later dependency only if complexity justifies it.
- Added PlantUML aliases in the deployment diagram to avoid renderer ambiguity.
- Added the initial Python package scaffold, Typer CLI boundary, Pydantic QAnstitution models, Hurl discovery adapter, tests, uv tooling, and GitHub Actions CI.
- Reworked `README.md` as a GitHub-facing project overview with product pitch, status, quick start, architecture diagrams, repo map, and security rules.
- Organized Markdown docs under `docs/product`, `docs/technical`, `docs/user`, `docs/evolution`, `docs/architecture`, and `docs/meta` while preserving root `README.md` and `00_INDEX.md`.
- Added a glossary, checkout API demo fixture, explicit bridge compiler boundaries, and initial typed condition DSL validation in response to external architecture review.
- Ran a repository-wide Codex Security scan. Current executable scaffold had no high or critical findings; the only reportable issue was a low-severity vulnerable optional proxy dependency tree.
- Raised the optional proxy dependency floor to `mitmproxy>=12.2.3`, refreshed vulnerable transitive packages, and verified the all-extras dependency audit is clean.
- Added project-local `AGENTS.md` so future Codex threads can rehydrate Entroping-specific architecture, runtime, AI, traffic, documentation, and verification rules quickly.
- Refreshed `.context/plan.md` from historical documentation synthesis into the active deterministic-core implementation plan.
- Added `docs/meta/CONTEXT_MANAGEMENT.md` to explain how Codex, Obsidian, `.context`, and optional retired graph tooling output fit together.
- Added `docs/meta/AUTONOMOUS_DEVELOPMENT.md` for the Codex-first development loop, Spec Kit pilot rules, and future OpenCode plus local Qwen/oMLX worker strategy.
- Added `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, `.github/pull_request_template.md`, and `scripts/feature_gate.sh` to make the feature workflow executable across TDD, regression, architecture, security, multi-agent review, documentation, and commit-readiness gates.
- Added GitHub issue forms, `docs/meta/ISSUE_TRACKING.md`, `docs/meta/TEST_STRATEGY.md`, `docs/meta/PROJECT_PROGRESS.md`, and `scripts/regression.sh` to make bug tracking, regression coverage, test-pyramid expectations, and progress tracking systematic.
- Created the `Alpha: deterministic core` GitHub milestone with six initial feature/docs issues and linked them from `docs/meta/PROJECT_PROGRESS.md`.
- Tightened Obsidian navigation by making `docs/meta/PROJECT_PROGRESS.md` the daily dashboard, reorganizing `00_INDEX.md` into reading tiers, and clarifying context tiers so agents do not treat every Markdown file as equally relevant.
- Created the GitHub Project board `Entroping Alpha`, linked it to the repo, added issues #1-#6, and marked issue #1 as in progress.
- Implemented the issue #1 Phase 1A slice: `entroping init --minimal` now creates a minimal `qanstitution.yaml` and runtime skeleton without overwriting existing policy, `entroping doctor` validates local config health without network calls, and `core.config_loader` loads root-bounded local QAnstitution imports with duplicate/final-gate validation.
- Implemented issue #2's Hurl discovery and metadata slice with pure `# entroping:` comment parsing, recursive `.hurl` discovery, generated-state ignores, tag-filter validation, and focused unit plus adapter tests.
- Added `scripts/start_issue.sh` and a tested prompt renderer for issue-scoped worktrees, dry-run previews, review/write session prompts, and best-effort GitHub issue/project status updates.
- Implemented issue #3's gate matching and temporary Hurl injection slice with shallow request metadata parsing, QAnstitution condition matching, gate-to-Hurl assertion compilation, deterministic execution-copy names, and source-immutability regression coverage.
- Implemented issue #4's deterministic Hurl subprocess runner with argument-array execution, timeout handling, bounded and redacted output, missing-binary handling, non-zero result aggregation, `entroping run` integration, temporary execution-copy cleanup, and focused subprocess/CLI tests.
- Implemented issue #5's report slice with redacted JSON run summaries, CI-consumable JUnit XML, latest-run state under `.entroping/`, `entroping report bug` Markdown generation, and report writer/CLI regression tests.
- Implemented issue #6's alpha quickstart with a tiny local checkout demo server, literal localhost Hurl fixture, README quickstart commands, updated fixture documentation, and demo-server tests.
- Implemented issue #11's first Architect build slice with a pure OpenAPI-to-Hurl compiler, local OpenAPI loader, deterministic `architect build --new` generation under `tests/generated/`, and docs/progress updates.
- Implemented issue #13's environment runner slice with local `envs/<name>.env` loading, process-env overrides for matching keys, Hurl variable passing, env-value output redaction, and fixture docs for generated tests.
- Hardened issue #13's Hurl variable passing in issue #15 by switching to short-lived `--variables-file` temp files so env values do not appear in subprocess argv.
- Implemented issue #17's HTML report slice with escaped dependency-free `reports/run-latest.html` output and repeatable `--report html` support.
- Closed the completed alpha, Architect, runner-usability, and reporting milestones; queued issue #19 as the next live CI proof slice.
- Implemented issue #19's live demo smoke script and GitHub Actions job with pinned Hurl, checksum verification, demo server startup, OpenAPI generation, env loading, real Hurl execution, and report artifact upload.
- Implemented issue #23's OpenAPI depth slice with deterministic path/query/header/cookie parameter rendering, schema example/default/const/enum request-body generation, parameter validation, review-driven Hurl template/non-finite/collision hardening, and a parameterized checkout demo endpoint.
- Implemented issue #25's Architect minimal slice with deterministic OpenAPI coverage audit, Markdown/JSON output, CLI pass/fail behavior, and review-driven hardening for executable Hurl coverage and Markdown validity.
- Implemented issue #29's non-secret config slice with `config list`, `config set`, schema-level unsafe model identifier rejection, effective-policy validation before writes, symlink-safe temporary YAML updates, and focused CLI/domain tests.
- Implemented issue #31's Brain foundation with validated Architect edit models, root-bounded persona loading, secret-checked prompt packaging, lazy LiteLLM adapter, and no provider/network calls in tests.
- Implemented issue #33's Architect output boundary with JSON-to-`ArchitectEditSet` parsing, Architect-owned Hurl staged writes, non-generated overwrite protection, and symlink-safe temporary writes.
- Implemented issue #35's Architect prompt build happy path with Builder persona loading, LiteLLM invocation, structured output parsing, staged Architect-owned Hurl writes, redacted CLI output, and `entroping run` regression isolation.
- Implemented issue #37's parser-backed prompt Hurl validation with a `hurlfmt` subprocess adapter, all-or-nothing pre-write validation, non-echoing validation errors, and Architect path control-character hardening.
- Implemented issue #39's config persona-template creation so `config set` safely creates missing local agent Markdown templates without overwriting existing files or accepting traversal, symlink, URL, non-Markdown, or control-character paths.
- Implemented issue #41's Architect-owned refactor path with safe target glob loading, Builder prompt context packaging, provider JSON parsing, selected-target enforcement, parser-backed Hurl validation, redacted CLI output, and staged writes.
- Implemented issue #43's executable architecture/provider boundary guard with AST-based regression tests for domain/bridge adapter imports, run-core Brain/LiteLLM imports, and direct provider SDK imports.
- Implemented issue #46's CI trigger dedupe so pull requests run once through `pull_request` and branch pushes do not start duplicate workflows unless the push is to `main`.
- Implemented issue #48's pure bridge managed-block Hurl merge primitive for replacing explicit Entroping-managed blocks while preserving manual content outside those blocks.
- Implemented issue #50's managed-block `architect refactor` integration so manual Hurl files can opt into block-level AI maintenance without whole-file overwrite.
- Implemented issue #52's prompt-backed `architect build --strategy merge` path for existing Architect-owned Hurl files and manual managed blocks.
- Implemented issue #54's deterministic repo hygiene slice with tracked local/generated-state rejection, feature-gate integration, optional local hook installation, Obsidian UI state removal from Git, and script tests.
- Added issue #56's alpha release-readiness gate and checklist so public release claims have deterministic local evidence.
- Refreshed the progress dashboard after the release-readiness merge, adding the license/package release blocker and the next Eye capture queue.
- Implemented issue #61's Eye foundation with typed traffic models, pre-persistence redaction, bounded SQLite traffic state, and tests proving secrets are not stored.
- Implemented issue #60's capture-only `watch` workflow with lazy mitmproxy loading, target-scope filtering, redacted flow persistence, CLI wiring, and proxy adapter tests that avoid live network dependence.
- Added issue #59's freeze/map implementation plan and ADR-0008 so filtering, sessioning, traffic-to-Hurl compilation, and graph export are split into implementation issues #66 through #69 before coding begins.
- Implemented issue #66's pure traffic session bridge with static-asset filtering, redacted-record enforcement, binary body text stripping, target/dependency/observed roles, ordering, and unit coverage.
- Implemented issue #67's redacted traffic-to-Hurl compiler with traffic metadata, request rendering, binary body omission, stable golden assertions, and bridge-only tests.
- Implemented issue #68's basic `freeze` CLI workflow with missing-state and unsafe-name errors, parser validation before writes, atomic generated Hurl writes, symlink protection, and redaction regression coverage.
- Implemented issue #69's dependency map export with a pure traffic-to-graph compiler, Mermaid/Markdown/DOT renderers, CLI map wiring, PNG missing-renderer messaging, and redaction/escaping coverage.
- Implemented issue #75's `freeze --mock` path with a pure traffic-to-WireMock compiler, safe mock service selection, staged mapping writes, symlink protection, and no-raw-secret coverage.
- Hardened the live demo CI Hurl install step with bounded retries after a transient GitHub release download 502 caused a flaky PR check.
- Implemented issue #197's reviewed drift baseline workflow with sanitized candidate baseline artifacts, no automatic active-baseline writes, path-safety and redaction regression tests, and user/technical docs for review, diff, and promotion.
- Implemented issue #203's report schema contracts with v1 schema versions for run, drift, and traceability report payloads; checked-in JSON Schema files; compatibility policy docs; and schema contract regression tests.
- Implemented issue #200's GitHub PR annotation integration with `report github-annotations`, JUnit/drift/optional-traceability annotation mapping, workflow-command escaping, redaction, downstream starter workflow updates, and regression tests.
- Ratcheted issue #521's quality audit default Radon cyclomatic-complexity ceiling
  from rank E to rank D after splitting the last rank-E CLI Architect test into
  focused assertion helpers.
- Added issue #530's local PR-body validation mode so agents can run
  `scripts/pr_body_check.py --body-file <path>` before opening or editing a PR.
- Added issue #532's `start_issue.sh` project-board recovery path so missing
  issues are best-effort added to the GitHub Project before being moved to
  `In Progress`.
- Added issue #534's `finish_issue.sh` project-board recovery path so missing
  completed issues are best-effort added to the GitHub Project before being
  moved to `Done`.
- Added issue #536's bounded Project item lookup retry after add for both
  `start_issue.sh` and `finish_issue.sh` to absorb GitHub Project eventual
  consistency.
- Fixed issue #546's alpha/stable status drift by separating v4.1 spec and
  command-surface versions from the current alpha implementation maturity in
  canonical product and technical docs, with a release-doc regression guard.
- Fixed issue #658's factory Python3 compatibility regression: context-pack
  metrics, graph probing, AI queue, OpenCode worker, and DeepSeek worker
  entrypoints now avoid evaluated Python 3.10+/3.11-only APIs when invoked by
  the default macOS `python3`, while product runtime support remains Python
  3.12/3.13.
- Added a temporary uv override to keep optional proxy-stack Tornado on a
  non-vulnerable `>=6.5.6` line, currently locked to 6.5.7, until mitmproxy
  relaxes its current 6.5.5 upper bound; optional extras smoke and security
  gates pass with the override.
- Hardened issue #661's provider-adjacent AI worker file selection: direct
  DeepSeek and OpenCode worker harnesses now reject sensitive credential-path
  variants such as `.env.backup`, `secret.env.prod`, and key/certificate backup
  names before provider review or subprocess execution can start.
- Closed issue #663's remaining OpenCode worker gap by sharing DeepSeek's
  secret-like content detection and rejecting selected files containing private
  key blocks, credential assignments, or bearer-token-like text before OpenCode
  subprocess execution.
- Closed issue #665's OpenCode transport follow-up: the worker now snapshots
  preflight-vetted selected file content under the ignored review artifact and
  attaches those snapshots to OpenCode instead of relying on live repo reads.
  The same selected-file boundary now rejects symlink inputs before resolving
  paths in both OpenCode and direct DeepSeek maintainer workers.
- Closed issue #677's OpenCode worker artifact-isolation follow-up: OpenCode
  subprocesses now run from a child scratch cwd under the ignored artifact
  directory, selected-file snapshots remain outside the live repo, and
  parent-owned stdout/stderr/metadata/proposal artifacts are written through
  temp-file replacement so worker-created symlink path entries cannot redirect
  captured output.
- Closed issue #679's issue-lifecycle Project lookup gap: `start_issue.sh` and
  `finish_issue.sh` now search a larger validated Project item window before
  deciding an issue is missing from the board, preserving the existing add/retry
  recovery path while avoiding duplicate-add attempts on larger project boards.
- Closed issue #724's context-tool cleanup: retired generated context tools
  are inactive for active agent workflow, graph-assisted context-pack/probe
  routing is removed, and prompt-library handoffs now direct workers back to
  `rg`, `scripts/context_pack.sh`, the decision registry, source files, tests,
  GitHub issues, and CI.
