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
1. local dirty files,
2. untracked files,
3. issue worktrees,
4. open PRs and CI state,
5. recently merged PRs,
6. closed issues,
7. failed or stuck Actions runs,
8. docs/progress drift,
9. whether any agent left unsafe or duplicate work,
10. next highest-value issue.

Return:
- current repo status,
- what changed since the last checkpoint,
- open PRs and CI status,
- dirty/uncommitted files,
- worktrees to clean or preserve,
- issues completed,
- issues ready next,
- blockers,
- recommended next command.

Do not start new implementation until the status is clear.
```
