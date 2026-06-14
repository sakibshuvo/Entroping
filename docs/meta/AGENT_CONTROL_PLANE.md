---
title: Agent Control Plane
type: runbook
status: active
tags:
  - agents
  - codex
  - opencode
  - claude-code
  - gemini
  - notebooklm
  - qwen
---

# Agent Control Plane

This is the operating model for using multiple agents without turning the repo into prompt soup.

## Prime Directive

Codex owns factory design, Tier B/Tier C integration, and merge readiness for
sensitive lanes. OpenCode/DeepSeek may operate the Tier A autonomous lane
defined below only after the issue, worktree, PR, local gates, and CI prove
scope.

No helper agent is a source of truth. The hierarchy is:

1. Local repo files and tests.
2. GitHub issues, PRs, and CI.
3. ADRs and canonical product/technical docs.
4. Source exports under `<source-archive>`, usually `../entroping-specs` or `ENTROPING_SOURCE_ROOT`.
5. Agent summaries, chat context, NotebookLM answers, Gemini answers, Claude Code output, OpenCode output, and local Qwen output.

## Software Factory Operating Model

Codex owns factory design, Tier B/Tier C integration, and merge readiness for sensitive lanes.
Treat the parent Codex thread as the control room for security-sensitive,
runtime, architecture, release, and ambiguous work: it chooses the issue,
verifies local files, runs tests, updates required docs, opens the PR, waits
for CI, and merges only when the evidence is clean.

OpenCode and free-model workers receive bounded issue prompts. They can propose
tests, patches, review notes, alternate designs, documentation drafts, and
Tier A autonomous lane PRs. Their output is still untrusted until it is proven
against the repo, issue, deterministic gates, and GitHub CI.

Use `scripts/ai_jobs.py` when batching affordable worker tasks. It queues
bounded jobs under `.entroping/ai-jobs/`, maps cost profiles such as
`flash-free` to `opencode/deepseek-v4-flash-free` through the default
OpenCode engine and `pro` to `deepseek/deepseek-v4-pro`. It can also route paid
jobs through direct DeepSeek with `--engine deepseek-api` and `pro` mapped to
`deepseek-v4-pro`. The queue runs the oldest job through the selected bounded
worker and lists completed artifact directories for Codex review. The queue is
an artifact conveyor, not an authority layer: it never applies patches,
commits, pushes, merges, or changes release status.

## Model Provider Lane Taxonomy

Use durable lane names when planning, running, or recording multi-model factory
work:

| Lane | Default use |
| --- | --- |
| `deepseek-api/direct` | Paid direct DeepSeek API through `scripts/deepseek_worker.py` or `scripts/ai_jobs.py --engine deepseek-api`. Direct DeepSeek API remains the default cheap queued worker lane for 24/7 review and patch proposals. |
| `opencode/native-deepseek` | DeepSeek configured directly inside the OpenCode host. Use only when explicitly requested or when the direct API lane is unsuitable. |
| `opencode-go/kimi-k2.7-code` | OpenCode Go subscription lane for Kimi K2.7 Code coding experiments, long-context review, and model comparison. |
| `opencode-go/qwen3.7-max` | OpenCode Go subscription lane for Qwen3.7 Max coding experiments and model comparison. |
| `opencode-go/other` | OpenCode Go subscription lane for MiniMax, GLM, MiMo, or other curated Go models when Kimi/Qwen are not the intended worker. |
| `local/offline` | Local model lane for private summarization, context compression, offline triage, and emergency fallback. |

OpenCode Go is the Kimi/Qwen/model-variety lane, not the default DeepSeek lane.
Every worker artifact, metrics event, review note, or handoff should name the
provider host, billing path, and concrete model id when known. Do not write only
`OpenCode`, `DeepSeek`, or `Kimi` when the useful distinction is
`opencode-go/kimi-k2.7-code`, `opencode-go/qwen3.7-max`,
`opencode/native-deepseek`, or `deepseek-api/direct`.

Use `scripts/opencode_worker.py` instead of raw `opencode run` for repeatable
OpenCode/DeepSeek work. The worker has `review` mode for bounded findings and
`patch` mode for a patch proposal artifact under `.entroping/ai-reviews/`.
Patch mode never applies changes; Codex validates and applies any useful diff
inside the issue worktree, then runs the normal gates.

OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane. It may use
OpenCode-configured agents, plugins, MCP servers, hooks, shell/tools, and
GitHub integrations only when those capabilities are present in the active
OpenCode host and permissioned there. Codex-native plugins, skills, Codex Security, Browser, Computer Use, thread tools, and Codex-specific MCP state are
not automatically available unless the OpenCode host exposes equivalent
capabilities. The `scripts/opencode_worker.py` prompt includes an OpenCode Host Capability Context that preserves this boundary, forbids
`--dangerously-skip-permissions`, keeps selected-file snapshots as the worker's
truth surface, and keeps `entroping run` deterministic, Hurl-backed,
QAnstitution-governed, and provider-free.

Use `scripts/deepseek_worker.py` when OpenCode is the wrong dependency for a
paid DeepSeek Flash or Pro task. It calls DeepSeek's OpenAI-compatible chat
completion endpoint with an env-provided `DEEPSEEK_API_KEY`, includes selected
repo files as bounded UTF-8 prompt context, writes prompt, request,
stdout/stderr, response, proposal diff, and value-free metadata under
`.entroping/ai-reviews/`, and never applies patches. Before any artifact is
written or provider request is made, the worker rejects selected files that are
too large, binary, non-UTF-8, credential-path-like, or contain secret-like
content. Before generated output artifacts are written, the worker withholds
secret-like stdout/stderr and serialized response payloads, skips raw
response/proposal artifacts for that run, and records only value-free failure
evidence. This is maintainer-only local development tooling
for cheap worker output; it
does not replace Entroping's LiteLLM product boundary, and it must not be called
by `entroping run`.
Direct DeepSeek workers default to
`--thinking disabled` to avoid empty hidden-reasoning output and token burn for
short reviews; opt into `--thinking enabled --reasoning-effort high|max` only
for deliberate deep-review jobs. The generated prompt includes a Factory
Capability Context section defined in `scripts/deepseek_worker.py` that tells
direct DeepSeek API workers they have no live MCP, shell, filesystem, GitHub,
Codex skill, Spark, Graphify, CodeGraph, or Headroom execution unless that
evidence is explicitly supplied in the prompt. This context should reduce
hallucinated tool use while preserving Codex or human integration authority.

local Qwen/oMLX handles private summarization, triage, and low-risk review. Use
it for source-archive summarization, duplicate-finding, wording variants, and
offline review prompts before sending anything sensitive to cloud models.

Generated codegraph, Graphify, and Obsidian graph output is evidence, not authority.
They can help humans and agents navigate relationships, but local tests, source
files, ADRs, GitHub Issues, and CI decide truth.
Use the generated context-tool output paths documented in
`docs/meta/CONTEXT_MANAGEMENT.md`; generated graph, wiki, comprehension,
codegraph, and compression artifacts remain local unless promoted through
normal review.

The portable software-factory protocol is split between
`docs/meta/AGENT_ROLE_REGISTRY.yaml` and `scripts/factory_metrics.py`. The
registry gives Product Manager, Architect, Dev Agent, QA Agent, Code Review
Agent, Security Agent, Monitoring Agent, and Integrator roles consistent
missions, authority limits, context modes, and metrics tags across Codex,
Claude Code, OpenCode, DeepSeek, Gemini, Spark, and local models. The metrics
script records local JSONL events with schema `entroping.factory-metrics.v1`
under `.entroping/factory-metrics/`; it is maintainer/development workflow
evidence, not product runtime evidence, and it must not store raw prompts,
provider transcripts, secrets, raw traffic, or product runtime evidence.
It also exports a per-issue report with schema
`entroping.factory-metrics-report.v1` so maintainers can compare context size,
estimated tokens, duration, cost, roles, provider/model usage, outcomes, and
accepted/rejected yield before future extraction into a reusable software
factory template. The report also includes an additive `model_comparison` view
grouped by issue, role, provider lane, and model id so OpenCode native
DeepSeek, direct DeepSeek API, OpenCode Go Kimi/Qwen, local models, Spark, and
Codex runs can be compared without collapsing missing cost or token evidence
into guessed values.
The same script owns the context-tool scorecard protocol with schema
`entroping.context-tool-scorecard.v1` and report schema
`entroping.context-tool-scorecard-report.v1`; use
`scripts/factory_metrics.py context-scorecard validate` and
`scripts/factory_metrics.py context-scorecard report --format json` before
promoting Graphify, Obsidian/curated Markdown, Understand Anything, CodeGraph,
or Headroom into the active agent workflow.
Recording from scripts is opt-in: use
`scripts/context_pack.sh --mode implementation --record-factory-metrics` to
measure context packs, use `scripts/ai_jobs.py run-next
--record-factory-metrics` for queued worker runs, and add
`--record-factory-metrics` plus, when needed, `--factory-metrics-ledger` to
direct `scripts/opencode_worker.py` or `scripts/deepseek_worker.py` worker
runs. These hooks record counts, status, duration, provider/model metadata,
and sanitized usage totals only; they are not release proof, patch approval, or
a substitute for tests and CI.
Use `scripts/factory_metrics.py report --format json` for machine-readable
analysis and `scripts/factory_metrics.py report --format md --output
.entroping/factory-metrics/factory-report.md` for a local human review report.
The factory framework owns workflow, context, metrics, and guardrails; the
project owns product truth.

