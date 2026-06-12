---
title: CI Failure Debug Prompt
type: prompt
status: active
tags:
  - ci
  - github-actions
  - debugging
  - pr
---

# CI Failure Debug Prompt

Use this when GitHub Actions blocks a PR or branch.

```text
You are debugging Entroping CI.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

PR or branch:
<pr-number-or-branch>

Goal:
Find the smallest correct fix for the CI failure. Do not change product behavior unless the logs prove the product behavior is wrong.

Start:
git pull --ff-only
git status --short
gh pr view <pr-number-or-branch> --repo sakibshuvo/Entroping --json number,title,headRefName,baseRefName,state
gh pr checks <pr-number-or-branch> --repo sakibshuvo/Entroping
gh run list --repo sakibshuvo/Entroping --limit 20

Debug flow:
1. Identify the failing workflow/job/step.
2. Fetch logs with `gh run view <run-id> --log-failed`.
3. Classify failure:
   - test failure,
   - lint/type failure,
   - docs governance,
   - PR body validation,
   - public claims audit,
   - dependency/security audit,
   - packaging/install smoke,
   - flaky/stuck GitHub Actions state.
4. Reproduce locally when practical.
5. Fix the narrow root cause.
6. Avoid empty commits unless a stuck Actions run needs a clean event and no file changes are required.

If PR checks are missing:
- inspect Actions runs directly,
- wait for checks to attach,
- avoid spending Project GraphQL quota unnecessarily.

Return:
- failing job and log evidence,
- root cause,
- files changed,
- local commands run,
- whether behavior changed,
- whether docs/context changed,
- next CI command to watch.
```
