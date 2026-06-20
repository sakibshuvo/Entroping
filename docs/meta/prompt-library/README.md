---
title: Prompt Library
type: prompt-library
status: active
tags:
  - agents
  - prompts
  - codex
  - opencode
  - deepseek
  - gemini
  - claude
---

# Prompt Library

This is the copy-paste shelf for Entroping agent work. It keeps reusable prompts
in one place so they do not get buried in chat history or duplicated across
strategy docs.

Use these prompts as launchers, not as source of truth. Every prompt should make
the receiving agent read local repo files, GitHub issue state, tests, and CI
before it claims facts or edits files.

This directory is for human copy-paste prompts. Machine-consumed worker
templates live under `prompts/` and are used by repo-local helpers such as
`scripts/opencode_worker.py` and `scripts/deepseek_worker.py`.

## Default Paths

These prompts are tuned for the maintainer workflow on this machine:

```text
Active repo: /Users/sakibshuvo/projects/Entroping
Source archive: /Users/sakibshuvo/projects/entroping-specs
Stale path: /Users/sakibshuvo/Documents/Entroping
```

Use those paths as-is for this project. Replace them only when sharing the
prompt with another contributor or running Entroping from a different checkout.

Codex Cloud note: if a prompt says `cd /Users/sakibshuvo/projects/Entroping`
and that path does not exist, use the repository root provided by the cloud
task, then continue with the same checks. If a prompt references
`/Users/sakibshuvo/projects/entroping-specs`, use it only when that source
archive is mounted or attached to the cloud task.

## Rules

- Do not paste secrets, API keys, raw traffic, cookies, headers, or private
  provider output into model prompts.
- Give one write agent one issue-scoped worktree.
- Keep Codex or the parent integrator responsible for final review, gates, PRs,
  and merge readiness for Tier B/Tier C work.
- Allow OpenCode/DeepSeek to merge only Tier A autonomous lane work after the
  PR declares merge authority, required local gates pass, and CI is green.
- Treat Gemini, DeepSeek, OpenCode, NotebookLM, and local
  models as evidence sources, not authorities.
- Declare the role from `docs/meta/AGENT_ROLE_REGISTRY.yaml` before starting
  worker prompts, and record local budget/context outcomes with
  `scripts/factory_metrics.py` when a session produces useful evidence.
- The portable software-factory protocol supports Codex, Claude Code,
  OpenCode, DeepSeek, Gemini, Spark, and local models, but prompts still make
  the receiving agent prove every claim against repo truth before edits or
  merge.

## Prompt Catalog