One write agent per issue-scoped worktree. Parallelism comes from independent
issues, not from multiple agents editing the same files.

## Autonomous OpenCode Shipping Lanes

Autonomous shipping is risk-tiered. It exists to keep the software factory
moving when Codex capacity is exhausted, not to relax source-of-truth,
security, architecture, or release gates.

| Tier | Merge authority | Allowed scope |
| --- | --- | --- |
| Tier A autonomous lane | OpenCode/DeepSeek may implement, push, open a PR, wait for GitHub CI, merge, and run `scripts/finish_issue.sh` without Codex when every condition below is met. | low-risk docs, tests, guard tests, prompt-library maintenance, and non-runtime scripts that do not change product behavior, provider behavior, release behavior, secrets handling, or security posture. |
| Tier B assisted lane | OpenCode/DeepSeek may implement in an issue worktree and open a PR, but it requires human or Codex review before merge. | CLI/report polish, low-blast-radius source code, workflow scripts that can affect local behavior, docs that change public claims, and changes where ownership or risk is unclear. |
| Tier C restricted lane | OpenCode/DeepSeek may review or draft proposals only and must never merge autonomously. | Hurl runner behavior, `entroping run`, protected-run safety, redaction, proxy or traffic capture, provider boundary or LiteLLM routing, release publishing, architecture boundary changes, dependencies, secrets or credentials, security fixes, destructive filesystem behavior, and anything touching raw traffic or audit evidence. |

Tier A merge conditions are all required:

- The GitHub issue explicitly scopes the change as Tier A, or the PR explains
  why the work stayed inside Tier A.
- The worker starts from the active repo with `scripts/start_issue.sh` and uses
  one issue-scoped worktree.
- The PR includes an Agent Autonomy Declaration, checked Documentation Impact
  Declaration, and `Closes #<issue>`.
- OpenCode/DeepSeek-produced PRs record provider lane, provider host, billing
  path, concrete model id when known, autonomy tier, merge authority, and
  commands run in the PR body. Validate that evidence before autonomous Tier A
  merge or Codex review with:

```bash
scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence --issue <issue>
```

- The diff touches only Tier A surfaces and contains no generated local state,
  secrets, `.entroping/`, Graphify output, provider transcripts, or local env
  files.
- Focused tests run for the touched surface, `scripts/regression.sh --security`
  passes, and GitHub CI is green.
- The worker reviews the final diff, merges only through the PR, then runs
  `scripts/finish_issue.sh` from a separate checkout.

If a Tier A worker discovers the issue touches Tier B or Tier C scope, it must
stop at a safe checkpoint, report the files and failing or uncertain evidence,
and wait for human or Codex review. Tier B and Tier C work must not be
reclassified downward just to save model budget.

## Context Engineering Factory Boundary

GitHub Issues, PRs, CI, source files, tests, ADRs, the decision registry, and
QAnstitution/Hurl evidence remain the source-of-truth layer. These surfaces
decide whether Entroping behavior, architecture, security posture, and release
claims are real.

Obsidian, the LLM wiki, and curated source exports are the memory layer. They
preserve product evolution, source history, rejected ideas, open questions, and
durable rationale so a fresh agent can rehydrate the project without treating
old chat context as current truth.

Graphify, Understand Anything, CodeGraph, and Obsidian graph views are
comprehension and retrieval aids. They can reduce exploration cost, show
relationships, support onboarding, and guide impact analysis, but they do not
promote requirements, override tests, replace ADRs, or approve patches.

Headroom and other compression tools are economic tooling. They can reduce
token spend around noisy, re-fetchable context after retrieval behavior is
stable, but they must not hide exact diffs, failing test output, security
findings, audit evidence, or secrets-sensitive material.

`entroping run` remains deterministic, Hurl-based, QAnstitution-governed, and
provider-free. No context, graph, compression, or helper-agent tool may move LLM
providers into the run path or weaken the Hurl execution boundary.

