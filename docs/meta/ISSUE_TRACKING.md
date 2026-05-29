---
title: Issue Tracking
type: runbook
status: active
tags:
  - issues
  - bugs
  - regression
  - github
---

# Issue Tracking

GitHub Issues are the canonical tracker for bugs, feature slices, regressions, and release blockers. Obsidian tracks strategy and progress; GitHub tracks work items.

## Labels

Use a small label system so the queue stays readable:

| Group | Labels |
| --- | --- |
| Type | `type:bug`, `type:feature`, `type:regression`, `type:security`, `type:docs`, `type:architecture` |
| Priority | `priority:p0`, `priority:p1`, `priority:p2`, `priority:p3` |
| Area | `area:cli`, `area:qanstitution`, `area:hurl-runner`, `area:reports`, `area:brain`, `area:eye`, `area:tests`, `area:docs` |
| Status | `status:needs-triage`, `status:ready`, `status:blocked`, `status:in-progress` |

## Triage Rules

- Every bug needs observed behavior, expected behavior, reproduction steps, area, and priority.
- Every feature slice needs one-sentence outcome, source-of-truth link, proof of completion, and required gates.
- Every regression needs a last-known-good state and a regression test plan.
- Security vulnerabilities should use private security advisories, not public issues.
- A ticket is ready only when the next action is clear enough for a fresh agent to execute.

## Bug Fix Flow

```text
Issue -> reproduce -> failing regression test -> narrow fix -> regression suite -> docs/context update -> commit -> close issue
```

Bug-fix requirements:

- Reproduce before fixing when possible.
- Add a failing regression test before or with the fix.
- Keep the fix scoped to the defect.
- Run `scripts/regression.sh`.
- Run `scripts/feature_gate.sh --security` if the bug touches paths, subprocesses, YAML, dependencies, reports, proxy capture, credentials, or LLM data boundaries.
- Update `.context/changelog.md` for meaningful fixes.
- Update `.context/lessons-learned.md` only when the bug reveals a durable pitfall.

## Feature Slice Flow

```text
Feature issue -> branch -> checklist -> TDD -> implementation -> review -> regression suite -> docs/context update -> commit
```

Feature-slice requirements:

- One issue should map to one narrow branch.
- Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`.
- Do not expand the command surface unless `docs/technical/COMMAND_CHEAT_SHEET.md` and product docs are updated first.
- Close the issue from the commit or PR with `Closes #<number>`.

## Starting A Session

Use the launcher from the repo root so every agent starts with the same issue context, worktree isolation, and guardrails:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
```

Examples:

```bash
scripts/start_issue.sh 3 feat/gate-injection --dry-run
scripts/start_issue.sh 3 feat/gate-injection
scripts/start_issue.sh 3 review/gate-injection --mode review
```

The launcher:

- Reads the issue title, URL, and state from GitHub.
- Creates `../Entroping-issue-<number>` unless `--dry-run` is used.
- Creates the requested branch from `main`.
- Saves a prompt under `.entroping/session-prompts/` in the worktree.
- Best-effort moves the issue to `status:in-progress` and the project board to `In Progress`.

Do not use this script to bypass planning. The generated prompt still requires `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, tests, regression checks, security review where relevant, and docs/context updates before merge.

## Obsidian Boundary

Do not duplicate every GitHub issue in Obsidian. Update Obsidian only for:

- Current phase and milestone progress in `docs/meta/PROJECT_PROGRESS.md`.
- Roadmap or scope changes in `docs/product/MVP_PLAN.md`.
- Architecture decisions in ADRs.
- Durable failures and fixes in `.context/lessons-learned.md`.
- User-facing behavior changes in user docs.
