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

Codex is the primary integrator for Entroping until the project explicitly changes that rule. Other agents can explore, critique, summarize, draft tests, or propose patches, but Codex owns final edits, validation, commits, and pull-request readiness.

No helper agent is a source of truth. The hierarchy is:

1. Local repo files and tests.
2. GitHub issues, PRs, and CI.
3. ADRs and canonical product/technical docs.
4. Source exports under `<source-archive>`, usually `../entroping-specs` or `ENTROPING_SOURCE_ROOT`.
5. Agent summaries, chat context, NotebookLM answers, Gemini answers, Claude Code output, OpenCode output, and local Qwen output.

## Software Factory Operating Model

Codex owns integration and merge readiness. Treat the parent Codex thread as
the control room: it chooses the issue, verifies local files, runs tests,
updates required docs, opens the PR, waits for CI, and merges only when the
evidence is clean.

OpenCode and free-model workers receive bounded issue prompts. They can propose
tests, patches, review notes, alternate designs, and documentation drafts, but
their output is untrusted until Codex validates it against the repo, issue, and
gates.

local Qwen/oMLX handles private summarization, triage, and low-risk review. Use
it for source-archive summarization, duplicate-finding, wording variants, and
offline review prompts before sending anything sensitive to cloud models.

Generated codegraph, Graphify, and Obsidian graph output is evidence, not authority.
They can help humans and agents navigate relationships, but local tests, source
files, ADRs, GitHub Issues, and CI decide truth.

One write agent per issue-scoped worktree. Parallelism comes from independent
issues, not from multiple agents editing the same files.

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

## Agent Roles

| Agent | Best Use | Not Allowed To Decide Alone |
| --- | --- | --- |
| Codex | Implementation, integration, security fixes, repo scripts, final validation | Product strategy without updating docs/issues |
| Claude Code | Independent implementation proposal, code review, refactor critique | Direct merge without Codex validation |
| OpenCode | Cheap review worker, test ideas, docs drafts, alternative analysis | Security severity, architecture authority, release readiness |
| Gemini | Broad product synthesis, marketing angles, source debate, launch copy | Current repo facts unless given a context pack |
| NotebookLM | Source-grounded Q&A over exports and spec history | Implementation truth after code changes |
| local Qwen via oMLX | Private/offline summarization, low-risk review, wording variants | Final code, security, release, or architecture decisions |

## Multi-Session Rules

- One write agent per issue, branch, and file family.
- Many read-only review agents are acceptable.
- Do not let two agents edit the same source area concurrently.
- Use `scripts/start_issue.sh` for issue worktrees when there is a GitHub issue.
- Use `scripts/context_pack.sh --mode review` when asking another model to review a diff.
- Parent Codex thread resolves conflicts against local files, tests, docs, ADRs, and CI.

## Marathon Pattern

Run marathons in waves:

1. Pick 2-4 independent GitHub issues.
2. Start one worktree per issue with `scripts/start_issue.sh`.
3. Keep one parent Codex thread as integrator.
4. Give helper agents read-only review prompts unless a worktree is isolated.
5. Require each write branch to pass `scripts/regression.sh`.
6. Require `scripts/regression.sh --security` for dependency, subprocess, proxy, path, LLM, report, or traffic-state changes.
7. Merge only through PRs with clean CI.
8. Run `scripts/finish_issue.sh` after merge to clean worktrees and project-board state.

## Hallucination Controls

- Every implementation claim needs a file path, test, command, issue, or ADR.
- Every source-history claim needs a source path from `sources/SOURCE_MAP.md`.
- Every product change must be promoted into a canonical doc or ADR before code follows it.
- Every bug fix should add or update a regression test when deterministic reproduction is possible.
- Every model-generated suggestion is untrusted until checked against local files.

## Prompt Template

```text
Work in <repo-root>.
Use AGENTS.md as the project rules.
Use scripts/context_pack.sh --mode implementation as the context pack.
Implement only the named GitHub issue or task.
Preserve the locked v4.1 command surface.
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