Codex remains the factory architect and Tier B/Tier C merge owner, while Tier A
autonomous workers can merge only under the documented shipping lanes.
Budget-friendly workers can review, summarize, draft, critique, and ship
allowed Tier A changes, but every claim is checked against local files, tests,
docs, issues, ADRs, and CI before it becomes project truth.

## Context Pack

Every agent session should start with a deterministic context pack instead of a vague chat summary.

```bash
scripts/context_pack.sh --mode implementation
scripts/context_pack.sh --mode review
scripts/context_pack.sh --mode source
scripts/context_pack.sh --mode growth
scripts/context_pack.sh --mode handoff
```

Use `implementation` for coding, `review` for critique, `source` for Gemini/NotebookLM reconciliation, `growth` for open-source positioning, and `handoff` when starting a fresh thread.

When local Graphify/CodeGraph output exists, agents may add an optional
graph-assisted agent context section:

```bash
scripts/context_pack.sh --mode implementation --with-local-graphs --graph-query "<issue title or symbol>"
```

That opt-in section is produced by `scripts/agent_context_probe.py`, can write
ignored manifests under `agent-context-out/`, and must skip cleanly when
Graphify or CodeGraph output is absent. Graphify/CodeGraph evidence is not
authority; it can narrow file and test discovery, but it must not replace source
reading, focused tests, or CI.

## Agent Roles

`docs/meta/AGENT_ROLE_REGISTRY.yaml` is the machine-readable role registry for
portable worker prompts, context-pack routing, and metrics tags. Keep the table
below as the human summary and the registry as the consumable contract. Role
definitions are a routing aid, not authority to override repo evidence,
GitHub Issues, ADRs, tests, CI, or QAnstitution/Hurl evidence.

| Agent | Best Use | Not Allowed To Decide Alone |
| --- | --- | --- |
| Codex | Factory design, Tier B/Tier C integration, security fixes, repo scripts, final validation | Product strategy without updating docs/issues |
| Claude Code | Independent implementation proposal, code review, refactor critique | Tier B/Tier C merge without human or Codex validation |
| OpenCode | Cheap review worker, test ideas, docs drafts, alternative analysis, Tier A autonomous implementation | Security severity, architecture authority, release readiness, Tier B/Tier C merge authority |
| Gemini | Broad product synthesis, marketing angles, source debate, launch copy | Current repo facts unless given a context pack |
| NotebookLM | Source-grounded Q&A over exports and spec history | Implementation truth after code changes |
| local Qwen via oMLX | Private/offline summarization, low-risk review, wording variants | Final code, security, release, or architecture decisions |

## Multi-Session Rules

- One write agent per issue, branch, and file family.
- Many read-only review agents are acceptable.
- Do not let two agents edit the same source area concurrently.
- Use `scripts/start_issue.sh` for issue worktrees when there is a GitHub issue.
- Use `scripts/context_pack.sh --mode review` when asking another model to review a diff.
- Parent Codex thread resolves Tier B/Tier C conflicts against local files,
  tests, docs, ADRs, and CI.
- Tier A autonomous workers stop and escalate if they touch Tier B/Tier C scope
  or collide with another active worker.

## Marathon Pattern

Run marathons in waves:

1. Pick 2-4 independent GitHub issues.
2. Start one worktree per issue with `scripts/start_issue.sh`.
3. Keep one parent Codex thread as integrator for Tier B/Tier C or mixed-risk work.
4. Give helper agents read-only review prompts unless a worktree is isolated.
5. Require each write branch to pass `scripts/regression.sh`.
6. Require `scripts/regression.sh --security` for dependency, subprocess, proxy, path, LLM, report, or traffic-state changes.
7. Merge Tier A autonomously only when the lane conditions are met; otherwise merge only after human or Codex review.
8. Run `scripts/finish_issue.sh` after merge to clean worktrees and project-board state.

## Codex-Outage OpenCode/DeepSeek Work Queue

#702 is the one-week Codex-low-availability queue for OpenCode Desktop,
OpenCode Go, and paid DeepSeek API work. It is a queue index, not a separate
source of truth and not product roadmap proof. Child issues own implementation;
the queue keeps the worker order, risk tier, provider lane, and merge authority
explicit so low-cost workers do not improvise architecture, security, or release
decisions while Codex capacity is low.

Operating model:

- Codex produces guardrails, backlog packets, architecture boundaries, and
  review prompts while available.
- OpenCode/DeepSeek workers execute only one issue per worktree using
  `scripts/start_issue.sh`.
