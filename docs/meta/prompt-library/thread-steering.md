---
title: Thread Steering Prompt
type: prompt
status: active
tags:
  - codex
  - handoff
  - steering
---

# Thread Steering Prompt

Use this when another Codex thread has already started and you need to add
rules, redirect it, or prevent context drift.

## Safe Pause

```text
Pause after your current safe checkpoint. Before doing more work, absorb this additional handoff prompt.

Do not restart from scratch.
Do not revert or discard current work.

First run:
git status --short
pwd
git branch --show-current

Then read the full prompt below and reply with:
1. what issue/worktree you are currently on,
2. what files you have touched,
3. what tests/gates have run,
4. whether this prompt changes your current plan.

After that, continue only from the safest next step.

[PASTE ADDITIONAL PROMPT HERE]
```

## If The Thread Is Already Editing

```text
Do not discard or revert any work already done. First run git status --short in the active worktree, then reconcile these rules with the current task. If the new rules conflict with your current work, stop and report the conflict instead of guessing.
```

## If The Thread Is On The Wrong Folder

```text
Stop. You appear to be outside the active Entroping implementation repo.

The active repo should be:
/Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Run:
pwd
git status --short

If you are not in /Users/sakibshuvo/projects/Entroping, the cloud task repository root, or an issue worktree named Entroping-issue-<number>, do not edit files. Report your current path and wait.
```

## If The Thread Should Become Review-Only

```text
Switch to review-only mode. Do not edit, stage, commit, push, or merge. Inspect the current diff and return findings ordered by severity with file/line evidence. Separate verified findings from interpretation.
```
