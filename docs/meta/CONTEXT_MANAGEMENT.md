---
title: Context Management
type: guide
status: active
tags:
  - context
  - codex
  - obsidian
  - factory
---

# Context Management

Entroping uses layered, repo-native context so Codex and other workers can
rehydrate the project quickly without depending on one long chat thread.
Optional graph, wiki, comprehension, or compression tooling is not part of
normal rehydration; it must earn promotion through measured scorecard evidence
before it shapes work.

## Repo-Native Context Budget Baseline

Context is evidence, not memory. Start each issue with one named question: what
local evidence is needed to change, review, or merge this issue?

`rg`, `scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`, GitHub
issues, source files, focused tests, CI, and `scripts/factory_metrics.py
report` are the active context-cost baseline. Load that baseline first, then
add files only when they answer the issue question. Do not add generated
context because it is interesting, visual, popular, or already installed.

Load extra context only when it answers the named issue question and records an
evidence pointer: a file path, test, issue, PR, CI check, ADR, decision-registry
entry, or curated Markdown section. Generated graph, wiki, comprehension, or
compression output must be promoted through that evidence path before it can
shape implementation or review.

Use `scripts/context_pack.sh --record-factory-metrics` and
`scripts/factory_metrics.py report` when token or cost claims matter. No
token-saving claim is accepted without measured local evidence from the current
workflow lane. If the measurement is missing, say it is missing instead of
crediting a tool or model with guessed savings.
Use `scripts/factory_metrics.py readiness --issue <issue> --format json` when
an issue handoff, PR, or finish decision claims quality, security, context
preservation, and token/cost evidence are all present.

## Context Tiers

Do not read the entire vault for every task. Obsidian preserves context by making the graph navigable; Codex preserves context by reading the smallest source set that can govern the current change.

Use `scripts/docs_inventory.py --format json --strict` to audit the tracked
Markdown set when a review says there is too much documentation. The strict
inventory keeps the default agent Markdown context at or below its budget,
flags duplicate active titles, confirms generated/wiki context has not become
active workflow by accident, and reports non-destructive prune/archive
candidates for stale reference docs, duplicate titles, default-agent context
risk, and archive/source material.

### Always Read