- Tier A issues may merge autonomously only after the documented lane
  conditions, local gates, GitHub CI, `Closes #<issue>`, and
  `scripts/finish_issue.sh` cleanup.
- Tier B issues may produce a PR, but Codex or a human must review before
  merge.
- Tier C issues are review/proposal only and must not merge autonomously.

Provider lanes:

- `opencode/native-deepseek`: OpenCode host using paid DeepSeek inside
  OpenCode.
- `deepseek-api/direct`: direct paid DeepSeek API through repo-local worker
  scripts.
- `opencode-go/kimi-k2.7-code`: OpenCode Go Kimi lane after that subscription
  is active.
- `opencode-go/qwen3.7-max`: OpenCode Go Qwen lane after that subscription is
  active.
- `opencode-go/other`: other OpenCode Go curated models.

Every worker handoff must name provider host, billing path, and concrete model
id when known. Use `opencode-desktop-handoff.md` for OpenCode Desktop or
OpenCode Go sessions. Use `issue-worker.md` only when the issue is already
scoped and the autonomy tier is clear.

Recommended rehearsal order:

This order records the planned queue and the evidence trail across completed
and remaining child issues. GitHub issue state remains authoritative for whether
each child is still open, merged, blocked, or finished.

1. #703 - first `opencode/native-deepseek` rehearsal for prompt-library docs
   and a guard test.
2. #704 - Codex-outage daily operations prompt.
3. #705 - OpenCode Desktop plugin/MCP/hook setup checklist.
4. #708 - OpenCode-only week monitoring prompt.
5. #709 - architecture-boundary brief template for worker issue packets.
6. #706 - PR body validator for provider-lane evidence.
7. #707 - factory metrics model-comparison report.
8. #710 - prove or discard Graphify, Obsidian, and CodeGraph context value.

Queue acceptance rules:

- Child issues must be ready, narrow, and tagged with a clear autonomy tier.
- Each child issue must name allowed files, forbidden files, focused tests,
  gates, and merge authority.
- The queue must include at least one immediate `opencode/native-deepseek`
  rehearsal issue.
- OpenCode Go model-variety work for Kimi/Qwen starts only after the
  subscription is active and the handoff names the concrete lane.
- No issue in this queue may ask unattended workers to touch `entroping run`,
  Hurl runner behavior, redaction, proxy capture, provider runtime boundaries,
  release publishing, secrets, dependencies, raw traffic, or audit evidence.
- Do not lower security, docs governance, CI, or coverage expectations, and do
  not treat model output as source of truth.
- Compare Codex, DeepSeek, Kimi, Qwen, or local/offline performance through
  issue outcome, diff quality, tests, CI, and review findings, not anecdotes.
  Use `model-comparison-trial.md` for the trial prompt and
  `scripts/factory_metrics.py report` for local value-free metrics summaries.

## Hallucination Controls

- Every implementation claim needs a file path, test, command, issue, or ADR.
- Every source-history claim needs a source path from `sources/SOURCE_MAP.md`.
- Every product change must be promoted into a canonical doc or ADR before code follows it.
- Every bug fix should add or update a regression test when deterministic reproduction is possible.
- Every model-generated suggestion is untrusted until checked against local files.

## Prompt Template

Reusable copy-paste prompts live in
`docs/meta/prompt-library/README.md`. Keep durable agent policy in this control
plane and keep session launchers in the prompt library.

```text
Work in <repo-root>.
Use AGENTS.md as the project rules.
Use scripts/context_pack.sh --mode implementation as the context pack.
Implement only the named GitHub issue or task.
Preserve the locked v4.1 command surface.
Declare the autonomy tier before implementation.
Use TDD where behavior is testable.
Run scripts/regression.sh before commit.
Run scripts/regression.sh --security for security-sensitive or dependency work.
Update docs and .context only when behavior, workflow, or durable lessons changed.
Return file/line evidence, commands run, and known gaps.
```

## Codex-Specific Flow

Codex should be boring and evidence-driven:

1. Read `AGENTS.md`.
2. Run `scripts/context_pack.sh --mode implementation` or read its listed files.
3. Inspect code before editing.
4. Write failing tests first where practical.
5. Apply narrow changes.
6. Run focused tests, then `scripts/regression.sh`.
7. Run `scripts/regression.sh --security` for sensitive boundaries.
8. Review `git diff`.
9. Update `.context/` and docs only when useful.
10. Commit with a Conventional Commit message.

Do not commit `.codex/` project state. Project behavior belongs in `AGENTS.md`, scripts, tests, docs, issue prompts, and CI.