| Prompt | Use |
| --- | --- |
| [Codex session handoff](codex-session-handoff.md) | Start a fresh Codex thread in the proper project folder. |
| [Issue worker](issue-worker.md) | Give a coding agent one GitHub issue and an isolated worktree, including the Self-Contained OpenCode/DeepSeek Work Packet and Autonomous Tier A OpenCode/DeepSeek Worker Prompt. |
| [Architecture boundary brief](architecture-boundary-brief.md) | Attach ownership, allowed files, forbidden files, invariants, tests, provider/runtime constraints, and stop conditions to worker issue packets. |
| [Spark-safe worker](spark-safe-worker.md) | Use low-risk Codex Spark capacity for docs/tests/project hygiene. |
| [Codex persistent marathon](codex-persistent-marathon.md) | Keep one Codex integrator session moving through the full issue-worktree-PR-CI-merge-finish loop instead of stopping after one issue or safe checkpoint. |
| [Multi-agent marathon](multi-agent-marathon.md) | Run several bounded sessions while one parent thread owns integration. |
| [OpenCode Desktop handoff](opencode-desktop-handoff.md) | Start OpenCode Desktop/OpenCode Go implementation or PR verification sessions with the self-contained worker packet, explicit provider lane, billing, model, role, merge authority, and `scripts/opencode_readiness.py` preflight evidence. |
| [OpenCode Desktop one-shot](opencode-desktop-one-shot.md) | Paste one bootstrap prompt into OpenCode Desktop with paid DeepSeek V4 Pro so it can pick one Tier A issue, create the work packet, run the issue worktree conveyor, open the PR, wait for CI, merge if allowed, and finish cleanup. |
| [OpenCode Codex review request](opencode-codex-review-request.md) | Let OpenCode request a read-only Codex CLI review of an OpenCode-produced local diff or PR before merge. |
| [Model-comparison trial](model-comparison-trial.md) | Compare Codex, OpenCode native DeepSeek, direct DeepSeek API, OpenCode Go Kimi/Qwen, and local/offline models through evidence. |
| [Model-output acceptance gate](model-output-acceptance-gate.md) | Decide what to accept, review, convert to issues, or reject from cheap-model reviews, patches, PRs, and drafts. |
| [Codex-outage daily operations](codex-outage-daily-operations.md) | Run daily OpenCode/DeepSeek operations safely when Codex capacity is low or unavailable. |
| [OpenCode-only week monitoring](opencode-week-monitoring.md) | Watch OpenCode/DeepSeek PRs, CI, ready issues, cleanup candidates, and factory metrics without mutating repo state. |
| [Thread steering](thread-steering.md) | Interrupt or redirect a running Codex thread without losing its current work. |
| [Gemini review](gemini-review.md) | Ask Gemini or NotebookLM for a brutal product/engineering review. |
| [Claude code review](claude-code-review.md) | Ask Claude Code or work-Claude for an occasional source-pinned code/security review. |
| [DeepSeek/OpenCode review](deepseek-opencode-review.md) | Ask DeepSeek/OpenCode for bounded repo review, bug bash, or patch proposals. |
| [Engineering health review](engineering-health-review.md) | Audit architectural drift, anti-patterns, code smells, docs health, quality, testability, debugging ergonomics, security, maintainability, and regression risk. |
| [PR review and merge gate](pr-review-merge-gate.md) | Decide if an open PR is safe to merge. |
| [Bug bash](bug-bash.md) | Run a brutal read-first bug-finding session and log verified issues. |
| [Backlog triage](backlog-triage.md) | Convert reviews, feedback, and ideas into clean GitHub issues. |
| [Roadmap and progress refresh](roadmap-progress-refresh.md) | Refresh project direction without creating docs sprawl. |
| [Launch readiness review](launch-readiness-review.md) | Audit README, install, demo, public surface, and first-five-minute UX. |
| [Stable-core audit](stable-core-audit.md) | Check stable-core evidence honestly before making readiness claims. |
| [Context reconciliation](context-reconciliation.md) | Compare historical source material against current repo truth. |
| [CI failure debug](ci-failure-debug.md) | Debug GitHub Actions without broad product changes. |
| [Security review](security-review.md) | Review security-sensitive diffs, branches, or issues. |
| [After-sleep status](after-sleep-status.md) | Summarize overnight or multi-session work before continuing. |

## Prompt Selection Matrix

Use this table first when choosing a launcher. It is a routing aid, not a
replacement for local repo evidence, GitHub issue state, tests, CI, or the
decision registry.

