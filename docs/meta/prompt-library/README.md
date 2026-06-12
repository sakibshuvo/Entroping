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
- Treat Gemini, DeepSeek, OpenCode, NotebookLM, Graphify, CodeGraph, and local
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
| [Issue worker](issue-worker.md) | Give a coding agent one GitHub issue and an isolated worktree, including the Autonomous Tier A OpenCode/DeepSeek Worker Prompt. |
| [Spark-safe worker](spark-safe-worker.md) | Use low-risk Codex Spark capacity for docs/tests/project hygiene. |
| [Multi-agent marathon](multi-agent-marathon.md) | Run several bounded sessions while one parent thread owns integration. |
| [Thread steering](thread-steering.md) | Interrupt or redirect a running Codex thread without losing its current work. |
| [Gemini review](gemini-review.md) | Ask Gemini or NotebookLM for a brutal product/engineering review. |
| [DeepSeek/OpenCode review](deepseek-opencode-review.md) | Ask DeepSeek/OpenCode for bounded repo review, bug bash, or patch proposals. |
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

## When To Use Which

- New Codex thread: start with `codex-session-handoff.md`.
- One implementation slice: use `issue-worker.md`; use its autonomous variant
  only for Tier A docs/tests/guard/script work.
- Low-token or cheaper model work: use `spark-safe-worker.md` or
  `deepseek-opencode-review.md`.
- Large overnight push: use `multi-agent-marathon.md` and keep a parent
  integrator thread open.
- Another thread already started: paste `thread-steering.md` before adding new
  context.
- External product sanity check: use `gemini-review.md`.
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
