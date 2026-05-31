---
title: Good First Issue Walkthrough
type: runbook
status: active
tags:
  - contributors
  - issues
  - onboarding
  - validation
---

# Good First Issue Walkthrough

This is the smallest safe path for a first Entroping contribution. It keeps the
workflow deterministic without asking a newcomer to read the whole knowledge
base first.

## The Small Path

1. Pick one issue labeled `good first issue` and `status:ready`.
2. Check the `milestone` so you know whether the issue belongs to the current
   adoption queue, product-depth queue, integration queue, or stable-core queue.
3. Read only these files before editing:
   - `CONTRIBUTING.md`
   - `AGENTS.md`
   - `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
   - `docs/technical/TDS.md` if code, architecture, or command behavior changes
4. Preview the isolated worktree and prompt:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
```

5. Start the issue session:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
```

6. Make the narrowest change that proves the issue outcome.
7. Run the validation gates in the issue.
8. Open a pull request with a Documentation Impact Declaration.

## Labels

Use labels as routing hints, not as a second roadmap:

| Label | Meaning |
| --- | --- |
| `good first issue` | Small enough for a first contribution. |
| `status:ready` | The next action is clear enough to start. |
| `type:docs` | Documentation-only change. |
| `type:bug` | Reproduce, add a regression test, then fix. |
| `type:feature` | Deliver one narrow user-visible slice. |
| `type:security` | Treat as sensitive; use private advisories when needed. |
| `priority:p0` to `priority:p3` | Urgency. Higher priority should not expand the scope. |
| `area:*` | The subsystem or doc family most likely to change. |

If an issue is missing `status:ready`, ask for triage before starting. If the
issue has `status:blocked`, do not start it unless the blocker is resolved in
the issue thread.

## Validation

Run the smallest gate that matches the change, then run the broader gate before
the PR when the change is not docs-only.

Docs-only:

```bash
scripts/doc_governance_check.sh
scripts/check.sh
```

Normal feature or bug fix:

```bash
scripts/feature_gate.sh
scripts/regression.sh
```

Security-sensitive, dependency, subprocess, path, proxy, report, YAML, LLM, or
captured-traffic change:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

Use `scripts/audit_quality.sh` for release-hardening, validation marathon, or
quality-risk work.

## Pull Request

Before opening the PR:

1. Confirm `git status --short` shows only intentional files.
2. Run `git diff --check`.
3. Re-read the issue outcome and confirm the change proves it.
4. Include the PR template's Documentation Impact Declaration.
5. Link the issue with `Closes #<issue-number>`.

For docs work, update only the canonical docs required by
`docs/meta/DOCS_GOVERNANCE.md`. GitHub Issues remain the backlog; Obsidian docs
explain phase-level progress, product decisions, architecture, and durable
workflow rules.

## Minimal Link Map

- Contribution rules: `CONTRIBUTING.md`
- Agent and architecture guardrails: `AGENTS.md`
- Feature delivery gate: `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
- Issue lifecycle: `docs/meta/ISSUE_TRACKING.md`
- Architecture contract: `docs/technical/TDS.md`
- Public roadmap: `ROADMAP.md`
