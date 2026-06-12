---
title: Context Management
type: guide
status: active
tags:
  - context
  - codex
  - obsidian
  - graphify
---

# Context Management

Entroping uses layered context so Codex, Obsidian, and future graph tooling can rehydrate the project quickly without depending on one long chat thread.

## Context Tiers

Do not read the entire vault for every task. Obsidian preserves context by making the graph navigable; Codex preserves context by reading the smallest source set that can govern the current change.

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
Read AGENTS.md, README.md, docs/meta/VAULT_INDEX.md, .context/plan.md, docs/product/MVP_PLAN.md, docs/technical/TDS.md, and docs/meta/PROJECT_PROGRESS.md first.
Preserve the locked v4.1 command surface and implement only the next narrow milestone.
Follow docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md, docs/meta/FEATURE_DELIVERY_CHECKLIST.md, docs/meta/ISSUE_TRACKING.md, and docs/meta/TEST_STRATEGY.md for the Codex-first workflow, TDD expectations, regression gates, multi-agent guardrails, issue tracking, and context updates.
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

When local Graphify or CodeGraph output already exists, agents may opt into the
optional graph-assisted agent context section:

```bash
scripts/context_pack.sh --mode implementation --with-local-graphs --graph-query "<issue title or symbol>"
```

This calls `scripts/agent_context_probe.py`, which reads local generated output
only. It must skip cleanly when Graphify or CodeGraph output is absent, and
Graphify/CodeGraph evidence is not authority. The section can suggest source
files or tests to inspect, but it must not replace source reading, focused
tests, or CI.

`source` mode defaults to a sibling `../entroping-specs` archive. Override it
when the source archive lives elsewhere:

```bash
ENTROPING_SOURCE_ROOT=/path/to/entroping-specs scripts/context_pack.sh --mode source
```

To measure context cost during a factory run, opt in explicitly:

```bash
scripts/context_pack.sh --mode implementation --record-factory-metrics
scripts/context_pack.sh --mode review --record-factory-metrics --factory-role code_review_agent
```

Use `--factory-metrics-ledger` only for a ledger under
`.entroping/factory-metrics/`, usually when a test or experiment needs a
separate local file. Context-pack recording stores byte estimates, token
estimates, file counts, role, mode, and outcome only; it does not persist the
generated pack body.

## Context Engineering Layers

Use context tools by layer, not by authority. GitHub Issues, PRs, CI, source
files, tests, ADRs, the decision registry, and QAnstitution/Hurl evidence
remain product truth. Obsidian, the LLM wiki, and curated source exports
preserve memory. Graphify, Understand Anything, CodeGraph, and Obsidian graph
views help comprehension, onboarding, and `src/` plus `tests/` impact analysis.
Headroom and similar compression tools are optional cost controls after
retrieval behavior is stable; they must not hide exact diffs, failing test
output, security findings, audit evidence, or secrets-sensitive material.

## Context Factory Rollout Order

Adopt context tools in layers so each layer has a clear owner, promotion path,
and failure mode before another tool starts compressing or reshaping the same
evidence.

1. Phase 1 - Obsidian vault discipline. Keep curated Markdown, source links,
   ADR pointers, and lessons accurate before adding generated graphs or model
   summaries. Obsidian preserves human memory; it does not track work.
2. Phase 2 - LLM wiki plus Graphify over the repo and vault. Use generated
   maps to discover relationships and navigation gaps after the Markdown
   source set is stable. Generated wiki or graph output stays local unless a
   finding is promoted into curated docs, an ADR, or a GitHub issue.
3. Phase 3 - Understand Anything for human comprehension and onboarding. Use it
   to learn the project and explain concepts, not to approve patches, change
   requirements, or replace source reading.
4. Phase 4 - CodeGraph for `src/` and `tests/` impact analysis. Keep code graph
   scope tight so navigation helps implementation and review without turning
   historical notes, generated reports, or local caches into product truth.
5. Phase 5 - Headroom around Codex and OpenCode after retrieval behavior is
   stable. Use compression only for noisy, re-fetchable context once exact
   source paths, diffs, failing tests, and security evidence are already known.
6. Phase 6 - bounded cheap, Chinese, and local model workers behind
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
| Graphify | `graphify-out/` |
| LLM wiki | `llm-wiki-out/` |
| Understand Anything | `understand-anything-out/` |
| CodeGraph | `codegraph-out/` |
| Headroom | `headroom-out/` |
| Agent context probe | `agent-context-out/` |
| Factory metrics ledger | `.entroping/factory-metrics/` |