| Prompt | Use When | Runner |
| --- | --- | --- |
| `codex-session-handoff.md` | Start a fresh Codex thread or recover after a context reset. | Codex integrator |
| `issue-worker.md` | Give one agent one GitHub issue, one worktree, and explicit acceptance criteria. | Codex, OpenCode, or DeepSeek worker |
| `opencode-desktop-one-shot.md` | Run one Tier A OpenCode Desktop issue conveyor with paid DeepSeek V4 Pro and minimal manual terminal work. | OpenCode Desktop with DeepSeek |
| `opencode-desktop-handoff.md` | Start OpenCode implementation or PR verification with provider, billing, model, role, autonomy tier, MCP/tooling, and stop conditions declared. | OpenCode Desktop or OpenCode Go |
| `opencode-codex-review-request.md` | Ask Codex CLI for a read-only review of an OpenCode-produced diff or PR before merge. | OpenCode requesting Codex review |
| `deepseek-opencode-review.md` | Run bounded low-cost review, bug bash, or patch-proposal work that Codex or a parent integrator must validate. | DeepSeek or OpenCode worker |
| `model-output-acceptance-gate.md` | Decide what to accept, reject, convert to issues, or escalate from cheap-model output. | Integrator or reviewer |
| `model-comparison-trial.md` | Compare model lanes with evidence, accepted output, correction effort, cost, and context metrics. | Integrator plus bounded workers |
| `codex-outage-daily-operations.md` | Keep safe Tier A progress moving when Codex capacity is low or unavailable. | OpenCode/DeepSeek operator |
| `opencode-week-monitoring.md` | Monitor OpenCode/DeepSeek PRs, CI, ready issues, cleanup candidates, and metrics without mutating repo state. | Monitoring agent |
| `codex-persistent-marathon.md` | Keep one Codex session acting as persistent integrator across repeated issue-worktree-PR-CI-merge-finish loops. | Codex integrator |
| `multi-agent-marathon.md` | Run several bounded agents while one parent thread owns integration, review, and merge readiness. | Parent integrator |
| `spark-safe-worker.md` | Spend low-risk Spark capacity on docs, tests, project hygiene, and small guardrail checks. | Spark or Codex Spark |
| `architecture-boundary-brief.md` | Attach ownership, allowed files, forbidden files, invariants, tests, provider/runtime constraints, and stop conditions to a worker packet. | Architect or integrator |
| `engineering-health-review.md` | Audit architectural drift, anti-patterns, code smells, docs health, code quality, testability, debugging ergonomics, security, maintainability, and regression risk. | Review agent |
| `claude-code-review.md` | Ask Claude Code or work-Claude for an occasional source-pinned code/security review. | Claude reviewer |
| `gemini-review.md` | Ask Gemini or NotebookLM for a brutal product and engineering sanity check. | Gemini or NotebookLM reviewer |
| `security-review.md` | Review a security-sensitive diff, branch, or issue without widening scope. | Security reviewer |
| `pr-review-merge-gate.md` | Decide whether an open PR is safe to merge. | Integrator |
| `ci-failure-debug.md` | Debug GitHub Actions failures without broad product changes. | Dev or QA agent |
| `bug-bash.md` | Find verified bugs and quality gaps from repo evidence. | QA or review agent |
| `backlog-triage.md` | Convert reviews, feedback, and ideas into scoped GitHub issues. | Product manager or triage agent |
| `after-sleep-status.md` | Summarize overnight, unattended, or multi-session work before continuing. | Any worker or integrator |
| `thread-steering.md` | Interrupt or redirect a running Codex thread without losing its safe checkpoint. | Human operator or parent integrator |
| `roadmap-progress-refresh.md` | Refresh project direction and progress without creating docs sprawl. | Product manager or integrator |
| `launch-readiness-review.md` | Audit README, install, demo, public surface, and first-five-minute UX without overclaiming readiness. | Product or review agent |
| `stable-core-audit.md` | Check stable-core evidence honestly before making readiness claims. | Integrator or reviewer |
| `context-reconciliation.md` | Compare historical source material or archived context against current repo truth. | Context reviewer |

## Quick Selection Rules

| Goal | Use |
| --- | --- |
| I want OpenCode Desktop + DeepSeek to just work | `opencode-desktop-one-shot.md` |
| I need to prepare a bounded OpenCode or DeepSeek implementation packet | `issue-worker.md` plus `architecture-boundary-brief.md` when risk is non-trivial |
| A cheap model produced a large patch or review; should I trust it? | `model-output-acceptance-gate.md` |
| Codex limit is low; keep moving safely | `codex-outage-daily-operations.md` |
| I want a Codex session to keep shipping issues | `codex-persistent-marathon.md` |
| Before merge, is this PR safe? | `pr-review-merge-gate.md` |
| Find code quality, design, security, and documentation problems | `engineering-health-review.md` |
| CI is red | `ci-failure-debug.md` |
| A review produced too many ideas | `backlog-triage.md` |

## When To Use Which

