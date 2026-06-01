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

Documentation ownership and roadmap update rules live in
[[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]]. Do not duplicate issue-level
backlog details into Obsidian.

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

For a first contribution, start with
[[docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH|GOOD_FIRST_ISSUE_WALKTHROUGH]].

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

## Finishing A Session

After the issue PR is merged and CI is green, use the finish script from a
separate checkout so local cleanup follows the same deterministic checks every
time:

```bash
scripts/finish_issue.sh <issue-number> --dry-run
scripts/finish_issue.sh <issue-number>
```

The finish script:

- Reads the closed issue and its closing pull request from GitHub.
- Verifies the pull request is merged and all reported checks passed.
- Verifies the issue worktree path belongs to this repository.
- Refuses to remove dirty or branch-mismatched worktrees.
- Removes the local issue worktree and deletes squash-merged local branches only
  after those checks pass.
- Best-effort removes active status labels and moves the GitHub Project item to
  `Done`.

Use `--dry-run` first when cleaning up a batch of sessions.

## Backlog Health

Before starting or ending a marathon, check that open issues still have the
minimum labels and milestone context needed for multi-session handoff:

```bash
python scripts/backlog_health.py
```

The script shells out to `gh issue list` by default. For reviews or tests, pass
a fixture exported from GitHub:

```bash
python scripts/backlog_health.py --input /path/to/issues.json
```

Open issues should have at least one `type:*`, one `priority:*`, one
`status:*`, and a milestone. The script is intentionally about queue hygiene,
not product priority judgment.

## Obsidian Boundary

Do not duplicate every GitHub issue in Obsidian. Update Obsidian only for:

- Current phase and milestone progress in `docs/meta/PROJECT_PROGRESS.md`.
- Roadmap or scope changes in `docs/product/MVP_PLAN.md`.
- Architecture decisions in ADRs.
- Durable failures and fixes in `.context/lessons-learned.md`.
- User-facing behavior changes in user docs.

Run `scripts/doc_governance_check.sh` before merging changes that affect the
documentation control plane.
