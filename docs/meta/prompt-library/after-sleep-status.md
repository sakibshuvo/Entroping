---
title: After Sleep Status Prompt
type: prompt
status: active
tags:
  - status
  - handoff
  - marathon
  - github
---

# After Sleep Status Prompt

Use this when returning after an unattended or multi-session run.

```text
You are giving an Entroping after-sleep status report.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Goal:
Tell me exactly what happened, what is dirty, what merged, what failed, and what I should do next.

Start:
git pull --ff-only
git status --short
git log --oneline --max-count=12
git worktree list
gh pr list --repo sakibshuvo/Entroping --state open --limit 40
gh issue list --repo sakibshuvo/Entroping --state open --limit 80
gh run list --repo sakibshuvo/Entroping --limit 20
python scripts/backlog_health.py

Check:
1. Provider evidence:
   - provider lane,
   - provider host,
   - billing path,
   - model id,
   - autonomy tier,
2. local dirty/untracked files,
3. issue worktrees,
4. current repo commit,
5. open PRs and CI status:
   - CI pending,
   - CI failed,
   - merged but finish cleanup pending,
   - blocked by Tier B/Tier C scope,
6. recently merged PRs and closed issues,
7. failed or stuck Actions runs,
8. docs/progress drift,
9. whether any agent left unsafe or duplicate work,
10. commands run,
11. dirty files to clean and which issue worktrees to preserve,
12. skipped gates and why,
13. next safe action.

Return:
- current repo status and current repo commit,
- provider lane, provider host, billing path, model id, and autonomy tier,
- what changed since the last checkpoint,
- open PRs and CI status (classified with the categories above),
- recently merged PRs and closed issues,
- failed or stuck Actions runs,
- docs/progress drift,
- unsafe or duplicate agent work,
- dirty and untracked files,
- worktrees to clean or preserve,
- commands run,
- issues completed and blockers,
- issues ready next only when no stop condition applies,
- skipped gates and rationale,
- safe next action with a concrete command.

Status is clear only when every Check item has a concrete answer, any pending or
failed CI has a stated reason, skipped gates have a stated rationale, and the
safe next action is a concrete command or an explicit stop.

Do not start new implementation until the status is clear.
```