- New Codex thread: start with `codex-session-handoff.md`.
- One implementation slice: use `issue-worker.md`; for OpenCode/DeepSeek
  write work, fill its Self-Contained OpenCode/DeepSeek Work Packet before
  the worker edits files. Use its autonomous variant only for Tier A
  docs/tests/guard/script work.
- Worker packet with architecture risk: attach `architecture-boundary-brief.md`
  before implementation so the agent has explicit ownership, invariant, test,
  provider/runtime, and stop-condition boundaries.
- Low-token or cheaper model work: use `spark-safe-worker.md` or
  `deepseek-opencode-review.md`; for queued low-risk Tier A work, prefer
  `scripts/ai_jobs.py submit --autonomy-tier tier-a` so the worker defaults to
  cheap routing and a context-pack manifest first.
- OpenCode Desktop/OpenCode Go write sessions: use
  `opencode-desktop-handoff.md` with the Self-Contained OpenCode/DeepSeek Work
  Packet so provider host, billing path, concrete model id, role, autonomy
  tier, allowed files, forbidden files, Verification lane, Exact tests/gates,
  Stop conditions, PR body requirements, CI/merge/finish expectations,
  Ask Codex only when rules, merge authority, and
  `uv run python scripts/opencode_readiness.py --mode implementation --require-clean --format json`
  evidence are explicit before work starts.
- Desktop-only DeepSeek V4 Pro run: use `opencode-desktop-one-shot.md` when
  you want OpenCode Desktop to run the whole Tier A conveyor through its own
  tools without asking you to open a separate terminal.
- OpenCode requesting Codex CLI review: use
  `opencode-codex-review-request.md` for a read-only local-diff review with
  `codex review` or a PR evidence review with `codex exec`.
- Model/cost experiments: use `model-comparison-trial.md` so trial identity,
  files changed/read, tests/gates, CI, cost/token/context evidence, accepted,
  rejected, and stale findings, and reviewer overrides are recorded before
  drawing conclusions.
- Cheap-model output intake: use `model-output-acceptance-gate.md` after a
  large OpenCode, DeepSeek, Kimi, Qwen, or local-model output so useful parts
  can be accepted while stale, unsafe, or out-of-scope parts are rejected or
  converted into GitHub issues.
- Codex low-capacity or outage period: use
  `codex-outage-daily-operations.md` to inspect PRs/issues, select only ready
  scoped issues, enforce stop conditions, watch CI, run finish cleanup, and
  return after-sleep status.
- OpenCode-only monitoring week: use `opencode-week-monitoring.md` to check
  open PRs, CI rollups, ready issues, merged PR cleanup candidates, and factory
  metrics while staying read-only by default.
- Single Codex marathon: use `codex-persistent-marathon.md` when one Codex
  session should keep repeating the issue-worktree-PR-CI-merge-finish conveyor
  until N issues are merged, a verified blocker appears, CI cannot be fixed
  safely, the user interrupts, or a tool/runtime limit stops continuation.
- Large overnight push: use `multi-agent-marathon.md` and keep a parent
  integrator thread open.
- Another thread already started: paste `thread-steering.md` before adding new
  context.
- External product sanity check: use `gemini-review.md`.
- Occasional deep Claude code/security review: use `claude-code-review.md`,
  then triage the output through `backlog-triage.md` before opening issues or
  accepting fixes.
- Holistic engineering-health audit: use `engineering-health-review.md`.
- After unattended work: use `after-sleep-status.md`.
- Before merge: use `pr-review-merge-gate.md`.
- CI blocked: use `ci-failure-debug.md`.
- Review output is overwhelming: use `backlog-triage.md`.
- Progress feels confusing: use `roadmap-progress-refresh.md`.
- Launch question: use `launch-readiness-review.md`.
- Stable-core claim: use `stable-core-audit.md`.
- Historical/spec drift question: use `context-reconciliation.md`.
- Security-sensitive area: use `security-review.md`.

## Maintenance

Update this library when a prompt becomes reusable across at least two sessions.
Do not add one-off chat dumps. If a prompt encodes a durable workflow rule,
also update `docs/meta/AGENT_CONTROL_PLANE.md` or the relevant canonical doc.
