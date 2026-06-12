---
title: Bug Bash Prompt
type: prompt
status: active
tags:
  - bug-bash
  - testing
  - regression
  - issues
---

# Bug Bash Prompt

Use this for a brutal read-first test session. The goal is to find and log real
bugs, not to churn code.

```text
You are running an Entroping bug bash.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Mode:
Start read-only. Do not edit files until a specific bug is reproduced and assigned.

Start:
git pull --ff-only
git status --short
scripts/context_pack.sh --mode review
gh issue list --repo sakibshuvo/Entroping --state open --limit 80

Focus areas:
1. CLI first-hour flows: init, doctor, run, dry-run, reports, demo scripts.
2. Protected production safety mode.
3. QAnstitution validation and schema drift.
4. Hurl runner subprocess boundaries.
5. Report JSON/JUnit/HTML consistency.
6. Install and release scripts.
7. Path traversal, symlink, YAML, env, and secret handling.
8. Docs claims that no longer match behavior.

Bug rules:
- Reproduce before claiming a bug whenever practical.
- Prefer a tiny temp project reproduction.
- Separate real bugs from unclear UX, docs confusion, and feature requests.
- Do not fix multiple bugs in one branch.
- Open or propose GitHub issues for verified bugs.

For each finding return:
- severity: P0/P1/P2/P3,
- area,
- reproduction steps,
- expected behavior,
- actual behavior,
- evidence command/output summary,
- likely files,
- suggested issue title,
- proposed regression test.

If asked to fix one bug, create one issue-scoped worktree and use TDD.
```