Generated context outputs must remain ignored/local unless intentionally
promoted into curated Markdown, an ADR, a GitHub issue, or `.context/` through
normal review. Do not delete, archive, or rewrite context-preservation material
just because generated output is noisy; compress with pointers and preserve the
source history.

Use `scripts/factory_metrics.py` to append, validate, or summarize local
software-factory metrics with schema `entroping.factory-metrics.v1`. These
events can record issue, PR, worktree, role, agent/tool, provider/model,
context-byte/token estimates, file counts, tests, gates, CI/check outcomes,
duration, cost, and accepted/rejected status. The ledger is ignored local
operational evidence for budget and workflow tuning; it is not release proof,
does not approve patches, and must not store raw prompts, provider transcripts,
secrets, raw traffic, or product runtime evidence.

Maintainer workflow scripts can append those events only when requested with
`--record-factory-metrics`. `scripts/context_pack.sh` records context-pack
size and file counts, while `scripts/opencode_worker.py` and
`scripts/deepseek_worker.py` record worker status, selected-file byte counts,
duration, provider/model metadata where known, and sanitized DeepSeek usage
totals when available. Metrics failures are warnings for these workflow
scripts; they must not hide the original context-pack or worker outcome.

For normal onboarding, ordinary contributors must not be required to install
Graphify, CodeGraph, Headroom, Obsidian plugins, LLM wiki tooling, or
Understand Anything before they can build, test, review, or contribute to
Entroping.

## Agent Context Probe

`scripts/agent_context_probe.py` is the bridge from generated graph output to
agent prompts. It reads existing `graphify-out/` and `codegraph-out/` artifacts,
matches them against issue terms or symbols, redacts obvious secret-like values,
and emits a small text or JSON manifest with candidate file/test references.

Use it directly when a worker prompt needs a compact manifest:

```bash
scripts/agent_context_probe.py --query "<issue title or symbol>" --format text
scripts/agent_context_probe.py --query "<issue title or symbol>" --format json --output agent-context-out/probe.json
```

The probe never runs Graphify, CodeGraph, Hurl, provider calls, or product
commands. It only summarizes local generated context that already exists.
Generated probe output stays under `agent-context-out/`, remains ignored by Git,
and is blocked by repo hygiene if accidentally tracked.

Treat the manifest as a routing hint for agents: inspect the suggested files,
run the focused tests, and escalate when the evidence points at Tier B/Tier C
scope or sensitive boundaries. Do not use graph evidence to approve patches,
lower autonomy tier, or skip deterministic gates.

## Obsidian Role

Obsidian is the human navigation layer. It shows product evolution, ADRs, source links, and relationships between docs.

Do not depend on Obsidian workspace state for project truth. The durable notes are Markdown files in Git.

Archive means lower default-reading priority, not deletion. Raw source exports,
ADRs, issues, and historical notes stay available; registry summaries compress
the path to them so agents do not have to read the entire vault.

## Graphify Role

Graphify is optional generated context. It can help find unexpected connections,
central nodes, symbol relationships, and graph summaries, but generated output
should stay out of Git unless a result is promoted into curated Markdown.

Recommended workflow:

```bash
uv tool install graphifyy
graphify update <repo-root> --no-cluster
```

Output belongs under `graphify-out/`, which is ignored by Git.

The 2026-06-12 issue #602 pilot ran `graphify update . --no-cluster` against
the active repo for issue #601's report artifact audit-chain task. Graphify did
not beat `rg`, `scripts/context_pack.sh`, and
`docs/meta/DECISION_REGISTRY.yaml` for initial task discovery: the broad natural
language query found useful schema nodes but missed the core Python
implementation until the query already knew exact names.

Graphify was useful for symbol-known impact analysis. Once seeded with
`write_report_artifact_manifest`, `graphify explain` and `graphify affected`
showed the CLI caller, core helper graph, and direct tests more compactly than a
plain text search. Keep it as a maintainer retrieval aid after ordinary repo
discovery, especially before focused review or refactor planning. Do not use it
to decide product truth, replace the decision registry, or generate mandatory
implementation context.

For normal onboarding, ordinary contributors must not be required to install
Graphify, CodeGraph-style tools, Obsidian plugins, MCP indexes, or any generated
graph stack before they can build, test, review, or contribute to Entroping.

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
- Spec Kit `specify`: available.
- oMLX: not installed in this shell yet.

Treat OpenCode and future local Qwen/oMLX outputs as supporting review artifacts until their results pass Codex validation and deterministic checks.
