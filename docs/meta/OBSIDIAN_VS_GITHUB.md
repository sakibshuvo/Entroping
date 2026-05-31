---
title: Obsidian Vs GitHub Operating Guide
type: guide
status: active
tags:
  - obsidian
  - github
  - workflow
  - roadmap
  - context
---

# Obsidian Vs GitHub Operating Guide

Use this when you are unsure where a thought, bug, feature, decision, or
roadmap change belongs.

## Fast Rule

```text
GitHub tracks work.
Obsidian explains why.
README sells.
Roadmap sequences.
Specs constrain.
Context hands off.
```

If something is actionable, it goes to GitHub first. If something explains why
the product changed, it goes to Obsidian.

## Where Things Go

| Thing | Put it here | Why |
| --- | --- | --- |
| Bug | GitHub issue | Needs reproduction, priority, owner, and closure |
| Feature idea | GitHub issue if actionable; source notes if raw | Prevents roadmap clutter |
| Active work status | GitHub Project | Shows live state |
| Release bucket | GitHub milestone | Groups work by release |
| Public release sequence | `ROADMAP.md` | Tells users what is now, next, later |
| Product behavior contract | `docs/product/PRODUCT_SPEC.md` | Defines what Entroping is |
| Architecture decision | ADR under `decisions/` | Explains a durable choice |
| Technical design | `docs/technical/TDS.md` | Keeps architecture and boundaries current |
| Daily dashboard | `docs/meta/PROJECT_PROGRESS.md` | Human orientation in Obsidian |
| Source evidence | `entroping-specs` plus `sources/SOURCE_MAP.md` | Keeps raw history separate |
| Durable lesson | `.context/lessons-learned.md` | Prevents repeated mistakes |
| Change history | `.context/changelog.md` | Preserves handoff context |

## Daily Workflow

1. Open `00_INDEX.md` in Obsidian.
2. Open `docs/meta/PROJECT_PROGRESS.md`.
3. Check the GitHub Project board for current work.
4. Pick exactly one issue.
5. Start or continue the issue branch.
6. Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`.
7. Run the required gates before merge.

Do not browse every Markdown file. The index, progress note, issue, and
checklist are enough for daily work.

## Brainstorming Workflow

Raw ideas are allowed to be messy. Promotion must be strict.

```text
Raw thought -> source note -> GitHub issue or ADR -> implementation -> changelog -> roadmap only if sequence changed
```

Use this template when brainstorming:

```text
Problem:
Who has it:
Why now:
Current workaround:
Entroping behavior:
Proof it works:
Non-goals:
Security or quality risk:
Docs impact:
Roadmap impact: yes/no
```

Promotion rules:

- If it is actionable implementation work, create a GitHub issue.
- If it changes architecture, create or update an ADR.
- If it changes current behavior, update product/user/technical docs.
- If it changes release sequence or public scope, update `ROADMAP.md`.
- If it is only historical evidence, leave it in the source archive.

## Bug Workflow

Every bug starts as a GitHub issue.

```text
Observe -> reproduce -> failing regression test -> narrow fix -> regression suite -> close issue
```

A useful bug issue has:

- observed behavior.
- expected behavior.
- reproduction steps.
- affected command or module.
- priority.
- security impact: yes/no.
- regression test plan.
- docs impact: yes/no.

Update Obsidian only when the bug changes phase status, reveals a durable
lesson, or changes product/architecture understanding.

## Roadmap Workflow

`ROADMAP.md` is not the backlog. It changes only when one of these changes:

- release target.
- milestone order.
- near-term scope.
- open-core boundary.
- public launch promise.

Small tasks, bugs, and polish belong in GitHub Issues. If a roadmap bullet needs
work, create issues under the matching milestone instead of adding sub-bullets
to the roadmap.

## Product Evolution Workflow

Use Obsidian to preserve the story, not to manage every task.

Update:

- `docs/evolution/EVOLUTION_TIMELINE.md` when the product story changes.
- `docs/evolution/REQUIREMENTS_ANALYSIS.md` when source reconciliation changes requirements.
- `docs/product/PRODUCT_SPEC.md` when the product contract changes.
- `docs/technical/TDS.md` when the architecture changes.
- ADRs when the reason must survive future context resets.

Do not update these for routine implementation.

## Source Material Workflow

Gemini, NotebookLM, and old chats are evidence, not current truth.

1. Save exports under `entroping-specs`.
2. Update `sources/SOURCE_MAP.md` only for curated source references.
3. Ask external tools for cited findings.
4. Promote accepted findings into issues, ADRs, or canonical docs.
5. Leave unpromoted findings archival.

## Starting A New Agent Session

Give the agent:

```text
Repo: /Users/sakibshuvo/projects/Entroping
Read first:
- AGENTS.md
- docs/meta/OBSIDIAN_VS_GITHUB.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- the target GitHub issue

Rules:
- GitHub Issues track work.
- Obsidian explains why.
- Do not edit ROADMAP.md unless release sequence or public scope changed.
- Run scripts/doc_governance_check.sh and scripts/regression.sh before completion.
```

Use `scripts/context_pack.sh --mode implementation` for a fuller handoff.

## Weekly Review

Once a week, do this:

1. Review open GitHub issues by milestone.
2. Close duplicates and stale tasks.
3. Promote only the next one to three issues to `status:ready`.
4. Check whether `ROADMAP.md` still matches milestone reality.
5. Update `PROJECT_PROGRESS.md` if phase status changed.
6. Add an ADR only for durable decisions.
7. Run `scripts/doc_governance_check.sh`.

The goal is a small number of clear next actions, not a bigger knowledge base.
