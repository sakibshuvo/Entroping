---
title: Codex-Outage Daily Operations Prompt
type: prompt
status: active
tags:
  - outage
  - opencode
  - deepseek
  - operations
  - marathon
---

# Codex-Outage Daily Operations Prompt

Use this when Codex capacity is low or unavailable for several days and
OpenCode/DeepSeek workers need to keep Entroping moving without improvising
architecture, security, or merge authority.

This prompt is for Tier A docs/tests/guard work unless the assigned issue says
otherwise. Tier B/Tier C PRs must wait for Codex or human review before merge.

## Daily Loop

```text
You are running Entroping daily operations during low Codex availability.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud or another host: if this macOS path does not exist, use the
repository root provided by the task, then continue with the same checks.

Start each day:
git pull --ff-only
git status --short
git branch --show-current
gh pr list --repo sakibshuvo/Entroping --state open --limit 40
gh issue list --repo sakibshuvo/Entroping --state open --label status:ready --limit 80
scripts/context_pack.sh --mode implementation

Choose work:
1. Inspect open PRs before starting new work.
2. Pick only ready scoped issues with explicit allowed files, forbidden files,
   autonomy tier, required tests/gates, and merge authority.
3. Prefer Tier A prompt-library docs, guard tests, docs governance, and
   low-risk project hygiene.
4. Do not start Tier B/Tier C implementation unless the goal is a proposal PR
   that will wait for Codex or human review before merge.
5. Use provider lanes explicitly:
   - opencode/native-deepseek
   - deepseek-api/direct
   - opencode-go/kimi-k2.7-code
   - opencode-go/qwen3.7-max
   - opencode-go/other

Work one issue:
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
cd ../Entroping-issue-<issue-number>
scripts/context_pack.sh --mode implementation

Then:
1. Read AGENTS.md, docs/meta/DOCS_GOVERNANCE.md,
   docs/meta/FEATURE_DELIVERY_CHECKLIST.md, the issue body, and the relevant
   prompt-library owner docs.
2. Write a failing guard/test first when practical.
3. Make the smallest scoped change.
4. Run focused tests/gates for touched behavior.
5. Run the issue's required full gate. scripts/feature_gate.sh already
   includes scripts/architecture_integrity.sh; workers may also run
   scripts/architecture_integrity.sh directly as a fast preflight when
   reviewing possible architecture drift.
6. Open a PR with Closes #<issue>, Agent Autonomy Declaration,
   Documentation Impact Declaration, commands run, and provider-lane evidence
   when OpenCode/DeepSeek produced the work.
7. Watch CI with gh pr checks <pr-number> --repo sakibshuvo/Entroping --watch.
8. Merge only Tier A PRs after local gates and GitHub CI are green.
9. Run scripts/finish_issue.sh <issue-number> from a separate checkout.
10. Write an after-sleep status before stopping.
```

## Reference Prompts

Use these prompt-library entries instead of inventing local variants:

- `opencode-desktop-handoff.md` for OpenCode Desktop/OpenCode Go sessions.
- `issue-worker.md` for one scoped issue in one issue worktree.
- `pr-review-merge-gate.md` before any merge decision.
- `after-sleep-status.md` before handing work back after unattended sessions.
- `model-comparison-trial.md` when comparing Codex, OpenCode, DeepSeek, Kimi,
  Qwen, or local/offline model performance.

## Emergency Stop Conditions

Stop the current worker and report status when any of these happen:

- failing security gate,
- forbidden file touched,
- ambiguous scope,
- secret exposure risk,
- CI red,
- merge conflict,
- stale main,
- missing close keyword,
- dirty worktree that includes generated state, provider transcripts, reports,
  `.entroping/` artifacts, generated local context output,
  local env files, or secrets,
- Tier A work expanding into Tier B/Tier C scope,
- any change that weakens hexagonal architecture, QAnstitution branding, or
  treats model summaries as source of truth,
- any change touching Hurl runner behavior, `entroping run`, redaction, proxy,
  provider runtime boundary, dependencies, release publishing, raw traffic, or
  audit evidence.

## After-Sleep Status

Before ending the day, return:

- current main commit,
- open PRs and CI status,
- issues completed,
- issue worktrees still present,
- dirty or untracked files,
- local factory metrics ledger locations,
- accepted/rejected/stale worker findings,
- safe next issue,
- blockers or stop conditions.

Do not claim launch, stable-core, package-index, enterprise, security, or
adoption readiness from outage-session progress alone.
