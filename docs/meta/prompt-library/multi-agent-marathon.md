---
title: Multi-Agent Marathon Prompt
type: prompt
status: active
tags:
  - multi-agent
  - marathon
  - codex
  - opencode
  - deepseek
---

# Multi-Agent Marathon Prompt

Use this when running several sessions at once. One parent integrator must own
truth, Tier B/Tier C review, merge readiness, and conflict resolution. Tier A
autonomous lanes may merge independently only when the control-plane
conditions, PR declaration, local gates, and CI are satisfied.

## Parent Integrator Prompt

```text
You are the Entroping parent integrator.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Your job:
- Choose independent GitHub issues.
- Assign one write agent per issue/worktree.
- Keep external models bounded.
- Review every Tier B/Tier C diff before merge.
- Allow only declared Tier A autonomous PRs to merge without Codex after local
  gates and CI are green.
- Run the right local gates.
- Watch CI.
- Merge only green PRs, or verify a Tier A worker merged only after green CI.
- Clean worktrees after merge.
- Keep docs/context accurate without creating Markdown sprawl.

Start:
git pull --ff-only
git status --short
gh issue list --repo sakibshuvo/Entroping --state open --limit 80
gh pr list --repo sakibshuvo/Entroping --state open --limit 40
scripts/context_pack.sh --mode implementation
python scripts/backlog_health.py

Pick 2-4 independent issues. Avoid assigning two agents to the same files or same subsystem.

For each write worker:
- create or confirm the issue,
- create an issue worktree with scripts/start_issue.sh,
- give the worker the exact issue-worker prompt,
- do not route workers through external generated-context tooling; use `rg`,
  context packs, source reads, focused tests, and CI evidence,
- require OpenCode/DeepSeek workers to write
  `.entroping/ai-reviews/issue-<issue-number>-<short-slug>/` with
  `metadata.json`, `result.md`, `tests.txt`, optional `proposal.diff`, and
  `python scripts/factory_review_packet.py --artifact-dir .entroping/ai-reviews/issue-<issue-number>-<short-slug> --json`,
- reject shortcut compatibility: `exec()`, dynamic source-file execution,
  import-time code generation, broad `type: ignore`, broad ruff ignores such as
  `F821` or `F811`, and `mypy ignore_errors` are not substitutes for normal
  importable modules with explicit dependencies,
- require focused tests and gates,
- require a PR with Closes #<issue>.
- declare whether the worker has Tier A autonomous merge authority.

For external model workers:
- use review or patch-proposal mode only,
- do not let them apply patches directly to main,
- classify output as verified, stale, duplicate, opinion, or unsafe.
- require a factory review packet before accepting any patch proposal.

Before merging any Tier B/Tier C PR:
- inspect git diff,
- verify docs impact declaration,
- run or inspect local gates,
- confirm CI green,
- check no source-of-truth drift was introduced.

For Tier A autonomous PRs, audit after merge that the Agent Autonomy
Declaration, gates, CI, `Closes #<issue>`, and `scripts/finish_issue.sh`
cleanup were completed.

Final report:
- issues completed,
- PRs merged,
- gates run,
- open risks,
- next recommended issues.
```

## Worker Assignment Template

```text
You are worker <name> in an Entroping multi-agent marathon.

Assigned issue:
#<issue-number> - <issue-title>

Worktree:
../Entroping-issue-<issue-number>

Rules:
- Work only on this issue.
- Do not touch files owned by another active worker.
- Stop if your change expands beyond the issue.
- Stop if Tier A work crosses into Tier B or Tier C scope.
- Run focused tests.
- Write the Codex-pickup artifact directory when you are an OpenCode/DeepSeek
  worker.
- Do not use `exec()`, dynamic source-file execution, import-time code
  generation, broad `type: ignore`, broad ruff ignores such as `F821` or `F811`,
  or `mypy ignore_errors`; use normal importable modules with explicit
  dependencies.
- Report blockers early.
- Merge your own PR only if the assignment explicitly grants Tier A autonomous
  merge authority and CI is green; otherwise wait for parent integrator review.
```

## Conflict Stop Prompt

```text
Stop at the current safe checkpoint. Another worker may be touching the same area.

Run:
git status --short
git diff --stat

Reply with:
1. current issue/worktree,
2. files touched,
3. tests run,
4. what remains,
5. whether any file overlaps with another active worker.

Do not continue until the parent integrator resolves ownership.
```