1. `AGENTS.md` - implementation rules for Codex.
2. `docs/meta/PROJECT_PROGRESS.md` - current alpha status and issue queue.
3. `.context/plan.md` - active implementation milestone.
4. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` - per-feature execution checklist.
5. `docs/meta/DECISION_REGISTRY.yaml` - fast lookup index for durable decisions and their source links.

### Read When Implementing

- `docs/product/MVP_PLAN.md` - implementation sequence.
- `docs/technical/TDS.md` - architecture details.
- `docs/technical/COMMAND_CHEAT_SHEET.md` - locked command surface.
- `docs/meta/TEST_STRATEGY.md` - test pyramid and regression rules.
- The GitHub issue, ADR, or failing test for the slice being implemented.

### Read When Reviewing Or Handing Off

- `README.md` - public project overview and quickstart.
- `docs/meta/VAULT_INDEX.md` - Obsidian vault map.
- `.context/changelog.md` - recent work.
- `.context/lessons-learned.md` - durable pitfalls and decisions.
- `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` - review and merge checklist.
- `docs/meta/DECISION_REGISTRY.yaml` - accepted decisions, supersession state, and source pointers.
- `docs/meta/ISSUE_TRACKING.md` - GitHub issue tracking rules.

### Read For Product History Only

- `docs/evolution/*`
- `sources/*`
- external source exports referenced by `sources/SOURCE_MAP.md`
- `docs/technical/CODEX_PROMPT.md`

Use `docs/meta/DECISION_REGISTRY.yaml` before reading broad historical material.
It is an index, not a replacement for the linked source files.

## New Codex Thread Prompt

Use this when starting a fresh thread:

```text
Work in <repo-root>.
Read AGENTS.md, docs/meta/PROJECT_PROGRESS.md, .context/plan.md, docs/meta/FEATURE_DELIVERY_CHECKLIST.md, and docs/meta/DECISION_REGISTRY.yaml first.
Preserve the locked v4.1 command surface and implement only the next narrow milestone.
Use README.md and docs/meta/VAULT_INDEX.md as reference/navigation only when the issue needs public positioning or vault history.
Follow docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md, docs/meta/ISSUE_TRACKING.md, and docs/meta/TEST_STRATEGY.md for the Codex-first workflow, TDD expectations, regression gates, multi-agent guardrails, issue tracking, and context updates.
```

## Agent Context Packs

For any agent, generate a deterministic pack instead of relying on old chat
context:

```bash
scripts/context_pack.sh --mode implementation
scripts/context_pack.sh --mode review
scripts/context_pack.sh --mode source
scripts/context_pack.sh --mode growth
scripts/context_pack.sh --mode handoff
```

Use `implementation` for coding, `review` for critique, `source` for
Gemini/NotebookLM reconciliation, `growth` for launch and monetization work, and
`handoff` when a new Codex thread needs fast continuity.
`implementation` mode intentionally omits `README.md` and
`docs/meta/VAULT_INDEX.md`; use `growth`, `source`, or `handoff` mode when
public positioning, vault navigation, or product-history context is the named
issue question.

Use the manifest first when planning work for Codex, OpenCode, DeepSeek, Spark,
or another worker that should not load the full pack immediately:

```bash
scripts/context_pack.sh --mode implementation --manifest
```

The manifest uses schema `entroping.context-pack-manifest.v1` and records the
selected file inventory, per-file byte counts, selection reasons, total context
bytes, estimated tokens, the mode budget, and `recommended_next_action`
guidance. It does not include file content. Follow
`recommended_next_action.action` before loading the full pack: use targeted
file reads when the manifest is within budget, and reduce scope when the
manifest exceeds budget.
Queued low-risk Tier A worker jobs should use
`scripts/ai_jobs.py submit --autonomy-tier tier-a`, which records the manifest
command in the queued job and injects a worker instruction to request only the
needed files/snippets after reviewing the manifest.
Use `--strict-budget` when a workflow should fail instead of silently expanding
agent context:

```bash
scripts/context_pack.sh --mode implementation --strict-budget
scripts/context_pack.sh --mode implementation --manifest --strict-budget
```

Per-mode byte budgets are intentionally explicit in `scripts/context_pack.sh`.
Use `ENTROPING_CONTEXT_PACK_BUDGET_<MODE>` only for local experiments and tests;
do not raise a budget without a PR that explains the context-cost reason.

`source` mode defaults to a sibling `../entroping-specs` archive. Override it
when the source archive lives elsewhere:

```bash
ENTROPING_SOURCE_ROOT=/path/to/entroping-specs scripts/context_pack.sh --mode source
```

To measure context cost during a factory run, opt in explicitly:

```bash
scripts/context_pack.sh --mode implementation --record-factory-metrics
scripts/context_pack.sh --mode review --record-factory-metrics --factory-role code_review_agent
scripts/ai_jobs.py run-next --record-factory-metrics
```

Use `--factory-metrics-ledger` only for a ledger under
`.entroping/factory-metrics/`, usually when a test or experiment needs a
separate local file. Context-pack recording stores byte estimates, token
estimates, file counts, role, mode, outcome, and value-free event metadata
such as event id, timestamp, event type, agent, tool, and optional
provider/model labels; it does not persist the generated pack body.

## Context Engineering Layers

Use context tools by layer, not by authority. GitHub Issues, PRs, CI, source
files, tests, ADRs, the decision registry, and QAnstitution/Hurl evidence
remain product truth. Obsidian, the LLM wiki pattern, and curated source
exports preserve memory only when their useful output is Git-backed Markdown,
ADR links, issue links, or decision-registry entries.

Retired generated context tooling is not part of active agent workflow. Do not
route normal Codex, OpenCode, DeepSeek, or Spark sessions through external
context tools unless a future issue re-promotes a replacement through measured
scorecard evidence. Use `rg`, `scripts/context_pack.sh`,
`docs/meta/DECISION_REGISTRY.yaml`, GitHub issues, source files, tests, and CI
first. Understand Anything remains optional for human comprehension and
onboarding; it does not approve patches, change requirements, or replace source
reading. Any compression or graph layer must not hide exact diffs, failing test
output, security findings, audit evidence, or secrets-sensitive material.

## Context Factory Rollout Order

Adopt context tools in layers so each layer has a clear owner, promotion path,
and failure mode before another tool starts compressing or reshaping the same
evidence.

1. Phase 1 - Obsidian vault discipline. Keep curated Markdown, source links,
   ADR pointers, and lessons accurate before adding generated or model-authored
   summaries. Obsidian preserves human memory; it does not track work.
2. Phase 2 - curated Markdown and LLM-wiki style source maps. The useful part
   of the LLM wiki idea is disciplined, source-linked Markdown that agents can
   verify through Git. Generated wiki or graph output stays local unless a
   finding is promoted into curated docs, an ADR, or a GitHub issue.
3. Phase 3 - Understand Anything for human comprehension and onboarding. Use it
   to learn the project and explain concepts, not to approve patches, change
   requirements, or replace source reading.
4. Phase 4 - bounded cheap, Chinese, and local model workers behind
   Codex-owned validation. Use affordable models for review, triage, summaries,
   and patch proposals, but keep Codex responsible for applying changes,
   running gates, opening PRs, waiting for CI, and merging.

Do not advance a layer until the previous layer has a documented owner, ignored
generated-output path, and reviewable promotion path. No rollout layer may
require ordinary contributors to install graph, wiki, compression, or
model-worker tooling before they can build, test, review, or contribute to
Entroping.

## Generated Context Tool Output Paths

Use explicit local output directories for generated context tooling so useful
findings can be reviewed without turning tool caches into project truth.

| Tool layer | Local output path |
| --- | --- |
| LLM wiki | `llm-wiki-out/` |
| Understand Anything | `understand-anything-out/` |
| Factory metrics ledger | `.entroping/factory-metrics/` |

Generated context outputs must remain ignored/local unless intentionally
promoted into curated Markdown, an ADR, a GitHub issue, or `.context/` through
normal review. Do not delete, archive, or rewrite context-preservation material
just because generated output is noisy; compress with pointers and preserve the
source history.

Use `scripts/factory_metrics.py` to append, validate, summarize, or report
local software-factory metrics with schema `entroping.factory-metrics.v1`.
These events can record issue, PR, worktree, role, agent/tool, provider/model,
context-byte/token estimates, file counts, tests, gates, CI/check outcomes,
duration, cost, and accepted/rejected status. The ledger is ignored local
operational evidence for budget and workflow tuning; it is not release proof,
does not approve patches, and must not store raw prompts, provider transcripts,
secrets, raw traffic, or product runtime evidence.
The optional note field is limited to short value-free status summaries and
rejects obvious raw prompt, transcript, stdout/stderr, raw-traffic, request-body,
or response-body material.

Use the per-issue report when measuring whether OpenCode, DeepSeek, Spark,
local models, Codex session patterns, or future replacement context tools are
actually improving context cost and review yield:

```bash
scripts/factory_metrics.py report --format json
scripts/factory_metrics.py report --format md --output .entroping/factory-metrics/factory-report.md
scripts/factory_metrics.py readiness --issue <issue> --format json
scripts/factory_metrics.py readiness --issue <issue> --format md --output .entroping/factory-metrics/issue-<issue>-readiness.md
```

The report uses schema `entroping.factory-metrics-report.v1` and groups events
by issue, including an `unassigned` bucket for exploratory runs. It summarizes
roles, agents, outcomes, decisions, provider/model usage, context bytes,
estimated tokens, duration, cost, file counts, tests, and gates without
rendering notes, prompts, transcripts, stdout/stderr, raw traffic, or secrets.
Its additive `model_comparison` view groups by issue, role, provider lane, and
model id, and records known and unknown metric counts so missing token, cost, or
duration evidence is visible instead of inferred.
The readiness scorecard uses schema `entroping.factory-readiness.v1` and checks
whether an issue ledger has all four handoff gates: quality, security, context
preservation, and token/cost efficiency. It returns nonzero when evidence is
missing and emits only value-free event metadata, matched markers, and missing
reasons.
Keep the report local unless a finding is promoted into a GitHub issue, PR,
ADR, or canonical doc. This is the measurement layer for future extraction into
a reusable software-factory template, not a replacement for Entroping's source
of truth.

Use the context-tool scorecard when deciding whether the curated Markdown
vault/Obsidian view, Understand Anything, or any future context tool deserves
active workflow status:

```bash
scripts/factory_metrics.py context-scorecard validate --input .entroping/factory-metrics/context-tools/issue-710-scorecard.json
scripts/factory_metrics.py context-scorecard report --input .entroping/factory-metrics/context-tools/issue-710-scorecard.json --format json
scripts/factory_metrics.py context-scorecard report --input .entroping/factory-metrics/context-tools/issue-710-scorecard.json --format md --output .entroping/factory-metrics/context-tool-scorecard.md
```

The scorecard input uses schema `entroping.context-tool-scorecard.v1`; reports
use schema `entroping.context-tool-scorecard-report.v1`. Keep both local unless
the finding is promoted into a GitHub issue, PR, ADR, or canonical doc. The
scorecard records only value-free measurement summaries and evidence pointers;
it must not store raw prompts, provider transcripts, secrets, raw traffic, or
product runtime evidence.

Each tool evaluation may also record setup evidence with `setup.status`,
`setup.duration_seconds`, `setup.command`, and `setup.failure_reason`. Use that
for tools that install but are not callable in the current agent session, tools
that need a CLI restart, tools with stale upstream lockfiles, or tools that have
no real local performance logs. Setup evidence follows the same redaction and
no-transcript rules as trial evidence.

Every measured trial compares the tool-assisted path against the repo-native
baseline and records these fields:

- `grounded_file_hit_rate`
- `nonexistent_reference_count`
- `forbidden_scope_incidents`
- `retrieval_precision`
- `retrieval_recall`
- `stale_claim_count`
- `context_recovery_time_seconds`
- `review_correction_count`
- `human_steering_count`
- `accepted_output_ratio`
- `context_bytes`
- `estimated_tokens`

Allowed scorecard evidence is source-linked and reviewable: repo files, tests,
GitHub issues or PRs, CI checks, ADRs, the decision registry, curated Markdown,
generated wiki/Understand Anything output, and factory metrics. Historical
retired-tool trial output can be cited as discard evidence, but it is not an
active workflow dependency. Obsidian workspace/cache/plugin state is not
scorecard evidence, and neither are provider transcripts, raw prompts, raw
traffic, or product runtime artifacts.

Keep/downgrade/discard decisions follow the measured scorecard:

- active only when measured evidence improves at least two metrics against
  the baseline without hiding necessary evidence.
- `optional_manual` when a tool helps a narrow source-linked case.
- `probation` when the tool is plausible but has insufficient local evidence.
- `discard` when it adds setup cost, stale context, noisy retrieval, human
  babysitting, or hallucination risk without measurable improvement.

Issue #712's full trial measured seven context/tool layers across initial
orientation, symbol-known impact, docs contradiction, large-context compression,
and worker-handoff packets. Issue #724 converts that evidence into cleanup:

- Keep curated Git-backed Markdown plus the Obsidian view as active source-truth
  navigation. Obsidian remains a viewer; Git-backed Markdown, ADRs, decision
  registry entries, issues, tests, and CI are the evidence.
- Remove the graph-assisted probe script and graph-assisted context-pack option
  from active workflow. They added an extra routing surface without beating the
  repo-native baseline.
- Remove retired generated context tooling from active workflow. The trial
  showed that broad/context queries missed relevant files or returned noisy
  neighborhoods, source snippets underreported related tests, and no real
  Entroping/Codex proxy evidence proved token savings. Agents should use `rg`,
  source reads, tests, and measured factory metrics instead.
- Keep Understand Anything on `probation`. A fake-home install, non-frozen
  package install, core build, and external core tests worked in an ignored
  clone, but the skills require a CLI restart and were not callable in the
  current Codex session. Do not require it in the active workflow until a fresh
  session generates and validates an Entroping graph.
- Treat the LLM wiki pattern as `optional_manual`. In Entroping, the practical
  implementation remains curated Markdown plus the decision registry unless a
  real source-linked Markdown workflow proves better measured retrieval.

Maintainer workflow scripts can append those events only when requested with
`--record-factory-metrics`. `scripts/context_pack.sh` records context-pack
size and file counts, while `scripts/opencode_worker.py` and
`scripts/deepseek_worker.py` record worker status, selected-file byte counts,
duration, provider/model metadata where known, and sanitized DeepSeek usage
totals when available. Metrics failures are warnings for these workflow
scripts; they must not hide the original context-pack or worker outcome.
Queued workers use the same boundary: `scripts/ai_jobs.py run-next
--record-factory-metrics` passes recording options to the selected worker
harness without writing ledger events itself or changing queue semantics when
the flag is absent.

For normal onboarding, ordinary contributors must not be required to install
external graph, compression, Obsidian plugin, LLM wiki, or comprehension tools
before they can build, test, review, or contribute to Entroping.

## Obsidian Role

Obsidian is the human navigation layer. It shows product evolution, ADRs, source links, and relationships between docs.

Do not depend on Obsidian workspace state for project truth. The durable notes are Markdown files in Git.

Archive means lower default-reading priority, not deletion. Raw source exports,
ADRs, issues, and historical notes stay available; registry summaries compress
the path to them so agents do not have to read the entire vault.

## Understand Anything Role

Understand Anything is a probationary onboarding and interactive-graph tool.
It is not an active dependency for Codex/OpenCode sessions until the relevant
agent host has loaded its skills and an Entroping graph exists under ignored
`.understand-anything/` output.

Issue #712 verified the installer in a fake home and built/tested the external
core package in an ignored clone. The frozen package install failed because the
upstream lockfile was stale, while a non-frozen install, core build, and core
tests passed. Because the skills require a CLI restart and no live `/understand`
command was available in the current Codex session, this tool remains
probationary for Entroping.

For normal onboarding, ordinary contributors must not be required to install
external graph, compression, Obsidian plugin, MCP index, or generated graph
stacks before they can build, test, review, or contribute to Entroping.

## Cross-Project Context

Project-specific rules belong in each repo's `AGENTS.md`. Global preferences
belong in your user-level Codex config, such as `~/.codex/AGENTS.md`.

Do not add a committed project `.codex/` directory unless the repo later needs shareable Codex-specific assets that cannot be represented in `AGENTS.md`, tracked scripts, issue prompts, or docs. For now, `.codex/`, installed skills, plugins, and machine hooks are user-local acceleration layers.

For another project, reuse the same pattern:

```text
AGENTS.md
.context/plan.md
.context/changelog.md
.context/lessons-learned.md
README.md
```

This gives Codex fast local context without requiring old conversation history.

## Agent Tooling

Current local agent tooling status:

- Codex CLI: available.
- OpenCode: available.
- Direct DeepSeek worker: available through `scripts/deepseek_worker.py` and
  queued jobs with `scripts/ai_jobs.py submit --engine deepseek-api`.
- Portable role registry: available through
  `docs/meta/AGENT_ROLE_REGISTRY.yaml`.
- Factory metrics ledger: available through `scripts/factory_metrics.py`, with
  ignored events under `.entroping/factory-metrics/`.
- Retired generated context tooling: removed from active workflow; use `rg`,
  source reads, tests, and measured factory metrics instead.
- Understand Anything: installable/testable in an ignored clone, but not active
  in this Codex session without a restart; generated graph output remains
  outside active workflow.
- Spec Kit `specify`: available.
- oMLX: not installed in this shell yet.

Treat OpenCode and future local Qwen/oMLX outputs as supporting review artifacts until their results pass Codex validation and deterministic checks.
