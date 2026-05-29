---
title: Context Management
type: guide
status: active
tags:
  - context
  - codex
  - obsidian
  - graphify
---

# Context Management

Entroping uses layered context so Codex, Obsidian, and future graph tooling can rehydrate the project quickly without depending on one long chat thread.

## Source of Truth

Use these files in this order:

1. `AGENTS.md` - implementation rules for Codex.
2. `README.md` - public project overview and quickstart.
3. `00_INDEX.md` - Obsidian vault map.
4. `.context/plan.md` - active implementation milestone.
5. `.context/changelog.md` - recent work.
6. `.context/lessons-learned.md` - durable pitfalls and decisions.
7. `docs/product/MVP_PLAN.md` - implementation sequence.
8. `docs/technical/TDS.md` - architecture details.
9. `docs/meta/AUTONOMOUS_DEVELOPMENT.md` - agent workflow and automation rules.
10. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` - per-feature execution checklist.
11. `docs/meta/PROJECT_PROGRESS.md` - simple phase-level dashboard.
12. `docs/meta/ISSUE_TRACKING.md` - GitHub issue tracking rules.
13. `docs/meta/TEST_STRATEGY.md` - test pyramid and regression rules.

## New Codex Thread Prompt

Use this when starting a fresh thread:

```text
Work in /Users/sakibshuvo/projects/Entroping.
Read AGENTS.md, README.md, 00_INDEX.md, .context/plan.md, docs/product/MVP_PLAN.md, docs/technical/TDS.md, and docs/meta/PROJECT_PROGRESS.md first.
Preserve the locked v4.1 command surface and implement only the next narrow milestone.
Follow docs/meta/AUTONOMOUS_DEVELOPMENT.md, docs/meta/FEATURE_DELIVERY_CHECKLIST.md, docs/meta/ISSUE_TRACKING.md, and docs/meta/TEST_STRATEGY.md for the Codex-first workflow, TDD expectations, regression gates, multi-agent guardrails, issue tracking, and context updates.
```

## Obsidian Role

Obsidian is the human navigation layer. It shows product evolution, ADRs, source links, and relationships between docs.

Do not depend on Obsidian workspace state for project truth. The durable notes are Markdown files in Git.

## Graphify Role

Graphify is optional generated context. It can help find unexpected connections, central nodes, and graph summaries, but generated output should stay out of Git unless a result is promoted into curated Markdown.

Recommended workflow:

```bash
uv tool install graphifyy
graphify install
graphify /Users/sakibshuvo/projects/Entroping
```

Output belongs under `graphify-out/`, which is ignored by Git.

## Cross-Project Context

Project-specific rules belong in each repo's `AGENTS.md`. Global preferences belong in `/Users/sakibshuvo/.codex/AGENTS.md`.

For another project, reuse the same pattern:

```text
AGENTS.md
.context/plan.md
.context/changelog.md
.context/lessons-learned.md
README.md
```

This gives Codex fast local context without requiring old conversation history.

## Agent Tooling

Current local agent tooling status:

- Codex CLI: available.
- OpenCode: available.
- Spec Kit `specify`: available.
- oMLX: not installed in this shell yet.

Treat OpenCode and future local Qwen/oMLX outputs as supporting review artifacts until their results pass Codex validation and deterministic checks.
